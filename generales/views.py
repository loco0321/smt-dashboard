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

class home(generic.TemplateView):
    template_name = "generales/monitoreo.html"
    
    

import os
import psycopg2
import pandas as pd

DB_CONFIG = {
    "dbname": os.environ.get("SURVEY_DB_NAME", "smt_data_db"),
    "user": os.environ.get("SURVEY_DB_USER", "smt_data_user"),
    "password": os.environ.get("SURVEY_DB_PASS", "smt_data_pass"),
    "host": os.environ.get("SURVEY_DB_HOST", "data.smt-onic.com"),
    "port": os.environ.get("SURVEY_DB_PORT", "5431"),
}



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


def monitoreo_dashboard(request):
    return render(request, "generales/monitoreo.html")


def monitoreo_data(request):
    conn = psycopg2.connect(**DB_CONFIG)

    # --- Encuestas por censista ---
    q1 = """
        SELECT su.user_id,
               CONCAT(u.first_name, ' ', u.last_name) AS nombre_completo,
               COUNT(*) AS total_encuestas
        FROM survey_surveyuser su
        JOIN auth_user u ON su.user_id = u.id
        WHERE su.created_at::date = CURRENT_DATE
        GROUP BY su.user_id, u.first_name, u.last_name
        ORDER BY total_encuestas DESC;
    """
    df_censistas = pd.read_sql(q1, conn)
    df_censistas["convencion"] = df_censistas["user_id"]

    # --- Sectores ---
    q2 = """
        SELECT sa.data->>'value' AS sector,
               COUNT(*) AS total
        FROM survey_answer sa
        JOIN survey_surveyuser su ON sa.survey_user_id = su.id
        WHERE su.created_at::date = CURRENT_DATE
          AND sa.survey_question_id IN (477, 863)
        GROUP BY sector;
    """
    df_sectores = pd.read_sql(q2, conn)

    # --- Viviendas distintas ---
    q3 = """
        SELECT COUNT(DISTINCT sa.data->>'value') AS total_viviendas
        FROM survey_answer sa
        JOIN survey_surveyuser su ON sa.survey_user_id = su.id
        WHERE su.created_at::date = CURRENT_DATE
          AND sa.survey_question_id IN (614, 615, 616);
    """
    df_viviendas = pd.read_sql(q3, conn)

    # --- Total encuestas ---
    q4 = """
        SELECT COUNT(*) AS total_encuestas
        FROM survey_surveyuser su
        WHERE su.created_at::date = CURRENT_DATE;
    """
    df_total = pd.read_sql(q4, conn)

    conn.close()

    # --- Convenciones ---
    convenciones = df_censistas[["user_id", "nombre_completo", "total_encuestas"]].drop_duplicates()
    convenciones = convenciones.to_dict(orient="records")

    # --- Respuesta JSON ---
    return JsonResponse({
        "kpis": {
            "total_encuestas": int(df_total["total_encuestas"].iloc[0]) if not df_total.empty else 0,
            "total_viviendas": int(df_viviendas["total_viviendas"].iloc[0]) if not df_viviendas.empty else 0,
            "total_sectores": int(df_sectores["sector"].nunique()) if not df_sectores.empty else 0,
        },
        "censistas": df_censistas.to_dict(orient="records"),
        "sectores": df_sectores.to_dict(orient="records"),
        "convenciones": convenciones
    })