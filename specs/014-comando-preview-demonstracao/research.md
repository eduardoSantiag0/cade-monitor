# Research: Comando /preview — demonstração para portfólio

## O que "reaproveitar o fluxo real" significa em segurança de dados

- **Decisão**: reaproveitar as duas funções puras que já fazem o trabalho de "entender a mudança"
  e "formatar a notificação" — `apps.monitoring.diff.compute_diff(old_text, new_text)` e
  `apps.notifications.services.build_test_notification_body(process_label, process_url, channel)`
  (essa última já existe especificamente para o botão "enviar e-mail de teste" do painel —
  `apps/dashboard/views.py::send_test_email`, mesmo padrão de "gerar conteúdo real sem enviar de
  verdade"). NÃO reaproveitar `apps.monitoring.services.run_check`/`_handle_change` inteiros, nem
  `get_snapshot`, nem `collect_new_documents`, nem `create_notifications_for_change`.
- **Rationale**: `run_check`/`_handle_change` fazem requisições HTTP reais (`get_snapshot` busca a
  página; `collect_new_documents`, dentro de `_handle_change`, baixa documentos novos encontrados
  no diff) — inaceitável para uma demonstração que MUST NOT tocar rede (FR-006). Já
  `create_notifications_for_change` cria registros `Notification` reais, que o `run_worker` real
  (`send_pending_notifications`) poderia pegar e efetivamente despachar por engano — inaceitável
  frente a FR-007. `compute_diff` e `build_test_notification_body` já são, por desenho, funções
  puras sem I/O — o par certo para reaproveitar sem herdar nenhum dos dois riscos.
- **Alternativas descartadas**: (a) reaproveitar `run_check` com `get_snapshot` mockado via
  `unittest.mock.patch` também em produção — descartada por ser um padrão de teste vazando para
  código de produção (frágil, difícil de auditar, e ainda herdaria o risco de
  `collect_new_documents`/`create_notifications_for_change` sem mock adicional); (b) reescrever a
  lógica de diff do zero só para a demo — descartada por duplicar lógica já existente e testada
  (Princípio VIII), e por deixar de cumprir literalmente o pedido de "reaproveitar a lógica real".

## Processo fictício: registro persistente único, isolado do ciclo real

- **Decisão**: um único `MonitoredProcess` reservado (get-or-create por um `source` fixo e
  claramente fictício, ex. `'08700.000000/2026-00'` — mesmo formato de número de processo real,
  mas com todos os dígitos variáveis zerados, impossível de colidir com um processo real), sempre
  criado com `status=ProcessStatus.ARCHIVED`.
- **Rationale**: `status=ARCHIVED` garante que `apps.monitoring.scheduler.get_due_processes` (que
  filtra por `status=ACTIVE`) NUNCA seleciona esse processo para uma checagem real — é
  estruturalmente impossível o processo fictício "vazar" para o ciclo do `run_worker`, sem precisar
  de nenhuma lista de exclusão nova. `ARCHIVED` já existe como valor de `ProcessStatus`, não exige
  nenhuma mudança de schema.
- **Alternativas descartadas**: (a) não persistir nada, gerar tudo em memória a cada chamada —
  descartada porque contraria FR-002 ("reaproveitado entre execuções") e reduziria a demonstração a
  texto estático, sem de fato exercitar os modelos reais (`DetectedChange` etc.); (b) um campo novo
  `is_demo` em `MonitoredProcess` — descartado por ser uma mudança de schema desproporcional a um
  problema que `status=ARCHIVED` já resolve sozinho (Princípio VIII).

## `DetectedChange` de demonstração: get-or-create, não um novo registro a cada chamada

- **Decisão**: assim como o processo, a "mudança" de demonstração (`CheckRun` + `PageSnapshot` +
  `DetectedChange`) é get-or-create/atualizada no lugar a cada execução de `/preview`, não recriada
  do zero a cada vez.
- **Rationale**: evita acumular registros de demonstração indefinidamente a cada execução (SC-004,
  "nunca deixa o banco num estado inconsistente"); ainda assim exercita de verdade os mesmos
  modelos que uma mudança real usaria.
- **Alternativas descartadas**: criar um novo `DetectedChange` a cada chamada — descartada por
  acumular lixo no banco proporcional ao número de vezes que alguém testa o comando (potencialmente
  alto, já que é pensado para ser executado livremente por visitantes do repositório).

## Visibilidade do processo fictício no painel administrativo

- **Decisão/Assunção explícita**: o processo fictício PODE aparecer na listagem do painel
  administrativo (`apps/dashboard`, que lista todo `MonitoredProcess` sem filtro de assinatura) —
  não há filtro adicional para escondê-lo de lá nesta versão. Fica visível só para quem já tem
  login no painel (não é a superfície pública/de portfólio), com rótulo claro de demonstração no
  `label`.
- **Rationale**: filtrar o painel administrativo para excluir o processo de demonstração é uma
  melhoria de polimento, não uma exigência de segurança — o painel já exige autenticação, e o
  processo vem com rótulo autoexplicativo. Evita complexidade desproporcional (Princípio VIII) para
  uma superfície que não é a que a feature pretende demonstrar (o valor de portfólio está na
  conversa com o bot, não no painel administrativo).
- **Alternativas descartadas**: adicionar um filtro `exclude(source=DEMO_SOURCE)` em toda selector
  de listagem do painel — descartado como escopo extra não pedido; pode virar melhoria futura se o
  dono do projeto achar confuso na prática.

## Comando aberto, sem restrição de grupo/administrador

- **Decisão**: `/preview` NÃO entra em `MANAGEMENT_COMMANDS` (o conjunto que exige administrador em
  grupos) — funciona igual em chat privado e em grupo, para qualquer usuário.
- **Rationale**: não altera nada que o chat acompanha (não é uma ação de gerenciamento no sentido
  já estabelecido pelo bot) — é só uma demonstração somente-leitura do ponto de vista do usuário.
