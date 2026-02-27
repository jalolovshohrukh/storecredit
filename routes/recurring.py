from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for

from db import fetch_all, execute, gen_id

recurring_bp = Blueprint('recurring_bp', __name__)


@recurring_bp.route('/recurring')
def recurring():
    rules = fetch_all("""
        SELECT r.*, c.name AS cat_name, c.icon AS cat_icon, a.name AS acct_name
        FROM recurring_rules r
        LEFT JOIN categories c ON r.category_id = c.id
        LEFT JOIN accounts   a ON r.account_id  = a.id
        ORDER BY r.active DESC, r.next_date
    """)
    accounts = fetch_all("SELECT * FROM accounts ORDER BY name")
    cats     = fetch_all("SELECT * FROM categories ORDER BY type, name")
    today    = datetime.now().strftime('%Y-%m-%d')

    return render_template(
        'recurring.html',
        rules=rules,
        accounts=accounts,
        cats=cats,
        today=today,
        active_nav='home',
    )


@recurring_bp.route('/recurring/add', methods=['POST'])
def add_recurring():
    title  = request.form.get('title',     '').strip()
    typ    = request.form.get('type',      'expense')
    amt_s  = request.form.get('amount',    '').strip()
    acc_id = request.form.get('account_id','').strip()
    cat_id = request.form.get('category_id','').strip() or None
    freq   = request.form.get('frequency', 'monthly')
    nd     = request.form.get('next_date', '').strip()

    if title and amt_s and acc_id and nd:
        try:
            execute(
                "INSERT INTO recurring_rules(id,title,type,amount,account_id,category_id,frequency,next_date)"
                " VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                (gen_id(), title, typ, float(amt_s), acc_id, cat_id, freq, nd),
            )
        except (ValueError, Exception):
            pass
    return redirect(url_for('recurring_bp.recurring'))


@recurring_bp.route('/recurring/<rid>/toggle', methods=['POST'])
def toggle_recurring(rid):
    from db import fetch_one
    r = fetch_one("SELECT active FROM recurring_rules WHERE id=%s", (rid,))
    if r:
        execute("UPDATE recurring_rules SET active=%s WHERE id=%s", (not r['active'], rid))
    return redirect(url_for('recurring_bp.recurring'))


@recurring_bp.route('/recurring/<rid>/delete', methods=['POST'])
def del_recurring(rid):
    execute("DELETE FROM recurring_rules WHERE id=%s", (rid,))
    return redirect(url_for('recurring_bp.recurring'))
