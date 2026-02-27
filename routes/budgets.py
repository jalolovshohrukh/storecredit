from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for

from db import fetch_all, fetch_one, execute, gen_id

budgets_bp = Blueprint('budgets_bp', __name__)


@budgets_bp.route('/budgets')
def budgets():
    now = datetime.now()
    ym  = now.strftime('%Y-%m')
    cats = fetch_all("""
        SELECT c.*, b.amount AS budget_amount, b.id AS budget_id, b.period
        FROM categories c
        LEFT JOIN budgets b ON c.id = b.category_id
        WHERE c.type = 'expense'
        ORDER BY c.name
    """)
    for cat in cats:
        spent = fetch_one(
            "SELECT COALESCE(SUM(amount),0) AS s FROM transactions"
            " WHERE category_id=%s AND type='expense' AND date::text LIKE %s",
            (cat['id'], ym + '%'),
        )
        cat['spent'] = spent['s'] if spent else 0
        if cat['budget_amount']:
            cat['pct'] = min(int(cat['spent'] / cat['budget_amount'] * 100), 100)
            cat['cls'] = 'over' if cat['pct'] >= 100 else ('warn' if cat['pct'] >= 75 else 'ok')
        else:
            cat['pct'] = 0
            cat['cls'] = ''

    return render_template(
        'budgets.html',
        cats=cats,
        month=now.strftime('%B %Y'),
        active_nav='budgets',
    )


@budgets_bp.route('/budgets/set', methods=['POST'])
def set_budget():
    cat_id = request.form.get('category_id', '').strip()
    amt_s  = request.form.get('amount', '').strip()
    try:
        amount = float(amt_s)
        if amount <= 0:
            raise ValueError()
        existing = fetch_one("SELECT id FROM budgets WHERE category_id=%s", (cat_id,))
        if existing:
            execute("UPDATE budgets SET amount=%s WHERE category_id=%s", (amount, cat_id))
        else:
            execute("INSERT INTO budgets(id,category_id,amount) VALUES(%s,%s,%s)",
                    (gen_id(), cat_id, amount))
    except (ValueError, TypeError):
        pass
    return redirect(url_for('budgets_bp.budgets'))


@budgets_bp.route('/budgets/delete/<bid>', methods=['POST'])
def del_budget(bid):
    execute("DELETE FROM budgets WHERE id=%s", (bid,))
    return redirect(url_for('budgets_bp.budgets'))
