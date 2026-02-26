from flask import Flask, request, render_template_string, redirect, url_for
from markupsafe import Markup
from datetime import datetime
from pymongo import MongoClient
import uuid
import os

app = Flask(__name__)

# ── MongoDB setup ─────────────────────────────────────────────────────────────
_client = MongoClient(os.environ['MONGODB_URI'])
db = _client.get_default_database()

COLORS = ['#6C63FF', '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#F7B731', '#A29BFE', '#FD79A8']

# ── Helpers ───────────────────────────────────────────────────────────────────
def gen_id():
    return str(uuid.uuid4())[:8]

def norm(doc):
    """Rename MongoDB _id → id so templates don't change."""
    if doc and '_id' in doc:
        doc['id'] = str(doc.pop('_id'))
    return doc

def norm_all(cursor):
    return [norm(d) for d in cursor]

def get_account(aid):
    return norm(db.accounts.find_one({'_id': aid}))

def get_loan(lid):
    return norm(db.loans.find_one({'_id': lid}))

def net_worth():
    result = list(db.accounts.aggregate([
        {'$group': {'_id': None, 'total': {'$sum': '$balance'}}}
    ]))
    return result[0]['total'] if result else 0.0

def add_txn(date, amount, txn_type, account_id, desc, loan_id=None):
    db.transactions.insert_one({
        '_id': gen_id(),
        'date': date, 'amount': amount, 'type': txn_type,
        'account_id': account_id, 'description': desc, 'loan_id': loan_id,
    })

def filter_txns(period):
    now = datetime.now()
    query = {}
    if period == 'today':
        query['date'] = now.strftime('%Y-%m-%d')
    elif period == 'month':
        query['date'] = {'$regex': f'^{now.strftime("%Y-%m")}'}
    elif period == 'year':
        query['date'] = {'$regex': f'^{str(now.year)}'}
    elif period == 'last_year':
        query['date'] = {'$regex': f'^{str(now.year - 1)}'}
    return norm_all(db.transactions.find(query).sort('date', -1))

def _nav(active):
    pages = [
        ('/', 'home',
         'M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z',
         'Home'),
        ('/loans', 'loans',
         'M20 4H4c-1.11 0-2 .89-2 2v12c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V6c0-1.11-.89-2-2-2zm0 14H4v-6h16v6zm0-10H4V6h16v2z',
         'Loans'),
        ('/transactions', 'txns',
         'M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z',
         'Txns'),
    ]
    html = '<nav class="bottom-nav">'
    for href, name, path, label in pages:
        cls = 'nav-item active' if active == name else 'nav-item'
        html += (
            f'<a href="{href}" class="{cls}">'
            f'<svg viewBox="0 0 24 24" fill="currentColor"><path d="{path}"/></svg>'
            f'{label}</a>'
        )
    html += '</nav>'
    return html

# ── Shared CSS ────────────────────────────────────────────────────────────────
CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f0f2f5; color: #1a1a2e;
  max-width: 480px; margin: 0 auto;
  padding-bottom: 80px; min-height: 100vh;
}
.header {
  background: linear-gradient(135deg, #6C63FF 0%, #4834d4 100%);
  color: white; padding: 28px 20px 22px;
}
.header .label { font-size: 13px; opacity: 0.8; margin-bottom: 4px; }
.header .amount { font-size: 40px; font-weight: 700; letter-spacing: -1px; }
.header .sub { font-size: 12px; opacity: 0.65; margin-top: 4px; }
.section { padding: 16px 16px 0; }
.section-title {
  font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
  color: #999; text-transform: uppercase; margin-bottom: 10px;
}
.card {
  background: white; border-radius: 16px; padding: 16px;
  margin-bottom: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.btn {
  display: block; padding: 14px; background: #6C63FF; color: white;
  border: none; border-radius: 12px; font-size: 16px; font-weight: 600;
  text-align: center; text-decoration: none; cursor: pointer; width: 100%;
  transition: background 0.2s;
}
.btn:hover { background: #5a52d5; }
.btn-green { background: #43A047; }
.btn-green:hover { background: #388E3C; }
.btn-sm { padding: 8px 16px; font-size: 14px; display: inline-block; width: auto; border-radius: 8px; }
.error { background: #ffebee; color: #c62828; padding: 12px; border-radius: 8px; margin-bottom: 16px; font-size: 14px; }
.bottom-nav {
  position: fixed; bottom: 0; left: 50%; transform: translateX(-50%);
  width: 100%; max-width: 480px; background: white;
  display: flex; border-top: 1px solid #eee; z-index: 100;
}
.nav-item {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  padding: 8px 0; text-decoration: none; color: #bbb;
  font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
}
.nav-item.active { color: #6C63FF; }
.nav-item svg { width: 22px; height: 22px; margin-bottom: 3px; }
.progress-bar { background: #f0f2f5; border-radius: 999px; height: 8px; overflow: hidden; }
.progress-fill {
  height: 100%; background: linear-gradient(90deg, #6C63FF, #a29bfe);
  border-radius: 999px; transition: width 0.4s ease;
}
.progress-fill.done { background: linear-gradient(90deg, #43A047, #81C784); }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 13px; font-weight: 600; color: #555; margin-bottom: 6px; }
.form-group input, .form-group select, .form-group textarea {
  width: 100%; padding: 12px; border: 1px solid #e0e0e0;
  border-radius: 10px; font-size: 15px; background: #fafafa;
  outline: none; transition: border 0.2s;
}
.form-group input:focus, .form-group select:focus { border-color: #6C63FF; background: white; }
.page-hdr {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px; background: white; border-bottom: 1px solid #f0f0f0;
  position: sticky; top: 0; z-index: 10;
}
.page-hdr h1 { font-size: 20px; font-weight: 700; }
.back-btn { color: #6C63FF; text-decoration: none; font-size: 24px; line-height: 1; }
.acct-scroll {
  display: flex; gap: 12px; overflow-x: auto; padding-bottom: 4px;
  scrollbar-width: none;
}
.acct-scroll::-webkit-scrollbar { display: none; }
.acct-card {
  min-width: 140px; border-radius: 16px; padding: 16px;
  color: white; text-decoration: none; flex-shrink: 0;
}
.acct-card .name { font-size: 13px; opacity: 0.85; margin-bottom: 8px; }
.acct-card .bal { font-size: 22px; font-weight: 700; }
.add-card {
  min-width: 90px; border-radius: 16px; padding: 16px;
  border: 2px dashed #ddd; display: flex; flex-direction: column;
  align-items: center; justify-content: center; text-decoration: none;
  color: #ccc; font-size: 11px; font-weight: 700; flex-shrink: 0;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.add-card .plus { font-size: 28px; margin-bottom: 4px; color: #bbb; }
.loan-avatar {
  width: 44px; height: 44px; border-radius: 50%; background: #ebe8ff;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; font-weight: 700; color: #6C63FF; flex-shrink: 0;
}
.fab {
  position: fixed; bottom: 90px; right: 20px;
  width: 56px; height: 56px; background: #6C63FF; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4px 16px rgba(108,99,255,0.45); text-decoration: none;
  color: white; font-size: 32px; line-height: 0; z-index: 99;
}
.txn-row {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 0; border-bottom: 1px solid #f5f5f5;
}
.txn-row:last-child { border-bottom: none; }
.txn-icon {
  width: 40px; height: 40px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; flex-shrink: 0;
}
.txn-icon.out { background: #ffebee; }
.txn-icon.in  { background: #e8f5e9; }
.txn-desc { font-size: 14px; font-weight: 600; }
.txn-meta { font-size: 12px; color: #aaa; margin-top: 1px; }
.txn-amount { font-size: 15px; font-weight: 700; text-align: right; white-space: nowrap; }
.txn-amount.out { color: #e53935; }
.txn-amount.in  { color: #43A047; }
.tabs {
  display: flex; background: white; border-bottom: 1px solid #eee;
  overflow-x: auto; scrollbar-width: none;
}
.tabs::-webkit-scrollbar { display: none; }
.tab {
  padding: 12px 14px; font-size: 13px; font-weight: 600; color: #aaa;
  white-space: nowrap; text-decoration: none; border-bottom: 2px solid transparent;
}
.tab.active { color: #6C63FF; border-bottom-color: #6C63FF; }
.pill { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.pill-active { background: #e8f5e9; color: #2e7d32; }
.pill-paid   { background: #e3f2fd; color: #1565c0; }
"""

_HEAD = (
    '<!DOCTYPE html><html lang="en"><head>'
    '<meta charset="UTF-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">'
    '<title>Debt Tracker</title>'
    '<style>' + CSS + '</style>'
    '</head><body>'
)
_FOOT = '</body></html>'

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return render_template_string(
        HOME_TMPL,
        accounts=norm_all(db.accounts.find()),
        active_loans=norm_all(db.loans.find({'status': 'active'})),
        nw=net_worth(),
        month=datetime.now().strftime('%B %Y'),
        nav=Markup(_nav('home')),
    )

@app.route('/accounts/add', methods=['GET', 'POST'])
def add_account():
    error = None
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        bal  = request.form.get('balance', '0').strip()
        if not name:
            error = 'Account name is required'
        else:
            try:
                balance = float(bal) if bal else 0.0
                count = db.accounts.count_documents({})
                db.accounts.insert_one({
                    '_id': gen_id(), 'name': name,
                    'balance': round(balance, 2),
                    'color': COLORS[count % len(COLORS)],
                })
                return redirect(url_for('home'))
            except ValueError:
                error = 'Invalid balance amount'
    return render_template_string(ADD_ACCOUNT_TMPL, error=error, nav=Markup(_nav('home')))

@app.route('/accounts/<aid>')
def account_detail(aid):
    acct = get_account(aid)
    if not acct:
        return redirect(url_for('home'))
    acct_txns = norm_all(db.transactions.find({'account_id': aid}).sort('date', -1))
    return render_template_string(
        ACCOUNT_DETAIL_TMPL, acct=acct, txns=acct_txns,
        nav=Markup(_nav('home')),
    )

@app.route('/loans')
def loan_list():
    active = norm_all(db.loans.find({'status': 'active'}))
    paid   = norm_all(db.loans.find({'status': 'paid'}))
    return render_template_string(LOANS_TMPL, active=active, paid=paid, nav=Markup(_nav('loans')))

@app.route('/loans/add', methods=['GET', 'POST'])
def add_loan():
    error = None
    all_accounts = norm_all(db.accounts.find())
    if request.method == 'POST':
        borrower = request.form.get('borrower', '').strip()
        phone    = request.form.get('phone', '').strip()
        amt_str  = request.form.get('amount', '').strip()
        from_acc = request.form.get('from_account', '').strip()
        to_acc   = request.form.get('to_account', '').strip()
        date     = request.form.get('date', datetime.now().strftime('%Y-%m-%d')).strip()
        note     = request.form.get('note', '').strip()

        if not borrower:   error = 'Borrower name is required'
        elif not amt_str:  error = 'Amount is required'
        elif not from_acc: error = 'Select the account you paid from'
        elif not to_acc:   error = 'Select the account to receive payments'
        else:
            try:
                amount = float(amt_str)
                if amount <= 0:
                    raise ValueError()
                acct = get_account(from_acc)
                if not acct:
                    error = 'Invalid source account'
                else:
                    lid = gen_id()
                    db.accounts.update_one({'_id': from_acc}, {'$inc': {'balance': -amount}})
                    db.loans.insert_one({
                        '_id': lid, 'borrower': borrower, 'phone': phone,
                        'total': amount, 'remaining': amount,
                        'from_account': from_acc, 'to_account': to_acc,
                        'date': date, 'note': note, 'status': 'active',
                        'payments': [],
                    })
                    add_txn(date, amount, 'loan_out', from_acc, f'Loan to {borrower}', lid)
                    return redirect(url_for('loan_detail', lid=lid))
            except ValueError:
                if not error:
                    error = 'Invalid amount'
    return render_template_string(
        ADD_LOAN_TMPL, accounts=all_accounts, error=error,
        today=datetime.now().strftime('%Y-%m-%d'),
        nav=Markup(_nav('loans')),
    )

@app.route('/loans/<lid>')
def loan_detail(lid):
    loan = get_loan(lid)
    if not loan:
        return redirect(url_for('loan_list'))
    pct = int((loan['total'] - loan['remaining']) / loan['total'] * 100) if loan['total'] else 100
    return render_template_string(
        LOAN_DETAIL_TMPL,
        loan=loan,
        from_acct=get_account(loan['from_account']),
        to_acct=get_account(loan['to_account']),
        pct=pct,
        accounts=norm_all(db.accounts.find()),
        today=datetime.now().strftime('%Y-%m-%d'),
        get_account=get_account,
        nav=Markup(_nav('loans')),
    )

@app.route('/loans/<lid>/payment', methods=['POST'])
def add_payment(lid):
    loan = get_loan(lid)
    if not loan or loan['status'] == 'paid':
        return redirect(url_for('loan_list'))
    amt_str = request.form.get('amount', '').strip()
    date    = request.form.get('date', datetime.now().strftime('%Y-%m-%d')).strip()
    to_acc  = request.form.get('to_account', loan['to_account']).strip()
    note    = request.form.get('note', '').strip()
    try:
        amount = min(float(amt_str), loan['remaining'])
        if amount <= 0:
            raise ValueError()
        new_remaining = round(loan['remaining'] - amount, 2)
        new_status = 'paid' if new_remaining <= 0 else 'active'
        payment = {'id': gen_id(), 'date': date, 'amount': amount, 'account_id': to_acc, 'note': note}
        db.accounts.update_one({'_id': to_acc}, {'$inc': {'balance': amount}})
        db.loans.update_one(
            {'_id': lid},
            {'$set': {'remaining': new_remaining, 'status': new_status}, '$push': {'payments': payment}}
        )
        add_txn(date, amount, 'payment_in', to_acc, f'Payment from {loan["borrower"]}', lid)
    except (ValueError, TypeError):
        pass
    return redirect(url_for('loan_detail', lid=lid))

@app.route('/transactions')
def txn_page():
    period = request.args.get('p', 'all')
    txns = filter_txns(period)
    for t in txns:
        a = get_account(t['account_id'])
        t['acct_name'] = a['name'] if a else '?'
    return render_template_string(
        TRANSACTIONS_TMPL, txns=txns, period=period,
        nav=Markup(_nav('txns')),
    )

# ── Templates ─────────────────────────────────────────────────────────────────

HOME_TMPL = _HEAD + """
<div class="header">
  <div class="label">Net Worth</div>
  <div class="amount">${{ '%.2f'|format(nw) }}</div>
  <div class="sub">{{ month }}</div>
</div>

<div class="section" style="margin-top:20px;">
  <div class="section-title">My Accounts</div>
  <div class="acct-scroll">
    {% for a in accounts %}
    <a href="/accounts/{{ a.id }}" class="acct-card" style="background:{{ a.color }};">
      <div class="name">{{ a.name }}</div>
      <div class="bal">${{ '%.2f'|format(a.balance) }}</div>
    </a>
    {% endfor %}
    <a href="/accounts/add" class="add-card">
      <div class="plus">+</div>Add
    </a>
  </div>
</div>

<div class="section" style="margin-top:20px; padding-bottom:16px;">
  <div class="section-title">Active Loans</div>
  {% if active_loans %}
    {% for loan in active_loans %}
    {% set pct = ((loan.total - loan.remaining) / loan.total * 100)|int if loan.total else 100 %}
    <a href="/loans/{{ loan.id }}" style="text-decoration:none; color:inherit;">
    <div class="card">
      <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
        <div class="loan-avatar">{{ loan.borrower[0].upper() }}</div>
        <div style="flex:1; min-width:0;">
          <div style="font-weight:700; font-size:15px;">{{ loan.borrower }}</div>
          <div style="font-size:12px; color:#999;">{{ loan.phone or 'No phone' }}</div>
        </div>
        <div style="text-align:right; flex-shrink:0;">
          <div style="font-weight:700; color:#e53935;">${{ '%.2f'|format(loan.remaining) }}</div>
          <div style="font-size:11px; color:#aaa;">remaining</div>
        </div>
      </div>
      <div class="progress-bar">
        <div class="progress-fill {% if pct == 100 %}done{% endif %}" style="width:{{ pct }}%;"></div>
      </div>
      <div style="display:flex; justify-content:space-between; font-size:11px; color:#aaa; margin-top:6px;">
        <span>Paid ${{ '%.2f'|format(loan.total - loan.remaining) }}</span>
        <span>of ${{ '%.2f'|format(loan.total) }}</span>
      </div>
    </div>
    </a>
    {% endfor %}
  {% else %}
    <div class="card" style="text-align:center; padding:36px; color:#ccc;">
      <div style="font-size:48px; margin-bottom:12px;">💳</div>
      <div style="font-weight:600; color:#bbb; margin-bottom:16px;">No active loans</div>
      <a href="/loans/add" style="display:inline-block; padding:10px 20px; background:#6C63FF; color:white; border-radius:10px; text-decoration:none; font-weight:600; font-size:14px;">+ Give a Loan</a>
    </div>
  {% endif %}
</div>

{{ nav }}
""" + _FOOT

ADD_ACCOUNT_TMPL = _HEAD + """
<div class="page-hdr">
  <a href="/" class="back-btn">&#8249;</a>
  <h1>Add Account</h1>
  <span></span>
</div>
<div class="section" style="margin-top:20px; padding-bottom:16px;">
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="POST">
    <div class="form-group">
      <label>Account Name</label>
      <input type="text" name="name" placeholder="e.g. Cash, Bank A, Savings" autofocus>
    </div>
    <div class="form-group">
      <label>Starting Balance ($)</label>
      <input type="number" name="balance" step="0.01" min="0" placeholder="0.00" value="0">
    </div>
    <button type="submit" class="btn">Add Account</button>
  </form>
</div>
{{ nav }}
""" + _FOOT

ACCOUNT_DETAIL_TMPL = _HEAD + """
<div style="background:{{ acct.color }}; padding:24px 20px 22px; color:white;">
  <a href="/" style="color:rgba(255,255,255,0.8); text-decoration:none; font-size:14px; font-weight:600;">&#8249; Back</a>
  <div style="font-size:18px; font-weight:700; margin-top:12px;">{{ acct.name }}</div>
  <div style="font-size:38px; font-weight:700; letter-spacing:-1px; margin-top:4px;">
    ${{ '%.2f'|format(acct.balance) }}
  </div>
</div>
<div class="section" style="margin-top:20px; padding-bottom:16px;">
  <div class="section-title">Transaction History</div>
  {% if txns %}
    <div class="card" style="padding:4px 16px;">
    {% for t in txns %}
    <div class="txn-row">
      <div class="txn-icon {{ 'out' if t.type == 'loan_out' else 'in' }}">
        {{ '&#8593;' if t.type == 'loan_out' else '&#8595;' }}
      </div>
      <div style="flex:1; min-width:0;">
        <div class="txn-desc">{{ t.description }}</div>
        <div class="txn-meta">{{ t.date }}</div>
      </div>
      <div class="txn-amount {{ 'out' if t.type == 'loan_out' else 'in' }}">
        {{ '-' if t.type == 'loan_out' else '+' }}${{ '%.2f'|format(t.amount) }}
      </div>
    </div>
    {% endfor %}
    </div>
  {% else %}
    <div class="card" style="text-align:center; color:#ccc; padding:36px;">
      <div style="font-size:40px; margin-bottom:10px;">📋</div>
      No transactions yet
    </div>
  {% endif %}
</div>
{{ nav }}
""" + _FOOT

LOANS_TMPL = _HEAD + """
<div class="page-hdr">
  <div></div>
  <h1>Loans</h1>
  <span></span>
</div>
<div class="section" style="margin-top:16px;">
  <div class="section-title">Active ({{ active|length }})</div>
  {% if active %}
    {% for loan in active %}
    {% set pct = ((loan.total - loan.remaining) / loan.total * 100)|int if loan.total else 100 %}
    <a href="/loans/{{ loan.id }}" style="text-decoration:none; color:inherit;">
    <div class="card">
      <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
        <div class="loan-avatar">{{ loan.borrower[0].upper() }}</div>
        <div style="flex:1; min-width:0;">
          <div style="font-weight:700; font-size:15px;">{{ loan.borrower }}</div>
          <div style="font-size:12px; color:#999;">{{ loan.phone or 'No phone' }}</div>
        </div>
        <div style="text-align:right; flex-shrink:0;">
          <span class="pill pill-active">Active</span>
          <div style="font-weight:700; color:#e53935; margin-top:6px;">${{ '%.2f'|format(loan.remaining) }}</div>
        </div>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" style="width:{{ pct }}%;"></div>
      </div>
      <div style="display:flex; justify-content:space-between; font-size:11px; color:#aaa; margin-top:6px;">
        <span>{{ pct }}% paid</span>
        <span>${{ '%.2f'|format(loan.total) }} total</span>
      </div>
    </div>
    </a>
    {% endfor %}
  {% else %}
    <div class="card" style="text-align:center; color:#ccc; padding:24px;">No active loans</div>
  {% endif %}
</div>
{% if paid %}
<div class="section" style="margin-top:4px; padding-bottom:16px;">
  <div class="section-title">Paid ({{ paid|length }})</div>
  {% for loan in paid %}
  <a href="/loans/{{ loan.id }}" style="text-decoration:none; color:inherit;">
  <div class="card">
    <div style="display:flex; align-items:center; gap:12px;">
      <div class="loan-avatar" style="background:#e8f5e9; color:#2e7d32;">{{ loan.borrower[0].upper() }}</div>
      <div style="flex:1; min-width:0;">
        <div style="font-weight:700; font-size:15px;">{{ loan.borrower }}</div>
        <div style="font-size:12px; color:#999;">{{ loan.phone or 'No phone' }}</div>
      </div>
      <div style="text-align:right;">
        <span class="pill pill-paid">Paid ✓</span>
        <div style="font-size:13px; color:#999; margin-top:6px;">${{ '%.2f'|format(loan.total) }}</div>
      </div>
    </div>
  </div>
  </a>
  {% endfor %}
</div>
{% endif %}
<a href="/loans/add" class="fab">+</a>
{{ nav }}
""" + _FOOT

ADD_LOAN_TMPL = _HEAD + """
<div class="page-hdr">
  <a href="/loans" class="back-btn">&#8249;</a>
  <h1>New Loan</h1>
  <span></span>
</div>
<div class="section" style="margin-top:20px; padding-bottom:16px;">
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  {% if accounts %}
  <form method="POST">
    <div class="form-group">
      <label>Borrower Name</label>
      <input type="text" name="borrower" placeholder="Full name" autofocus required>
    </div>
    <div class="form-group">
      <label>Phone (optional)</label>
      <input type="tel" name="phone" placeholder="+1 555 000 0000">
    </div>
    <div class="form-group">
      <label>Loan Amount ($)</label>
      <input type="number" name="amount" step="0.01" min="0.01" placeholder="0.00" required>
    </div>
    <div class="form-group">
      <label>Date</label>
      <input type="date" name="date" value="{{ today }}" required>
    </div>
    <div class="form-group">
      <label>Paid From Account</label>
      <select name="from_account" required>
        <option value="">Select account…</option>
        {% for a in accounts %}
        <option value="{{ a.id }}">{{ a.name }} (${{ '%.2f'|format(a.balance) }})</option>
        {% endfor %}
      </select>
    </div>
    <div class="form-group">
      <label>Receive Payments Into</label>
      <select name="to_account" required>
        <option value="">Select account…</option>
        {% for a in accounts %}
        <option value="{{ a.id }}">{{ a.name }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="form-group">
      <label>Note (optional)</label>
      <input type="text" name="note" placeholder="e.g. Monthly installment, emergency loan">
    </div>
    <button type="submit" class="btn">Give Loan</button>
  </form>
  {% else %}
  <div class="card" style="text-align:center; padding:36px; color:#bbb;">
    <div style="font-size:48px; margin-bottom:12px;">🏦</div>
    <div style="font-weight:600; margin-bottom:16px;">Add an account first</div>
    <a href="/accounts/add" class="btn btn-sm" style="background:#6C63FF; color:white; text-decoration:none;">+ Add Account</a>
  </div>
  {% endif %}
</div>
{{ nav }}
""" + _FOOT

LOAN_DETAIL_TMPL = _HEAD + """
<div style="background:linear-gradient(135deg,#6C63FF,#4834d4); padding:24px 20px 22px; color:white;">
  <a href="/loans" style="color:rgba(255,255,255,0.8); text-decoration:none; font-size:14px; font-weight:600;">&#8249; Loans</a>
  <div style="display:flex; align-items:center; gap:14px; margin-top:16px;">
    <div style="width:52px; height:52px; border-radius:50%; background:rgba(255,255,255,0.2); display:flex; align-items:center; justify-content:center; font-size:22px; font-weight:700;">
      {{ loan.borrower[0].upper() }}
    </div>
    <div style="flex:1; min-width:0;">
      <div style="font-size:20px; font-weight:700;">{{ loan.borrower }}</div>
      <div style="font-size:13px; opacity:0.75;">{{ loan.phone or 'No phone' }}</div>
    </div>
    <span class="pill {% if loan.status == 'active' %}pill-active{% else %}pill-paid{% endif %}">
      {{ 'Active' if loan.status == 'active' else 'Paid ✓' }}
    </span>
  </div>
</div>

<div class="section" style="margin-top:16px;">
  <div class="card">
    <div style="display:flex; justify-content:space-between; margin-bottom:16px; text-align:center;">
      <div style="flex:1;">
        <div style="font-size:11px; color:#aaa; text-transform:uppercase; letter-spacing:1px;">Total</div>
        <div style="font-size:22px; font-weight:700; margin-top:4px;">${{ '%.2f'|format(loan.total) }}</div>
      </div>
      <div style="width:1px; background:#f0f0f0;"></div>
      <div style="flex:1;">
        <div style="font-size:11px; color:#aaa; text-transform:uppercase; letter-spacing:1px;">Paid</div>
        <div style="font-size:22px; font-weight:700; color:#43A047; margin-top:4px;">${{ '%.2f'|format(loan.total - loan.remaining) }}</div>
      </div>
      <div style="width:1px; background:#f0f0f0;"></div>
      <div style="flex:1;">
        <div style="font-size:11px; color:#aaa; text-transform:uppercase; letter-spacing:1px;">Left</div>
        <div style="font-size:22px; font-weight:700; color:#e53935; margin-top:4px;">${{ '%.2f'|format(loan.remaining) }}</div>
      </div>
    </div>
    <div class="progress-bar" style="height:10px;">
      <div class="progress-fill {% if pct == 100 %}done{% endif %}" style="width:{{ pct }}%;"></div>
    </div>
    <div style="text-align:center; font-size:12px; color:#aaa; margin-top:8px;">{{ pct }}% repaid</div>
  </div>

  <div class="card" style="font-size:14px; padding:0 16px;">
    <div style="display:flex; justify-content:space-between; padding:12px 0; border-bottom:1px solid #f5f5f5;">
      <span style="color:#999;">Date</span>
      <span style="font-weight:600;">{{ loan.date }}</span>
    </div>
    <div style="display:flex; justify-content:space-between; padding:12px 0; border-bottom:1px solid #f5f5f5;">
      <span style="color:#999;">Paid From</span>
      <span style="font-weight:600;">{{ from_acct.name if from_acct else '?' }}</span>
    </div>
    <div style="display:flex; justify-content:space-between; padding:12px 0; {% if not loan.note %}{% else %}border-bottom:1px solid #f5f5f5;{% endif %}">
      <span style="color:#999;">Payments To</span>
      <span style="font-weight:600;">{{ to_acct.name if to_acct else '?' }}</span>
    </div>
    {% if loan.note %}
    <div style="display:flex; justify-content:space-between; padding:12px 0;">
      <span style="color:#999;">Note</span>
      <span style="font-weight:600; text-align:right; max-width:65%;">{{ loan.note }}</span>
    </div>
    {% endif %}
  </div>

  {% if loan.status == 'active' %}
  <div class="card">
    <div style="font-weight:700; font-size:15px; margin-bottom:14px;">Record Payment</div>
    <form method="POST" action="/loans/{{ loan.id }}/payment">
      <div class="form-group">
        <label>Amount ($)</label>
        <input type="number" name="amount" step="0.01" min="0.01"
               max="{{ loan.remaining }}" placeholder="0.00" required>
      </div>
      <div class="form-group">
        <label>Date</label>
        <input type="date" name="date" value="{{ today }}">
      </div>
      <div class="form-group">
        <label>Received Into Account</label>
        <select name="to_account">
          {% for a in accounts %}
          <option value="{{ a.id }}" {% if a.id == loan.to_account %}selected{% endif %}>
            {{ a.name }}
          </option>
          {% endfor %}
        </select>
      </div>
      <div class="form-group">
        <label>Note (optional)</label>
        <input type="text" name="note" placeholder="e.g. Installment 1 of 6">
      </div>
      <button type="submit" class="btn btn-green">Record Payment</button>
    </form>
  </div>
  {% endif %}

  {% if loan.payments %}
  <div class="section-title" style="margin-top:8px;">Payment History</div>
  <div class="card" style="padding:4px 16px; margin-bottom:16px;">
    {% for p in loan.payments|reverse %}
    {% set pa = get_account(p.account_id) %}
    <div class="txn-row">
      <div class="txn-icon in">&#8595;</div>
      <div style="flex:1; min-width:0;">
        <div class="txn-desc">{{ p.note or 'Payment' }}</div>
        <div class="txn-meta">{{ p.date }} · {{ pa.name if pa else '?' }}</div>
      </div>
      <div class="txn-amount in">+${{ '%.2f'|format(p.amount) }}</div>
    </div>
    {% endfor %}
  </div>
  {% endif %}
</div>
{{ nav }}
""" + _FOOT

TRANSACTIONS_TMPL = _HEAD + """
<div class="page-hdr">
  <div></div>
  <h1>Transactions</h1>
  <span></span>
</div>
<div class="tabs">
  <a href="/transactions?p=all"       class="tab {% if period == 'all' %}active{% endif %}">All</a>
  <a href="/transactions?p=today"     class="tab {% if period == 'today' %}active{% endif %}">Today</a>
  <a href="/transactions?p=month"     class="tab {% if period == 'month' %}active{% endif %}">This Month</a>
  <a href="/transactions?p=year"      class="tab {% if period == 'year' %}active{% endif %}">This Year</a>
  <a href="/transactions?p=last_year" class="tab {% if period == 'last_year' %}active{% endif %}">Last Year</a>
</div>
<div style="padding:12px 16px 16px;">
  {% if txns %}
    <div class="card" style="padding:4px 16px;">
    {% for t in txns %}
    <div class="txn-row">
      <div class="txn-icon {{ 'out' if t.type == 'loan_out' else 'in' }}">
        {{ '&#8593;' if t.type == 'loan_out' else '&#8595;' }}
      </div>
      <div style="flex:1; min-width:0;">
        <div class="txn-desc">{{ t.description }}</div>
        <div class="txn-meta">{{ t.date }} · {{ t.acct_name }}</div>
      </div>
      <div class="txn-amount {{ 'out' if t.type == 'loan_out' else 'in' }}">
        {{ '-' if t.type == 'loan_out' else '+' }}${{ '%.2f'|format(t.amount) }}
      </div>
    </div>
    {% endfor %}
    </div>
  {% else %}
    <div class="card" style="text-align:center; color:#ccc; padding:48px 16px;">
      <div style="font-size:48px; margin-bottom:12px;">📊</div>
      <div>No transactions for this period</div>
    </div>
  {% endif %}
</div>
{{ nav }}
""" + _FOOT

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
