"""
Testes da validação de SECRET_KEY insegura em produção (config/env_schema.py).

Constrói EnvSettings diretamente (sem passar por from_env/os.environ) para
isolar o comportamento do validador do resto do processo de carregamento do
Django, que já roda uma vez na subida do settings.py.
"""
from django.test import SimpleTestCase
from pydantic import ValidationError

from config.env_schema import INSECURE_SECRET_KEY_DEFAULT, EnvSettings


class SecretKeyValidationTests(SimpleTestCase):
    def test_rejects_empty_secret_key_in_production(self):
        with self.assertRaises(ValidationError):
            EnvSettings(debug=False, secret_key='')

    def test_rejects_default_example_secret_key_in_production(self):
        with self.assertRaises(ValidationError):
            EnvSettings(debug=False, secret_key=INSECURE_SECRET_KEY_DEFAULT)

    def test_accepts_custom_secret_key_in_production(self):
        settings = EnvSettings(debug=False, secret_key='uma-chave-realmente-aleatoria-e-longa-o-suficiente')
        self.assertEqual(settings.secret_key, 'uma-chave-realmente-aleatoria-e-longa-o-suficiente')

    def test_allows_empty_secret_key_in_development(self):
        """DEBUG=true (desenvolvimento local) não exige SECRET_KEY própria."""
        settings = EnvSettings(debug=True, secret_key='')
        self.assertEqual(settings.secret_key, '')
