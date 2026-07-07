.DEFAULT_GOAL := help
.PHONY: help install migrate superuser run worker test check collectstatic clean digest backup

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
PYTHON  ?= python
MANAGE  = $(PYTHON) manage.py

# ---------------------------------------------------------------------------
# Ajuda
# ---------------------------------------------------------------------------
help:
	@echo ""
	@echo "  CADE Monitor — comandos disponíveis"
	@echo ""
	@echo "  make install        Instala dependências Python"
	@echo "  make migrate        Aplica migrations pendentes"
	@echo "  make superuser      Cria superusuário Django"
	@echo "  make run            Inicia o servidor de desenvolvimento"
	@echo "  make worker         Inicia o worker de monitoramento"
	@echo "  make test           Roda todos os testes"
	@echo "  make check          Verifica configuração Django"
	@echo "  make collectstatic  Coleta arquivos estáticos"
	@echo "  make clean          Remove __pycache__ e .pyc"
	@echo "  make digest         Envia resumo diário (dry-run)"
	@echo "  make backup         Backup do SQLite em backups/"
	@echo ""

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------
install:
	pip install -r requirements.txt

migrate:
	$(MANAGE) migrate

superuser:
	$(MANAGE) createsuperuser

run:
	$(MANAGE) runserver

worker:
	$(MANAGE) run_worker

test:
	$(MANAGE) test tests --verbosity=2

check:
	$(MANAGE) check

collectstatic:
	$(MANAGE) collectstatic --noinput

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

digest:
	$(MANAGE) generate_daily_digest --dry-run

backup:
	$(MANAGE) backup_db --dest backups --keep 7

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
PYTHON  ?= python
MANAGE  = $(PYTHON) manage.py

# ---------------------------------------------------------------------------
# Ajuda
# ---------------------------------------------------------------------------
help:
	@echo ""
	@echo "  CADE Monitor — comandos disponíveis"
	@echo ""
	@echo "  make install        Instala dependências Python"
	@echo "  make migrate        Aplica migrations pendentes"
	@echo "  make superuser      Cria superusuário Django"
	@echo "  make run            Inicia o servidor de desenvolvimento"
	@echo "  make worker         Inicia o worker de monitoramento"
	@echo "  make test           Roda todos os testes"
	@echo "  make check          Verifica configuração Django"
	@echo "  make collectstatic  Coleta arquivos estáticos"
	@echo "  make clean          Remove __pycache__ e .pyc"
	@echo "  make digest         Envia resumo diário (dry-run)"
	@echo ""

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------
install:
	pip install -r requirements.txt

migrate:
	$(MANAGE) migrate

superuser:
	$(MANAGE) createsuperuser

run:
	$(MANAGE) runserver

worker:
	$(MANAGE) run_worker

test:
	$(MANAGE) test tests --verbosity=2

check:
	$(MANAGE) check

collectstatic:
	$(MANAGE) collectstatic --noinput

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

digest:
	$(MANAGE) generate_daily_digest --dry-run
