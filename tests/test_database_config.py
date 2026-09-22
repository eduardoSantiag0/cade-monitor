"""
Testes da seleção/configuração de banco (spec 005-postgres-render).
Não abrem conexão: apenas validam o dict gerado para settings.DATABASES.
"""
import os
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from pydantic import ValidationError

from config.database import build_databases, database_config_from_url
from config.env_schema import EnvSettings

BASE_ENV = {'DEBUG': 'true', 'SECRET_KEY': 'teste-nao-usar'}


def _env(**extra) -> EnvSettings:
    with patch.dict(os.environ, {**BASE_ENV, **extra}, clear=True):
        return EnvSettings.from_env()


class DatabaseConfigFromUrlTest(SimpleTestCase):
    def _parse(self, url, sslmode='require', conn_max_age=60):
        return database_config_from_url(url, conn_max_age=conn_max_age, sslmode=sslmode)

    def test_full_url(self):
        cfg = self._parse('postgresql://user:pass@db.example.com:6543/cade_db')
        self.assertEqual(cfg['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(cfg['NAME'], 'cade_db')
        self.assertEqual(cfg['USER'], 'user')
        self.assertEqual(cfg['PASSWORD'], 'pass')
        self.assertEqual(cfg['HOST'], 'db.example.com')
        self.assertEqual(cfg['PORT'], '6543')
        self.assertEqual(cfg['CONN_MAX_AGE'], 60)
        self.assertTrue(cfg['CONN_HEALTH_CHECKS'])
        self.assertEqual(cfg['OPTIONS'], {'sslmode': 'require'})

    def test_postgres_scheme_and_default_port(self):
        cfg = self._parse('postgres://user:pass@internal-host/cade_db')
        self.assertEqual(cfg['PORT'], '5432')
        self.assertEqual(cfg['HOST'], 'internal-host')

    def test_password_with_special_chars_is_unquoted(self):
        cfg = self._parse('postgresql://user:p%40ss%2Fw%25rd@host/db')
        self.assertEqual(cfg['PASSWORD'], 'p@ss/w%rd')

    def test_sslmode_from_url_overrides_default(self):
        cfg = self._parse('postgresql://u:p@localhost/db?sslmode=disable', sslmode='require')
        self.assertEqual(cfg['OPTIONS']['sslmode'], 'disable')

    def test_conn_max_age_is_configurable(self):
        cfg = self._parse('postgresql://u:p@h/db', conn_max_age=0)
        self.assertEqual(cfg['CONN_MAX_AGE'], 0)

    def test_unsupported_scheme(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "'mysql'"):
            self._parse('mysql://u:p@h/db')

    def test_missing_host_or_name(self):
        for url in ('postgresql://u:p@/db', 'postgresql://u:p@host', 'postgresql://u:p@host/'):
            with self.subTest(url=url), self.assertRaises(ImproperlyConfigured):
                self._parse(url)

    def test_error_message_never_contains_password(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            self._parse('postgresql://user:SuperSecreta123@host')
        self.assertNotIn('SuperSecreta123', str(ctx.exception))
        self.assertIn('***', str(ctx.exception))

    def test_invalid_port_message_never_contains_password(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            self._parse('postgresql://user:SuperSecreta123@host:notaport/db')
        self.assertNotIn('SuperSecreta123', str(ctx.exception))


class BuildDatabasesTest(SimpleTestCase):
    def test_without_database_url_uses_current_sqlite_block(self):
        env = _env(SQLITE_PATH='/tmp/x.sqlite3')
        self.assertIsNone(env.database_url)
        self.assertEqual(
            build_databases(env),
            {
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': '/tmp/x.sqlite3',
                    'OPTIONS': {'timeout': 20},
                }
            },
        )

    def test_with_database_url_uses_postgres(self):
        env = _env(DATABASE_URL='postgresql://u:p@h/db', DB_SSLMODE='prefer', DB_CONN_MAX_AGE='30')
        cfg = build_databases(env)['default']
        self.assertEqual(cfg['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(cfg['OPTIONS']['sslmode'], 'prefer')
        self.assertEqual(cfg['CONN_MAX_AGE'], 30)

    def test_empty_database_url_fails_instead_of_falling_back(self):
        for value in ('', '   '):
            with self.subTest(value=repr(value)), self.assertRaises(ValidationError) as ctx:
                _env(DATABASE_URL=value)
            self.assertIn('DATABASE_URL', str(ctx.exception))

    def test_invalid_sslmode_is_rejected(self):
        with self.assertRaises(ValidationError):
            _env(DB_SSLMODE='sometimes')

    def test_negative_conn_max_age_is_rejected(self):
        with self.assertRaises(ValidationError):
            _env(DB_CONN_MAX_AGE='-1')
