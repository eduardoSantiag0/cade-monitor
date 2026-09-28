import os
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.processes.models import MonitoredProcess

from ..models import AutosPackageJob

User = get_user_model()


class AutosViewsTest(TestCase):
    def setUp(self):
        self.tmp_media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_media, ignore_errors=True)
        self.override = override_settings(MEDIA_ROOT=self.tmp_media)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.process = MonitoredProcess.objects.create(label='P', source='08700.000001/2027-01')
        self.user = User.objects.create_user(username='u', password='x')

    def test_pedido_sem_autenticacao_redireciona_login(self):
        response = self.client.post(reverse('processes:autos_request', args=[self.process.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)
        self.assertEqual(AutosPackageJob.objects.count(), 0)

    def test_pedido_autenticado_cria_job(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('processes:autos_request', args=[self.process.pk]))
        self.assertRedirects(response, reverse('processes:detail', args=[self.process.pk]))
        self.assertEqual(AutosPackageJob.objects.count(), 1)

    def test_download_job_nao_pronto_404(self):
        self.client.force_login(self.user)
        job = AutosPackageJob.objects.create(process=self.process, status=AutosPackageJob.Status.PROCESSING)
        response = self.client.get(reverse('processes:autos_download', args=[self.process.pk, job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_download_job_expirado_404(self):
        self.client.force_login(self.user)
        job = AutosPackageJob.objects.create(
            process=self.process, status=AutosPackageJob.Status.READY,
            file_path='autos_packages/job_x.zip', expires_at=timezone.now() - timedelta(minutes=1),
        )
        response = self.client.get(reverse('processes:autos_download', args=[self.process.pk, job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_download_job_pronto_serve_arquivo(self):
        self.client.force_login(self.user)
        media_path = os.path.join(self.tmp_media, 'autos_packages')
        os.makedirs(media_path, exist_ok=True)
        rel_path = os.path.join('autos_packages', 'job_x.zip')
        with open(os.path.join(self.tmp_media, rel_path), 'wb') as fh:
            fh.write(b'PK\x03\x04conteudo')
        job = AutosPackageJob.objects.create(
            process=self.process, status=AutosPackageJob.Status.READY,
            file_path=rel_path, expires_at=timezone.now() + timedelta(days=1),
        )
        response = self.client.get(reverse('processes:autos_download', args=[self.process.pk, job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'PK\x03\x04conteudo')
