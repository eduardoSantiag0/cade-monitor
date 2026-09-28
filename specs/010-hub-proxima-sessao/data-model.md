# Data Model: Próxima sessão de julgamento no dashboard

Esta feature não introduz nenhum modelo Django novo. Os dois dados cacheados vivem na tabela
genérica do backend `DatabaseCache` do Django (`cache_hub`, criada por `createcachetable`), não
em modelos com campos próprios — ver research.md para o racional.

## Chaves de cache (`django.core.cache.cache`)

| Chave | Valor | TTL | Escrita por |
|---|---|---|---|
| `hub:sessoes` | lista de `{'data': 'AAAA-MM-DD', 'titulo': str}`, todas as sessões lidas do calendário (não só as futuras — a view filtra) | 7 dias | `apps/dashboard/hub.py::refresh_sessoes()` |
| `hub:pauta:{ano}:{numero}` | URL (str) do PDF da pauta, ou string vazia quando confirmadamente ainda não publicada | 7 dias (achada) / 6 horas (não achada — retenta mais cedo) | `apps/dashboard/hub.py::refresh_pauta(ano, numero)` |

Um marcador de "última tentativa" por fonte (reaproveitando o mesmo padrão de `DouFetchState` da
feature 009, mas como chaves de cache em vez de modelo — ver Alternativas em research.md) garante
a cadência mínima entre buscas:

| Chave | Valor | Uso |
|---|---|---|
| `hub:last_attempt:sessoes` | timestamp ISO da última tentativa | gate de cadência em `refresh_sessoes()` |
| `hub:last_attempt:pauta` | timestamp ISO da última tentativa | gate de cadência em `refresh_pauta()` |

## Relação com entidades existentes

Nenhuma — a feature não referencia `MonitoredProcess`, `Subscriber` nem qualquer modelo já
existente. É um dado global (uma sessão, uma pauta), não por processo/assinante.

Ver [contracts/hub.md](contracts/hub.md) para o contrato das funções de `apps/dashboard/hub.py`.
