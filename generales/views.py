from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views import generic
from django.http import JsonResponse
from django.db import connection
import folium
from folium.plugins import MarkerCluster, HeatMap
import geopandas as gpd
from django.shortcuts import render
from folium.features import DivIcon
import pandas as pd
from django.http import JsonResponse

class home(generic.TemplateView):
    template_name = "generales/monitoreo.html"
    
# ==========
# Endpoint de datos
# ==========

DB_CONFIG = {
    "dbname": "smt_data_db",
    "user": "smt_data_user",
    "password": "smt_data_pass",
    "host": "data.smt-onic.com",
    "port": "5431",
}

# ✅ IDs de encuestas válidas
SURVEY_IDS = (18, 30, 31)

def monitoreo_data(request):
    conn = connection

    # Total encuestas
    q_total = """
        SELECT COUNT(DISTINCT survey_user_id) AS total_encuestas
        FROM survey_answer
        WHERE (created_at AT TIME ZONE 'UTC' AT TIME ZONE 'America/Bogota')::date = CURRENT_DATE
        AND survey_id IN (18, 30, 31);
    """
    df_total = pd.read_sql(q_total, conn)
    total_encuestas = int(df_total["total_encuestas"].iloc[0]) if not df_total.empty else 0


    # Viviendas
    q_viviendas = """
        SELECT COUNT(DISTINCT TRIM(data->>'value')) AS total_viviendas
        FROM survey_answer
        WHERE (created_at AT TIME ZONE 'UTC' AT TIME ZONE 'America/Bogota')::date = CURRENT_DATE
        AND survey_id IN (18, 30, 31)
        AND survey_question_id IN (614, 615, 616);
    """
    df_viviendas = pd.read_sql(q_viviendas, conn)
    total_viviendas = int(df_viviendas["total_viviendas"].iloc[0]) if not df_viviendas.empty else 0

    # Sectores
    q_sectores = """
        SELECT (data->>'value') AS sector, COUNT(*) AS total
        FROM survey_answer
        WHERE (created_at AT TIME ZONE 'UTC' AT TIME ZONE 'America/Bogota')::date = CURRENT_DATE
        AND survey_id IN (18, 30, 31)
        AND survey_question_id IN (477, 863)
        GROUP BY data->>'value';
    """
    df_sectores = pd.read_sql(q_sectores, conn)
    sectores = df_sectores.to_dict(orient="records")

    # Censistas
    q_censistas = """
        SELECT sa.user_id AS convencion,
        CONCAT(COALESCE(u.first_name,''),' ',COALESCE(u.last_name,'')) AS nombre_completo,
        COUNT(DISTINCT sa.survey_user_id) AS total_encuestas
        FROM survey_answer sa
        JOIN auth_user u ON u.id = sa.user_id
        WHERE (sa.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'America/Bogota')::date = CURRENT_DATE
        AND sa.survey_id IN (18, 30, 31)
        GROUP BY sa.user_id, u.first_name, u.last_name
        ORDER BY total_encuestas DESC;
    """
    df_censistas = pd.read_sql(q_censistas, conn)
    censistas = df_censistas.to_dict(orient="records")

    return JsonResponse({
        "kpis": {
            "total_encuestas": total_encuestas,
            "total_viviendas": total_viviendas,
            "total_sectores": len(sectores)
        },
        "censistas": censistas,
        "sectores": sectores,
        "convenciones": censistas   # mismo array, pero lo usas para la tabla
    })