from django.urls import path

from . import views

app_name = 'subscribers'

urlpatterns = [
    path('', views.subscriber_list, name='list'),
    path('new/', views.subscriber_create, name='create'),
    path('<int:pk>/', views.subscriber_detail, name='detail'),
    path('<int:pk>/edit/', views.subscriber_edit, name='edit'),
    path('<int:subscriber_pk>/subscribe/', views.subscription_add, name='subscribe'),
    path('subscription/<int:pk>/remove/', views.subscription_remove, name='unsubscribe'),
]
