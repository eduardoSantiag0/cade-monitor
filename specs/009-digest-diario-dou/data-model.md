# Data Model: Digest diário do DOU

Todos os modelos novos vivem em `apps/dou/models.py`. Nenhum modelo existente (`Subscriber`,
`MonitoredProcess`, etc.) é alterado.

## `DouSubscription`

Inscrição de um assinante existente no digest do DOU. Independente de qualquer
`ProcessSubscription`.

| Campo | Tipo | Notas |
|---|---|---|
| `subscriber` | FK → `subscribers.Subscriber` | `on_delete=CASCADE`, `related_name='dou_subscription'` |
| `enabled` | `BooleanField(default=True)` | Recebe o digest diário (P1) |
| `nextday_enabled` | `BooleanField(default=False)` | Optou pela antecipação da véspera (P2) e confirmação (P3) |
| `nextday_time` | `TimeField(default=time(19, 30))` | Horário de envio da antecipação; padrão 19h30 |
| `created_at` / `updated_at` | `DateTimeField` | Auditoria padrão do projeto |

Restrição: `unique=True` em `subscriber` (um assinante tem no máximo uma inscrição no DOU).

## `DouMonitoredTerm`

Termo (pessoa/empresa/palavra-chave) usado só para destaque visual — lista própria, sem sincronia
com outra lista do sistema (FR-002, confirmado em conversa).

| Campo | Tipo | Notas |
|---|---|---|
| `subscription` | FK → `DouSubscription` | `related_name='monitored_terms'` |
| `term` | `CharField(max_length=200)` | Texto livre; comparação por fold (sem acento/caixa) no `render.py`, não no banco |
| `created_at` | `DateTimeField` | |

## `DouSendLog`

Um registro por e-mail efetivamente enviado (ou tentado) por esta feature — cobre dedup (FR-005,
FR-012) e auditoria (FR-013, SC-003).

| Campo | Tipo | Notas |
|---|---|---|
| `subscription` | FK → `DouSubscription` | `related_name='send_logs'` |
| `kind` | `CharField(choices=Kind)` | `digest`, `pubdou_ant`, `pubdou_compl`, `pubdou_conf` |
| `reference_date` | `DateField` | Data do DOU/antecipação a que o envio se refere (não a data/hora do envio em si) |
| `status` | `CharField(choices=('sent', 'failed'))` | Resultado do envio |
| `error` | `TextField(blank=True)` | Mensagem de erro quando `status='failed'` |
| `sent_at` | `DateTimeField(auto_now_add=True)` | |

Restrição: `unique_together = ('subscription', 'kind', 'reference_date')` — é a garantia física de
FR-012 (nunca mais de um envio do mesmo tipo, mesmo assinante, mesmo dia): a tentativa de inserir
um segundo registro para a mesma combinação falha, e o service trata isso como "já enviado hoje".

## `DouFetchState`

Marcador de última tentativa de busca por fonte — implementa a cadência de 5 min da emenda do
Princípio II (v2.2.0). Deliberadamente genérico o mínimo necessário (não um sistema de cache).

| Campo | Tipo | Notas |
|---|---|---|
| `source` | `CharField(choices=('resenha', 'ingov_listing'), unique=True)` | Uma linha por fonte |
| `last_attempt_at` | `DateTimeField(null=True)` | Atualizado a cada tentativa (sucesso ou falha) |
| `last_success_at` | `DateTimeField(null=True)` | Atualizado só em sucesso — útil para diagnóstico |

## `DouAnticipation`

Snapshot do que foi antecipado na véspera para um assinante, usado na manhã seguinte para montar
o "exceto ..." (P3). Um campo JSON em vez de tabela normalizada (ver research.md).

| Campo | Tipo | Notas |
|---|---|---|
| `subscription` | FK → `DouSubscription` | `related_name='anticipations'` |
| `reference_date` | `DateField` | Data do DOU que se espera no dia seguinte |
| `items` | `JSONField` | Lista de itens antecipados (título/texto/referência de processo), formato interno de `render.py` |
| `created_at` / `updated_at` | `DateTimeField` | `updated_at` avança a cada complemento (P2) |

Restrição: `unique_together = ('subscription', 'reference_date')`.

## Relação com entidades existentes

```text
Subscriber (existente) 1───1 DouSubscription 1───N DouMonitoredTerm
                                    │
                                    ├──N DouSendLog
                                    └──N DouAnticipation

DouFetchState — sem relação, uma linha por fonte externa (resenha, ingov_listing)
```

Ver [contracts/dou-services.md](contracts/dou-services.md) para as funções de `services.py` que
operam sobre estes modelos.
