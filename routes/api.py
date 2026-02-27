from datetime import datetime

from flask import Blueprint, jsonify, request

from db import fetch_all, fetch_one, execute, gen_id, get_conn

api_bp = Blueprint('api_bp', __name__, url_prefix='/api')


@api_bp.route('/accounts')
def get_accounts():
    return jsonify(fetch_all("SELECT * FROM accounts ORDER BY name"))


@api_bp.route('/categories')
def get_categories():
    return jsonify(fetch_all("SELECT * FROM categories ORDER BY type, name"))


@api_bp.route('/transactions', methods=['GET'])
def get_transactions():
    period = request.args.get('p', 'month')
    typ    = request.args.get('t', 'all')
    now    = datetime.now()
    filters, params = [], []

    if period == 'today':
        filters.append("t.date=%s");           params.append(now.strftime('%Y-%m-%d'))
    elif period == 'month':
        filters.append("t.date::text LIKE %s"); params.append(now.strftime('%Y-%m') + '%')
    elif period == 'year':
        filters.append("t.date::text LIKE %s"); params.append(str(now.year) + '%')
    if typ != 'all':
        filters.append("t.type=%s");            params.append(typ)

    where = ('WHERE ' + ' AND '.join(filters)) if filters else ''
    rows = fetch_all(f"""
        SELECT t.*, c.name AS cat_name, c.icon AS cat_icon,
               a.name AS acct_name, a.currency
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN accounts   a ON t.account_id  = a.id
        {where}
        ORDER BY t.date DESC, t.id DESC
    """, tuple(params))
    # Ensure date is a string for JSON serialisation
    for r in rows:
        if r.get('date') and not isinstance(r['date'], str):
            r['date'] = str(r['date'])
    return jsonify(rows)


@api_bp.route('/transactions', methods=['POST'])
def create_transaction():
    data   = request.get_json(force=True)
    typ    = data.get('type', 'expense')
    amt    = float(data.get('amount', 0))
    acc_id = data.get('account_id', '')
    to_acc = data.get('to_account_id') or None
    cat_id = data.get('category_id') or None
    dt     = data.get('date') or datetime.now().strftime('%Y-%m-%d')
    note   = data.get('note') or None

    if not amt or not acc_id:
        return jsonify({'ok': False, 'error': 'amount and account_id are required'}), 400

    conn = get_conn()
    with conn.cursor() as c:
        c.execute(
            "INSERT INTO transactions(id,date,amount,type,account_id,to_account_id,category_id,note)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (gen_id(), dt, amt, typ, acc_id, to_acc, cat_id, note),
        )
        if typ == 'expense':
            c.execute("UPDATE accounts SET balance=balance-%s WHERE id=%s", (amt, acc_id))
        elif typ == 'income':
            c.execute("UPDATE accounts SET balance=balance+%s WHERE id=%s", (amt, acc_id))
        elif typ == 'transfer' and to_acc:
            c.execute("UPDATE accounts SET balance=balance-%s WHERE id=%s", (amt, acc_id))
            c.execute("UPDATE accounts SET balance=balance+%s WHERE id=%s", (amt, to_acc))
    conn.commit()
    return jsonify({'ok': True})


@api_bp.route('/budgets')
def get_budgets():
    now = datetime.now()
    ym  = now.strftime('%Y-%m')
    cats = fetch_all("""
        SELECT c.id, c.name, c.icon, c.color,
               b.amount AS budget_amount, b.id AS budget_id
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
        else:
            cat['pct'] = 0
    return jsonify(cats)


@api_bp.route('/stats')
def get_stats():
    now = datetime.now()
    ym  = now.strftime('%Y-%m')

    by_cat = fetch_all("""
        SELECT c.name, c.color, COALESCE(SUM(t.amount),0) AS total
        FROM categories c
        LEFT JOIN transactions t
          ON t.category_id=c.id AND t.type='expense' AND t.date::text LIKE %s
        WHERE c.type='expense'
        GROUP BY c.id, c.name, c.color
        HAVING COALESCE(SUM(t.amount),0) > 0
        ORDER BY total DESC
    """, (ym + '%',))

    months = []
    for i in range(5, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12; y -= 1
        months.append(f'{y:04d}-{m:02d}')

    bar = []
    for ym2 in months:
        inc = fetch_one(
            "SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='income'  AND date::text LIKE %s",
            (ym2 + '%',),
        )
        exp = fetch_one(
            "SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='expense' AND date::text LIKE %s",
            (ym2 + '%',),
        )
        bar.append({'month': ym2, 'income': inc['s'] if inc else 0, 'expense': exp['s'] if exp else 0})

    return jsonify({'by_category': by_cat, 'bar': bar})
