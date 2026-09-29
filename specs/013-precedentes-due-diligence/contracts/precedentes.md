# Contrato: `apps/precedentes` — services e views

App interno ao monolito (sem API HTTP própria). Toda regra de negócio mora em `services.py`;
`views.py` só valida entrada de formulário e chama o service.

## `apps/precedentes/services.py`

### `create_case(user, titulo, cliente='', notas='') -> PrecedentCase`

Simples `PrecedentCase.objects.create(...)`. Sem regra especial.

### `add_entity(case, papel, razao_social, cnpj='', pais='Brasil') -> PrecedentEntity`

Simples `PrecedentEntity.objects.create(...)`. Sem dedup automática (spec.md, Edge Cases).

### `remove_entity(entity) -> None`

FR-012: deleta `entity` (cascata nativa do Django remove seus `PrecedentFact`); em seguida, deleta
qualquer `PrecedentAnalysis` do mesmo `case` cujo `facts.count() == 0` após a cascata (análise que
ficou órfã porque todos os fatos-base eram só dessa empresa). Análises com fatos de OUTRAS empresas
sobrevivem, só perdendo o link para os fatos removidos.

### `record_fact(entity, user, campo, valor, status, fonte_descricao='', fonte_url='', citacao='') -> PrecedentFact`

- **FR-004**: se `status == CONFIRMADO` e nem `fonte_descricao` nem `fonte_url` estiverem
  preenchidas, levanta `ValidationError` — não cria o fato.
- **FR-005**: se `valor` vazio, levanta `ValidationError`.
- Cria a linha-raiz (`root=None`, `is_current=True`, `motivo=''`).

### `correct_fact(fact, user, motivo, **campos_novos) -> PrecedentFact`

- **FR-007**: `motivo` vazio → levanta `ValidationError`, não corrige.
- Aplica a mesma validação de FR-004 se o novo `status` for `CONFIRMADO`.
- Resolve a raiz do grupo (`fact.root or fact`); marca a versão atualmente `is_current=True` desse
  grupo como `is_current=False`; cria uma nova linha com `root=<raiz>`, `is_current=True`, os
  campos atualizados, `motivo` preenchido. **Nunca** faz `UPDATE` no valor da linha existente
  (FR-006).

### `record_analysis(case, user, texto, fact_roots: list[PrecedentFact]) -> PrecedentAnalysis`

- **FR-010**: `fact_roots` MUST ser só linhas-raiz (`root__isnull=True`) — se algum item recebido
  não for raiz, resolve para `item.root or item` antes de associar (nunca falha silenciosamente
  associando a versão errada).
- Cria a `PrecedentAnalysis` e associa via M2M.

## `apps/precedentes/selectors.py`

### `current_facts(entity) -> QuerySet[PrecedentFact]`

`PrecedentFact.objects.filter(entity=entity, is_current=True)` — o que a página do caso lista por
padrão (FR-011, distinto de análises).

### `fact_history(fact) -> QuerySet[PrecedentFact]`

Resolve a raiz (`fact.root or fact`) e retorna todas as versões desse grupo (`Q(id=raiz.id) |
Q(root_id=raiz.id)`), ordenadas por `created_at` (FR-009).

### `case_analyses(case) -> QuerySet[PrecedentAnalysis]`

`case.analyses.all()` com `prefetch_related('facts')` — para exibir junto dos fatos-base na página
do caso (FR-011).

## `apps/precedentes/views.py` (autenticadas, `@login_required` — FR-013)

- `GET /precedentes/` — lista de casos (`PrecedentCase` do usuário ou de todos os usuários
  autenticados, mesmo padrão de acesso do resto do painel — sem multi-tenancy nova).
- `POST /precedentes/novo/` — cria caso (`create_case`), redireciona para o detalhe.
- `GET /precedentes/<int:pk>/` — detalhe do caso: empresas, fatos atuais por empresa (FR-011,
  agrupados/destacados por status), análises (destacadas separadamente), formulários inline para
  adicionar empresa/fato/análise.
- `POST /precedentes/<int:pk>/empresas/` — adiciona empresa (`add_entity`).
- `POST /precedentes/empresas/<int:pk>/remover/` — remove empresa (`remove_entity`), com
  confirmação prévia no template (spec.md, Edge Cases: "advogado é avisado do que será removido").
- `POST /precedentes/empresas/<int:pk>/fatos/` — registra fato (`record_fact`).
- `POST /precedentes/fatos/<int:pk>/corrigir/` — corrige fato (`correct_fact`).
- `GET /precedentes/fatos/<int:pk>/historico/` — histórico de versões (`fact_history`), FR-009.
- `POST /precedentes/<int:pk>/analises/` — registra análise (`record_analysis`).

Todas as views POST fazem `ValidationError` → mensagem de erro via Django `messages`, permanecendo
na mesma página (mesmo padrão já usado em `apps/dashboard/views.py`).
