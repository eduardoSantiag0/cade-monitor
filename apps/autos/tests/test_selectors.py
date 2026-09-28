from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.processes.models import MonitoredProcess

from ..models import AutosPackageJob
from ..selectors import active_or_recent_job


class ActiveOrRecentJobTest(TestCase):
    def setUp(self):
        self.process = MonitoredProcess.objects.create(label='P', source='08700.000001/2027-01')

    def test_job_em_andamento_encontrado(self):
        for status in (AutosPackageJob.Status.QUEUED, AutosPackageJob.Status.PROCESSING):
            with self.subTest(status=status):
                AutosPackageJob.objects.all().delete()
                job = AutosPackageJob.objects.create(process=self.process, status=status)
                self.assertEqual(active_or_recent_job(self.process), job)

    def test_pronto_nao_expirado_encontrado(self):
        job = AutosPackageJob.objects.create(
            process=self.process, status=AutosPackageJob.Status.READY,
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.assertEqual(active_or_recent_job(self.process), job)

    def test_pronto_expirado_nao_encontrado(self):
        AutosPackageJob.objects.create(
            process=self.process, status=AutosPackageJob.Status.READY,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertIsNone(active_or_recent_job(self.process))

    def test_failed_nao_encontrado(self):
        AutosPackageJob.objects.create(process=self.process, status=AutosPackageJob.Status.FAILED)
        self.assertIsNone(active_or_recent_job(self.process))

    def test_sem_job_nenhum(self):
        self.assertIsNone(active_or_recent_job(self.process))
