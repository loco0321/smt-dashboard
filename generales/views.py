import json
import pandas as pd
from io import BytesIO
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views import generic
from django.db import connection
from django.utils import timezone
from datetime import timedelta
from zoneinfo import ZoneInfo
from django.conf import settings



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


SURVEY_ID_TARGET = 9  # <- filtra la encuesta solicitada

def monitoreo_data(request):
    """
    Dashboard diario agrupando por (user_id, fecha y hora):
      - Se toma UNA sola observación por cada (user_id, date_trunc('hour', first_created_at)) del día
      - Nombres desde auth_user (username + nombre completo)
      - Departamento/Municipio robustos desde JSON (q1 y q2)
    """

    SQL_BASE = """
    WITH answers AS (
      SELECT a.*
      FROM survey_answer a
      WHERE a.survey_id = %s
        AND a.created_at::date = CURRENT_DATE
    ),
    -- Resumen por formulario (misma que ya tenías)
    forms AS (
      SELECT
        CASE
          WHEN sa.survey_user_form_id IS NOT NULL THEN 'F:' || sa.survey_user_form_id::text
          WHEN sa.survey_user_id      IS NOT NULL THEN 'SU:'|| sa.survey_user_id::text
          ELSE 'A:'|| sa.id::text
        END                              AS form_key,
        MIN(sa.created_at)               AS first_created_at,
        MAX(sa.user_id)                  AS user_id,
        MAX(COALESCE(NULLIF(BTRIM(u.username),''),'—')) AS username,
        MAX(
          COALESCE(
            NULLIF(BTRIM(u.first_name||' '||u.last_name),' '),
            NULLIF(BTRIM(u.username),''),
            'Sin nombre'
          )
        )                                AS nombre_completo
      FROM answers sa
      LEFT JOIN auth_user u ON u.id = sa.user_id
      GROUP BY 1
    ),
    -- ====== DEDUP estricta por (user_id, FECHA, HORA) ======
    -- Colapsa múltiples reintentos del mismo usuario en la misma hora del día.
    grouped AS (
      SELECT
        f.user_id,
        f.username,
        f.nombre_completo,
        -- guardamos el primer timestamp real del bloque (útil para la serie por hora)
        MIN(f.first_created_at) AS first_created_at,
        -- elegimos un form_key representativo del bloque
        MIN(f.form_key)         AS form_key
      FROM forms f
      -- aunque ya filtramos por CURRENT_DATE arriba, dejamos la fecha explícita para claridad
      GROUP BY
        f.user_id,
        f.username,
        f.nombre_completo,
        date_trunc('hour', f.first_created_at)
    )
    """

    # ================== MÉTRICAS SOBRE "grouped" ==================

    SQL_TOTAL = SQL_BASE + """
      SELECT COUNT(*) FROM grouped;
    """

    SQL_POR_DEPTO = SQL_BASE + """
      , dept AS (
        SELECT
          CASE
            WHEN a.survey_user_form_id IS NOT NULL THEN 'F:'||a.survey_user_form_id::text
            WHEN a.survey_user_id      IS NOT NULL THEN 'SU:'||a.survey_user_id::text
            ELSE 'A:'||a.id::text
          END AS form_key,
          INITCAP(
            COALESCE(
              NULLIF(BTRIM((a.data::jsonb)->>'departamento'), ''),
              NULLIF(BTRIM((a.data::jsonb)->>'Departamento'), ''),
              NULLIF(BTRIM((a.data::jsonb)->>'depto'), ''),
              NULLIF(BTRIM((a.data::jsonb)->>'dept'), ''),
              NULLIF(BTRIM((a.data::jsonb)->>'label'), ''),
              (SELECT NULLIF(BTRIM(e->>'label'), '')
                 FROM jsonb_path_query(a.data::jsonb, '$.value[*]') AS elem(e)
                WHERE jsonb_typeof(a.data::jsonb->'value')='array' LIMIT 1),
              (SELECT NULLIF(BTRIM(e->>'value'), '')
                 FROM jsonb_path_query(a.data::jsonb, '$.value[*]') AS elem(e)
                WHERE jsonb_typeof(a.data::jsonb->'value')='array' LIMIT 1),
              NULLIF(BTRIM((a.data::jsonb)->>'value'), ''),
              'Sin dato'
            )
          ) AS departamento
        FROM answers a
        WHERE a.question_id = 1
      )
      SELECT COALESCE(d.departamento,'Sin Dato') AS departamento,
             COUNT(*) AS total
      FROM grouped g
      LEFT JOIN dept d USING(form_key)
      GROUP BY 1
      ORDER BY total DESC, departamento;
    """

    SQL_POR_MUNI = SQL_BASE + """
      , muni AS (
        SELECT
          CASE
            WHEN a.survey_user_form_id IS NOT NULL THEN 'F:'||a.survey_user_form_id::text
            WHEN a.survey_user_id      IS NOT NULL THEN 'SU:'||a.survey_user_id::text
            ELSE 'A:'||a.id::text
          END AS form_key,
          INITCAP(
            COALESCE(
              NULLIF(BTRIM((a.data::jsonb)->>'municipio'), ''),
              NULLIF(BTRIM((a.data::jsonb)->>'Municipio'), ''),
              NULLIF(BTRIM((a.data::jsonb)->>'ciudad'), ''),
              NULLIF(BTRIM((a.data::jsonb)->>'city'), ''),
              NULLIF(BTRIM((a.data::jsonb)->>'label'), ''),
              (SELECT NULLIF(BTRIM(e->>'label'), '')
                 FROM jsonb_path_query(a.data::jsonb, '$.value[*]') AS elem(e)
                WHERE jsonb_typeof(a.data::jsonb->'value')='array' LIMIT 1),
              (SELECT NULLIF(BTRIM(e->>'value'), '')
                 FROM jsonb_path_query(a.data::jsonb, '$.value[*]') AS elem(e)
                WHERE jsonb_typeof(a.data::jsonb->'value')='array' LIMIT 1),
              NULLIF(BTRIM((a.data::jsonb)->>'value'), ''),
              'Sin dato'
            )
          ) AS municipio
        FROM answers a
        WHERE a.question_id = 2
      )
      SELECT COALESCE(m.municipio,'Sin Dato') AS municipio,
             COUNT(*) AS total
      FROM grouped g
      LEFT JOIN muni m USING(form_key)
      GROUP BY 1
      ORDER BY total DESC, municipio;
    """

    SQL_POR_USUARIO = SQL_BASE + """
      , dept AS (
        SELECT
          CASE
            WHEN a.survey_user_form_id IS NOT NULL THEN 'F:'||a.survey_user_form_id::text
            WHEN a.survey_user_id      IS NOT NULL THEN 'SU:'||a.survey_user_id::text
            ELSE 'A:'||a.id::text
          END AS form_key,
          INITCAP(
            COALESCE(
              NULLIF(BTRIM((a.data::jsonb)->>'departamento'), ''),
              NULLIF(BTRIM((a.data::jsonb)->>'Departamento'), ''),
              NULLIF(BTRIM((a.data::jsonb)->>'depto'), ''),
              NULLIF(BTRIM((a.data::jsonb)->>'dept'), ''),
              NULLIF(BTRIM((a.data::jsonb)->>'label'), ''),
              (SELECT NULLIF(BTRIM(e->>'label'), '')
                 FROM jsonb_path_query(a.data::jsonb, '$.value[*]') AS elem(e)
                WHERE jsonb_typeof(a.data::jsonb->'value')='array' LIMIT 1),
              (SELECT NULLIF(BTRIM(e->>'value'), '')
                 FROM jsonb_path_query(a.data::jsonb, '$.value[*]') AS elem(e)
                WHERE jsonb_typeof(a.data::jsonb->'value')='array' LIMIT 1),
              NULLIF(BTRIM((a.data::jsonb)->>'value'), ''),
              'Sin dato'
            )
          ) AS departamento
        FROM answers a
        WHERE a.question_id = 1
      ),
      user_rows AS (
        SELECT
          g.user_id, g.username, g.nombre_completo, g.form_key,
          COALESCE(d.departamento,'Sin Dato') AS departamento
        FROM grouped g
        LEFT JOIN dept d USING(form_key)
      )
      SELECT
        ur.user_id                       AS convencion,
        MAX(ur.username)                 AS username,
        MAX(ur.nombre_completo)          AS nombre_completo,
        (
          SELECT departamento FROM (
            SELECT departamento, COUNT(*) c
            FROM user_rows ur2
            WHERE ur2.user_id = ur.user_id
            GROUP BY departamento
            ORDER BY c DESC, departamento
            LIMIT 1
          ) x
        ) AS departamento,
        COUNT(*) AS total
      FROM user_rows ur
      GROUP BY ur.user_id
      ORDER BY total DESC, username;
    """

    SQL_POR_HORA = SQL_BASE + """
      SELECT
        TO_CHAR(date_trunc('hour', first_created_at), 'HH24:00') AS hora,
        COUNT(*) AS total
      FROM grouped
      GROUP BY 1
      ORDER BY 1;
    """

    try:
        with connection.cursor() as cur:
            cur.execute(SQL_TOTAL, [SURVEY_ID_TARGET])
            total = int(cur.fetchone()[0] or 0)

            cur.execute(SQL_POR_DEPTO, [SURVEY_ID_TARGET])
            deptos = [{"departamento": r[0], "total": int(r[1] or 0)} for r in cur.fetchall()]

            cur.execute(SQL_POR_MUNI, [SURVEY_ID_TARGET])
            munis = [{"municipio": r[0], "total": int(r[1] or 0)} for r in cur.fetchall()]

            cur.execute(SQL_POR_USUARIO, [SURVEY_ID_TARGET])
            usuarios = [
                {
                    "convencion": r[0],
                    "username": r[1] or "—",
                    "nombre_completo": r[2] or "",
                    "departamento": r[3] or "Sin Dato",
                    "total": int(r[4] or 0),
                }
                for r in cur.fetchall()
            ]

            cur.execute(SQL_POR_HORA, [SURVEY_ID_TARGET])
            horas = [{"hora": r[0], "total": int(r[1] or 0)} for r in cur.fetchall()]

        data = {
            "kpis": {
                "total_encuestas": total,
                "total_departamentos": len(deptos),
                "total_municipios": len(munis),
                "total_usuarios": len(usuarios),
            },
            "departamentos": deptos,
            "municipios": munis,
            "usuarios": usuarios,
            "horas": horas,
        }
        return JsonResponse(data, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# ================
# CONSOLIDADO (General y del día)
# ================
def dashboard_consolidado(request):
    return render(request, "generales/consolidado.html")

def dashboard_consolidado_data(request):
    conn = connection

    # === Total encuestas (sin filtro de fecha) ===
    q_total = """
        SELECT COUNT(DISTINCT survey_user_id) AS total_encuestas
        FROM survey_answer
        WHERE survey_id IN %s;
    """
    df_total = pd.read_sql(q_total, conn, params=(SURVEY_IDS,))
    total_encuestas = int(df_total["total_encuestas"].iloc[0]) if not df_total.empty else 0

    # === departamentos ===
    q_departamentos = """
        SELECT COUNT(DISTINCT TRIM(data->>'value')) AS total_departamentos
        FROM survey_answer
        WHERE survey_id IN %s
          AND survey_question_id IN (614, 615, 616);
    """
    df_departamentos = pd.read_sql(q_departamentos, conn, params=(SURVEY_IDS,))
    total_departamentos = int(df_departamentos["total_departamentos"].iloc[0]) if not df_departamentos.empty else 0

    # === Sectores ===
    q_sectores = """
        SELECT (data->>'value') AS sector, COUNT(*) AS total
        FROM survey_answer
        WHERE survey_id IN (18, 30, 31)
        AND survey_question_id IN (477, 863)
        GROUP BY data->>'value';
    """
    df_sectores = pd.read_sql(q_sectores, conn)
    sectores = df_sectores.to_dict(orient="records")

    # === Censistas ===
    q_censistas = """
        SELECT sa.user_id,
        CONCAT(COALESCE(u.first_name,''),' ',COALESCE(u.last_name,'')) AS nombre_completo,
        COUNT(DISTINCT sa.survey_user_id) AS total_encuestas
        FROM survey_answer sa
        JOIN auth_user u ON u.id = sa.user_id
        WHERE sa.survey_id IN %s
        GROUP BY sa.user_id, u.first_name, u.last_name
        ORDER BY total_encuestas DESC;
    """
    df_censistas = pd.read_sql(q_censistas, conn, params=(SURVEY_IDS,))
    censistas = df_censistas.to_dict(orient="records")

    return JsonResponse({
        "kpis": {
            "total_encuestas": total_encuestas,
            "total_departamentos": total_departamentos,
            "total_sectores": len(sectores)
        },
        "censistas": censistas,
        "sectores": sectores,
        "convenciones": censistas
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

