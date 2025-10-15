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
    Monitoreo diario (HOY) con deduplicación por (user_id, answered_at) desde survey_surveyuser.
    Métricas: total, por usuario, por departamento (q=1), por municipio (q=2), por hora.
    """

    # CTE base: pares únicos del día por (user_id, answered_at)
    SQL_DU = """
      SELECT DISTINCT sa.user_id, su.answered_at
      FROM survey_answer sa
      JOIN survey_surveyuser su
        ON su.user_id = sa.user_id
       AND su.survey_id = sa.survey_id
      WHERE sa.survey_id = %s
        AND su.answered_at::date = CURRENT_DATE
    """

    # Total hoy (sin repetidos)
    SQL_TOTAL = f"""
      SELECT COUNT(*) AS total_encuestas
      FROM ({SQL_DU}) t
    """

    # Por usuario (username + nombre completo)
    SQL_USUARIOS = f"""
      WITH du AS ({SQL_DU})
      SELECT
        du.user_id                                               AS convencion,
        COALESCE(u.username, '—')                                AS username,
        COALESCE(NULLIF(BTRIM(u.first_name||' '||u.last_name),' '), u.username, 'Sin nombre') AS nombre_completo,
        COUNT(*)                                                 AS total
      FROM du
      LEFT JOIN auth_user u ON u.id = du.user_id
      GROUP BY du.user_id, username, nombre_completo
      ORDER BY total DESC, username;
    """

    # Departamentos (q=1)
    SQL_DEPTOS = f"""
      WITH du AS ({SQL_DU}),
      dept AS (
        SELECT DISTINCT ON (sa.user_id, su.answered_at)
          sa.user_id,
          su.answered_at,
          INITCAP(
            COALESCE(
              NULLIF(BTRIM((sa.data::jsonb)->>'departamento'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'Departamento'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'depto'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'dept'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'label'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'value'), ''),
              'Sin Dato'
            )
          ) AS departamento
        FROM survey_answer sa
        JOIN survey_surveyuser su
          ON su.user_id = sa.user_id
         AND su.survey_id = sa.survey_id
        WHERE sa.survey_id = %s
          AND su.answered_at::date = CURRENT_DATE
          AND sa.question_id = 1
        ORDER BY sa.user_id, su.answered_at, sa.id
      )
      SELECT COALESCE(d.departamento, 'Sin Dato') AS departamento,
             COUNT(*)                              AS total
      FROM du
      LEFT JOIN dept d
        ON d.user_id = du.user_id
       AND d.answered_at = du.answered_at
      GROUP BY 1
      ORDER BY total DESC, departamento;
    """

    # Municipios (q=2)
    SQL_MUNIS = f"""
      WITH du AS ({SQL_DU}),
      muni AS (
        SELECT DISTINCT ON (sa.user_id, su.answered_at)
          sa.user_id,
          su.answered_at,
          INITCAP(
            COALESCE(
              NULLIF(BTRIM((sa.data::jsonb)->>'municipio'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'Municipio'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'ciudad'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'city'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'label'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'value'), ''),
              'Sin Dato'
            )
          ) AS municipio
        FROM survey_answer sa
        JOIN survey_surveyuser su
          ON su.user_id = sa.user_id
         AND su.survey_id = sa.survey_id
        WHERE sa.survey_id = %s
          AND su.answered_at::date = CURRENT_DATE
          AND sa.question_id = 2
        ORDER BY sa.user_id, su.answered_at, sa.id
      )
      SELECT COALESCE(m.municipio, 'Sin Dato') AS municipio,
             COUNT(*)                          AS total
      FROM du
      LEFT JOIN muni m
        ON m.user_id = du.user_id
       AND m.answered_at = du.answered_at
      GROUP BY 1
      ORDER BY total DESC, municipio;
    """

    # Usuarios con su departamento más frecuente
    SQL_USUARIOS_CON_DEPTO = f"""
      WITH du AS ({SQL_DU}),
      dept AS (
        SELECT DISTINCT ON (sa.user_id, su.answered_at)
          sa.user_id,
          su.answered_at,
          INITCAP(
            COALESCE(
              NULLIF(BTRIM((sa.data::jsonb)->>'departamento'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'Departamento'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'depto'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'dept'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'label'), ''),
              NULLIF(BTRIM((sa.data::jsonb)->>'value'), ''),
              'Sin Dato'
            )
          ) AS departamento
        FROM survey_answer sa
        JOIN survey_surveyuser su
          ON su.user_id = sa.user_id
         AND su.survey_id = sa.survey_id
        WHERE sa.survey_id = %s
          AND su.answered_at::date = CURRENT_DATE
          AND sa.question_id = 1
        ORDER BY sa.user_id, su.answered_at, sa.id
      ),
      base AS (
        SELECT
          du.user_id,
          du.answered_at,
          COALESCE(d.departamento, 'Sin Dato') AS departamento
        FROM du
        LEFT JOIN dept d
          ON d.user_id = du.user_id
         AND d.answered_at = du.answered_at
      )
      SELECT
        b.user_id                                               AS convencion,
        COALESCE(u.username, '—')                               AS username,
        COALESCE(NULLIF(BTRIM(u.first_name||' '||u.last_name),' '), u.username, 'Sin nombre') AS nombre_completo,
        (
          SELECT departamento FROM (
            SELECT departamento, COUNT(*) c
            FROM base b2
            WHERE b2.user_id = b.user_id
            GROUP BY departamento
            ORDER BY c DESC, departamento
            LIMIT 1
          ) x
        )                                                       AS departamento,
        COUNT(*)                                                AS total
      FROM base b
      LEFT JOIN auth_user u ON u.id = b.user_id
      GROUP BY b.user_id, username, nombre_completo
      ORDER BY total DESC, username;
    """

    # Por hora (answered_at)
    SQL_HORAS = f"""
      WITH du AS ({SQL_DU})
      SELECT
        TO_CHAR(date_trunc('hour', du.answered_at), 'HH24:00') AS hora,
        COUNT(*)                                               AS total
      FROM du
      GROUP BY 1
      ORDER BY 1;
    """

    try:
        with connection.cursor() as cur:
            # Total: 1 placeholder
            cur.execute(SQL_TOTAL, [SURVEY_ID_TARGET])
            total = int(cur.fetchone()[0] or 0)

            # Departamentos: 2 placeholders (uno en du, uno en dept)
            cur.execute(SQL_DEPTOS, [SURVEY_ID_TARGET, SURVEY_ID_TARGET])
            deptos = [{"departamento": r[0], "total": int(r[1] or 0)} for r in cur.fetchall()]

            # Municipios: 2 placeholders
            cur.execute(SQL_MUNIS, [SURVEY_ID_TARGET, SURVEY_ID_TARGET])
            munis = [{"municipio": r[0], "total": int(r[1] or 0)} for r in cur.fetchall()]

            # Usuarios + departamento más frecuente: 2 placeholders
            cur.execute(SQL_USUARIOS_CON_DEPTO, [SURVEY_ID_TARGET, SURVEY_ID_TARGET])
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

            # Horas: 1 placeholder
            cur.execute(SQL_HORAS, [SURVEY_ID_TARGET])
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
        # Muestra el error en consola (útil en desarrollo)
        print("[monitoreo_data] ERROR:", e)
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

