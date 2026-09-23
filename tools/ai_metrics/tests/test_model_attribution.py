import unittest

from tools.ai_metrics import ingest
from tools.ai_metrics.tests.helpers import git, make_repo
from tools.ai_metrics.tests.metrics_base import MetricsBase
from tools.ai_metrics.wal import Wal


def born(fid, at="2026-09-22T09:00:00Z"):
    return {"type": "feature.born", "ts": at, "source": "manual", "data": {
        "featureId": fid, "bornAt": at, "bornSource": "declared", "dataClass": "observed", "coverage": "complete"}}


class AttributionTests(MetricsBase):
    def simple(self, branch="main", session="s1", tools=(), start="2026-09-22T10:00:00"):
        t = self.transcript(branch=branch, session=session, start=start)
        t.prompt()
        t.assistant(tools=list(tools), stop=None if tools else "end_turn")
        if tools:
            t.assistant(stop="end_turn")
        return t

    def modes(self, model=None):
        model = model or self.model()
        return [(t["feature"], t["mode"]) for t in model.turns]

    def test_branch_da_feature_e_inferido(self):
        self.build(self.simple(branch="007-x"))
        self.assertEqual(set(self.modes()), {("007-x", "inferred")})

    def test_sem_evidencia_fica_unattributed(self):
        self.build(self.simple(branch="main"))
        self.assertEqual(set(self.modes()), {(None, "unattributed")})

    def test_evidencia_de_caminho_em_diretorio_de_spec_da_feature(self):
        self.build(self.simple(branch="007-x"), self.simple(branch="main", session="s2",
                                                             tools=[("Read", "specs/009-z/plan.md")]))
        Wal(self.home).append([{"type": "feature.alias", "source": "manual", "data": {
            "featureId": "007-x", "alias": "specs/009-z", "source": "manual"}}])
        m = self.model()
        s2 = [(t["feature"], t["mode"]) for t in m.turns if t["sessionId"] == "s2"]
        self.assertEqual(set(s2), {("007-x", "inferred")})
        self.assertEqual(m.resolve("009-z"), "007-x")
        self.assertEqual(m.resolve("specs/009-z"), "007-x")

    def test_declaracao_explicita_vence_o_branch(self):
        self.build(self.simple(branch="007-x", session="sA"))
        Wal(self.home).append([born("008-y"), {"type": "attribution.set", "source": "manual", "data": {
            "featureId": "008-y", "scope": {"sessionId": "sA"}, "reason": "teste"}}])
        self.assertEqual(set(self.modes()), {("008-y", "explicit")})

    def test_correcao_e_um_evento_novo_e_o_historico_continua_integro(self):
        self.build(self.simple(branch="007-x", session="sA"))
        w = Wal(self.home)
        (rec,) = w.append([born("008-y"), {"type": "attribution.set", "source": "manual", "data": {
            "featureId": "008-y", "scope": {"sessionId": "sA"}}}])[1:]
        before = w.read()
        w.append([{"type": "attribution.corrected", "source": "manual", "data": {
            "corrects": rec["seq"], "featureId": "007-x", "scope": {"sessionId": "sA"}}}])
        self.assertEqual(w.read()[:len(before)], before)  # nada anterior foi editado
        self.assertTrue(w.verify()[0])
        self.assertEqual(set(self.modes()), {("007-x", "corrected")})

    def test_declarar_unattributed_explicitamente(self):
        self.build(self.simple(branch="007-x", session="sA"))
        Wal(self.home).append([{"type": "attribution.set", "source": "manual", "data": {
            "featureId": None, "scope": {"sessionId": "sA"}}}])
        self.assertEqual(set(self.modes()), {(None, "explicit")})

    def test_escopos_por_intervalo_e_por_turno(self):
        t = self.simple(branch="007-x", session="sA")
        self.build(t)
        turns = self.model().turns
        Wal(self.home).append([born("008-y"), {"type": "attribution.set", "source": "manual", "data": {
            "featureId": "008-y", "scope": {"turns": [turns[0]["msgId"]]}}}])
        self.assertEqual(self.modes()[0], ("008-y", "explicit"))
        Wal(self.home).append([{"type": "attribution.set", "source": "manual", "data": {
            "featureId": "007-x", "scope": {"from": turns[0]["ts"], "to": turns[0]["ts"]}}}])
        self.assertEqual(self.modes()[0], ("007-x", "explicit"))  # a declaração mais recente vence

    def test_duas_features_simultaneas_sem_sobreposicao(self):
        a, b = self.simple(branch="007-x", session="sA"), self.simple(branch="008-y", session="sB")
        self.build(a, b)
        m = self.model()
        self.assertEqual({t["msgId"] for t in m.turns_of("007-x")} & {t["msgId"] for t in m.turns_of("008-y")}, set())
        self.assertEqual({t["sessionId"] for t in m.turns_of("007-x")}, {"sA"})
        self.assertEqual({t["sessionId"] for t in m.turns_of("008-y")}, {"sB"})

    def test_workflow_declarado_sobrescreve_a_deteccao(self):
        self.build(self.simple(branch="007-x", session="sA"))
        Wal(self.home).append([{"type": "attribution.set", "source": "manual", "data": {
            "featureId": "007-x", "scope": {"sessionId": "sA"}, "workflow": "grill"}}])
        self.assertEqual(self.compute()[1]["facts"]["workflow"], "grill")

    def test_tag_setup_marca_os_turnos(self):
        self.build(self.simple(branch="main", session="sS"), self.simple(branch="007-x", session="sA"))
        Wal(self.home).append([{"type": "attribution.set", "source": "manual", "data": {
            "featureId": "007-x", "scope": {"sessionId": "sS"}, "tag": "setup"}}])
        m = self.model()
        self.assertTrue(all("setup" in t["tags"] for t in m.turns if t["sessionId"] == "sS"))
        self.assertEqual(len(m.turns_of("007-x")), 2)
        self.assertEqual(len(m.turns_of("007-x", include_setup=False)), 1)


class CycleSplitTests(MetricsBase):
    def test_ciclo_que_atravessa_features_vira_uma_parte_por_feature(self):
        t = self.transcript(branch="main", session="longa")
        t.prompt(skill="speckit-implement")
        t.assistant(tools=[("Read", "specs/010-y/plan.md")], usage=(0, 0, 10, 0))   # evidência da feature 010-y
        t.branch = "007-x"
        t.assistant(tools=[("Write", "apps/x/a.py", "l")], usage=(0, 0, 20, 0))      # agora no branch da feature 007-x
        t.assistant(usage=(0, 0, 30, 0), stop="end_turn")
        t.turn_duration(5000)
        self.build(t)
        Wal(self.home).append([born("010-y"), {"type": "feature.alias", "source": "manual", "data": {
            "featureId": "010-y", "alias": "specs/010-y", "source": "manual"}}])
        m = self.model()
        parts = [c for c in m.cycles if c["sessionId"] == "longa"]
        self.assertEqual([(c["feature"], len(c["turns"])) for c in parts], [("010-y", 1), ("007-x", 2)])
        feat = m.cycles_of("007-x")
        self.assertEqual(len(feat), 1)
        self.assertIsNone(feat[0]["prompt"])   # o prompt humano fica só na 1ª parte atribuída (não conta 2 vezes)
        first = m.cycles_of("010-y")
        self.assertEqual((len(first), (first[0]["prompt"] or {}).get("skill")), (1, "speckit-implement"))

    def test_rascunho_antes_do_branch_liga_o_ciclo_todo_a_feature_criada(self):
        t = self.transcript(branch="main", session="longa")
        t.prompt()
        t.assistant(tools=[("Read", "README.md")], usage=(0, 0, 10, 0))
        t.branch = "007-x"
        t.assistant(usage=(0, 0, 20, 0), stop="end_turn")
        self.build(t)
        m = self.model()
        self.assertEqual({x["feature"] for x in m.turns}, {"007-x"})
        self.assertEqual(len(m.cycles_of("007-x")), 1)

    def test_turno_sem_evidencia_herda_do_anterior_dentro_da_janela(self):
        t = self.transcript(branch="main", session="s")
        t.prompt()
        t.assistant(tools=[("Read", "specs/009-z/plan.md")])
        t.assistant(usage=(0, 0, 5, 0), stop="end_turn")
        self.build(t)
        Wal(self.home).append([born("007-x"), {"type": "feature.alias", "source": "manual", "data": {
            "featureId": "007-x", "alias": "specs/009-z", "source": "manual"}}])
        self.assertEqual({(x["feature"], x["mode"]) for x in self.model().turns}, {("007-x", "inferred")})
        # fora da janela da feature (histórica com fim antes do turno) não herda
        Wal(self.home).append([{"type": "feature.born", "source": "backfill", "data": {
            "featureId": "007-x", "bornAt": "2026-09-21T00:00:00Z", "bornSource": "declared", "dataClass": "historical",
            "coverage": "partial", "window": {"to": "2026-09-21T12:00:00Z"}}}])
        self.assertEqual({x["feature"] for x in self.model().turns}, {None})


class AliasIngestTests(MetricsBase):
    def test_spec_criada_no_branch_ativo_vira_alias_automatico(self):
        t = self.transcript(branch="007-x")
        t.prompt(skill="speckit-specify")
        t.assistant(tools=[("Read", "specs/006-outra/spec.md"), ("Write", "specs/008-foo/spec.md", "a")])
        t.assistant(tools=[("Write", "specs/008-foo/spec.md", "b")])   # 2ª escrita: não duplica
        t.assistant(stop="end_turn")
        self.build(t)
        aliases = [r["data"] for r in self.events("feature.alias")]
        self.assertEqual(aliases, [{"featureId": "007-x", "alias": "specs/008-foo",
                                    "source": "spec-created-on-active-branch"}])
        self.assertEqual(self.model().resolve("008-foo"), "007-x")   # numerações diferentes
        self.run_ingest(final=True)
        self.assertEqual(len(self.events("feature.alias")), 1)

    def test_spec_em_branch_que_nao_e_feature_nao_vira_alias(self):
        t = self.transcript(branch="main")
        t.prompt()
        t.assistant(tools=[("Write", "specs/008-foo/spec.md", "a")])
        t.assistant(stop="end_turn")
        self.build(t)
        self.assertEqual(self.events("feature.alias"), [])


class DerivedBranchTests(MetricsBase):
    def test_branch_derivado_de_branch_de_feature_e_ignorado(self):
        repo = make_repo(self, {"README.md": "x"})
        self.repo, self.pdir = repo, self.projects / ingest.slug(repo)
        git(repo, "switch", "-q", "-c", "007-x")
        git(repo, "switch", "-q", "-c", "008-derivado")   # criado a partir de um branch de feature
        t1, t2 = self.transcript(branch="007-x", session="a"), self.transcript(branch="008-derivado", session="b")
        for t in (t1, t2):
            t.prompt()
            t.assistant(stop="end_turn")
        self.build(t1, t2)
        born_ids = [r["data"]["featureId"] for r in self.events("feature.born")]
        self.assertEqual(born_ids, ["007-x"])
        aliases = [r["data"] for r in self.events("feature.alias")]
        self.assertEqual(aliases, [{"featureId": "007-x", "alias": "008-derivado", "source": "derived-branch"}])
        m = self.model()
        self.assertEqual({t["feature"] for t in m.turns}, {"007-x"})   # o trabalho no derivado é da feature-mãe

    def test_branch_criado_a_partir_do_principal_e_feature(self):
        repo = make_repo(self, {"README.md": "x"})
        self.repo, self.pdir = repo, self.projects / ingest.slug(repo)
        git(repo, "switch", "-q", "-c", "007-x")
        git(repo, "switch", "-q", "main")
        git(repo, "switch", "-q", "-c", "008-y")
        t1, t2 = self.transcript(branch="007-x", session="a"), self.transcript(branch="008-y", session="b")
        for t in (t1, t2):
            t.prompt()
            t.assistant(stop="end_turn")
        self.build(t1, t2)
        self.assertEqual(sorted(r["data"]["featureId"] for r in self.events("feature.born")), ["007-x", "008-y"])


if __name__ == "__main__":
    unittest.main()
