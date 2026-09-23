"""Base comum dos testes de métricas: monta transcrições sintéticas, captura e calcula."""
from datetime import datetime, timezone

from tools.ai_metrics import metrics
from tools.ai_metrics.model import Model
from tools.ai_metrics.tests.test_ingest import IngestBase


def tok(n):
    """Usage que soma exatamente `n` tokens (tudo em leitura de cache)."""
    return (0, 0, n, 0)


class MetricsBase(IngestBase):
    FID = "007-x"

    def branch_transcript(self, **kw):
        return self.transcript(branch=self.FID, **kw)

    def build(self, *transcripts, final=True):
        for t in transcripts:
            self.save(t)
        self.run_ingest(final=final)

    def model(self):
        return Model.load(self.home, repo=self.repo, now=datetime(2026, 9, 25, tzinfo=timezone.utc))

    def compute(self, fid=None):
        model = self.model()
        res = metrics.compute(model, fid or self.FID)
        return {m["id"]: m for m in res["metrics"]}, res

    def cycle(self, t, skill=None, args="", turns=(), ms=1000):
        """Um ciclo: prompt + turnos (lista de dicts com tools/usage/is_error) + fim."""
        t.prompt(skill=skill, args=args)
        for spec in turns:
            t.assistant(tools=spec.get("tools", ()), usage=tok(spec.get("n", 10)), is_error=spec.get("err", ()),
                        stop=spec.get("stop"))
        t.assistant(usage=tok(1), stop="end_turn")
        t.turn_duration(ms)
