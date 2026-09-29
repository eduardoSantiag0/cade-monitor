from django.urls import path

from . import views

app_name = 'precedentes'

urlpatterns = [
    path('', views.case_list, name='list'),
    path('novo/', views.case_create, name='case_create'),
    path('<int:pk>/', views.case_detail, name='case_detail'),
    path('<int:case_pk>/empresas/', views.entity_add, name='entity_add'),
    path('empresas/<int:pk>/editar/', views.entity_update, name='entity_update'),
    path('empresas/<int:pk>/remover/', views.entity_remove, name='entity_remove'),
    path('empresas/<int:entity_pk>/fatos/', views.fact_add, name='fact_add'),
    path('fatos/<int:pk>/corrigir/', views.fact_correct, name='fact_correct'),
    path('fatos/<int:pk>/historico/', views.fact_history, name='fact_history'),
    path('<int:case_pk>/analises/', views.analysis_add, name='analysis_add'),
]
