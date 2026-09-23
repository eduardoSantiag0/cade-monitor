"""Linha de comando: `python -m tools.ai_metrics <comando>` (contrato: contracts/cli.md).

Códigos de saída: 0 ok, 1 erro de uso ou de dados, 2 integridade comprometida."""
import argparse
import sys
from pathlib import Path

from tools.ai_metrics import config
from tools.ai_metrics.wal import Wal, WalError


def _utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def cmd_verify(args):
    ok, message, seq = Wal(args.home).verify()
    if ok:
        print(f"OK: {message}")
        return 0
    print(f"FALHA: {message} (primeira posição comprometida: seq {seq})")
    return 2


def _repo(args):
    return Path(args.repo) if getattr(args, "repo", None) else config.REPO_ROOT


def cmd_ingest(args):
    from tools.ai_metrics import ingest
    dump = Path(args.dump_stdin) if args.dump_stdin else None
    if dump and not dump.exists() and not sys.stdin.isatty():
        # só para o spike do hook (T024): registra UMA vez o stdin recebido e o diretório de trabalho
        try:
            import json
            import os
            dump.write_text(json.dumps({"cwd": os.getcwd(), "stdin": sys.stdin.read()}, ensure_ascii=False),
                            encoding="utf-8")
        except (OSError, UnicodeError):
            pass
    if args.hook:
        return ingest.run_hook(args.home, _repo(args), args.projects_dir)
    summary = ingest.run(args.home, _repo(args), args.projects_dir, final=args.final)
    if not args.quiet:
        print(ingest.summary_text(summary))
    return 0


def _model(args):
    """Verifica a integridade e carrega o histórico. Devolve (model, None) ou (None, exit_code)."""
    from tools.ai_metrics.model import Model
    ok, message, seq = Wal(args.home).verify()
    if not ok:
        print(f"FALHA de integridade: {message} (seq {seq}). Nenhum relatório foi gerado sobre dados suspeitos; "
              "rode `verify` e investigue.", file=sys.stderr)
        return None, 2
    cfg = config.load(args.home)
    return Model.load(args.home, cfg, _repo(args)), None


def cmd_report(args):
    from tools.ai_metrics import metrics, report
    model, code = _model(args)
    if code:
        return code
    ids = model.feature_ids()
    if args.all:
        names = ids
    elif args.feature:
        fid = model.resolve(args.feature)
        if fid is None:
            print(f"erro: feature desconhecida: {args.feature}. Conhecidas: {', '.join(ids) or 'nenhuma'}",
                  file=sys.stderr)
            return 1
        names = [fid]
    else:
        print("erro: informe a feature ou use --all", file=sys.stderr)
        return 1
    for fid in names:
        res = metrics.compute(model, fid, _repo(args))
        from tools.ai_metrics import analysis
        text = report.render_feature(model, fid, res, analysis.latest_accepted(_repo(args), model, fid),
                                     position=(ids.index(fid) + 1, len(ids)))
        if args.stdout or args.no_write:
            print(text)
        if not args.no_write:
            try:
                path = report.write_report(_repo(args), fid, text)
            except report.ReportError as exc:
                print(f"erro: {exc}", file=sys.stderr)
                return 1
            print(f"Relatório gravado em {path}")
    if args.all and not args.no_write:
        return _write_comparison(args, model)
    return 0


def _write_comparison(args, model):
    from tools.ai_metrics import report
    text = report.render_comparison(report.compare(model, _repo(args)), model)
    if getattr(args, "stdout", False):
        print(text)
    try:
        print(f"Comparação gravada em {report.write_report(_repo(args), '_comparacao', text)}")
    except report.ReportError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_compare(args):
    model, code = _model(args)
    return code or _write_comparison(args, model)


def cmd_analyze(args):
    from tools.ai_metrics import analysis, metrics, report
    from tools.ai_metrics.model import Model
    model, code = _model(args)
    if code:
        return code
    fid = model.resolve(args.feature)
    if fid is None:
        print(f"erro: feature desconhecida: {args.feature}. Conhecidas: {', '.join(model.feature_ids()) or 'nenhuma'}",
              file=sys.stderr)
        return 1
    try:
        accepted, reasons, out = analysis.analyze(args.home, _repo(args), model, fid, args.model)
    except analysis.AnalysisError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    if not accepted:
        print("Análise REJEITADA (o relatório não foi alterado):")
        for r in reasons:
            print(f"- {r}")
        return 1
    model = Model.load(args.home, model.cfg, _repo(args))
    ids = model.feature_ids()
    res = metrics.compute(model, fid, _repo(args))
    text = report.render_feature(model, fid, res, analysis.latest_accepted(_repo(args), model, fid),
                                 position=(ids.index(fid) + 1, len(ids)))
    try:
        path = report.write_report(_repo(args), fid, text)
    except report.ReportError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    print(f"Análise aceita ({out['model']}); seção Análise atualizada em {path}")
    return 0


def cmd_timeline(args):
    from tools.ai_metrics import metrics, report
    model, code = _model(args)
    if code:
        return code
    print("| # | Feature | Nascimento | Workflow | Situação | Classe / cobertura | Turnos | Tokens medidos |")
    print("|---|---|---|---|---|---|---|---|")
    for i, fid in enumerate(model.feature_ids(), 1):
        f = metrics.compute(model, fid, _repo(args))
        facts, tot = f["facts"], next(m for m in f["metrics"] if m["id"] == "M-tokens-total")
        print(f"| {i} | `{fid}` | {facts['bornAt']} | {facts['workflow']} | {facts['status']} | "
              f"{facts['dataClass']} / {facts['coverage']} | {facts['turns']} | {report.fmt(tot)} |")
    outside = {}
    for t in model.turns:
        if not t["feature"]:
            klass = model.cost_class(t)
            n, tok = outside.get(klass, (0, 0))
            outside[klass] = (n + 1, tok + sum(t["usage"].get(k, 0) for k in ("in", "out", "cacheRead", "cacheCreate")))
    if outside:
        print()
        print("Custo fora de features (tokens medidos):")
        for klass, (n, tok) in sorted(outside.items()):
            print(f"- {klass}: {report.num(tok)} tokens em {n} turnos")
    return 0


# ---- correções e declarações (geram eventos; nunca editam o histórico) ----------------
def _scope(args):
    scope = {}
    if getattr(args, "session", None):
        scope["sessionId"] = args.session
    if getattr(args, "from_ts", None):
        scope["from"] = args.from_ts
    if getattr(args, "to_ts", None):
        scope["to"] = args.to_ts
    if getattr(args, "turns", None):
        scope["turns"] = args.turns.split(",")
    return scope


def _emit(args, events):
    recs = Wal(args.home).append([dict({"source": "manual"}, **e) for e in events])
    for r in recs:
        print(f"Registrado: {r['type']} (seq {r['seq']})")
    return 0


def _known(args, fid):
    model, code = _model(args)
    if code:
        return None, code
    if fid is not None and fid not in model.features:
        print(f"erro: feature desconhecida: {fid}. Conhecidas: {', '.join(model.feature_ids()) or 'nenhuma'}",
              file=sys.stderr)
        return None, 1
    return model, None


def _optional(args, data, keys=("workflow", "tag", "reason")):
    for key in keys:
        if getattr(args, key, None):
            data[key] = getattr(args, key)
    return data


def cmd_feature_use(args):
    scope = _scope(args)
    if not scope:
        print("erro: informe o escopo (--session, --from/--to ou --turns)", file=sys.stderr)
        return 1
    fid = None if args.feature.lower() == "none" else args.feature
    model, code = _model(args)
    if code:
        return code
    events = []
    if fid and fid not in model.features:  # feature nova declarada: nasce agora, por declaração
        from tools.ai_metrics.wal import now_iso
        events.append({"type": "feature.born", "data": {
            "featureId": fid, "bornAt": now_iso(), "bornSource": "declared",
            "dataClass": "observed", "coverage": "complete"}})
    data = _optional(args, {"featureId": fid, "scope": scope})
    return _emit(args, events + [{"type": "attribution.set", "data": data}])


def cmd_feature_correct(args):
    model, code = _model(args)
    if code:
        return code
    old = next((r for r in model.attr_events if r["seq"] == args.seq), None)
    if old is None:
        print(f"erro: o registro {args.seq} não é uma atribuição (attribution.set/corrected)", file=sys.stderr)
        return 1
    fid = None if args.feature.lower() == "none" else args.feature
    data = _optional(args, {"corrects": args.seq, "featureId": fid, "scope": _scope(args) or old["scope"]})
    return _emit(args, [{"type": "attribution.corrected", "data": data}])


def cmd_feature_status(args):
    model, code = _known(args, args.feature)
    if code:
        return code
    data = _optional(args, {"featureId": args.feature, "status": args.status.replace("-", " ")}, ("reason",))
    return _emit(args, [{"type": "status.corrected", "data": data}])


def cmd_feature_first_pass(args):
    model, code = _known(args, args.feature)
    if code:
        return code
    uuid = None if args.cycle.lower() == "unknown" else args.cycle
    if uuid and not any((c["prompt"] or {}).get("uuid") == uuid for c in model.cycles_of(args.feature)):
        print("erro: esse ciclo (uuid do prompt) não pertence à feature", file=sys.stderr)
        return 1
    data = _optional(args, {"featureId": args.feature, "cycleUuid": uuid}, ("reason",))
    return _emit(args, [{"type": "firstPass.corrected", "data": data}])


GAP_REASONS = ("copilot", "hook-failed", "transcript-missing", "unlogged-api-calls", "unreadable-lines")


def cmd_gap_add(args):
    model, code = _known(args, args.feature)
    if code:
        return code
    data = {"source": args.source, "from": args.from_ts, "to": args.to_ts, "reason": args.reason,
            "recovered": False}
    if args.feature:
        data["featureId"] = args.feature
    return _emit(args, [{"type": "coverage.gap", "ts": args.from_ts, "data": data}])


def cmd_backfill(args):
    from tools.ai_metrics import model as modelmod
    model, code = _model(args)
    if code:
        return code
    events, notes = modelmod.backfill_events(model, _repo(args), model.cfg)
    for note in notes:
        print(note)
    if not events:
        print("Nada a importar.")
        return 0
    return _emit(args, events)


def cmd_setup(args):
    from tools.ai_metrics import setup
    return setup.run(args.home, _repo(args), args.projects_dir, dry_run=args.dry_run,
                     remove=args.remove, check=args.check)


def build_parser():
    p = argparse.ArgumentParser(
        prog="python -m tools.ai_metrics",
        description="Métricas de desenvolvimento assistido por IA: registra tokens e tempo do "
                    "agente por feature, de forma local e auditável (estudo observacional).")
    p.add_argument("--home", default=None,
                   help="pasta do histórico (padrão: ~/.cade-metrics; útil em testes)")
    sub = p.add_subparsers(dest="command", metavar="comando")

    v = sub.add_parser("verify", help="confere o encadeamento e a âncora do histórico",
                       description="Recalcula a sequência e os hashes do histórico e compara o "
                                   "final com head.json. Sai com 2 se detectar edição ou remoção.")
    v.set_defaults(func=cmd_verify)

    i = sub.add_parser("ingest", help="captura o consumo das transcrições para o histórico",
                       description="Varre as transcrições do Claude Code deste projeto e grava os "
                                   "eventos novos (idempotente). Sem texto de conversa e sem valores "
                                   "monetários.")
    i.add_argument("--hook", action="store_true",
                   help="modo do hook Stop: ignora o stdin, não imprime nada, nunca falha (exit 0)")
    i.add_argument("--final", action="store_true",
                   help="aceita também a última resposta, mesmo que ainda incompleta")
    i.add_argument("--quiet", action="store_true", help="não imprime o resumo")
    i.add_argument("--projects-dir", default=None, help=argparse.SUPPRESS)
    i.add_argument("--repo", default=None, help=argparse.SUPPRESS)
    i.add_argument("--dump-stdin", default=None, help=argparse.SUPPRESS)
    i.set_defaults(func=cmd_ingest)

    r = sub.add_parser("report", help="gera o relatório Markdown de uma feature",
                       description="Fatos → Métricas → Análise → Evidências → Limitações. Grava em "
                                   ".ai-metrics/reports/<feature>.md (recusa se .ai-metrics/ não estiver "
                                   "ignorado pelo Git) e/ou imprime no terminal.")
    r.add_argument("feature", nargs="?", help="id da feature (nome do branch) ou alias (specs/NNN-nome)")
    r.add_argument("--all", action="store_true", help="um relatório para cada feature conhecida")
    r.add_argument("--stdout", action="store_true", help="também imprime o relatório no terminal")
    r.add_argument("--no-write", action="store_true", help="só imprime; não grava arquivo")
    r.add_argument("--repo", default=None, help=argparse.SUPPRESS)
    r.set_defaults(func=cmd_report)

    cp = sub.add_parser("compare", help="compara os workflows (só features elegíveis)",
                        description="Números brutos, n por grupo, classes de custo separadas, vieses conhecidos "
                                    "e o aviso de comparação fraca. Grava .ai-metrics/reports/_comparacao.md.")
    cp.add_argument("--stdout", action="store_true", help="também imprime no terminal")
    cp.add_argument("--repo", default=None, help=argparse.SUPPRESS)
    cp.set_defaults(func=cmd_compare)

    an = sub.add_parser("analyze", help="pede uma análise interpretativa (por LLM) de uma feature",
                        description="Monta a entrada só com fatos e métricas estruturados, executa o `claude` "
                                    "headless fora do repositório, valida a resposta (evidências, números, "
                                    "linguagem causal) e registra o evento analysis.generated. Só análises "
                                    "aceitas entram no relatório.")
    an.add_argument("feature", help="id da feature ou alias")
    an.add_argument("--model", default=None, help="modelo do claude (padrão: o padrão da conta)")
    an.add_argument("--repo", default=None, help=argparse.SUPPRESS)
    an.set_defaults(func=cmd_analyze)

    tl = sub.add_parser("timeline", help="lista as features em ordem cronológica",
                        description="Features com nascimento, workflow, classe de dado, cobertura e custo medido.")
    tl.add_argument("--repo", default=None, help=argparse.SUPPRESS)
    tl.set_defaults(func=cmd_timeline)

    g = sub.add_parser("gap", help="registra uma lacuna de cobertura conhecida",
                       description="Lacuna = fonte, intervalo e motivo pelos quais algo não foi medido. "
                                   "Métricas que a tocam passam a ser limites inferiores (≥).")
    gsub = g.add_subparsers(dest="gap_command", metavar="ação")
    ga = gsub.add_parser("add", help="adiciona uma lacuna (evento coverage.gap)")
    ga.add_argument("--source", required=True, help="fonte sem medição (ex.: copilot)")
    ga.add_argument("--from", dest="from_ts", required=True, help="início do intervalo (ISO UTC)")
    ga.add_argument("--to", dest="to_ts", required=True, help="fim do intervalo (ISO UTC)")
    ga.add_argument("--reason", required=True, choices=GAP_REASONS, help="motivo da lacuna")
    ga.add_argument("--feature", default=None, help="feature afetada (opcional)")
    ga.add_argument("--repo", default=None, help=argparse.SUPPRESS)
    ga.set_defaults(func=cmd_gap_add)

    bf = sub.add_parser("backfill", help="importa as features 005 e 006 como histórico parcial",
                        description="Cria feature.born (historical/partial), lacuna `copilot` e aliases por "
                                    "evidência de caminho, dentro da janela dos commits de history_windows. "
                                    "Idempotente. As features importadas ficam fora das agregações.")
    bf.add_argument("--repo", default=None, help=argparse.SUPPRESS)
    bf.set_defaults(func=cmd_backfill)

    fe = sub.add_parser("feature", help="declara ou corrige atribuições, situação e first-pass (gera eventos)",
                        description="Correções são eventos novos: o histórico anterior nunca é editado.")
    fsub = fe.add_subparsers(dest="feature_command", metavar="ação")

    def scope_args(p):
        p.add_argument("--session", help="sessão inteira (sessionId)")
        p.add_argument("--from", dest="from_ts", help="início do intervalo (ISO UTC)")
        p.add_argument("--to", dest="to_ts", help="fim do intervalo (ISO UTC)")
        p.add_argument("--turns", help="lista de msgId separados por vírgula")
        p.add_argument("--reason", help="motivo curto (não inclua nomes sensíveis)")
        p.add_argument("--repo", default=None, help=argparse.SUPPRESS)

    u = fsub.add_parser("use", help="atribui um período à feature (e opcionalmente ao workflow)",
                        description="Override/correção (o `/feature <id> --workflow <w>` da spec). Use `none` "
                                    "como id para declarar o período como unattributed.")
    u.add_argument("feature")
    u.add_argument("--workflow", choices=["direct", "grill", "speckit", "grill+speckit"])
    u.add_argument("--tag", help="marca o período (ex.: setup: fica fora das agregações)")
    scope_args(u)
    u.set_defaults(func=cmd_feature_use)

    c = fsub.add_parser("correct", help="corrige uma atribuição anterior (pela seq)")
    c.add_argument("seq", type=int, help="seq do attribution.set/corrected a corrigir")
    c.add_argument("--feature", required=True, help="feature correta (ou `none`)")
    c.add_argument("--workflow", choices=["direct", "grill", "speckit", "grill+speckit"])
    c.add_argument("--tag")
    scope_args(c)
    c.set_defaults(func=cmd_feature_correct)

    ss = fsub.add_parser("status", help="declara a situação: em-andamento, entregue ou abandonada")
    ss.add_argument("feature")
    ss.add_argument("status", choices=["em-andamento", "entregue", "abandonada"])
    ss.add_argument("--reason")
    ss.add_argument("--repo", default=None, help=argparse.SUPPRESS)
    ss.set_defaults(func=cmd_feature_status)

    fp = fsub.add_parser("first-pass", help="corrige o ciclo de first-pass (uuid do prompt ou `unknown`)")
    fp.add_argument("feature")
    fp.add_argument("cycle")
    fp.add_argument("--reason")
    fp.add_argument("--repo", default=None, help=argparse.SUPPRESS)
    fp.set_defaults(func=cmd_feature_first_pass)

    tg = fsub.add_parser("tag", help="marca um período de uma feature (ex.: --tag setup)")
    tg.add_argument("feature")
    tg.add_argument("--tag", required=True)
    scope_args(tg)
    tg.set_defaults(func=cmd_feature_use, workflow=None)

    st = sub.add_parser("setup", help="configuração única: instala o hook Stop e cria a pasta do histórico",
                        description="Instala (ou atualiza) o hook Stop em .claude/settings.local.json, "
                                    "preservando o restante do arquivo, cria ~/.cade-metrics e faz uma "
                                    "primeira captura. Depois disso o tracking é automático.")
    st.add_argument("--dry-run", action="store_true", help="mostra o que mudaria, sem gravar nada")
    st.add_argument("--remove", action="store_true",
                    help="remove só a entrada da ferramenta do settings.local.json (mantém o histórico)")
    st.add_argument("--check", action="store_true",
                    help="só informa se o hook está instalado e a pasta existe (exit 1 se faltar)")
    st.add_argument("--projects-dir", default=None, help=argparse.SUPPRESS)
    st.add_argument("--repo", default=None, help=argparse.SUPPRESS)
    st.set_defaults(func=cmd_setup)
    return p


def main(argv=None):
    _utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    try:
        return args.func(args)
    except WalError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2 if exc.integrity else 1
    except config.ConfigError as exc:
        print(f"erro de configuração: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # gitinfo.GitError e afins
        print(f"erro: {exc}", file=sys.stderr)
        return 1
