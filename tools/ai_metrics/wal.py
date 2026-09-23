"""Histórico de eventos apenas-anexar, encadeado por hash (contrato: contracts/wal-events.md)."""
import contextlib
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from tools.ai_metrics import config

GENESIS = "0" * 64
LOCK_STALE_SECONDS = 60


class WalError(Exception):
    """Falha ao gravar/ler o histórico. `integrity=True` quando os dados parecem adulterados."""

    def __init__(self, message, integrity=False):
        super().__init__(message)
        self.integrity = integrity


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(record):
    body = {k: v for k, v in record.items() if k != "hash"}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def _has_money(obj):
    if isinstance(obj, dict):
        return any("costusd" in str(k).lower() or _has_money(v) for k, v in obj.items())
    if isinstance(obj, list):
        return any(_has_money(v) for v in obj)
    return False


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class Wal:
    def __init__(self, home=None):
        self.home = Path(home or config.DEFAULT_HOME)
        self.path = self.home / "wal.jsonl"
        self.head_path = self.home / "head.json"
        self.lock_path = self.home / "wal.lock"

    # ---- trava (FR-010b) -------------------------------------------------------------
    @contextlib.contextmanager
    def lock(self, timeout=5.0):
        self.home.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except (FileExistsError, PermissionError):  # Windows: PermissionError se a trava está sendo removida
                with contextlib.suppress(OSError):
                    if time.time() - self.lock_path.stat().st_mtime > LOCK_STALE_SECONDS:
                        os.remove(self.lock_path)  # processo morto deixou a trava
                        continue
                if time.monotonic() > deadline:
                    raise WalError("não consegui a trava do histórico (outra captura em andamento)")
                time.sleep(0.05)
        try:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            yield
        finally:
            with contextlib.suppress(OSError):
                os.remove(self.lock_path)

    # ---- leitura ---------------------------------------------------------------------
    def _lines(self):
        if not self.path.exists():
            return []
        text = self.path.read_bytes().decode("utf-8")
        return [ln for ln in text.split("\n") if ln.strip()]

    def read(self):
        """Todos os registros (JSON). Linha inválida levanta WalError de integridade."""
        out = []
        for i, line in enumerate(self._lines(), 1):
            try:
                out.append(json.loads(line))
            except ValueError as exc:
                raise WalError(f"registro {i} não é JSON válido", integrity=True) from exc
        return out

    def _head(self):
        if not self.head_path.exists():
            return None
        try:
            return json.loads(self.head_path.read_text(encoding="utf-8"))
        except ValueError:
            return {"seq": -1, "hash": ""}

    def _write_head(self, record):
        tmp = self.head_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"seq": record["seq"], "hash": record["hash"]}), encoding="utf-8")
        os.replace(tmp, self.head_path)

    # ---- escrita ---------------------------------------------------------------------
    def append(self, events, _locked=False):
        """Anexa eventos `{type, data, ts?, source?}`. Devolve os registros gravados.

        Recusa (sem gravar nada) eventos com valor monetário ou com o nome real do bot.
        Recusa anexar sobre um histórico que já falha a verificação de integridade.
        `_locked=True`: o chamador já segura `self.lock()` (captura = ler + decidir + anexar)."""
        events = list(events)
        if not events:
            return []
        for ev in events:
            if _has_money(ev):
                raise WalError("evento com campo monetário recusado (o estudo é em tokens)")
            if config.contains_bot_name(canonical(ev)):
                raise WalError("evento recusado: contém o nome real do bot (Princípio V)")
        with (contextlib.nullcontext() if _locked else self.lock()):
            ok, message, _ = self._verify_locked()
            if not ok:
                raise WalError(f"histórico não íntegro: {message}", integrity=True)
            lines = self._lines()
            last = json.loads(lines[-1]) if lines else None
            seq = last["seq"] if last else 0
            prev = last["hash"] if last else GENESIS
            written, chunks = [], []
            for ev in events:
                seq += 1
                rec = {"seq": seq, "ts": ev.get("ts") or now_iso(), "type": ev["type"],
                       "source": ev.get("source", "claude-code"), "prev": prev, "data": ev["data"]}
                rec["hash"] = _hash(rec)
                prev = rec["hash"]
                chunks.append(canonical(rec) + "\n")
                written.append(rec)
            self.home.mkdir(parents=True, exist_ok=True)
            with open(self.path, "ab") as fh:
                fh.write("".join(chunks).encode("utf-8"))
                fh.flush()
                os.fsync(fh.fileno())
            self._write_head(written[-1])
            return written

    # ---- verificação (FR-006) --------------------------------------------------------
    def verify(self):
        """(ok, mensagem, primeira_seq_comprometida). Conserta a âncora se estiver uma atrás."""
        with self.lock():
            return self._verify_locked()

    def _repair_torn_tail(self):
        """Queda no meio de uma gravação: remove os bytes de uma última linha incompleta.

        Só age se o arquivo não termina em quebra de linha E a âncora não referencia o registro
        truncado (a âncora só é atualizada depois da gravação). Assim os bytes removidos nunca
        fizeram parte oficial do histórico; edição ou remoção de registros reconhecidos pela
        âncora continua sendo detectada. Devolve uma nota ou None."""
        if not self.path.exists():
            return None
        raw = self.path.read_bytes()
        if not raw or raw.endswith(b"\n"):
            return None
        cut = raw.rfind(b"\n") + 1
        complete = [ln for ln in raw[:cut].split(b"\n") if ln.strip()]
        head = self._head()
        if (head["seq"] if head else 0) > len(complete):
            return None  # a âncora conhece o registro truncado: isso é perda, não queda
        try:
            json.loads(raw[cut:].decode("utf-8"))
            self.path.write_bytes(raw + b"\n")   # registro completo, só faltou a quebra de linha
        except ValueError:
            self.path.write_bytes(raw[:cut])
        return "última linha interrompida reparada"

    def _verify_locked(self):
        repaired = self._repair_torn_tail()
        ok, message, seq = self._verify_chain()
        if ok and repaired:
            message += f" ({repaired})"
        return ok, message, seq

    def _verify_chain(self):
        prev, expected, last = GENESIS, 1, None
        for line in self._lines():
            try:
                rec = json.loads(line)
            except ValueError:
                return False, f"registro {expected} ilegível", expected
            if rec.get("seq") != expected:
                return False, f"sequência quebrada no registro {expected}", expected
            if rec.get("prev") != prev:
                return False, f"encadeamento quebrado no registro {expected}", expected
            if rec.get("hash") != _hash(rec):
                return False, f"conteúdo alterado no registro {expected}", expected
            prev, last, expected = rec["hash"], rec, expected + 1
        head = self._head()
        if last is None:
            if head and head.get("seq", 0) > 0:
                return False, "histórico vazio, mas a âncora indica registros (arquivo apagado?)", 1
            return True, "histórico vazio", None
        if head is None:
            return False, "âncora head.json ausente (histórico pode ter sido truncado)", last["seq"] + 1
        if head["seq"] == last["seq"] and head["hash"] == last["hash"]:
            return True, f"{last['seq']} registros íntegros", None
        if head["seq"] == last["seq"] - 1 and head["hash"] == last["prev"]:
            self._write_head(last)  # queda entre anexar e atualizar a âncora
            return True, f"{last['seq']} registros íntegros (âncora reparada)", None
        return False, "o final do histórico não bate com a âncora (registros removidos?)", \
            min(head.get("seq", 0), last["seq"]) + 1
