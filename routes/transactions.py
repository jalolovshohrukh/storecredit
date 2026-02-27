from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for

from db import fetch_all, execute, gen_id, get_conn

txns_bp = Blueprint('txns_bp', __name__)


@txns_bp.route('/transactions')
def txn_list():
    period = request.args.get('p', 'month')
    typ    = request.args.get('t', 'all')
    now    = datetime.now()
    filters, params = [], []

    if period == 'today':
        filters.append("t.date=%s");          params.append(now.strftime('%Y-%m-%d'))
    elif period == 'month':
        filters.append("t.date::text LIKE %s"); params.append(now.strftime('%Y-%m') + '%')
    elif period == 'year':
        filters.append("t.date::text LIKE %s"); params.append(str(now.year) + '%')
    if typ != 'all':
        filters.append("t.type=%s");           params.append(typ)

    where = ('WHERE ' + ' AND '.join(filters)) if filters else ''
    txns  = fetch_all(f"""
        SELECT t.*, c.name AS cat_name, c.icon AS cat_icon,
               a.name AS acct_name, a.currency
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN accounts   a ON t.account_id  = a.id
        {where} ORDER BY t.date DESC, t.id DESC
    """, tuple(params))

    return render_template(
        'transactions/list.html',
        txns=txns,
        period=period,
        typ=typ,
        active_nav='txns',
    )


@txns_bp.route('/transactions/add', methods=['GET', 'POST'])
def add_txn():
    error      = None
    accounts   = fetch_all("SELECT * FROM accounts ORDER BY name")
    categories = fetch_all("SELECT * FROM categories ORDER BY type, name")
    today      = datetime.now().strftime('%Y-%m-%d')

    if request.method == 'POST':
        typ    = request.form.get('type', 'expense')
        amt_s  = request.form.get('amount', '').strip()
        acc_id = request.form.get('account_id', '').strip()
        to_acc = request.form.get('to_account_id', '').strip() or None
        cat_id = request.form.get('category_id', '').strip() or None
        dt     = request.form.get('date', today).strip()
        note   = request.form.get('note', '').strip() or None

        if not amt_s:
            error = 'Amount is required'
        elif not acc_id:
            error = 'Select an account'
        elif typ == 'transfer' and not to_acc:
            error = 'Select a destination account for the transfer'
        else:
            try:
                amount = float(amt_s)
                if amount <= 0:
                    raise ValueError()
                conn = get_conn()
                with conn.cursor() as c:
                    c.execute(
                        "INSERT INTO transactions(id,date,amount,type,account_id,to_account_id,category_id,note)"
                        " VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                        (gen_id(), dt, amount, typ, acc_id, to_acc, cat_id, note),
                    )
                    if typ == 'expense':
                        c.execute("UPDATE accounts SET balance=balance-%s WHERE id=%s", (amount, acc_id))
                    elif typ == 'income':
                        c.execute("UPDATE accounts SET balance=balance+%s WHERE id=%s", (amount, acc_id))
                    elif typ == 'transfer':
                        c.execute("UPDATE accounts SET balance=balance-%s WHERE id=%s", (amount, acc_id))
                        c.execute("UPDATE accounts SET balance=balance+%s WHERE id=%s", (amount, to_acc))
                conn.commit()
                return redirect(url_for('txns_bp.txn_list'))
            except ValueError:
                error = 'Invalid amount'

    return render_template(
        'transactions/add.html',
        error=error,
        accounts=accounts,
        categories=categories,
        today=today,
        active_nav='txns',
    )
