# Data Model: Precedentes — dossiê de due diligence (fundação)

4 modelos novos em `apps/precedentes/models.py`. Nenhum modelo existente é alterado.

## `PrecedentCase`

| Campo | Tipo | Notas |
|---|---|---|
| `titulo` | `CharField` | |
| `cliente` | `CharField(blank=True)` | |
| `notas` | `TextField(blank=True)` | |
| `created_by` | FK → `auth.User` | |
| `created_at` | `DateTimeField(auto_now_add)` | |

## `PrecedentEntity`

| Campo | Tipo | Notas |
|---|---|---|
| `case` | FK → `PrecedentCase` | `on_delete=CASCADE`, `related_name='entities'` |
| `papel` | `CharField(choices)` | `requerente`, `parte_identificada`, `outro` |
| `razao_social` | `CharField` | |
| `cnpj` | `CharField(blank=True)` | Sem validação de dígito verificador nesta versão — texto livre |
| `pais` | `CharField(default='Brasil')` | |
| `created_at` | `DateTimeField(auto_now_add)` | |

## `PrecedentFact`

Tabela append-only: cada linha é uma versão. Ver research.md "Versionamento de fato".

| Campo | Tipo | Notas |
|---|---|---|
| `entity` | FK → `PrecedentEntity` | `on_delete=CASCADE`, `related_name='facts'` |
| `root` | FK → `self` (`null=True, blank=True`) | `None` na própria raiz (1ª versão); aponta pra raiz nas correções |
| `is_current` | `BooleanField(default=True)` | Só uma versão `True` por grupo (raiz + suas correções) |
| `campo` | `CharField` | Texto livre nesta versão (research.md) |
| `valor` | `TextField` | |
| `status` | `CharField(choices)` | `confirmado`, `confirmar_cliente`, `solicitar_cliente`, `nao_localizado` |
| `fonte_descricao` | `CharField` | Ex.: "site da empresa", "informação do cliente", nome do documento |
| `fonte_url` | `URLField(blank=True)` | |
| `citacao` | `TextField(blank=True)` | Trecho de evidência, quando houver |
| `motivo` | `TextField(blank=True)` | Obrigatório (validado em `services.py`, não na constraint de banco) em toda correção; vazio só na 1ª versão |
| `created_by` | FK → `auth.User` | |
| `created_at` | `DateTimeField(auto_now_add)` | |

Regra de negócio (não constraint de banco, `services.py::record_fact`/`correct_fact`):
`status='confirmado'` MUST ter `fonte_descricao` ou `fonte_url` preenchida (FR-004); toda correção
(`root` não-nulo) MUST ter `motivo` preenchido (FR-007).

## `PrecedentAnalysis`

| Campo | Tipo | Notas |
|---|---|---|
| `case` | FK → `PrecedentCase` | `on_delete=CASCADE`, `related_name='analyses'` |
| `texto` | `TextField` | |
| `facts` | `ManyToManyField(PrecedentFact)` | Sempre aponta para linhas-raiz (`root__isnull=True`) — ver research.md |
| `created_by` | FK → `auth.User` | |
| `created_at` | `DateTimeField(auto_now_add)` | |

## Relação com entidades existentes

```text
auth.User (existente) 1───N PrecedentCase, PrecedentEntity(via case), PrecedentFact, PrecedentAnalysis

PrecedentCase 1───N PrecedentEntity
PrecedentCase 1───N PrecedentAnalysis
PrecedentEntity 1───N PrecedentFact
PrecedentFact 1───N PrecedentFact (self, via `root` — grupo de versões)
PrecedentAnalysis N───N PrecedentFact (via `facts`, só linhas-raiz)
```

Nenhuma relação com `apps.processes.MonitoredProcess` nesta spec (spec.md, Assumptions — um caso
de due diligence não precisa de um processo SEI já monitorado). Ver
[contracts/precedentes.md](contracts/precedentes.md) para o contrato das funções de `services.py`.
