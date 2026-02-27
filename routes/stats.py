import json
from datetime import datetime

from flask import Blueprint, render_template

from db import fetch_all, fetch_one

stats_bp = Blueprint('stats_bp', __name__)


@stats_bp.route('/stats')
def stats():
    now = datetime.now()
    ym  = now.strftime('%Y-%m')

    cat_data = fetch_all("""
        SELECT c.name, c.color, COALESCE(SUM(t.amount),0) AS total
        FROM categories c
        LEFT JOIN transactions t
          ON t.category_id = c.id AND t.type = 'expense' AND t.date::text LIKE %s
        WHERE c.type = 'expense'
        GROUP BY c.id, c.name, c.color
        HAVING COALESCE(SUM(t.amount),0) > 0
        ORDER BY total DESC
    """, (ym + '%',))

    months = []
    for i in range(5, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        months.append(f'{y:04d}-{m:02d}')

    bar_data = []
    for ym2 in months:
        i2 = fetch_one(
            "SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='income'  AND date::text LIKE %s",
            (ym2 + '%',),
        )
        e2 = fetch_one(
            "SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='expense' AND date::text LIKE %s",
            (ym2 + '%',),
        )
        bar_data.append({'month': ym2, 'income': i2['s'] if i2 else 0, 'expense': e2['s'] if e2 else 0})

    ti = fetch_one(
        "SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='income'  AND date::text LIKE %s",
        (ym + '%',),
    )
    te = fetch_one(
        "SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='expense' AND date::text LIKE %s",
        (ym + '%',),
    )

    return render_template(
        'stats.html',
        pie_labels=json.dumps([d['name']  for d in cat_data]),
        pie_values=json.dumps([d['total'] for d in cat_data]),
        pie_colors=json.dumps([d['color'] for d in cat_data]),
        bar_labels=json.dumps([d['month']   for d in bar_data]),
        bar_income=json.dumps([d['income']  for d in bar_data]),
        bar_expense=json.dumps([d['expense'] for d in bar_data]),
        income=ti['s'] if ti else 0,
        expense=te['s'] if te else 0,
        month=now.strftime('%B %Y'),
        active_nav='stats',
    )
