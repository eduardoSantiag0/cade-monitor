import os
import shutil
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.processes.models import MonitoredProcess

from ..models import AutosPackageJob
from ..services import request_package, run_pending_packages

User = get_user_model()


class AutosServicesTest(TestCase):
    def setUp(self):
        self.tmp_media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_media, ignore_errors=True)
        self.override = override_settings(MEDIA_ROOT=self.tmp_media)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.process = MonitoredProcess.objects.create(label='P', source='08700.000001/2027-01')
        self.user = User.objects.create_user(username='u', password='x')

    def test_request_package_cria_job_quando_nao_ha_ativo(self):
        job = request_package(self.process, self.user)
        self.assertEqual(job.status, AutosPackageJob.Status.QUEUED)
        self.assertEqual(job.process, self.process)
        self.assertEqual(job.requested_by, self.user)
        self.assertEqual(AutosPackageJob.objects.count(), 1)

    def test_request_package_reaproveita_job_ativo(self):
        first = request_package(self.process, self.user)
        second = request_package(self.process, self.user)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(AutosPackageJob.objects.count(), 1)

    def test_request_package_apos_falha_cria_novo(self):
        failed = AutosPackageJob.objects.create(process=self.process, status=AutosPackageJob.Status.FAILED)
        job = request_package(self.process, self.user)
        self.assertNotEqual(job.pk, failed.pk)
        self.assertEqual(job.status, AutosPackageJob.Status.QUEUED)

    @patch('apps.autos.services.monta_pacote')
    def test_run_pending_packages_pega_o_mais_antigo_e_marca_processing(self, mock_monta):
        older = AutosPackageJob.objects.create(process=self.process)
        AutosPackageJob.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(hours=1))
        other_process = MonitoredProcess.objects.create(label='Q', source='08700.000002/2027-01')
        newer = AutosPackageJob.objects.create(process=other_process)

        result = run_pending_packages(timezone.now())

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual(result['job_id'], older.pk)
        self.assertEqual(older.status, AutosPackageJob.Status.PROCESSING)
        self.assertEqual(newer.status, AutosPackageJob.Status.QUEUED)
        mock_monta.assert_called_once()

    @patch('apps.autos.services.monta_pacote', side_effect=RuntimeError('boom'))
    def test_run_pending_packages_nunca_lanca_excecao(self, mock_monta):
        job = AutosPackageJob.objects.create(process=self.process)
        result = run_pending_packages(timezone.now())  # não deve levantar
        job.refresh_from_db()
        self.assertEqual(job.status, AutosPackageJob.Status.FAILED)
        self.assertIn('boom', job.error)
        self.assertTrue(result['processed'])

    def test_run_pending_packages_sem_job_nao_faz_nada(self):
        result = run_pending_packages(timezone.now())
        self.assertFalse(result['processed'])

    def test_run_pending_packages_expira_pacote_vencido(self):
        media_path = os.path.join(self.tmp_media, 'autos_packages')
        os.makedirs(media_path, exist_ok=True)
        file_rel = os.path.join('autos_packages', 'job_x.zip')
        with open(os.path.join(self.tmp_media, file_rel), 'wb') as fh:
            fh.write(b'PK\x03\x04')
        expired = AutosPackageJob.objects.create(
            process=self.process, status=AutosPackageJob.Status.READY,
            file_path=file_rel, expires_at=timezone.now() - timedelta(minutes=1),
        )
        still_valid = AutosPackageJob.objects.create(
            process=MonitoredProcess.objects.create(label='R', source='08700.000003/2027-01'),
            status=AutosPackageJob.Status.READY, expires_at=timezone.now() + timedelta(days=1),
        )

        result = run_pending_packages(timezone.now())

        expired.refresh_from_db()
        still_valid.refresh_from_db()
        self.assertEqual(expired.status, AutosPackageJob.Status.EXPIRED)
        self.assertFalse(os.path.exists(os.path.join(self.tmp_media, file_rel)))
        self.assertEqual(still_valid.status, AutosPackageJob.Status.READY)
        self.assertEqual(result['expired'], 1)
