# Quickstart: validar o endurecimento da resolução de processo

Pré-requisitos: ambiente já configurado conforme o README do projeto (`.venv` com
`requirements.txt` instalado, `.env` com `DJANGO_SETTINGS_MODULE` apontando para o settings de
teste/dev).

## 1. Rodar a suíte de testes automatizados (sem rede)

```powershell
python manage.py test apps.monitoring apps.telegram_bot
```

Resultado esperado: todos os testes passam, incluindo os novos casos desta feature (ver
`tasks.md`), sem nenhuma chamada HTTP real (tudo mockado com fixtures HTML locais, conforme o
Princípio VII da constituição).

## 2. Validar manualmente contra o SEI de verdade (opcional, respeita o rate limit)

Use o management command já existente, com um número de processo público conhecido:

```powershell
python manage.py resolve_process "08700.005905/2026-38"
```

Cenários para conferir manualmente (cada um só precisa ser feito uma vez, não repetidamente — é
uma página pública do governo, seja econômico com as consultas):

1. **Caminho feliz de hoje continua igual**: um processo que já era resolvido pela busca por
   protocolo continua resolvendo para a mesma URL de detalhe.
2. **Zero a mais no número**: rodar o mesmo comando prefixando um `0` extra no primeiro bloco
   (ex. `008700.005905/2026-38`) deve resolver para a mesma URL do passo 1.
3. **Processo inexistente**: um número bem formado mas inexistente (ex. trocar o ano por um que
   não existe) deve retornar "não encontrado", nunca lançar erro de falha de acesso.

## 3. Verificar que o formulário de defaults está sendo lido

Não é possível forçar o SEI a mudar um campo oculto sob demanda, então este ponto (User Story 3)
é validado só com fixture local no teste automatizado (passo 1) — uma página de pesquisa
sintética com um campo oculto extra deve ter esse campo refletido no payload enviado.

## Critério de aceite da feature

- Passo 1 (testes automatizados) passa integralmente.
- Passo 2.1 e 2.2 resolvem para a mesma URL.
- Passo 2.3 não lança exceção nem trava — retorna ausência de resultado como hoje.
