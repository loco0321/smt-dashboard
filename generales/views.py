from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views import generic
from django.http import JsonResponse
from django.db import connection


class home(generic.TemplateView):
    template_name = 'generales/home.html'
    success_url = reverse_lazy('generales:home')
    
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
            sa.data->>'value' AS sector,
            COUNT(DISTINCT sa.survey_user_id) AS total_encuestas
        FROM survey_answer sa
        WHERE sa.survey_question_id IN (477, 863)   -- sector puede venir de cualquiera
          AND sa.created_at::date = CURRENT_DATE    -- solo encuestas de hoy
        GROUP BY sa.data->>'value'
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
