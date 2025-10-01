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
