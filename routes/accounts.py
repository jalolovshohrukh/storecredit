from flask import Blueprint, render_template, request, redirect, url_for

from config import COLORS, CURRENCIES
from db import fetch_one, execute, gen_id

accounts_bp = Blueprint('accounts_bp', __name__)


@accounts_bp.route('/accounts/add', methods=['GET', 'POST'])
def add_account():
    error = None
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        bal  = request.form.get('balance', '0').strip()
        cur  = request.form.get('currency', 'USD').strip()
        if not name:
            error = 'Account name is required'
        else:
            try:
                balance = float(bal) if bal else 0.0
                n       = fetch_one("SELECT COUNT(*) AS c FROM accounts")
                count   = int(n['c']) if n else 0
                execute(
                    "INSERT INTO accounts(id,name,balance,currency,color) VALUES(%s,%s,%s,%s,%s)",
                    (gen_id(), name, round(balance, 2), cur, COLORS[count % len(COLORS)]),
                )
                return redirect(url_for('home_bp.home'))
            except ValueError:
                error = 'Invalid balance amount'

    return render_template(
        'accounts/add.html',
        error=error,
        currencies=CURRENCIES,
        active_nav='home',
    )
