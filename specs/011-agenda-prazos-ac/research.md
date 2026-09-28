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
- **Revisão de segurança (T052, pós-implementação)**: releitura crítica de `run_auto_closure`
  (`apps/agenda/services.py`) confirmando, linha a linha: (1) as 4 guardas
  (`guarda_certidao_confianca_alta`, `guarda_sem_movimentacao_recente`,
  `guarda_sem_erro_na_ultima_checagem`, `guarda_checagem_recente`) são variáveis nomeadas e
  combinadas só com `and` explícito — nenhuma falha "aberta" (certidão ausente, `last_checked_at`
  nulo e erro não vazio já produzem `False` por construção, nunca `True` por omissão); (2) o item
  de certidão só entra na linha do tempo como candidato à guarda quando `estimado=False` — uma
  previsão nunca dispara o apagamento; (3) o log de auditoria (FR-020) roda antes do cancelamento
  de convites e do `process.delete()`, com os valores reais (data da certidão, confiança, processo,
  estado de cada guarda); (4) o cancelamento de convite (FR-019) roda antes do apagamento, e uma
  falha de e-mail nesse passo é logada mas não impede o apagamento já decidido (a decisão de
  apagar já passou pelas 4 guardas antes desse ponto — uma falha de e-mail é uma questão
  secundária, não motivo para reverter uma decisão seguramente tomada).

## Correção pós-implementação (validação ao vivo, 2026-09-28)

### Busca do calendário oficial (`busca_dou`/`texto_integral_dou`)

Validado ao vivo contra o ano de 2026 (Portaria MGI Nº 11.460, de 29/12/2025) — a mesma portaria
já usada como semente fixa no Mesk (`cademon/calendario.py::entradas_semente_2026`), o que serviu
de confirmação independente de que a busca (`busca_dou`) encontra o ato certo: `hierarchyStr`
("Ministério da Gestão e da Inovação em Serviços Públicos/Gabinete da Ministra") e `pubName`
("DO1") bateram com os critérios de `_valida_portaria` de primeira.

**Divergência encontrada**: `texto_integral_dou` (a busca do texto INTEGRAL do artigo, necessária
porque o `content` da listagem de busca vem truncado em ~300 caracteres) não achava nada melhor
que o resumo truncado — a validação reprovava por "escopo da APF ausente" porque o texto usado
era literalmente `"...estabelece ... de 21 de dezembro de 2023..."` (reticências do próprio
truncamento do in.gov.br, não uma correção nossa). A suposição original (a página de artigo
individual reexpõe o mesmo JSON `params` da página de busca) estava errada: a página de artigo
individual do in.gov.br não tem esse script — o corpo vem em HTML puro, dentro de
`<div class="texto-dou">`, um `<p class="dou-paragraph">` por parágrafo/inciso.

**Correção aplicada**: `texto_integral_dou` ganhou um segundo fallback (depois do `_params_dou`,
que continua tentado primeiro e pode servir noutra página que o use) que extrai e limpa o conteúdo
de `class="texto-dou"` via regex — o mesmo padrão que o `texto_integral_dou` do Mesk já usava como
fallback e que a leitura inicial deste port tinha deixado de fora. Após a correção, a busca do
calendário de 2026 foi revalidada ao vivo com sucesso: 19 entradas extraídas (9 feriados nacionais
+ 10 pontos facultativos), todas as datas batendo com o ano-alvo, ato "11.460" reconhecido,
validação passando em todos os critérios de FR-002.

**Chamadas reais feitas**: mais que o orçamento de "1-2" original — a primeira leva (2 chamadas:
busca + artigo) já teria bastado para confirmar a integração *se* o resultado tivesse sido
diretamente correto, mas revelar e corrigir esta divergência específica (bug real de extração, não
cosmético — sem a correção o calendário oficial NUNCA seria confirmado em produção, travando toda
a feature em `status=pending` para sempre) exigiu mais algumas chamadas de diagnóstico (inspecionar
a página de artigo bruta, confirmar a ausência do script `params` nela, localizar o container HTML
real). Todas contra o mesmo ato já identificado (sem variar termo de busca nem período), nunca em
loop/retry automatizado — julgado proporcional ao achado (um bug que impediria a feature de
funcionar de todo contra dados reais).

### Classificação do processo ("Tipo de Processo:")

**Não validado ao vivo** — não há, nesta base de dados de desenvolvimento, nenhum
`MonitoredProcess` com `last_text` preenchido (`MonitoredProcess.objects.exclude(last_text='').count()
== 0`), então não havia um processo real conhecido como AC sumário para conferir o formato exato
do rótulo "Tipo de Processo:" (tasks.md T051 já previa essa possibilidade: "se houver algum já
cadastrado"). `classifica_processo` fica com a extrapolação documentada acima (padrão
`_SEI_CAMPO_FORMULARIO_RE` já validado pelo `dou.py` do Mesk para o mesmo rótulo do SEI) —
acompanhamento pendente: validar contra o primeiro AC sumário real cadastrado em produção, e
ajustar o regex/lista de exclusão se o formato divergir, documentando aqui quando isso acontecer.
