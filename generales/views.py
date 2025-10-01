import json
import pandas as pd
from io import BytesIO
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views import generic
from django.db import connection


# ================
# HOME
# ================
class Home(generic.TemplateView):
    template_name = "generales/monitoreo.html"


# ================
# MONITOREO (Día actual)
# ================
def monitoreo_dashboard(request):
    return render(request, "generales/monitoreo.html")


def monitoreo_data(request):
    conn = connection

    # Total encuestas
    q_total = """
        SELECT COUNT(survey_id) AS total_encuestas
        FROM survey_surveyuser 
        WHERE created_at::date = CURRENT_DATE
    """
    df_total = pd.read_sql(q_total, conn)
    total_encuestas = int(df_total["total_encuestas"].iloc[0]) if not df_total.empty else 0

    # Viviendas
    q_viviendas = """
        SELECT COUNT(DISTINCT TRIM(data->>'value')) AS total_viviendas
        FROM survey_answer
        WHERE created_at::date = CURRENT_DATE
          AND survey_id IN (18, 30, 31)
          AND survey_question_id IN (614, 615, 616);
    """
    df_viviendas = pd.read_sql(q_viviendas, conn)
    total_viviendas = int(df_viviendas["total_viviendas"].iloc[0]) if not df_viviendas.empty else 0

    # Sectores
    q_sectores = """
        SELECT (data->>'value') AS sector, COUNT(*) AS total
        FROM survey_answer
        WHERE created_at::date = CURRENT_DATE
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
        WHERE sa.created_at::date = CURRENT_DATE
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
        "convenciones": censistas  # mismo array para tabla
    })


# ================
# CONSOLIDADO (General y del día)
# ================
def dashboard_consolidado(request):
    return render(request, "generales/consolidado.html")


def dashboard_consolidado_data(request):
    conn = connection
    q = """
        SELECT sa.id, sa.survey_id, sa.survey_user_id, sa.user_id,
               sa.survey_question_id, sa.data, sa.created_at
        FROM survey_answer sa
        WHERE sa.survey_id IN (18, 30, 31);
    """
    df = pd.read_sql(q, conn)

    if not df.empty:
        df_json = pd.json_normalize(df["data"].apply(json.loads))
        df = pd.concat([df.drop(columns=["data"]), df_json], axis=1)

    data_preview = df.head(50).to_dict(orient="records")

    return JsonResponse({
        "total_registros": len(df),
        "preview": data_preview,
        "columnas": list(df.columns)
    })


def exportar_consolidado_excel(request):
    """Exporta todas las encuestas"""
    conn = connection
    q = """
        SELECT sa.id, sa.survey_id, sa.survey_user_id, sa.user_id,
               sa.survey_question_id, sa.data, sa.created_at
        FROM survey_answer sa
        WHERE sa.survey_id IN (18, 30, 31);
    """
    df = pd.read_sql(q, conn)

    if not df.empty:
        df_json = pd.json_normalize(df["data"].apply(json.loads))
        df = pd.concat([df.drop(columns=["data"]), df_json], axis=1)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Consolidado")
    buffer.seek(0)

    response = HttpResponse(
        buffer,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="consolidado_encuestas.xlsx"'
    return response


def exportar_consolidado_excel_dia(request):
    """Exporta solo las encuestas del día actual"""
    conn = connection
    q = """
        SELECT sa.id, sa.survey_id, sa.survey_user_id, sa.user_id,
               sa.survey_question_id, sa.data, sa.created_at
        FROM survey_answer sa
        WHERE sa.survey_id IN (18, 30, 31)
          AND sa.created_at::date = CURRENT_DATE;
    """
    df = pd.read_sql(q, conn)

    if not df.empty:
        df_json = pd.json_normalize(df["data"].apply(json.loads))
        df = pd.concat([df.drop(columns=["data"]), df_json], axis=1)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Consolidado_Dia")
    buffer.seek(0)

    response = HttpResponse(
        buffer,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="consolidado_encuestas_dia.xlsx"'
    return response

from django.db import connection
from django.shortcuts import render
from django.http import JsonResponse
import pandas as pd

def reporte_censistas(request):
    """Renderiza el template con el formulario del rango de fechas"""
    return render(request, "generales/reporte_censistas.html")


def reporte_censistas_data(request):
    """Devuelve JSON con encuestas por censista en el rango de fechas"""
    fecha_inicio = request.GET.get("inicio")
    fecha_fin = request.GET.get("fin")

    if not fecha_inicio or not fecha_fin:
        return JsonResponse({"error": "Debe indicar inicio y fin"}, status=400)

    conn = connection
    q = """
        SELECT sa.user_id AS censista_id,
               CONCAT(COALESCE(u.first_name,''),' ',COALESCE(u.last_name,'')) AS nombre_completo,
               COUNT(DISTINCT sa.survey_user_id) AS total_encuestas
        FROM survey_answer sa
        JOIN auth_user u ON u.id = sa.user_id
        WHERE sa.created_at::date 
              BETWEEN %s AND %s
          AND sa.survey_id IN (18, 30, 31)
        GROUP BY sa.user_id, u.first_name, u.last_name
        ORDER BY total_encuestas DESC;
    """
    df = pd.read_sql(q, conn, params=[fecha_inicio, fecha_fin])
    datos = df.to_dict(orient="records")

    return JsonResponse({"resultados": datos})


from django.http import JsonResponse
from django.db import connection
import pandas as pd

# ====== Constantes de negocio ======
SURVEY_IDS = (18, 30, 31)
COORD_QID = 535                 # lat/lon en data -> value -> latitude/longitude
VIVIENDA_QIDS = (614, 615, 616) # preguntas "vivienda"
SECTOR_QIDS = (477, 863)        # preguntas "sector"

def _scope_sql(alias: str, scope: str) -> str:
    """
    Filtro temporal opcional.
    scope='today' -> limita a hoy (fecha local ya insertada en DB).
    scope='all'   -> sin filtro.
    """
    if scope == "today":
        return f" AND ({alias}.created_at)::date = CURRENT_DATE "
    return ""

def monitoreo_data(request):
    conn = connection

    # Total encuestas (contando survey_user_id distintos)
    q_total = f"""
        SELECT COUNT(DISTINCT survey_user_id) AS total_encuestas
        FROM survey_answer
        WHERE survey_id IN {SURVEY_IDS};
    """
    df_total = pd.read_sql(q_total, conn)
    total_encuestas = int(df_total["total_encuestas"].iloc[0]) if not df_total.empty else 0

    # Viviendas únicas
    q_viviendas = f"""
        SELECT COUNT(DISTINCT TRIM(data->>'value')) AS total_viviendas
        FROM survey_answer
        WHERE survey_id IN {SURVEY_IDS}
          AND survey_question_id IN {VIVIENDA_QIDS};
    """
    df_viviendas = pd.read_sql(q_viviendas, conn)
    total_viviendas = int(df_viviendas["total_viviendas"].iloc[0]) if not df_viviendas.empty else 0

    # Sectores
    q_sectores = f"""
        SELECT (data->>'value') AS sector, COUNT(*) AS total
        FROM survey_answer
        WHERE survey_id IN {SURVEY_IDS}
          AND survey_question_id IN {SECTOR_QIDS}
        GROUP BY data->>'value';
    """
    df_sectores = pd.read_sql(q_sectores, conn)
    sectores = df_sectores.to_dict(orient="records")

    # Censistas
    q_censistas = f"""
        SELECT sa.user_id AS convencion,
               CONCAT(COALESCE(u.first_name,''),' ',COALESCE(u.last_name,'')) AS nombre_completo,
               COUNT(DISTINCT sa.survey_user_id) AS total_encuestas
        FROM survey_answer sa
        JOIN auth_user u ON u.id = sa.user_id
        WHERE sa.survey_id IN {SURVEY_IDS}
        GROUP BY sa.user_id, u.first_name, u.last_name
        ORDER BY total_encuestas DESC;
    """
    df_censistas = pd.read_sql(q_censistas, conn)
    censistas = df_censistas.to_dict(orient="records")

    # GEO: Encuestas con coordenadas
    q_geo = f"""
        SELECT sa.survey_user_id, sa.user_id,
               (c.data->'value'->>'latitude')::float AS lat,
               (c.data->'value'->>'longitude')::float AS lng
        FROM survey_answer c
        JOIN survey_answer sa ON sa.survey_user_id = c.survey_user_id
        WHERE c.survey_id IN {SURVEY_IDS}
          AND c.survey_question_id = {COORD_QID}
          AND (c.data->'value'->>'latitude') IS NOT NULL
          AND (c.data->'value'->>'longitude') IS NOT NULL;
    """
    df_geo = pd.read_sql(q_geo, conn)
    geo = df_geo.to_dict(orient="records")

    # GEO: Viviendas
    q_viv_geo = f"""
        SELECT v.data->>'value' AS vivienda,
               (c.data->'value'->>'latitude')::float AS lat,
               (c.data->'value'->>'longitude')::float AS lng
        FROM survey_answer v
        JOIN survey_answer c
          ON c.survey_user_id = v.survey_user_id
         AND c.survey_id = v.survey_id
         AND c.survey_question_id = {COORD_QID}
        WHERE v.survey_id IN {SURVEY_IDS}
          AND v.survey_question_id IN {VIVIENDA_QIDS}
          AND (c.data->'value'->>'latitude') IS NOT NULL
          AND (c.data->'value'->>'longitude') IS NOT NULL;
    """
    df_viv_geo = pd.read_sql(q_viv_geo, conn)
    viviendas_geo = df_viv_geo.to_dict(orient="records")

    # GEO: Sectores -> puntos
    q_sector_points = f"""
        SELECT s.data->>'value' AS sector,
               (c.data->'value'->>'latitude')::float AS lat,
               (c.data->'value'->>'longitude')::float AS lng
        FROM survey_answer s
        JOIN survey_answer c
          ON c.survey_user_id = s.survey_user_id
         AND c.survey_id = s.survey_id
         AND c.survey_question_id = {COORD_QID}
        WHERE s.survey_id IN {SURVEY_IDS}
          AND s.survey_question_id IN {SECTOR_QIDS}
          AND TRIM(s.data->>'value') <> ''
          AND (c.data->'value'->>'latitude') IS NOT NULL
          AND (c.data->'value'->>'longitude') IS NOT NULL;
    """
    df_sector_points = pd.read_sql(q_sector_points, conn)
    sectores_geo = df_sector_points.to_dict(orient="records")

    return JsonResponse({
        "kpis": {
            "total_encuestas": total_encuestas,
            "total_viviendas": total_viviendas,
            "total_sectores": len(sectores)
        },
        "censistas": censistas,
        "sectores": sectores,
        "convenciones": censistas,
        "geo": geo,
        "viviendas_geo": viviendas_geo,
        "sectores_geo": sectores_geo
    })

