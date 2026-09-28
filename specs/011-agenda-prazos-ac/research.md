# Research: Agenda e prazos de AC sumário

## Fonte do calendário oficial

- **Decisão**: buscar o ato (Portaria) que fixa os feriados nacionais e pontos facultativos da
  administração pública federal na listagem pública do DOU (`in.gov.br`), já em escopo
  constitucional (emenda v2.2.0, feature 009) — mesma fonte/parser de `apps/dou/parsers.py`,
  filtrando por texto ("dias de feriados nacionais") e órgão emissor em vez de por CADE, numa
  janela de busca de outubro do ano anterior a março do ano-alvo.
- **Rationale**: a camada estatutária (feriados nacionais) cobre a grande maioria dos dias não
  úteis relevantes para o cálculo de prazo, e a fonte já está em escopo — zero custo
  constitucional adicional.
- **Alternativas descartadas**: (a) a camada de comunicados avulsos específicos do CADE (suspensão
  pontual de prazo), que no Mesk vem de um endpoint de busca (`portalunico.estaleiro.serpro.gov.br`)
  fora do domínio já coberto pela constituição — descartada para o v1 porque exigiria uma nova
  avaliação de escopo do Princípio II (mesma decisão de "adiar" já tomada para PDF de ata/pauta na
  feature 009), sem impedir que o v1 já calcule prazos corretos na maioria dos casos; (b) manter
  uma tabela de feriados fixa no código (sem sincronização) — descartada porque o calendário muda
  todo ano (Portaria nova) e ficaria desatualizado silenciosamente, o oposto do espírito de
  "nunca usar dado não confirmado como certeza" da spec (FR-011).
- **Validação de ato oficial (FR-002)**: mesmo critério do Mesk — é Portaria, do(s) órgão(s)
  competente(s) (Ministério da Gestão e Inovação em Serviços Públicos, ou nome histórico
  equivalente), publicada na Seção 1, não revogada, referencia o ano-alvo, tem um número mínimo de
  datas extraídas, nenhuma fora do ano. Documentar aqui, após a validação ao vivo, se algum desses
  critérios precisar de ajuste contra o formato real de 2026/2027.

## Fórmula de prazo (`calcula_prazo_cade`)

- **Decisão**: portar a fórmula do Mesk como está (FR-004): início = primeiro dia útil do CADE
  estritamente após a data-evento; vencimento preliminar = início + (dias−1) corridos;
  vencimento final = preliminar, ou o próximo dia útil se cair em dia não útil.
- **Rationale**: é uma fórmula já validada em produção contra prazos reais do CADE; reimplementar
  diferente sem motivo introduziria risco sem benefício.
- **Alternativas descartadas**: contar só em dias úteis (cada um dos "N dias" sendo um dia útil) —
  descartada porque não é assim que o CADE conta (confirmado pelo próprio comentário do código
  original do Mesk, replicado como comentário aqui): só os dois extremos (início e vencimento)
  são ajustados para dia útil, os dias do meio contam corridos.

## Classificação do processo (Ato de Concentração Sumário)

- **Decisão**: extrair a classificação de um trecho do próprio `MonitoredProcess.last_text` (campo
  "Tipo:"/"Tipo de Processo:" já presente no HTML do SEI, mesmo padrão que o `dou.py` do Mesk já
  precisou reconhecer e descartar do texto formatado — `_SEI_CAMPO_FORMULARIO_RE`), com lista de
  exclusão explícita para classificações parecidas (ordinário, apuração, consulta, recurso).
- **Rationale**: evita nova fonte externa — o dado já está no texto que `apps/monitoring` já
  coleta.
- **A confirmar na implementação**: o formato exato do rótulo dessa classificação no HTML real do
  SEI (posição, se vem sempre com o mesmo rótulo) — validar contra 1-2 processos reais conhecidos
  como AC sumário durante a implementação, documentando aqui o que for encontrado (seguindo o
  padrão de "correção pós-implementação" das features 008/009/010).

## Geração de `.ics`

- **Decisão**: gerar o conteúdo do arquivo por template de texto puro (stdlib), replicando a
  técnica do Mesk: UID estável por (processo, tipo de prazo), `SEQUENCE` incrementado a cada
  atualização, `METHOD:REQUEST`/`METHOD:CANCEL`, dobra de linha em 75 octetos (RFC 5545),
  `TRANSP:TRANSPARENT` + `X-MICROSOFT-CDO-ALLDAYEVENT:TRUE` para evento de dia inteiro.
- **Rationale**: nenhuma dependência nova (Princípio VIII); o formato `.ics` é simples o bastante
  para não justificar uma lib externa, e o Mesk já validou essa abordagem em produção (Outlook e
  Gmail).
- **Anexo com `method=`**: `send_email_notification` (`apps/notifications/channels/email.py`) hoje
  aceita anexos com `content_type` livre, mas não propaga um parâmetro `method=` no cabeçalho
  `Content-Type` do anexo — necessário para os botões de Aceitar/Recusar aparecerem no Gmail/
  Outlook. Pequeno ajuste necessário nesse canal (adicionar `content_type` completo, ex.
  `text/calendar; method=REQUEST`, já é suportado pela assinatura atual via o campo
  `content_type` do anexo — não deve exigir mudança de assinatura, só o valor passado).
- **Alternativas descartadas**: biblioteca `icalendar` (PyPI) — descartada por ser uma dependência
  nova não justificada (o volume/complexidade do `.ics` gerado aqui — 2 tipos de evento, sem
  recorrência — não precisa de uma lib inteira de parsing/geração RFC 5545).

## Auto-encerramento — segurança

- **Decisão**: implementar as quatro guardas de FR-017/FR-018 como condições explícitas e
  testadas isoladamente (SC-004), reaproveitando campos já existentes de `MonitoredProcess`
  (`last_checked_at`, `last_error`) em vez de duplicar estado. A contagem de "10 dias sem
  movimentação" usa `DetectedChange.detected_at` mais recente (se houver, posterior à certidão) ou
  a data da própria certidão.
- **Rationale**: reaproveitar o estado que `apps/monitoring` já mantém evita inconsistência (dois
  lugares dizendo coisas diferentes sobre "a última verificação foi bem-sucedida?").
- **Alternativas descartadas**: arquivar (`ProcessStatus.ARCHIVED`) em vez de apagar — essa era a
  alternativa mais segura e foi explicitamente rejeitada pelo dono do projeto em favor de replicar
  o comportamento original do Mesk; documentado aqui para que a decisão fique rastreável (não foi
  uma omissão, foi escolha consciente).
