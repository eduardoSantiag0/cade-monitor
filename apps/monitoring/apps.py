"""
AppConfig do app monitoring.

O método ready() conecta o signal connection_created para ativar WAL mode
e outros PRAGMAs de desempenho no SQLite a cada nova conexão.

Por que aqui e não no settings.py:
  - AppConfig.ready() é o ponto correto do Django para código de inicialização.
  - Garante que o signal seja registrado depois que todos os apps estão carregados.
  - Centraliza a configuração do banco no app que mais depende de performance.
"""
from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.monitoring'
    verbose_name = 'Monitoramento'

    def ready(self) -> None:
        from django.db.backends.signals import connection_created

        def activate_sqlite_pragmas(sender, connection, **kwargs):
            """
            Ativa otimizações de desempenho e integridade para SQLite.

            WAL mode: permite leituras concorrentes enquanto o worker escreve.
            NORMAL sync: bom equilíbrio entre durabilidade e velocidade.
            cache_size -4096: usa ~4 MB de RAM para cache de páginas.
            foreign_keys ON: garante integridade referencial sempre.
            temp_store MEMORY: tabelas temporárias em memória (mais rápido).
            """
            if connection.vendor == 'sqlite':
                cursor = connection.cursor()
                cursor.execute('PRAGMA journal_mode=WAL;')
                cursor.execute('PRAGMA synchronous=NORMAL;')
                cursor.execute('PRAGMA cache_size=-4096;')
                cursor.execute('PRAGMA foreign_keys=ON;')
                cursor.execute('PRAGMA temp_store=MEMORY;')

        connection_created.connect(activate_sqlite_pragmas)
