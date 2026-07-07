# ---------------------------------------------------------------------------
# Dockerfile — CADE Monitor
#
# Imagem única compartilhada pelos serviços web e worker.
# Serviço web roda Gunicorn; worker roda run_worker.
# ---------------------------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# Variáveis de ambiente para Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings

# Dependências de sistema mínimas (curl para healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências Python antes de copiar o código
# (aprovita cache de camadas do Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código
COPY . .

# Garante que os diretórios de dados e logs existam
RUN mkdir -p /app/data /app/logs /app/staticfiles

# Coleta arquivos estáticos durante o build.
# SECRET_KEY dummy é aceito porque collectstatic não usa criptografia.
RUN SECRET_KEY=build-dummy-key-not-used-at-runtime \
    python manage.py collectstatic --noinput

EXPOSE 8000
