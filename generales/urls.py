from django.urls import path
from . import views

app_name = 'generales'

urlpatterns = [
    path('', views.Home.as_view(), name='home'),

    # Monitoreo
    path("dashboard/", views.monitoreo_dashboard, name="dashboard"),
    path("dashboard/data/", views.monitoreo_data, name="dashboard-data"),

    # Consolidado
    path("dashboard/consolidado/", views.dashboard_consolidado, name="dashboard-consolidado"),
    path("dashboard/consolidado/data/", views.dashboard_consolidado_data, name="dashboard-consolidado-data"),
    path("dashboard/consolidado/exportar/", views.exportar_consolidado_excel, name="dashboard-consolidado-exportar"),
    path("dashboard/consolidado/exportar-dia/", views.exportar_consolidado_excel_dia, name="dashboard-consolidado-exportar-dia"),
    path("dashboard/reporte-censistas/", views.reporte_censistas, name="reporte-censistas"),
    path("dashboard/reporte-censistas/data/", views.reporte_censistas_data, name="reporte-censistas-data"),
]
