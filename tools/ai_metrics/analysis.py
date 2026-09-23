"""Análise interpretativa por LLM, sob demanda (contracts/analysis-io.md).

Separada dos fatos: recebe SÓ fatos e métricas estruturados (nunca transcrições), roda como
subprocesso `claude` headless a partir de uma pasta fora do repositório e é validada por código.
Uma análise rejeitada nunca aparece no relatório."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

from tools.ai_metrics import metrics, report
from tools.ai_metrics.ingest import analysis_cwd
from tools.ai_metrics.wal import Wal, canonical

PROMPT_VERSION = "1"
TYPES = ("fact", "association", "hypothesis", "unsupported")
CAUSAL = re.compile(r"(?<!\w)(causou|causa|reduziu|reduz|porque|por causa de|devido a|levou a|resultou em)(?!\w)",
                    re.IGNORECASE)
TOTAL_CLAIM = re.compile(r"consumiu[^.]{0,60}no total|total consumido|no total consumiu", re.IGNORECASE)
INSTRUCTIONS = """Você interpreta métricas de desenvolvimento assistido por IA (estudo observacional).
Use SOMENTE os dados do JSON abaixo. Responda APENAS com um JSON no formato:
{"statements": [{"type": "fact|association|hypothesis|unsupported", "text": "...",
"evidence": ["ID"], "numbers": [{"metric": "ID", "value": 0}]}], "limitations": ["..."]}
Regras: cada afirmação cita IDs (métricas M-*, fatos F-*, lacunas G-*) em "evidence"; "numbers" só com
valores idênticos aos do JSON; "unsupported" é para o que os dados não sustentam; NUNCA use linguagem
causal (causou, reduziu, porque, por causa de, devido a, levou a, resultou em); não diga "consumiu X tokens no
total" para feature parcial ou com valores marcados como limite inferior; se a feature for histórica,
mencione nas limitações a ausência dos custos de especificação; "limitations" não pode ser vazio."""


class AnalysisError(Exception):
    pass


# ---- entrada -------------------------------------------------------------------------
def build_input(model, fid, repo=None, res=None):
    res = res or metrics.compute(model, fid, repo)
    f = res["facts"]
    return {
        "promptVersion": PROMPT_VERSION,
        "feature": {"id": fid, "workflow": f["workflow"], "status": f["status"], "dataClass": f["dataClass"],
                    "coverage": f["coverageEffective"], "n": 1},
        "metrics": [{"id": m["id"], "value": m["value"], "lowerBound": m["lower"], "unit": m["unit"],
                     **({"reason": m["note"]} if m["state"] != "ok" and m["note"] else {})}
                    for m in res["metrics"]],
        "coverage": [{"id": f"G-{i}", "reason": r, "recovered": rec}
                     for i, (r, rec) in enumerate(f["gaps"], 1)],
        "facts": [{"id": f"F-{i}", "text": s} for i, s in enumerate(report.sentences(res), 1)],
    }


def input_hash(inp):
    return hashlib.sha256(canonical(inp).encode("utf-8")).hexdigest()


def build_prompt(inp):
    return INSTRUCTIONS + "\n\nDADOS:\n" + json.dumps(inp, ensure_ascii=False, sort_keys=True)


# ---- execução ------------------------------------------------------------------------
def default_command(model_name=None):
    cmd = ["claude", "-p", "--output-format", "json", "--tools", "", "--disable-slash-commands"]
    return cmd + (["--model", model_name] if model_name else [])


def run_claude(prompt, home, model_name=None, cmd=None, timeout=600):
    """Executa o `claude` headless em <home>/analysis-cwd (fora do repositório). Devolve
    (texto_do_resultado, modelo). Só o campo `result` é usado; qualquer valor monetário é ignorado."""
    cwd = analysis_cwd(home)
    cwd.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(cmd or default_command(model_name), input=prompt, cwd=cwd, capture_output=True,
                           text=True, encoding="utf-8", timeout=timeout)
    except FileNotFoundError as exc:
        raise AnalysisError("o comando `claude` não foi encontrado no PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise AnalysisError(f"a análise excedeu {timeout}s") from exc
    if r.returncode:
        raise AnalysisError(f"o `claude` terminou com código {r.returncode}: {r.stderr.strip()[:200]}")
    try:
        data = json.loads(r.stdout)
    except ValueError as exc:
        raise AnalysisError("a saída do `claude` não é JSON") from exc
    if data.get("is_error") or not isinstance(data.get("result"), str):
        raise AnalysisError("o `claude` reportou erro na execução")
    used = model_name or next(iter(data.get("modelUsage") or {}), "default")
    return data["result"], used


def parse_output(text):
    """JSON puro ou dentro de uma cerca ```json ... ```."""
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    try:
        return json.loads(m.group(1) if m else text)
    except ValueError:
        return None


# ---- validação (qualquer falha rejeita a análise inteira) ----------------------------
def validate(output, inp):
    if not isinstance(output, dict) or not isinstance(output.get("statements"), list):
        return ["a saída não é um JSON no esquema esperado"]
    ids = {x["id"] for key in ("metrics", "facts", "coverage") for x in inp[key]}
    values = {m["id"]: m["value"] for m in inp["metrics"]}
    partial = (inp["feature"]["dataClass"] == "historical" or inp["feature"]["coverage"] == "partial"
               or any(m["lowerBound"] for m in inp["metrics"]))
    reasons, texts = [], []
    for i, s in enumerate(output["statements"], 1):
        if not isinstance(s, dict) or s.get("type") not in TYPES or not isinstance(s.get("text"), str) or not s["text"].strip():
            reasons.append(f"afirmação {i}: tipo ou texto inválido")
            continue
        texts.append(s["text"])
        ev = s.get("evidence", [])
        if not isinstance(ev, list) or not all(isinstance(e, str) for e in ev):
            reasons.append(f"afirmação {i}: evidência inválida")
            continue
        for e in ev:
            if e not in ids:
                reasons.append(f"afirmação {i}: evidência inexistente {e}")
        if s["type"] != "unsupported" and not ev:
            reasons.append(f"afirmação {i}: {s['type']} sem evidência")
        for n in s.get("numbers", []) or []:
            mid, val = (n or {}).get("metric"), (n or {}).get("value")
            if mid not in values:
                reasons.append(f"afirmação {i}: métrica inexistente {mid}")
            elif not _same(values[mid], val):
                reasons.append(f"afirmação {i}: número de {mid} não confere ({val} ≠ {values[mid]})")
    limitations = output.get("limitations")
    if not isinstance(limitations, list) or not limitations or not all(isinstance(x, str) and x.strip() for x in limitations):
        reasons.append("limitations ausente ou vazio")
        limitations = []
    texts += limitations
    for t in texts:
        m = CAUSAL.search(t)
        if m:
            reasons.append(f"linguagem causal rejeitada: “{m.group(1)}”")
        if partial and TOTAL_CLAIM.search(t):
            reasons.append("afirma custo total para feature parcial ou com limite inferior")
    if inp["feature"]["dataClass"] == "historical" and not any("especifica" in x.lower() for x in limitations):
        reasons.append("feature histórica: as limitações devem mencionar a ausência de custos de especificação")
    return reasons


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) < 1e-9
    return a == b


# ---- armazenamento do texto aceito (fora do histórico: o histórico guarda só hashes) --
def analyses_dir(repo):
    return Path(repo) / ".ai-metrics" / "analyses"


def save_accepted(repo, fid, output_hash, analysis):
    path = analyses_dir(repo) / f"{report.slug_for_file(fid)}-{output_hash[:16]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def latest_accepted(repo, model, fid):
    """Análise aceita mais recente da feature (evento + arquivo local), ou None."""
    for ev in sorted((e for e in model.analyses if e["featureId"] == fid and e.get("accepted")),
                     key=lambda e: e["seq"], reverse=True):
        path = analyses_dir(repo) / f"{report.slug_for_file(fid)}-{ev['outputHash'][:16]}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if hashlib.sha256(canonical(data["output"]).encode("utf-8")).hexdigest() == ev["outputHash"]:
                return {**data["output"], "model": ev["model"], "promptVersion": ev["promptVersion"]}
    return None


def analyze(home, repo, model, fid, model_name=None, cmd=None, timeout=600):
    """Roda, valida e registra. Devolve (aceita, motivos, análise). Sempre grava `analysis.generated`
    (aceita ou rejeitada); só a aceita vai para o relatório."""
    res = metrics.compute(model, fid, repo)
    inp = build_input(model, fid, repo, res)
    text, used = run_claude(build_prompt(inp), home, model_name, cmd, timeout)
    output = parse_output(text)
    reasons = validate(output, inp)
    out_hash = hashlib.sha256(canonical(output if output is not None else text).encode("utf-8")).hexdigest()
    accepted = not reasons
    Wal(home).append([{"type": "analysis.generated", "source": "manual", "data": {
        "featureId": fid, "model": used, "promptVersion": PROMPT_VERSION, "inputHash": input_hash(inp),
        "outputHash": out_hash, "accepted": accepted, "rejectReasons": reasons,
        "reportFile": f".ai-metrics/reports/{report.slug_for_file(fid)}.md"}}])
    if accepted:
        save_accepted(repo, fid, out_hash, {"output": output})
    return accepted, reasons, ({**output, "model": used, "promptVersion": PROMPT_VERSION} if accepted else None)
