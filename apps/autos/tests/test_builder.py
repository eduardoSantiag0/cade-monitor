import os
import shutil
import tempfile
import zipfile
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.monitoring.clients import FetchError, NativeDocumentError, Snapshot
from apps.processes.models import MonitoredProcess

from ..builder import monta_pacote
from ..models import AutosPackageJob
from .fixtures import load_fixture


def _snapshot(base: str) -> Snapshot:
    return Snapshot(
        url='https://sei.cade.gov.br/sei/processo.php?id=1',
        status_code=200,
        title='Processo',
        text=load_fixture(f'{base}.txt'),
        content_hash='x' * 64,
        fetched_at='2027-01-01T00:00:00',
        content_length=0,
        html=load_fixture(f'{base}.html'),
    )


def _fake_download(url, record, timeout, user_agent, max_bytes=None):
    return {
        'document': record.get('document', ''),
        'title': record.get('doc_type', ''),
        'filename': f"{record.get('document', '')}.pdf",
        'content_type': 'application/pdf',
        'content': b'%PDF-1.4 conteudo de teste',
        'url': url,
    }


class AutosBuilderTest(TestCase):
    def setUp(self):
        self.tmp_media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_media, ignore_errors=True)
        self.override = override_settings(MEDIA_ROOT=self.tmp_media, SLEEP_BETWEEN_REQUESTS_SECONDS=0)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.process = MonitoredProcess.objects.create(
            label='Processo Teste', source='https://sei.cade.gov.br/sei/processo.php?id=1',
        )

    def _job(self):
        return AutosPackageJob.objects.create(process=self.process)

    @patch('apps.autos.builder.download_document', side_effect=_fake_download)
    @patch('apps.autos.builder.get_snapshot')
    def test_caminho_feliz_todos_com_link(self, mock_snapshot, mock_download):
        mock_snapshot.return_value = _snapshot('processo_todos_com_link')
        job = self._job()

        monta_pacote(job, timeout=15, user_agent='test', max_documents=10)

        job.refresh_from_db()
        self.assertEqual(job.status, AutosPackageJob.Status.READY)
        self.assertEqual(job.total_declared, 5)
        self.assertEqual(job.total_processed, 5)
        self.assertEqual(mock_download.call_count, 5)

        full_path = os.path.join(self.tmp_media, job.file_path)
        with zipfile.ZipFile(full_path) as zf:
            names = zf.namelist()
        self.assertEqual(len(names), 5)
        self.assertTrue(names[0].startswith('1. '))
        self.assertTrue(names[-1].startswith('5. '))

    @patch('apps.autos.builder.download_document', side_effect=_fake_download)
    @patch('apps.autos.builder.get_snapshot')
    def test_pausa_entre_downloads(self, mock_snapshot, mock_download):
        mock_snapshot.return_value = _snapshot('processo_todos_com_link')
        job = self._job()
        with override_settings(SLEEP_BETWEEN_REQUESTS_SECONDS=0.01), \
                patch('apps.autos.builder.time.sleep') as mock_sleep:
            monta_pacote(job, timeout=15, user_agent='test', max_documents=10)
        self.assertEqual(mock_sleep.call_count, 5)

    @patch('apps.autos.builder.download_document', side_effect=_fake_download)
    @patch('apps.autos.builder.get_snapshot')
    def test_placeholder_corroborado(self, mock_snapshot, mock_download):
        mock_snapshot.return_value = _snapshot('processo_um_indisponivel')
        job = self._job()

        monta_pacote(job, timeout=15, user_agent='test', max_documents=10)

        job.refresh_from_db()
        self.assertEqual(job.status, AutosPackageJob.Status.READY)
        full_path = os.path.join(self.tmp_media, job.file_path)
        with zipfile.ZipFile(full_path) as zf:
            names = zf.namelist()
            self.assertEqual(len(names), 5)
            self.assertTrue(names[2].startswith('3. ') and names[2].endswith('.txt'))
            content = zf.read(names[2]).decode('utf-8')
        self.assertIn('restrit', content.lower())

    @patch('apps.autos.builder.get_snapshot')
    def test_download_falha_com_corroboracao_vira_placeholder(self, mock_snapshot):
        # 4000003 TEM link, mas o download falha; o andamento já explica a
        # indisponibilidade -> deve virar placeholder, não derrubar o job.
        mock_snapshot.return_value = _snapshot('processo_falha_download')
        job = self._job()

        def flaky_download(url, record, timeout, user_agent, max_bytes=None):
            if record.get('document') == '4000003':
                raise FetchError('falha de rede simulada')
            return _fake_download(url, record, timeout, user_agent, max_bytes)

        with patch('apps.autos.builder.download_document', side_effect=flaky_download):
            monta_pacote(job, timeout=15, user_agent='test', max_documents=10)

        job.refresh_from_db()
        self.assertEqual(job.status, AutosPackageJob.Status.READY)
        full_path = os.path.join(self.tmp_media, job.file_path)
        with zipfile.ZipFile(full_path) as zf:
            names = zf.namelist()
            self.assertEqual(len(names), 5)
            self.assertTrue(names[2].startswith('3. ') and names[2].endswith('.txt'))
            content = zf.read(names[2]).decode('utf-8')
        self.assertIn('indispon', content.lower())

    @patch('apps.autos.builder.download_document', side_effect=_fake_download)
    @patch('apps.autos.builder.get_snapshot')
    def test_download_falha_sem_corroboracao_diverge(self, mock_snapshot, mock_download):
        mock_snapshot.return_value = _snapshot('processo_divergencia')
        job = self._job()

        def flaky_download(url, record, timeout, user_agent, max_bytes=None):
            if record.get('document') == '3000001':
                raise FetchError('falha de rede simulada')
            return _fake_download(url, record, timeout, user_agent, max_bytes)
        mock_download.side_effect = flaky_download

        monta_pacote(job, timeout=15, user_agent='test', max_documents=10)

        job.refresh_from_db()
        self.assertEqual(job.status, AutosPackageJob.Status.FAILED)
        self.assertIn('3000001', job.error)
        self.assertIn('3000004', job.error)

    @patch('apps.autos.builder.download_document', side_effect=_fake_download)
    @patch('apps.autos.builder.get_snapshot')
    def test_zip_dentro_dos_autos_incluido_sem_expandir(self, mock_snapshot, mock_download):
        mock_snapshot.return_value = _snapshot('processo_todos_com_link')
        job = self._job()

        def download_zip_for_third(url, record, timeout, user_agent, max_bytes=None):
            if record.get('document') == '1000003':
                return {
                    'document': '1000003', 'title': 'Anexo', 'filename': '1000003.zip',
                    'content_type': 'application/zip', 'content': b'PK\x03\x04fake-zip-bytes', 'url': url,
                }
            return _fake_download(url, record, timeout, user_agent, max_bytes)

        with patch('apps.autos.builder.download_document', side_effect=download_zip_for_third):
            monta_pacote(job, timeout=15, user_agent='test', max_documents=10)

        job.refresh_from_db()
        self.assertEqual(job.status, AutosPackageJob.Status.READY)
        full_path = os.path.join(self.tmp_media, job.file_path)
        with zipfile.ZipFile(full_path) as zf:
            names = zf.namelist()
            third_bytes = zf.read([n for n in names if n.startswith('3. ')][0])
        self.assertTrue(third_bytes.startswith(b'PK\x03\x04'))

    @patch('apps.autos.builder.download_document', side_effect=_fake_download)
    @patch('apps.autos.builder.get_snapshot')
    def test_divergencia_falha_job_sem_deixar_arquivo(self, mock_snapshot, mock_download):
        mock_snapshot.return_value = _snapshot('processo_divergencia')
        job = self._job()

        monta_pacote(job, timeout=15, user_agent='test', max_documents=10)

        job.refresh_from_db()
        self.assertEqual(job.status, AutosPackageJob.Status.FAILED)
        self.assertIn('3000004', job.error)
        self.assertEqual(job.file_path, '')
        # Nenhum arquivo (nem final, nem .building) deve sobrar em disco.
        leftovers = []
        for root, _dirs, files in os.walk(self.tmp_media):
            leftovers.extend(files)
        self.assertEqual(leftovers, [], f'arquivo(s) órfão(s) deixado(s) em disco: {leftovers}')

    @patch('apps.autos.builder.download_document', side_effect=_fake_download)
    @patch('apps.autos.builder.get_snapshot')
    def test_processamento_incremental_por_tick(self, mock_snapshot, mock_download):
        # monta_pacote não gerencia queued->processing (isso é responsabilidade de
        # services.run_pending_packages) — aqui simulamos o estado que o serviço já
        # teria deixado antes de chamar monta_pacote.
        mock_snapshot.return_value = _snapshot('processo_todos_com_link')
        job = self._job()
        job.status = AutosPackageJob.Status.PROCESSING
        job.save(update_fields=['status'])

        monta_pacote(job, timeout=15, user_agent='test', max_documents=2)
        job.refresh_from_db()
        self.assertEqual(job.status, AutosPackageJob.Status.PROCESSING, 'ainda não terminou')
        self.assertEqual(job.total_processed, 2)
        self.assertEqual(mock_snapshot.call_count, 1, 'não deve refazer o fetch em chamadas seguintes')

        monta_pacote(job, timeout=15, user_agent='test', max_documents=2)
        job.refresh_from_db()
        self.assertEqual(job.total_processed, 4)
        self.assertEqual(job.status, AutosPackageJob.Status.PROCESSING)

        monta_pacote(job, timeout=15, user_agent='test', max_documents=2)
        job.refresh_from_db()
        self.assertEqual(job.total_processed, 5)
        self.assertEqual(job.status, AutosPackageJob.Status.READY)
        self.assertEqual(mock_snapshot.call_count, 1)

    @patch('apps.autos.builder.get_snapshot', side_effect=FetchError('processo indisponível'))
    def test_falha_no_fetch_inicial_marca_failed(self, mock_snapshot):
        job = self._job()
        monta_pacote(job, timeout=15, user_agent='test', max_documents=10)
        job.refresh_from_db()
        self.assertEqual(job.status, AutosPackageJob.Status.FAILED)
        self.assertTrue(job.error)

    @patch('apps.autos.builder.get_snapshot')
    def test_documento_nativo_sem_corroboracao_diverge(self, mock_snapshot):
        mock_snapshot.return_value = _snapshot('processo_todos_com_link')
        job = self._job()

        def native_for_first(url, record, timeout, user_agent, max_bytes=None):
            if record.get('document') == '1000001':
                raise NativeDocumentError('nativo do SEI')
            return _fake_download(url, record, timeout, user_agent, max_bytes)

        with patch('apps.autos.builder.download_document', side_effect=native_for_first):
            monta_pacote(job, timeout=15, user_agent='test', max_documents=10)

        job.refresh_from_db()
        self.assertEqual(job.status, AutosPackageJob.Status.FAILED)
        self.assertIn('1000001', job.error)
