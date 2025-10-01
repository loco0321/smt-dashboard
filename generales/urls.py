from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
#from .views import home, total_encuestas_realtime, encuestas_sector_477
from .views import home

app_name = 'generales'

urlpatterns = [
    path('', views.home.as_view(), name='home'),
    path('dashboard/data/', views.monitoreo_data, name='dashboard-data'),
    # path('otro/', views.otro, name='otro'),
]
"""
    path('api/encuestas/total/', total_encuestas_realtime, name='total_encuestas'),
    path('api/encuestas/sector-477/', encuestas_sector_477, name='encuestas_sector_477'),
    path('api/encuestas/viviendas/', views.encuestas_viviendas, name='encuestas_viviendas'),
    path("api/encuestas/personas/", views.total_personas_realtime, name="total_personas_realtime"),
    path("api/encuestas/por-usuario-hoy/", views.encuestas_por_usuario_hoy, name="encuestas_por_usuario_hoy"),
    """