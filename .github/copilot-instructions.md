# Copilot Instructions for smt-dashboard

## Project Overview
- **Framework:** Django 5.x (see `requirements.txt`)
- **Main App:** `generales` (models, views, urls)
- **Entrypoint:** `manage.py` (standard Django commands)
- **Settings:** `smt_dash/settings.py` (PostgreSQL DB, static/media config)
- **Docker:** Use `docker-compose.yml` for local dev (exposes port 8124)

## Key Patterns & Conventions
- **Database:**
  - Uses PostgreSQL (see `DATABASES` in `settings.py`).
  - Some models (`SurveyResult`) are unmanaged (Django does not create/drop these tables).
  - Data access in views often uses raw SQL with Pandas (`pd.read_sql`).
- **Views:**
  - Mix of class-based (`Home`) and function-based views.
  - Data endpoints return JSON (for dashboards, etc.).
  - Templates in `templates/generales/` and `templates/base/`.
- **Static/Media:**
  - Static files in `static/`, media in `media/` (see `settings.py`).
- **App URLs:**
  - All main routes are in `generales/urls.py` and included at root in `smt_dash/urls.py`.

## Developer Workflows
- **Run locally:**
  - `python manage.py runserver` (or use Docker: `docker-compose up`)
- **Migrations:**
  - `python manage.py makemigrations` / `migrate` (for managed models)
- **Testing:**
  - No explicit test suite found; add tests in `generales/tests.py` if needed.
- **Database access:**
  - Use Django ORM for managed models, but raw SQL is common for analytics endpoints.
- **Export:**
  - Some endpoints export Excel via Pandas (see `views.py`).

## Integration & Dependencies
- **External packages:** See `requirements.txt` (notably: pandas, geopandas, folium, openpyxl, psycopg2).
- **Docker:**
  - Service runs as user `${UID}:${GID}` (set in env or override for Windows).
  - Mounts project as `/app` in container.

## Examples
- **Add a dashboard endpoint:**
  - Add function to `generales/views.py`, route in `generales/urls.py`, template in `templates/generales/`.
- **Add a model:**
  - Define in `generales/models.py`, migrate if managed.

## Special Notes
- **Unmanaged models:** Mark with `managed = False` in `Meta` if table is not controlled by Django.
- **Raw SQL:** Use Pandas for analytics queries, but prefer ORM for CRUD if possible.
- **Static/media config:** Adjust `STATICFILES_DIRS`, `MEDIA_ROOT` in `settings.py` as needed for deployment.

---
_Keep instructions concise and up to date. Update this file if project structure or conventions change._
