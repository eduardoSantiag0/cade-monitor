from django.urls import path

from . import views

app_name = 'processes'

urlpatterns = [
    path('', views.process_list, name='list'),
    path('new/', views.process_create, name='create'),
    path('<int:pk>/', views.process_detail, name='detail'),
    path('<int:pk>/edit/', views.process_edit, name='edit'),
    path('<int:pk>/toggle/', views.process_toggle, name='toggle'),
    path('<int:pk>/check/', views.process_check_now, name='check_now'),
    path('change/<int:pk>/', views.change_detail, name='change_detail'),
    path('change/<int:pk>/review/', views.change_review, name='change_review'),
]
