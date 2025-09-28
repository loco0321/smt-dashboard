from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views import generic
from django.http import JsonResponse
from django.db import connection
import folium
from django.shortcuts import render


class home(generic.TemplateView):
    template_name = 'generales/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        query = """
            SELECT
                su.id AS encuesta_id,
                (sa.data->'value'->>'latitude')::numeric AS latitud,
                (sa.data->'value'->>'longitude')::numeric AS longitud,
                sa.created_at
            FROM survey_answer sa
            JOIN survey_surveyuser su ON sa.survey_user_id = su.id
            WHERE sa.survey_question_id = 55
              AND sa.data->'value' IS NOT NULL
              AND jsonb_typeof(sa.data->'value') = 'object'
              AND sa.data->'value'->>'latitude' IS NOT NULL
              AND sa.data->'value'->>'longitude' IS NOT NULL
            ORDER BY sa.created_at DESC;
        """

        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        # Crear mapa base (no centrado aún, solo con estilo limpio)
        m = folium.Map(
            tiles="CartoDB positron",
            zoom_start=13
        )

        centro_chia = [4.85, -74.05]   # lat, lon
        m = folium.Map(
            location=centro_chia,
            zoom_start=12,
            tiles="CartoDB positron"   # mapa base claro y de buena calidad
        )

        # añadir todos los puntos como círculos fijos
        for encuesta_id, lat, lon, created_at in rows:
            folium.CircleMarker(
                location=[lat, lon],
                radius=5,
                color="blue",
                fill=True,
                fill_color="blue",
                fill_opacity=0.6,
                popup=f"Encuesta {encuesta_id} - {created_at}"
            ).add_to(m)

        # guardar mapa
        m.save("mapa_chia.html")


        # Pasar el mapa renderizado al template
        context["mapa_html"] = m._repr_html_()
        return context

def total_encuestas_realtime(request):
    query = """
        SELECT COUNT(DISTINCT sa.survey_user_id) AS total_encuestas
        FROM survey_answer sa
        INNER JOIN survey_surveyuser su 
            ON sa.survey_user_id = su.id
        WHERE su.survey_id IN (18, 30)                -- solo encuestas 18 y 30
          AND sa.created_at::date = CURRENT_DATE;     -- solo encuestas de hoy
    """
    
    with connection.cursor() as cursor:
        cursor.execute(query)
        row = cursor.fetchone()
    
    total = row[0] if row else 0
    
    return JsonResponse({
        "total_encuestas": total
    })

def encuestas_sector_477(request):
    query = """
       SELECT
            COALESCE(sa.data->>'value', 'SIN SECTOR') AS sector,
            COUNT(DISTINCT sa.survey_user_id) AS total_encuestas
        FROM survey_answer sa
        WHERE sa.survey_question_id IN (477, 863)   -- sector puede venir de cualquiera
        AND sa.created_at::date = CURRENT_DATE
        GROUP BY ROLLUP (sa.data->>'value')
        ORDER BY sector;
    """
    
    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
    
    # Convertimos a lista de dicts [{sector: "1", total: 38}, ...]
    sectores = [{"sector": row[0], "total": row[1]} for row in rows]

    return JsonResponse({
        "pregunta_id": 477,
        "sectores": sectores
    })


def encuestas_viviendas(request):
    """
    Retorna cuántas encuestas tienen la pregunta con id = 122 (viviendas)
    para las encuestas con survey_id 18 y 30.
    """
    query = """
        SELECT COUNT(DISTINCT sa.data->>'value') AS total_viviendas
            FROM survey_answer sa
            JOIN survey_surveyuser su 
            ON sa.survey_user_id = su.id
            WHERE su.survey_id IN (18, 30)
            AND sa.survey_question_id IN (614, 615, 616)
            AND sa.created_at::date = CURRENT_DATE;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        row = cursor.fetchone()

    total_viviendas = row[0] if row else 0

    return JsonResponse({
        "pregunta_id": 122,
        "total_viviendas": total_viviendas
    })
    
def total_personas_realtime(request):
    query = """
        WITH latest AS (
          SELECT DISTINCT ON (sa.survey_user_id)
                 sa.survey_user_id,
                 TRIM(sa.data->>'value') AS v
          FROM survey_answer sa
          JOIN survey_surveyuser su ON sa.survey_user_id = su.id
          WHERE su.survey_id IN (18, 30)
            AND sa.survey_question_id = 600
            AND sa.created_at::date = CURRENT_DATE
          ORDER BY sa.survey_user_id, sa.created_at DESC
        )
        SELECT COALESCE(SUM((NULLIF(regexp_replace(v, '\\D', '', 'g'), ''))::int), 0) AS total_personas
        FROM latest;
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        row = cursor.fetchone()

    total = row[0] if row and row[0] is not None else 0
    return JsonResponse({"total_personas": total})

def encuestas_por_usuario_hoy(request):
    """
    Devuelve encuestas agrupadas por usuario para la fecha actual.
    """
    query = """
        SELECT 
            u.id AS usuario_id,
            u.username AS usuario_login,
            (u.first_name || ' ' || u.last_name) AS usuario_nombre,
            COUNT(DISTINCT su.id) AS total_encuestas_hoy
        FROM survey_surveyuser su
        JOIN auth_user u 
            ON su.user_id = u.id
        JOIN survey_answer sa 
            ON sa.survey_user_id = su.id
        WHERE su.survey_id IN (18, 30)
          AND sa.created_at::date = CURRENT_DATE
        GROUP BY u.id, u.username, u.first_name, u.last_name
        ORDER BY total_encuestas_hoy DESC;
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

    data = [dict(zip(columns, row)) for row in rows]
    return JsonResponse({"encuestas": data})