import traceback

from flask import Flask

from config import DATABASE_URL
from db import fmt, ensure_tables, init_app as db_init
from models.recurring import run_recurring
from routes import register_blueprints

app = Flask(__name__, template_folder='templates', static_folder='static')

# ── Register DB teardown ─────────────────────────────────────────────────────
db_init(app)

# ── Expose fmt() as a Jinja2 global (available in every template) ────────────
app.jinja_env.globals['fmt'] = fmt

# ── Register all blueprints ──────────────────────────────────────────────────
register_blueprints(app)


# ── Before-request: guard + schema init ─────────────────────────────────────
@app.before_request
def setup():
    if not DATABASE_URL:
        return (
            '<div style="font-family:sans-serif;padding:2rem;max-width:480px;margin:auto">'
            '<h2>Database not configured</h2>'
            '<p>Set the <code>DATABASE_URL</code> environment variable, then redeploy.</p>'
            '</div>'
        ), 503
    try:
        ensure_tables()
        run_recurring()
    except Exception:
        pass


# ── Error handler ─────────────────────────────────────────────────────────────
@app.errorhandler(Exception)
def handle_err(e):
    tb = traceback.format_exc()
    return (
        '<div style="font-family:monospace;padding:2rem;max-width:700px;margin:auto">'
        f'<h2 style="color:#c62828">Error</h2>'
        f'<pre style="background:#fafafa;padding:1rem;border-radius:8px;overflow:auto;font-size:13px">{tb}</pre>'
        '</div>'
    ), 500
