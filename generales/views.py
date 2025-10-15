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
    Monitoreo diario (HOY) con deduplicación por (user_id, answered_at) usando survey_surveyuser.
    Métricas: total, por usuario, por departamento (q=1), por municipio (q=2), por hora.
    """

    # Pares únicos del día por (user_id, answered_at), con la instancia exacta (survey_user_id)
    SQL_DU = """
      SELECT DISTINCT ON (su.user_id, su.answered_at)
             su.id         AS survey_user_id,
             su.user_id    AS user_id,
             su.answered_at
      FROM survey_surveyuser su
      WHERE su.survey_id = %s
        AND su.answered_at::date = CURRENT_DATE
      ORDER BY su.user_id, su.answered_at, su.id
    """

    # Total hoy (sin repetidos)
    SQL_TOTAL = f"""
      SELECT COUNT(*) AS total_encuestas
      FROM ({SQL_DU}) du
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

    # Departamento por envío (q=1), luego agregamos
    SQL_DEPTOS = f"""
      WITH du AS ({SQL_DU}),
      dept AS (
        SELECT DISTINCT ON (sa.survey_user_id)
               sa.survey_user_id,
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
        JOIN du ON du.survey_user_id = sa.survey_user_id
        WHERE sa.question_id = 1
        ORDER BY sa.survey_user_id, sa.id
      )
      SELECT COALESCE(d.departamento, 'Sin Dato') AS departamento,
             COUNT(*)                              AS total
      FROM du
      LEFT JOIN dept d ON d.survey_user_id = du.survey_user_id
      GROUP BY 1
      ORDER BY total DESC, departamento;
    """

    # Municipio por envío (q=2), luego agregamos
    SQL_MUNIS = f"""
      WITH du AS ({SQL_DU}),
      muni AS (
        SELECT DISTINCT ON (sa.survey_user_id)
               sa.survey_user_id,
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
        JOIN du ON du.survey_user_id = sa.survey_user_id
        WHERE sa.question_id = 2
        ORDER BY sa.survey_user_id, sa.id
      )
      SELECT COALESCE(m.municipio, 'Sin Dato') AS municipio,
             COUNT(*)                          AS total
      FROM du
      LEFT JOIN muni m ON m.survey_user_id = du.survey_user_id
      GROUP BY 1
      ORDER BY total DESC, municipio;
    """

    # Usuarios con su departamento más frecuente (usando el depto por envío, ligado por survey_user_id)
    SQL_USUARIOS_CON_DEPTO = f"""
      WITH du AS ({SQL_DU}),
      dept AS (
        SELECT DISTINCT ON (sa.survey_user_id)
               sa.survey_user_id,
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
        JOIN du ON du.survey_user_id = sa.survey_user_id
        WHERE sa.question_id = 1
        ORDER BY sa.survey_user_id, sa.id
      ),
      base AS (
        SELECT
          du.user_id,
          du.answered_at,
          COALESCE(d.departamento, 'Sin Dato') AS departamento
        FROM du
        LEFT JOIN dept d ON d.survey_user_id = du.survey_user_id
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

    # Por hora (desde answered_at)
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
            # Total
            cur.execute(SQL_TOTAL, [SURVEY_ID_TARGET])
            total = int(cur.fetchone()[0] or 0)

            # Departamentos
            cur.execute(SQL_DEPTOS, [SURVEY_ID_TARGET])
            deptos = [{"departamento": r[0], "total": int(r[1] or 0)} for r in cur.fetchall()]

            # Municipios
            cur.execute(SQL_MUNIS, [SURVEY_ID_TARGET])
            munis = [{"municipio": r[0], "total": int(r[1] or 0)} for r in cur.fetchall()]

            # Usuarios + departamento más frecuente (CORREGIDO por survey_user_id)
            cur.execute(SQL_USUARIOS_CON_DEPTO, [SURVEY_ID_TARGET])
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

            # Horas
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
        print("[monitoreo_data] ERROR:", e)
        return JsonResponse({"error": str(e)}, status=500)

# ================
# CONSOLIDADO (General y del día)
# ================
def dashboard_consolidado(request):
    return render(request, "generales/consolidado.html")

def dashboard_consolidado_data(request):
    """
    Consolidado histórico (SIN FILTRAR POR FECHA) para survey_id = SURVEY_ID_TARGET.
    - Deduplicación por (user_id, answered_at) a partir de survey_surveyuser
    - Métricas: total, por usuario, por departamento (q=1), por municipio (q=2), por hora
    - Departamento/Municipio se unen por survey_user_id (instancia exacta del envío)
    """

    # Instancias únicas por (user_id, answered_at) EN TODO EL HISTÓRICO
    SQL_DU_ALL = """
      SELECT DISTINCT ON (su.user_id, su.answered_at)
             su.id         AS survey_user_id,
             su.user_id    AS user_id,
             su.answered_at
      FROM survey_surveyuser su
      WHERE su.survey_id = %s
      ORDER BY su.user_id, su.answered_at, su.id
    """

    # Total histórico (sin repetidos)
    SQL_TOTAL = f"""
      SELECT COUNT(*) AS total_encuestas
      FROM ({SQL_DU_ALL}) du
    """

    # Por usuario (username + nombre completo)
    SQL_USUARIOS = f"""
      WITH du AS ({SQL_DU_ALL})
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

    # Departamentos (q=1) por envío → agregados
    SQL_DEPTOS = f"""
      WITH du AS ({SQL_DU_ALL}),
      dept AS (
        SELECT DISTINCT ON (sa.survey_user_id)
               sa.survey_user_id,
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
        JOIN du ON du.survey_user_id = sa.survey_user_id
        WHERE sa.question_id = 1
        ORDER BY sa.survey_user_id, sa.id
      )
      SELECT COALESCE(d.departamento, 'Sin Dato') AS departamento,
             COUNT(*)                              AS total
      FROM du
      LEFT JOIN dept d ON d.survey_user_id = du.survey_user_id
      GROUP BY 1
      ORDER BY total DESC, departamento;
    """

    # Municipios (q=2) por envío → agregados
    SQL_MUNIS = f"""
      WITH du AS ({SQL_DU_ALL}),
      muni AS (
        SELECT DISTINCT ON (sa.survey_user_id)
               sa.survey_user_id,
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
        JOIN du ON du.survey_user_id = sa.survey_user_id
        WHERE sa.question_id = 2
        ORDER BY sa.survey_user_id, sa.id
      )
      SELECT COALESCE(m.municipio, 'Sin Dato') AS municipio,
             COUNT(*)                          AS total
      FROM du
      LEFT JOIN muni m ON m.survey_user_id = du.survey_user_id
      GROUP BY 1
      ORDER BY total DESC, municipio;
    """

    # Por usuario con su departamento más frecuente (de sus envíos)
    SQL_USUARIOS_CON_DEPTO = f"""
      WITH du AS ({SQL_DU_ALL}),
      dept AS (
        SELECT DISTINCT ON (sa.survey_user_id)
               sa.survey_user_id,
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
        JOIN du ON du.survey_user_id = sa.survey_user_id
        WHERE sa.question_id = 1
        ORDER BY sa.survey_user_id, sa.id
      ),
      base AS (
        SELECT
          du.user_id,
          du.answered_at,
          COALESCE(d.departamento, 'Sin Dato') AS departamento
        FROM du
        LEFT JOIN dept d ON d.survey_user_id = du.survey_user_id
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

    # Serie por hora (histórico) usando answered_at
    SQL_HORAS = f"""
      WITH du AS ({SQL_DU_ALL})
      SELECT
        TO_CHAR(date_trunc('hour', du.answered_at), 'YYYY-MM-DD HH24:00') AS hora,
        COUNT(*)                                                          AS total
      FROM du
      GROUP BY 1
      ORDER BY 1;
    """

    try:
        with connection.cursor() as cur:
            cur.execute(SQL_TOTAL, [SURVEY_ID_TARGET])
            total = int(cur.fetchone()[0] or 0)

            cur.execute(SQL_DEPTOS, [SURVEY_ID_TARGET])
            deptos = [{"departamento": r[0], "total": int(r[1] or 0)} for r in cur.fetchall()]

            cur.execute(SQL_MUNIS, [SURVEY_ID_TARGET])
            munis = [{"municipio": r[0], "total": int(r[1] or 0)} for r in cur.fetchall()]

            cur.execute(SQL_USUARIOS_CON_DEPTO, [SURVEY_ID_TARGET])
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
        print("[monitoreo_consolidado_data] ERROR:", e)
        return JsonResponse({"error": str(e)}, status=500)

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

