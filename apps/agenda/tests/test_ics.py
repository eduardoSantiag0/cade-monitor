from datetime import date

from django.test import SimpleTestCase

from apps.agenda.ics import build_ics


class BuildIcsTests(SimpleTestCase):
    def _text(self, **kwargs) -> str:
        defaults = dict(
            uid='ac-1-sg_analysis@cade-monitor', sequence=0, method='REQUEST',
            summary='Prazo de análise da SG', event_date=date(2027, 2, 3),
        )
        defaults.update(kwargs)
        return build_ics(**defaults).decode('utf-8')

    def test_request_has_expected_headers(self):
        text = self._text()
        self.assertIn('BEGIN:VCALENDAR', text)
        self.assertIn('METHOD:REQUEST', text)
        self.assertIn('UID:ac-1-sg_analysis@cade-monitor', text)
        self.assertIn('SUMMARY:Prazo de análise da SG', text)
        self.assertIn('DTSTART;VALUE=DATE:20270203', text)
        self.assertIn('TRANSP:TRANSPARENT', text)

    def test_cancel_sets_method_and_status(self):
        text = self._text(method='CANCEL')
        self.assertIn('METHOD:CANCEL', text)
        self.assertIn('STATUS:CANCELLED', text)

    def test_long_line_is_folded_at_75_octets(self):
        text = self._text(summary='S' * 200)
        for line in text.split('\r\n'):
            if line.startswith(' '):
                continue
            self.assertLessEqual(len(line.encode('utf-8')), 75)
        self.assertIn('\r\n ', text)
