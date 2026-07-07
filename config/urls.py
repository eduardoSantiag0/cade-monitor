from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.dashboard.urls')),
    path('processes/', include('apps.processes.urls')),
    path('subscribers/', include('apps.subscribers.urls')),
]
