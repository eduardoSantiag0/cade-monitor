import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.processes.models import MonitoredProcess

from .models import AutosPackageJob
from .services import request_package


@login_required
@require_POST
def request_package_view(request, pk):
    process = get_object_or_404(MonitoredProcess, pk=pk)
    request_package(process, request.user)
    return redirect('processes:detail', pk=process.pk)


@login_required
def download_view(request, pk, job_id):
    job = get_object_or_404(AutosPackageJob, pk=job_id, process_id=pk)
    if job.status != AutosPackageJob.Status.READY or not job.file_path:
        raise Http404
    if job.expires_at and job.expires_at <= timezone.now():
        raise Http404
    full_path = os.path.join(settings.MEDIA_ROOT, job.file_path)
    if not os.path.exists(full_path):
        raise Http404
    filename = f'{job.process.label} - Autos.zip'
    return FileResponse(open(full_path, 'rb'), as_attachment=True, filename=filename)
