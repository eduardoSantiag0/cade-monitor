# Feature Specification: Endurecimento da resolução de processo no SEI/CADE

**Feature Branch**: `008-endurecer-scraper-sei`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "Endurecer o scraper do SEI/CADE (apps/monitoring/clients.py e extractors.py) na resolução de número de processo para URL pública de detalhe. Hoje a busca faz uma única tentativa de POST com payload de campos ocultos fixado (hardcoded) e usando só o campo de protocolo; se o SEI mudar um campo oculto do formulário ou se a busca por protocolo não retornar link (mas a busca por texto ou por número de documento retornaria), a resolução falha silenciosamente. Quero resolver isso com três estratégias de busca em sequência (campo de protocolo, campo de texto, campo de número de documento) até achar o link do processo, e lendo os valores padrão dos campos ocultos do formulário (via GET na página de pesquisa) antes de montar o POST, em vez de fixar esses valores no código. Também quero corrigir automaticamente um erro comum de digitação do número do processo (zero a mais no início, ex: 008700.003718/2015-67 -> 08700.003718/2015-67) antes de pesquisar. Quero que o cade-monitor adote esse comportamento de resolução de processo, mantendo a mesma interface pública (resolve_process_url, lookup_process_url, get_snapshot) usada pelo bot do Telegram e por apps/processes/services.py, sem quebrar os testes existentes em tests/test_monitoring.py, tests/test_telegram_actions.py e tests/test_telegram_latest.py."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Processo só é achado por busca alternativa (Priority: P1)

Um usuário manda ao bot do Telegram (ou cadastra pelo painel) um número de processo cuja busca pública do SEI só retorna o link de detalhe quando pesquisada pelo campo de texto livre ou pelo campo de número de documento — a busca pelo campo de protocolo, usada hoje como única tentativa, não encontra nada para esse processo. Hoje isso é reportado ao usuário como "processo não encontrado", mesmo o processo sendo público. Depois da mudança, o sistema deve continuar tentando com as outras estratégias antes de desistir.

**Why this priority**: é o caminho crítico do produto inteiro — se o processo não é resolvido para uma URL, nenhum monitoramento, alerta ou consulta seguinte é possível. Hoje esse é o ponto de falha silenciosa mais caro: o usuário acha que o processo não existe.

**Independent Test**: pode ser testado isoladamente simulando a resposta pública do SEI de forma que só a segunda ou terceira estratégia de busca retorne um link de detalhe válido, e confirmando que `resolve_process_url`/`lookup_process_url` ainda encontram o processo.

**Acceptance Scenarios**:

1. **Given** um número de processo público cuja busca por protocolo não retorna link mas a busca por texto livre retorna, **When** o usuário pede para acompanhar esse processo, **Then** o sistema encontra e resolve a URL de detalhe do processo.
2. **Given** um número de processo público cuja busca por protocolo e por texto livre não retornam link mas a busca por número de documento retorna, **When** o usuário pede para acompanhar esse processo, **Then** o sistema encontra e resolve a URL de detalhe do processo.
3. **Given** um número de processo que não existe ou não é público em nenhuma das três buscas, **When** o usuário pede para acompanhar esse processo, **Then** o sistema informa que não encontrou o processo, exatamente como hoje.

---

### User Story 2 - Número de processo digitado com zero a mais (Priority: P2)

Um usuário digita o número do processo com um erro comum de digitação: um zero a mais no início do primeiro bloco de dígitos (ex.: `008700.003718/2015-67` em vez de `08700.003718/2015-67`). Hoje isso pode fazer a busca falhar mesmo o processo existindo. O sistema deve corrigir esse formato automaticamente antes de pesquisar.

**Why this priority**: reduz um erro de digitação comum sem exigir que o usuário perceba e corrija sozinho, evitando uma segunda tentativa e a impressão de que o bot "não funciona".

**Independent Test**: pode ser testado isoladamente chamando a resolução de processo com um número contendo o zero extra e confirmando que o resultado é idêntico ao de pesquisar com o número correto.

**Acceptance Scenarios**:

1. **Given** um número de processo público válido com um zero a mais no início, **When** o usuário pede para acompanhar esse processo, **Then** o sistema encontra e resolve a URL de detalhe do processo normalmente.
2. **Given** um número de processo digitado corretamente (sem o zero a mais), **When** o usuário pede para acompanhar esse processo, **Then** o comportamento não muda em relação ao existente hoje.

---

### User Story 3 - Formulário público do SEI muda um campo oculto (Priority: P3)

O formulário de pesquisa pública do SEI ganha, remove ou renomeia um campo oculto (comportamento fora do controle do CADE-Monitor). Hoje o payload de busca é fixo no código; se um campo oculto novo se tornar obrigatório, a busca pode parar de funcionar até alguém atualizar o código manualmente. Depois da mudança, o sistema deve ler os valores padrão atuais do formulário antes de montar a busca, adaptando-se sem precisar de um novo deploy.

**Why this priority**: é uma proteção contra manutenção reativa de longo prazo; tem menor urgência que os dois cenários acima porque depende de uma mudança externa que pode não acontecer no curto prazo, mas seu custo de não implementar é alto quando ocorre (o app para de funcionar até alguém notar e corrigir).

**Independent Test**: pode ser testado isoladamente simulando uma página de pesquisa com um campo oculto adicional (nome e valor não previstos no payload fixo atual) e confirmando que a busca ainda é enviada com sucesso, incluindo esse campo.

**Acceptance Scenarios**:

1. **Given** a página pública de pesquisa do SEI retorna um campo oculto novo com um valor padrão, **When** o sistema realiza uma busca de processo, **Then** esse campo e seu valor padrão são incluídos na requisição enviada.
2. **Given** a página pública de pesquisa do SEI está exatamente como hoje (sem campos novos), **When** o sistema realiza uma busca de processo, **Then** o resultado da busca não muda em relação ao comportamento existente.

---

### Edge Cases

- O que acontece quando a página de resultado da busca cita mais de um processo (ex.: busca por texto livre retornando vários processos correlatos)? O sistema deve escolher o link que realmente corresponde ao número do processo pesquisado, nunca o primeiro link da página por padrão.
- O que acontece se a requisição inicial (para ler os campos ocultos do formulário) falhar por rede/timeout? O sistema deve propagar o mesmo tipo de erro de falha de acesso já usado hoje, sujeito à mesma política de novas tentativas.
- O que acontece se as três estratégias de busca não encontrarem nenhum link de detalhe? O comportamento observável para quem chama a função deve ser idêntico ao caso atual de "processo não encontrado" (sem lançar erro de falha de acesso).
- O que acontece com o cache/hash de conteúdo já salvo para processos que hoje já são resolvidos com sucesso pela busca por protocolo? Não deve mudar — a nova lógica só amplia os casos cobertos, não deve alterar o resultado dos que já funcionam.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST tentar resolver a URL pública de detalhe de um processo usando, em sequência, pelo menos três estratégias de busca na página pública do SEI — por campo de protocolo, por campo de texto livre e por campo de número de documento — parando na primeira estratégia que retornar um link de detalhe válido.
- **FR-002**: Antes de montar qualquer requisição de busca, o sistema MUST ler os valores padrão atuais dos campos ocultos do formulário de pesquisa pública do SEI e usá-los como base do envio, em vez de depender exclusivamente de uma lista fixa de campos no código.
- **FR-003**: O sistema MUST normalizar o número de processo informado antes de pesquisar, corrigindo automaticamente o erro de digitação de um zero a mais no início do primeiro bloco de dígitos.
- **FR-004**: Quando a página de resultado citar mais de um processo, o sistema MUST escolher o link de detalhe cujo contexto (linha/trecho da página) referencia o número do processo pesquisado, em vez de assumir o primeiro link encontrado.
- **FR-005**: O sistema MUST manter o mesmo contrato público hoje usado pelos chamadores existentes (bot do Telegram e cadastro de processos): mesma assinatura e mesmo comportamento observável de `resolve_process_url`, `lookup_process_url` e `get_snapshot`.
- **FR-006**: Quando nenhuma das estratégias de busca encontrar um link de detalhe, o sistema MUST se comportar como hoje — `resolve_process_url`/`lookup_process_url` retornam ausência de resultado (não um erro de falha de acesso), preservando o snapshot de fallback da própria página de pesquisa quando aplicável.
- **FR-007**: Falhas de rede ou tempo esgotado durante qualquer uma das estratégias de busca MUST continuar sujeitas à mesma política de novas tentativas com espera crescente já existente hoje.
- **FR-008**: A suíte de testes automatizados existente relacionada a monitoramento e ao bot do Telegram MUST continuar passando sem exigir mudança de comportamento observável nos testes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Processos públicos que hoje falham em ser encontrados porque só a busca por texto livre ou por número de documento retornaria o link passam a ser encontrados com sucesso, sem qualquer intervenção manual no código ou nova tentativa do usuário.
- **SC-002**: Números de processo digitados com um zero a mais no início são resolvidos com a mesma taxa de sucesso que números digitados corretamente.
- **SC-003**: 100% dos testes automatizados hoje relacionados à resolução de processo e ao bot do Telegram continuam passando após a mudança.
- **SC-004**: Quando o formulário público do SEI ganha ou altera um campo oculto, a resolução de processo continua funcionando sem exigir alteração de código, verificável simulando essa mudança em ambiente de teste.

## Assumptions

- A página pública de pesquisa do SEI continua respondendo em português, com os mesmos nomes de campo de busca já usados hoje (protocolo, texto livre, número de documento).
- A política de novas tentativas com espera crescente já configurada (`REQUEST_RETRY_ATTEMPTS`/`REQUEST_RETRY_BACKOFF_SECONDS`) é reaproveitada, não substituída por uma nova.
- Um fallback via navegador automatizado (para páginas que dependem de JavaScript) está fora do escopo desta feature — exige uma dependência nova (navegador headless) e pode ser avaliado como feature futura separada.
- Esta feature não introduz nem altera modelos de dados nem migrations; é uma mudança de comportamento na camada de acesso a páginas públicas.
- Os três números de exemplo de processo público já usados nos testes existentes continuam representativos dos formatos aceitos.
