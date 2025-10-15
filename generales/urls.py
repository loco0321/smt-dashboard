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

]
