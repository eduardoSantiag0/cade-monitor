# Data Model: Endurecimento da resolução de processo no SEI/CADE

Esta feature não introduz, remove nem altera nenhum modelo Django, tabela ou migration. Ela muda
apenas o comportamento interno de funções puras/de acesso HTTP em `apps/monitoring/clients.py` e
`apps/monitoring/extractors.py`. Nenhuma entidade persistida (`MonitoredProcess`, `Subscription`,
etc.) ganha campo novo.

As únicas estruturas de dados novas são em memória, internas à resolução de um processo, e vivem
inteiramente dentro de uma chamada de função — não são gravadas em lugar nenhum:

| Estrutura (em memória) | Onde vive | Representa |
|---|---|---|
| Dicionário de defaults do formulário | `extract_input_defaults()` → `dict[str, str]` | `name` → `value` de cada `<input>` da página pública de pesquisa do SEI no momento da consulta |
| Lista de tentativas de payload | dentro de `_fetch_by_process_number()` | até 3 dicionários de payload (protocolo, texto, nº de documento), cada um derivado do dicionário de defaults acima |

Ver [contracts/process-resolution.md](contracts/process-resolution.md) para o contrato de
entrada/saída das funções afetadas.
