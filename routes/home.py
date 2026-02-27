import os
from datetime import datetime

from flask import Blueprint, render_template, send_from_directory

from db import fetch_all, fetch_one

home_bp = Blueprint('home_bp', __name__)


@home_bp.route('/')
def home():
    accounts = fetch_all("SELECT * FROM accounts ORDER BY name")
    now = datetime.now()
    ym  = now.strftime('%Y-%m')
    inc = fetch_one(
        "SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='income' AND date::text LIKE %s",
        (ym + '%',),
    )
    exp = fetch_one(
        "SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='expense' AND date::text LIKE %s",
        (ym + '%',),
    )
    recent = fetch_all("""
        SELECT t.*, c.name AS cat_name, c.icon AS cat_icon, a.currency, a.name AS acct_name
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN accounts   a ON t.account_id  = a.id
        ORDER BY t.date DESC, t.id DESC LIMIT 5
    """)
    nw = {}
    for a in accounts:
        cur = a.get('currency', 'USD')
        nw[cur] = nw.get(cur, 0.0) + a['balance']

    return render_template(
        'home.html',
        accounts=accounts,
        recent=recent,
        nw=nw,
        income=inc['s'] if inc else 0,
        expense=exp['s'] if exp else 0,
        month=now.strftime('%B %Y'),
        active_nav='home',
    )


@home_bp.route('/ui')
def react_ui():
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
    return send_from_directory(static_dir, 'ui.html')
