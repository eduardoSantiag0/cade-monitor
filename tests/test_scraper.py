
import unittest

from cademon.scraper import diff_summary, extract_cade_entries, latest_cade_records, normalize_html, stable_hash


class ScraperTests(unittest.TestCase):
    def test_normalize_html_removes_scripts_and_noise(self):
        html = '''
        <html><head><title>Processo X</title><script>dynamic()</script></head>
        <body><h1>Processo 08700</h1><p>Movimentacao nova</p><p>Data/Hora da Consulta 01/01/2026 10:00</p></body></html>
        '''
        text, title = normalize_html(html)
        self.assertEqual(title, 'Processo X')
        self.assertIn('Processo 08700', text)
        self.assertIn('Movimentacao nova', text)
        self.assertNotIn('dynamic', text)
        self.assertNotIn('Data/Hora da Consulta', text)

    def test_hash_changes_when_text_changes(self):
        self.assertNotEqual(stable_hash('a'), stable_hash('b'))

    def test_diff_summary_prefers_added_lines(self):
        summary, diff = diff_summary('linha antiga', 'linha antiga\nlinha nova')
        self.assertIn('linha nova', summary)
        self.assertIn('+ linha nova', diff)

    def test_extract_cade_entries_from_protocols_and_movements(self):
        text = '''
Lista de Protocolos (2 registros):
Documento / Processo
Tipo de Documento
Data do Documento
Data de Registro
Unidade
1773000
Edital
24/06/2026
24/06/2026
CGAA5
1773932
Relatorio Ato de Concentracao
25/06/2026
25/06/2026
GAB1
Lista de Andamentos (2 registros):
Data/Hora
Unidade
Descricao
24/06/2026 10:00
PROT
Processo recebido na unidade
25/06/2026 16:29
GAB1
Assinado Documento 1773932 (Relatorio Ato de Concentracao) por bruno.renzetti
'''
        entries = extract_cade_entries(text)
        self.assertIn('Novo documento: 1773932 | Relatorio Ato de Concentracao | Data do documento: 25/06/2026 | Registro: 25/06/2026 | Unidade: GAB1', entries['protocols'])
        self.assertIn('Novo andamento: 25/06/2026 16:29 | GAB1 | Assinado Documento 1773932 (Relatorio Ato de Concentracao) por bruno.renzetti', entries['movements'])

    def test_diff_summary_reports_new_cade_records(self):
        old = '''
Lista de Protocolos (1 registros):
Documento / Processo
Tipo de Documento
Data do Documento
Data de Registro
Unidade
1773000
Edital
24/06/2026
24/06/2026
CGAA5
Lista de Andamentos (1 registros):
Data/Hora
Unidade
Descricao
24/06/2026 10:00
PROT
Processo recebido na unidade
'''
        new = '''
Lista de Protocolos (2 registros):
Documento / Processo
Tipo de Documento
Data do Documento
Data de Registro
Unidade
1773000
Edital
24/06/2026
24/06/2026
CGAA5
1773932
Relatorio Ato de Concentracao
25/06/2026
25/06/2026
GAB1
Lista de Andamentos (2 registros):
Data/Hora
Unidade
Descricao
24/06/2026 10:00
PROT
Processo recebido na unidade
25/06/2026 16:29
GAB1
Assinado Documento 1773932 (Relatorio Ato de Concentracao) por bruno.renzetti
'''
        summary, diff = diff_summary(old, new)
        self.assertIn('novo(s) andamento(s)', summary)
        self.assertIn('Novo andamento: 25/06/2026 16:29 | GAB1', diff)
        self.assertIn('Novo documento: 1773932 | Relatorio Ato de Concentracao', diff)


    def test_latest_cade_records_returns_three_newest_items(self):
        text = '''
Lista de Protocolos (3 registros):
Documento / Processo
Tipo de Documento
Data do Documento
Data de Registro
Unidade
1771000
Edital
24/06/2026
24/06/2026
CGAA5
1773932
Relatorio Ato de Concentracao
25/06/2026
25/06/2026
GAB1
1775000
Anexo
29/06/2026
29/06/2026
SECONT
Lista de Andamentos (3 registros):
Data/Hora
Unidade
Descricao
30/06/2026 17:55
CGAA5
Processo recebido na unidade
25/06/2026 16:29
GAB1
Assinado Documento 1773932 (Relatorio Ato de Concentracao) por bruno.renzetti
24/06/2026 10:00
PROT
Processo recebido na unidade
'''
        records = latest_cade_records(text, 3)
        self.assertEqual(len(records), 3)
        self.assertIn('30/06/2026 17:55', records[0])
        self.assertIn('1775000', records[1])
        self.assertIn('25/06/2026 16:29', records[2])

if __name__ == '__main__':
    unittest.main()
