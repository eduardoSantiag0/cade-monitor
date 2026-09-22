"""Testes de parsing do bot: comandos e normalização de processos (funções puras)."""
from django.test import SimpleTestCase

from apps.telegram_bot.parsing import TgUpdate, normalize_process_ref, parse_command


class NormalizeProcessRefTest(SimpleTestCase):
    def test_canonical_and_variants(self):
        canonical = '08700.005905/2026-38'
        for value in (canonical, f'  {canonical} ', '08700005905202638', '08700 . 005905 / 2026-38'):
            with self.subTest(value=value):
                self.assertEqual(normalize_process_ref(value), canonical)

    def test_sei_url_is_kept(self):
        url = 'https://sei.cade.gov.br/sei/modulos/pesquisa/md_pesq_processo_exibir.php?abc'
        self.assertEqual(normalize_process_ref(url), url)

    def test_rejects_invalid(self):
        for value in ('', '123', '08700.005905/2026', 'https://example.com/x', 'abc', '087000059052026381'):
            with self.subTest(value=value):
                self.assertIsNone(normalize_process_ref(value))

    def test_rejects_lookalike_host(self):
        self.assertIsNone(normalize_process_ref('https://cade.gov.br.evil.com/x'))


class ParseCommandTest(SimpleTestCase):
    def test_plain_command_with_args(self):
        cmd = parse_command('/watch 08700.005905/2026-38', 'CadeBot')
        self.assertEqual((cmd.name, cmd.args), ('watch', '08700.005905/2026-38'))

    def test_addressed_to_us_is_accepted_case_insensitive(self):
        self.assertEqual(parse_command('/LIST@cadebot', 'CadeBot').name, 'list')

    def test_addressed_to_other_bot_is_ignored(self):
        self.assertIsNone(parse_command('/list@OutroBot', 'CadeBot'))

    def test_not_a_command(self):
        self.assertIsNone(parse_command('olá', 'CadeBot'))
        self.assertIsNone(parse_command('/', 'CadeBot'))

    def test_unknown_bot_username_accepts_any_target(self):
        self.assertEqual(parse_command('/help@Qualquer', '').name, 'help')


class UpdateSchemaTest(SimpleTestCase):
    def test_parses_from_alias_and_ignores_extra_fields(self):
        update = TgUpdate.model_validate({
            'update_id': 1,
            'message': {
                'message_id': 2, 'date': 0, 'text': '/start',
                'chat': {'id': 5, 'type': 'private', 'first_name': 'Ana', 'last_name': 'Lima'},
                'from': {'id': 5, 'is_bot': False, 'first_name': 'Ana'},
            },
        })
        self.assertEqual(update.message.from_user.id, 5)
        self.assertEqual(update.message.chat.display_name, 'Ana Lima')
