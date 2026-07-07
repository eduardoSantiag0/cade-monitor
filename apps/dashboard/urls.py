from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('notifications/', views.notifications_list, name='notifications'),
    path('notifications/test-email/', views.send_test_email, name='send_test_email'),
    path('notifications/test-whatsapp/', views.send_test_whatsapp, name='send_test_whatsapp'),
]
