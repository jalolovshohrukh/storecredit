from datetime import datetime

from flask import Blueprint, jsonify, request

from db import fetch_all, fetch_one, execute, gen_id, get_conn

api_bp = Blueprint('api_bp', __name__, url_prefix='/api')


@api_bp.route('/accounts')
def get_accounts():
    return jsonify(fetch_all("SELECT * FROM accounts ORDER BY name"))


@api_bp.route('/accounts', methods=['POST'])
def create_account():
    from config import COLORS
    d    = request.get_json(force=True)
    name = (d.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'name required'}), 400
    n     = fetch_one("SELECT COUNT(*) AS c FROM accounts")
    count = int(n['c']) if n else 0
    aid   = gen_id()
    execute(
        "INSERT INTO accounts(id,name,balance,currency,color,type) VALUES(%s,%s,%s,%s,%s,%s)",
        (aid, name, float(d.get('balance') or 0), d.get('currency', 'USD'),
         COLORS[count % len(COLORS)], d.get('type', 'debit')),
    )
    return jsonify({'ok': True, 'id': aid})


@api_bp.route('/accounts/<aid>', methods=['DELETE'])
def delete_account(aid):
    execute("DELETE FROM transactions WHERE account_id=%s OR to_account_id=%s", (aid, aid))
    execute("DELETE FROM accounts WHERE id=%s", (aid,))
    return jsonify({'ok': True})


@api_bp.route('/accounts/<aid>', methods=['PUT'])
def update_account(aid):
    d = request.get_json(force=True)
    fields, vals = [], []
    for col in ('name', 'balance', 'currency', 'type', 'color'):
        if col in d:
            fields.append(f"{col}=%s"); vals.append(d[col])
    if fields:
        execute(f"UPDATE accounts SET {', '.join(fields)} WHERE id=%s", (*vals, aid))
    return jsonify({'ok': True})


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
    elif len(period) == 4 and period.isdigit():          # e.g. "2025"
        filters.append("t.date::text LIKE %s"); params.append(period + '%')
    elif len(period) == 7 and period[4] == '-':          # e.g. "2025-03"
        filters.append("t.date::text LIKE %s"); params.append(period + '%')
    if typ != 'all':
        filters.append("t.type=%s");            params.append(typ)
    account_id = request.args.get('account_id')
    if account_id:
        filters.append("(t.account_id=%s OR t.to_account_id=%s)")
        params.extend([account_id, account_id])

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


@api_bp.route('/home')
def get_home():
    """Returns category cards (with totals) for the home screen grid."""
    account_id = request.args.get('account_id')
    period     = request.args.get('p', 'all')
    now        = datetime.now()

    t_filters, t_params = [], []
    if period == 'today':
        t_filters.append("t.date = %s");            t_params.append(now.strftime('%Y-%m-%d'))
    elif period == 'month':
        t_filters.append("t.date::text LIKE %s");   t_params.append(now.strftime('%Y-%m') + '%')
    elif period == 'year':
        t_filters.append("t.date::text LIKE %s");   t_params.append(str(now.year) + '%')
    elif period and period != 'all' and len(period) == 7:
        t_filters.append("t.date::text LIKE %s");   t_params.append(period + '%')
    if account_id:
        t_filters.append("t.account_id = %s");      t_params.append(account_id)

    t_where = ('AND ' + ' AND '.join(t_filters)) if t_filters else ''

    def cat_rows(typ):
        return fetch_all(f"""
            SELECT c.id, c.name, c.icon, c.color, c.type,
                   COALESCE(SUM(t.amount), 0) AS total,
                   b.amount AS budget_amount
            FROM categories c
            LEFT JOIN transactions t
              ON t.category_id = c.id AND t.type = %s {t_where}
            LEFT JOIN budgets b ON b.category_id = c.id
            WHERE c.type = %s
            GROUP BY c.id, c.name, c.icon, c.color, c.type, b.amount
            ORDER BY total DESC, c.name
        """, (typ, *t_params, typ))

    exp_cats = cat_rows('expense')
    inc_cats = cat_rows('income')
    return jsonify({
        'expense_total': sum(r['total'] for r in exp_cats),
        'income_total':  sum(r['total'] for r in inc_cats),
        'expense_cats':  exp_cats,
        'income_cats':   inc_cats,
    })


@api_bp.route('/categories', methods=['POST'])
def create_category():
    d    = request.get_json(force=True)
    name = (d.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'name required'}), 400
    cid = gen_id()
    execute(
        "INSERT INTO categories(id,name,type,icon,color) VALUES(%s,%s,%s,%s,%s)",
        (cid, name, d.get('type','expense'), d.get('icon','💰'), d.get('color','#2A3A1A')),
    )
    return jsonify({'ok': True, 'id': cid})


@api_bp.route('/categories/<cid>', methods=['DELETE'])
def delete_category(cid):
    execute("DELETE FROM transactions WHERE category_id=%s", (cid,))
    execute("DELETE FROM budgets WHERE category_id=%s", (cid,))
    execute("DELETE FROM categories WHERE id=%s", (cid,))
    return jsonify({'ok': True})


@api_bp.route('/categories/<cid>', methods=['PUT'])
def update_category(cid):
    d = request.get_json(force=True)
    fields, vals = [], []
    for col in ('name', 'icon', 'color', 'type'):
        if col in d:
            fields.append(f"{col}=%s"); vals.append(d[col])
    if fields:
        execute(f"UPDATE categories SET {', '.join(fields)} WHERE id=%s", (*vals, cid))
    return jsonify({'ok': True})


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
