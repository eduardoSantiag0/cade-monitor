# Contrato: configuração

Padrões versionados em `tools/ai_metrics/config.default.json`. Sobrescrita opcional (mesclagem
por chave de primeiro nível) em `~/.cade-metrics/config.json`. Caminhos são globs relativos à raiz.
Estes são os valores **iniciais**; a lista de caminhos é ajustável sem mudar código (FR-024).

```json
{
  "executable_paths": ["apps/**", "config/**", "tests/**", "tools/**", "scripts/**",
                       "manage.py", "Dockerfile", "docker-compose.yml", "Makefile",
                       "requirements.txt", ".github/workflows/**"],
  "production_paths": ["apps/**", "config/**", "scripts/**", "manage.py"],
  "test_paths": ["tests/**", "tools/ai_metrics/tests/**", "**/test_*.py"],
  "ignore_paths": ["specs/**", "docs/**", "**/*.md", ".specify/**", ".claude/**", ".ai-metrics/**",
                   ".github/prompts/**"],
  "verification_commands": [
    {"id": "django-test", "pattern": "manage\\.py test"},
    {"id": "pytest", "pattern": "\\bpytest\\b"},
    {"id": "unit", "pattern": "unittest"}
  ],
  "git_operations": {"commit": "\\bgit\\s+commit\\b", "merge": "\\bgit\\s+merge\\b"},
  "skill_labels": {"speckit": ["speckit-*"], "grill": ["grill-me", "grill*"]},
  "main_branches": ["main", "master"],
  "idle_minutes": 30,
  "abandon_after_days": 30,
  "draft_link_grace_minutes": 30,
  "cost_divergence_threshold_pct": 5,
  "history_windows": {
    "005-postgres-render": {"endCommit": "6d098f9"},
    "006-telegram-bot":    {"startAfterCommit": "6d098f9", "endCommit": "95dbc2a"}
  }
}
```

Regras:

- Um caminho é **executável** se casa `executable_paths` e não casa `ignore_paths`
  (`ignore_paths` vence). Escrita fora do repositório nunca conta.
- `verification_commands` e `git_operations` são regexes aplicadas ao comando **no ingest**; o
  comando em si não é gravado (research R12).
- `skill_labels` só rotula workflow e submétricas (nunca define fronteira de fase).
- Chave desconhecida é ignorada com aviso; regex inválida faz o comando falhar com mensagem clara.
