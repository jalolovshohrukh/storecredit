from flask import Flask, request, render_template_string, redirect, url_for, g
from markupsafe import Markup
from datetime import datetime, date, timedelta
import psycopg2
import psycopg2.extras
import decimal
import uuid
import json
import os

app = Flask(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL', '')
COLORS = ['#6C63FF','#FF6B6B','#4ECDC4','#45B7D1','#96CEB4','#F7B731','#A29BFE','#FD79A8']
CURRENCIES = ['USD','EUR','UZS','RUB','GBP','CNY','KZT','TRY','JPY','AED']
CUR_SYM = {'USD':'$','EUR':'€','UZS':"so'm",'RUB':'₽','GBP':'£','CNY':'¥','KZT':'₸','TRY':'₺','JPY':'¥','AED':'AED'}

# ── DB ─────────────────────────────────────────────────────────────────────────

def get_conn():
    if 'conn' not in g:
        url = DATABASE_URL
        if 'sslmode' not in url:
            url += ('&' if '?' in url else '?') + 'sslmode=require'
        g.conn = psycopg2.connect(url)
    return g.conn

@app.teardown_appcontext
def close_conn(e=None):
    conn = g.pop('conn', None)
    if conn:
        conn.close()

@app.before_request
def setup():
    if not DATABASE_URL:
        return (
            '<div style="font-family:sans-serif;padding:2rem;max-width:480px;margin:auto">'
            '<h2>Database not configured</h2>'
            '<p>Set the <code>DATABASE_URL</code> environment variable in Vercel, then redeploy.</p>'
            '</div>'
        ), 503
    try:
        ensure_tables()
        run_recurring()
    except Exception:
        pass

@app.errorhandler(Exception)
def handle_err(e):
    import traceback
    tb = traceback.format_exc()
    return (
        '<div style="font-family:monospace;padding:2rem;max-width:700px;margin:auto">'
        f'<h2 style="color:#c62828">Error</h2>'
        f'<pre style="background:#fafafa;padding:1rem;border-radius:8px;overflow:auto;font-size:13px">{tb}</pre>'
        '</div>'
    ), 500

# ── Helpers ────────────────────────────────────────────────────────────────────

def gen_id():
    return str(uuid.uuid4())[:8]

def dictify(row):
    if not row:
        return None
    return {k: (float(v) if isinstance(v, decimal.Decimal) else v) for k, v in dict(row).items()}

def fetch_one(sql, p=()):
    with get_conn().cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
        c.execute(sql, p)
        return dictify(c.fetchone())

def fetch_all(sql, p=()):
    with get_conn().cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
        c.execute(sql, p)
        return [dictify(r) for r in c.fetchall()]

def execute(sql, p=(), commit=True):
    conn = get_conn()
    with conn.cursor() as c:
        c.execute(sql, p)
    if commit:
        conn.commit()

def fmt(amount, currency='USD'):
    sym = CUR_SYM.get(currency, currency)
    if currency in ('UZS', 'KZT', 'JPY'):
        return f"{sym} {amount:,.0f}"
    return f"{sym}{amount:,.2f}"

# ── Schema ─────────────────────────────────────────────────────────────────────

_initialized = False

def ensure_tables():
    global _initialized
    if _initialized:
        return
    conn = get_conn()
    with conn.cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id VARCHAR(8) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                balance DECIMAL(15,2) DEFAULT 0,
                currency VARCHAR(3) DEFAULT 'USD',
                color VARCHAR(7),
                created_at TIMESTAMP DEFAULT NOW()
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id VARCHAR(8) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                type VARCHAR(10) NOT NULL,
                icon VARCHAR(10),
                color VARCHAR(7)
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id VARCHAR(8) PRIMARY KEY,
                date DATE NOT NULL,
                amount DECIMAL(15,2) NOT NULL,
                type VARCHAR(10) NOT NULL,
                account_id VARCHAR(8),
                to_account_id VARCHAR(8),
                category_id VARCHAR(8),
                note TEXT,
                recurring_id VARCHAR(8),
                created_at TIMESTAMP DEFAULT NOW()
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                id VARCHAR(8) PRIMARY KEY,
                category_id VARCHAR(8) UNIQUE,
                amount DECIMAL(15,2) NOT NULL,
                period VARCHAR(10) DEFAULT 'monthly'
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS recurring_rules (
                id VARCHAR(8) PRIMARY KEY,
                title VARCHAR(100) NOT NULL,
                type VARCHAR(10) NOT NULL,
                amount DECIMAL(15,2) NOT NULL,
                account_id VARCHAR(8),
                category_id VARCHAR(8),
                frequency VARCHAR(10) NOT NULL,
                next_date DATE NOT NULL,
                active BOOLEAN DEFAULT TRUE
            )""")
        c.execute("SELECT COUNT(*) FROM categories")
        if c.fetchone()[0] == 0:
            cats = [
                ('expense','Food & Dining','🍔','#FF6B6B'),
                ('expense','Transport','🚗','#45B7D1'),
                ('expense','Shopping','🛍','#A29BFE'),
                ('expense','Entertainment','🎬','#F7B731'),
                ('expense','Health','💊','#96CEB4'),
                ('expense','Bills','💡','#FD79A8'),
                ('expense','Education','📚','#4ECDC4'),
                ('expense','Other','💸','#bbb'),
                ('income','Salary','💼','#43A047'),
                ('income','Freelance','💻','#6C63FF'),
                ('income','Investment','📈','#F7B731'),
                ('income','Other Income','💰','#4ECDC4'),
            ]
            for typ, name, icon, color in cats:
                c.execute(
                    "INSERT INTO categories(id,name,type,icon,color) VALUES(%s,%s,%s,%s,%s)",
                    (gen_id(), name, typ, icon, color)
                )
    conn.commit()
    _initialized = True

# ── Recurring ──────────────────────────────────────────────────────────────────

_rec_date = None

def run_recurring():
    global _rec_date
    today = date.today()
    if _rec_date == today:
        return
    _rec_date = today
    rules = fetch_all(
        "SELECT * FROM recurring_rules WHERE active=TRUE AND next_date<=%s", (today,)
    )
    conn = get_conn()
    for r in rules:
        existing = fetch_one(
            "SELECT id FROM transactions WHERE recurring_id=%s AND date=%s",
            (r['id'], r['next_date'])
        )
        if existing:
            continue
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO transactions(id,date,amount,type,account_id,category_id,note,recurring_id)"
                " VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                (gen_id(), r['next_date'], r['amount'], r['type'],
                 r['account_id'], r['category_id'], r['title'], r['id'])
            )
            if r['type'] == 'income':
                c.execute("UPDATE accounts SET balance=balance+%s WHERE id=%s",
                          (r['amount'], r['account_id']))
            else:
                c.execute("UPDATE accounts SET balance=balance-%s WHERE id=%s",
                          (r['amount'], r['account_id']))
            nd = r['next_date']
            if isinstance(nd, str):
                nd = datetime.strptime(nd, '%Y-%m-%d').date()
            freq = r['frequency']
            if freq == 'daily':
                nd += timedelta(days=1)
            elif freq == 'weekly':
                nd += timedelta(weeks=1)
            elif freq == 'monthly':
                m = nd.month % 12 + 1
                y = nd.year + (nd.month // 12)
                try:
                    nd = nd.replace(year=y, month=m)
                except ValueError:
                    nd = nd.replace(year=y, month=m, day=1)
            c.execute("UPDATE recurring_rules SET next_date=%s WHERE id=%s", (nd, r['id']))
    conn.commit()

# ── Nav ────────────────────────────────────────────────────────────────────────

NAV_ITEMS = [
    ('/', 'home',
     'M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z', 'Home'),
    ('/transactions', 'txns',
     'M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z', 'Txns'),
    ('/budgets', 'budgets',
     'M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z', 'Budget'),
    ('/stats', 'stats',
     'M5 9.2h3V19H5zM10.6 5h2.8v14h-2.8zm5.6 8H19v6h-2.8z', 'Stats'),
]

def _nav(active):
    html = '<nav class="bottom-nav">'
    for href, name, path, label in NAV_ITEMS:
        cls = 'nav-item active' if active == name else 'nav-item'
        html += (
            f'<a href="{href}" class="{cls}">'
            f'<svg viewBox="0 0 24 24" fill="currentColor"><path d="{path}"/></svg>'
            f'{label}</a>'
        )
    return html + '</nav>'

# ── CSS ────────────────────────────────────────────────────────────────────────

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
.header .amount { font-size: 34px; font-weight: 700; letter-spacing: -1px; }
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
.btn-green { background: #43A047; } .btn-green:hover { background: #388E3C; }
.btn-red { background: #e53935; } .btn-red:hover { background: #c62828; }
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
  height: 100%; border-radius: 999px; transition: width 0.4s ease;
  background: linear-gradient(90deg, #6C63FF, #a29bfe);
}
.progress-fill.ok  { background: linear-gradient(90deg, #43A047, #81C784); }
.progress-fill.warn { background: linear-gradient(90deg, #F7B731, #ffd700); }
.progress-fill.over { background: linear-gradient(90deg, #e53935, #ef9a9a); }
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
  display: flex; gap: 12px; overflow-x: auto; padding-bottom: 4px; scrollbar-width: none;
}
.acct-scroll::-webkit-scrollbar { display: none; }
.acct-card { min-width: 140px; border-radius: 16px; padding: 16px; color: white; text-decoration: none; flex-shrink: 0; }
.acct-card .name { font-size: 13px; opacity: 0.85; margin-bottom: 2px; }
.acct-card .cur  { font-size: 11px; opacity: 0.65; margin-bottom: 8px; }
.acct-card .bal  { font-size: 20px; font-weight: 700; }
.add-card {
  min-width: 90px; border-radius: 16px; padding: 16px;
  border: 2px dashed #ddd; display: flex; flex-direction: column;
  align-items: center; justify-content: center; text-decoration: none;
  color: #ccc; font-size: 11px; font-weight: 700; flex-shrink: 0;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.add-card .plus { font-size: 28px; margin-bottom: 4px; color: #bbb; }
.txn-row { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px solid #f5f5f5; }
.txn-row:last-child { border-bottom: none; }
.txn-icon {
  width: 40px; height: 40px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; flex-shrink: 0;
}
.txn-icon.out { background: #ffebee; }
.txn-icon.in  { background: #e8f5e9; }
.txn-icon.tr  { background: #e3f2fd; }
.txn-desc { font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.txn-meta { font-size: 12px; color: #aaa; margin-top: 1px; }
.txn-amount { font-size: 15px; font-weight: 700; text-align: right; white-space: nowrap; }
.txn-amount.out { color: #e53935; }
.txn-amount.in  { color: #43A047; }
.txn-amount.tr  { color: #1565c0; }
.tabs { display: flex; background: white; border-bottom: 1px solid #eee; overflow-x: auto; scrollbar-width: none; }
.tabs::-webkit-scrollbar { display: none; }
.tab {
  padding: 12px 14px; font-size: 13px; font-weight: 600; color: #aaa;
  white-space: nowrap; text-decoration: none; border-bottom: 2px solid transparent;
}
.tab.active { color: #6C63FF; border-bottom-color: #6C63FF; }
.fab {
  position: fixed; bottom: 90px; right: 50%;
  transform: translateX(calc(50% + 176px));
  width: 56px; height: 56px; background: #6C63FF; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4px 16px rgba(108,99,255,0.45); text-decoration: none;
  color: white; font-size: 32px; line-height: 0; z-index: 99;
}
.summary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.summary-box { background: white; border-radius: 16px; padding: 16px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.summary-box .lbl { font-size: 11px; color: #999; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
.summary-box .val { font-size: 20px; font-weight: 700; }
.summary-box .val.green { color: #43A047; }
.summary-box .val.red   { color: #e53935; }
.type-tabs { display: flex; gap: 8px; margin-bottom: 20px; }
.type-tab {
  flex: 1; padding: 10px; border: 2px solid #e0e0e0; border-radius: 10px;
  font-size: 14px; font-weight: 600; text-align: center; cursor: pointer;
  background: white; color: #aaa; transition: all 0.15s;
}
.type-tab.active-expense { border-color: #e53935; background: #ffebee; color: #e53935; }
.type-tab.active-income  { border-color: #43A047; background: #e8f5e9; color: #43A047; }
.type-tab.active-transfer{ border-color: #1565c0; background: #e3f2fd; color: #1565c0; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.badge-income   { background: #e8f5e9; color: #2e7d32; }
.badge-expense  { background: #ffebee; color: #c62828; }
.badge-transfer { background: #e3f2fd; color: #1565c0; }
"""

HEAD = (
    '<!DOCTYPE html><html lang="en"><head>'
    '<meta charset="UTF-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0">'
    '<title>Budget Tracker</title>'
    '<style>' + CSS + '</style>'
    '</head><body>'
)
FOOT = '</body></html>'

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    accounts = fetch_all("SELECT * FROM accounts ORDER BY name")
    now = datetime.now()
    ym = now.strftime('%Y-%m')
    inc  = fetch_one("SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='income' AND TO_CHAR(date,'YYYY-MM')=%s", (ym,))
    exp  = fetch_one("SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='expense' AND TO_CHAR(date,'YYYY-MM')=%s", (ym,))
    recent = fetch_all("""
        SELECT t.*, c.name AS cat_name, c.icon AS cat_icon, a.currency, a.name AS acct_name
        FROM transactions t
        LEFT JOIN categories c ON t.category_id=c.id
        LEFT JOIN accounts a ON t.account_id=a.id
        ORDER BY t.date DESC, t.id DESC LIMIT 5
    """)
    nw = {}
    for a in accounts:
        cur = a.get('currency', 'USD')
        nw[cur] = nw.get(cur, 0.0) + a['balance']
    return render_template_string(HOME_TMPL,
        accounts=accounts, recent=recent, nw=nw,
        income=inc['s'] if inc else 0,
        expense=exp['s'] if exp else 0,
        month=now.strftime('%B %Y'),
        nav=Markup(_nav('home')), fmt=fmt, CUR_SYM=CUR_SYM,
    )

@app.route('/accounts/add', methods=['GET', 'POST'])
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
                n = fetch_one("SELECT COUNT(*) AS c FROM accounts")
                count = int(n['c']) if n else 0
                execute(
                    "INSERT INTO accounts(id,name,balance,currency,color) VALUES(%s,%s,%s,%s,%s)",
                    (gen_id(), name, round(balance, 2), cur, COLORS[count % len(COLORS)])
                )
                return redirect(url_for('home'))
            except ValueError:
                error = 'Invalid balance amount'
    return render_template_string(ADD_ACCOUNT_TMPL,
        error=error, currencies=CURRENCIES, nav=Markup(_nav('home'))
    )

@app.route('/transactions/add', methods=['GET', 'POST'])
def add_txn():
    error = None
    accounts   = fetch_all("SELECT * FROM accounts ORDER BY name")
    categories = fetch_all("SELECT * FROM categories ORDER BY type, name")
    today = datetime.now().strftime('%Y-%m-%d')
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
                        (gen_id(), dt, amount, typ, acc_id, to_acc, cat_id, note)
                    )
                    if typ == 'expense':
                        c.execute("UPDATE accounts SET balance=balance-%s WHERE id=%s", (amount, acc_id))
                    elif typ == 'income':
                        c.execute("UPDATE accounts SET balance=balance+%s WHERE id=%s", (amount, acc_id))
                    elif typ == 'transfer':
                        c.execute("UPDATE accounts SET balance=balance-%s WHERE id=%s", (amount, acc_id))
                        c.execute("UPDATE accounts SET balance=balance+%s WHERE id=%s", (amount, to_acc))
                conn.commit()
                return redirect(url_for('txn_list'))
            except ValueError:
                error = 'Invalid amount'
    return render_template_string(ADD_TXN_TMPL,
        error=error, accounts=accounts, categories=categories,
        today=today, nav=Markup(_nav('txns'))
    )

@app.route('/transactions')
def txn_list():
    period = request.args.get('p', 'month')
    typ    = request.args.get('t', 'all')
    now = datetime.now()
    filters, params = [], []
    if period == 'today':
        filters.append("t.date=%s"); params.append(now.strftime('%Y-%m-%d'))
    elif period == 'month':
        filters.append("TO_CHAR(t.date,'YYYY-MM')=%s"); params.append(now.strftime('%Y-%m'))
    elif period == 'year':
        filters.append("EXTRACT(YEAR FROM t.date)=%s"); params.append(now.year)
    if typ != 'all':
        filters.append("t.type=%s"); params.append(typ)
    where = ('WHERE ' + ' AND '.join(filters)) if filters else ''
    txns = fetch_all(f"""
        SELECT t.*, c.name AS cat_name, c.icon AS cat_icon,
               a.name AS acct_name, a.currency
        FROM transactions t
        LEFT JOIN categories c ON t.category_id=c.id
        LEFT JOIN accounts a ON t.account_id=a.id
        {where} ORDER BY t.date DESC, t.id DESC
    """, tuple(params))
    return render_template_string(TXN_LIST_TMPL,
        txns=txns, period=period, typ=typ,
        nav=Markup(_nav('txns')), fmt=fmt
    )

@app.route('/budgets')
def budgets():
    now = datetime.now()
    ym = now.strftime('%Y-%m')
    cats = fetch_all("""
        SELECT c.*, b.amount AS budget_amount, b.id AS budget_id, b.period
        FROM categories c
        LEFT JOIN budgets b ON c.id=b.category_id
        WHERE c.type='expense'
        ORDER BY c.name
    """)
    for cat in cats:
        spent = fetch_one(
            "SELECT COALESCE(SUM(amount),0) AS s FROM transactions"
            " WHERE category_id=%s AND type='expense' AND TO_CHAR(date,'YYYY-MM')=%s",
            (cat['id'], ym)
        )
        cat['spent'] = spent['s'] if spent else 0
        if cat['budget_amount']:
            cat['pct'] = min(int(cat['spent'] / cat['budget_amount'] * 100), 100)
            cat['cls'] = 'over' if cat['pct'] >= 100 else ('warn' if cat['pct'] >= 75 else 'ok')
        else:
            cat['pct'] = 0
            cat['cls'] = ''
    return render_template_string(BUDGETS_TMPL,
        cats=cats, month=now.strftime('%B %Y'),
        nav=Markup(_nav('budgets')), fmt=fmt
    )

@app.route('/budgets/set', methods=['POST'])
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
    return redirect(url_for('budgets'))

@app.route('/budgets/delete/<bid>', methods=['POST'])
def del_budget(bid):
    execute("DELETE FROM budgets WHERE id=%s", (bid,))
    return redirect(url_for('budgets'))

@app.route('/stats')
def stats():
    now = datetime.now()
    ym = now.strftime('%Y-%m')
    cat_data = fetch_all("""
        SELECT c.name, c.color, COALESCE(SUM(t.amount),0) AS total
        FROM categories c
        LEFT JOIN transactions t
          ON t.category_id=c.id AND t.type='expense' AND TO_CHAR(t.date,'YYYY-MM')=%s
        WHERE c.type='expense'
        GROUP BY c.id, c.name, c.color
        HAVING COALESCE(SUM(t.amount),0) > 0
        ORDER BY total DESC
    """, (ym,))
    months = []
    for i in range(5, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12; y -= 1
        months.append(f'{y:04d}-{m:02d}')
    bar_data = []
    for ym2 in months:
        i2 = fetch_one("SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='income' AND TO_CHAR(date,'YYYY-MM')=%s", (ym2,))
        e2 = fetch_one("SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='expense' AND TO_CHAR(date,'YYYY-MM')=%s", (ym2,))
        bar_data.append({'month': ym2, 'income': i2['s'] if i2 else 0, 'expense': e2['s'] if e2 else 0})
    ti = fetch_one("SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='income' AND TO_CHAR(date,'YYYY-MM')=%s", (ym,))
    te = fetch_one("SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='expense' AND TO_CHAR(date,'YYYY-MM')=%s", (ym,))
    return render_template_string(STATS_TMPL,
        pie_labels=json.dumps([d['name'] for d in cat_data]),
        pie_values=json.dumps([d['total'] for d in cat_data]),
        pie_colors=json.dumps([d['color'] for d in cat_data]),
        bar_labels=json.dumps([d['month'] for d in bar_data]),
        bar_income=json.dumps([d['income'] for d in bar_data]),
        bar_expense=json.dumps([d['expense'] for d in bar_data]),
        income=ti['s'] if ti else 0,
        expense=te['s'] if te else 0,
        month=now.strftime('%B %Y'),
        nav=Markup(_nav('stats')), fmt=fmt
    )

@app.route('/recurring')
def recurring():
    rules = fetch_all("""
        SELECT r.*, c.name AS cat_name, c.icon AS cat_icon, a.name AS acct_name
        FROM recurring_rules r
        LEFT JOIN categories c ON r.category_id=c.id
        LEFT JOIN accounts a ON r.account_id=a.id
        ORDER BY r.active DESC, r.next_date
    """)
    accounts = fetch_all("SELECT * FROM accounts ORDER BY name")
    cats = fetch_all("SELECT * FROM categories ORDER BY type, name")
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template_string(RECURRING_TMPL,
        rules=rules, accounts=accounts, cats=cats, today=today,
        nav=Markup(_nav('home'))
    )

@app.route('/recurring/add', methods=['POST'])
def add_recurring():
    title  = request.form.get('title', '').strip()
    typ    = request.form.get('type', 'expense')
    amt_s  = request.form.get('amount', '').strip()
    acc_id = request.form.get('account_id', '').strip()
    cat_id = request.form.get('category_id', '').strip() or None
    freq   = request.form.get('frequency', 'monthly')
    nd     = request.form.get('next_date', '').strip()
    if title and amt_s and acc_id and nd:
        try:
            execute(
                "INSERT INTO recurring_rules(id,title,type,amount,account_id,category_id,frequency,next_date)"
                " VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                (gen_id(), title, typ, float(amt_s), acc_id, cat_id, freq, nd)
            )
        except (ValueError, Exception):
            pass
    return redirect(url_for('recurring'))

@app.route('/recurring/<rid>/toggle', methods=['POST'])
def toggle_recurring(rid):
    r = fetch_one("SELECT active FROM recurring_rules WHERE id=%s", (rid,))
    if r:
        execute("UPDATE recurring_rules SET active=%s WHERE id=%s", (not r['active'], rid))
    return redirect(url_for('recurring'))

@app.route('/recurring/<rid>/delete', methods=['POST'])
def del_recurring(rid):
    execute("DELETE FROM recurring_rules WHERE id=%s", (rid,))
    return redirect(url_for('recurring'))

# ── Templates ──────────────────────────────────────────────────────────────────

HOME_TMPL = HEAD + """
<div class="header">
  <div class="label">Total Balance</div>
  <div class="amount">
    {% for cur, bal in nw.items() %}
      <div style="{% if not loop.first %}font-size:22px;opacity:0.8;margin-top:4px;{% endif %}">
        {{ fmt(bal, cur) }}
      </div>
    {% else %}
      <div>—</div>
    {% endfor %}
  </div>
  <div class="sub">{{ month }}</div>
</div>

<div class="section" style="margin-top:16px;">
  <div class="summary-grid">
    <div class="summary-box">
      <div class="lbl">Income</div>
      <div class="val green">{{ fmt(income) }}</div>
    </div>
    <div class="summary-box">
      <div class="lbl">Expenses</div>
      <div class="val red">{{ fmt(expense) }}</div>
    </div>
  </div>
</div>

<div class="section" style="margin-top:16px;">
  <div class="section-title">My Accounts</div>
  <div class="acct-scroll">
    {% for a in accounts %}
    <a href="#" class="acct-card" style="background:{{ a.color }};">
      <div class="name">{{ a.name }}</div>
      <div class="cur">{{ a.currency }}</div>
      <div class="bal">{{ fmt(a.balance, a.currency) }}</div>
    </a>
    {% endfor %}
    <a href="/accounts/add" class="add-card">
      <div class="plus">+</div>Add
    </a>
  </div>
</div>

<div class="section" style="margin-top:20px; padding-bottom:16px;">
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
    <div class="section-title" style="margin-bottom:0;">Recent</div>
    <a href="/transactions" style="font-size:13px; color:#6C63FF; text-decoration:none; font-weight:600;">See all</a>
  </div>
  {% if recent %}
  <div class="card" style="padding:4px 16px;">
    {% for t in recent %}
    <div class="txn-row">
      <div class="txn-icon {{ 'out' if t.type=='expense' else ('in' if t.type=='income' else 'tr') }}">
        {{ t.cat_icon or ('↑' if t.type=='expense' else ('↓' if t.type=='income' else '⇄')) }}
      </div>
      <div style="flex:1; min-width:0;">
        <div class="txn-desc">{{ t.cat_name or t.note or t.type.title() }}</div>
        <div class="txn-meta">{{ t.date }} · {{ t.acct_name or '' }}</div>
      </div>
      <div class="txn-amount {{ 'out' if t.type=='expense' else ('in' if t.type=='income' else 'tr') }}">
        {{ '-' if t.type=='expense' else ('+' if t.type=='income' else '⇄') }}{{ fmt(t.amount, t.currency or 'USD') }}
      </div>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <div class="card" style="text-align:center; padding:36px; color:#ccc;">
    <div style="font-size:48px; margin-bottom:12px;">💸</div>
    <div style="font-weight:600; color:#bbb; margin-bottom:16px;">No transactions yet</div>
    <a href="/transactions/add" style="display:inline-block; padding:10px 20px; background:#6C63FF; color:white; border-radius:10px; text-decoration:none; font-weight:600; font-size:14px;">+ Add Transaction</a>
  </div>
  {% endif %}
</div>

<a href="/transactions/add" class="fab">+</a>
{{ nav }}
""" + FOOT

ADD_ACCOUNT_TMPL = HEAD + """
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
      <input type="text" name="name" placeholder="e.g. Cash, Bank, Savings" autofocus required>
    </div>
    <div class="form-group">
      <label>Currency</label>
      <select name="currency">
        {% for c in currencies %}
        <option value="{{ c }}" {% if c=='USD' %}selected{% endif %}>{{ c }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="form-group">
      <label>Starting Balance</label>
      <input type="number" name="balance" step="0.01" min="0" placeholder="0.00" value="0">
    </div>
    <button type="submit" class="btn">Add Account</button>
  </form>
</div>
{{ nav }}
""" + FOOT

ADD_TXN_TMPL = HEAD + """
<div class="page-hdr">
  <a href="/transactions" class="back-btn">&#8249;</a>
  <h1>Add Transaction</h1>
  <span></span>
</div>
<div class="section" style="margin-top:20px; padding-bottom:16px;">
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  {% if accounts %}
  <form method="POST" id="txn-form">
    <input type="hidden" name="type" id="txn-type" value="expense">
    <div class="type-tabs">
      <div class="type-tab active-expense" onclick="setType('expense',this)">Expense</div>
      <div class="type-tab" onclick="setType('income',this)">Income</div>
      <div class="type-tab" onclick="setType('transfer',this)">Transfer</div>
    </div>
    <div class="form-group">
      <label>Amount</label>
      <input type="number" name="amount" step="0.01" min="0.01" placeholder="0.00" required autofocus>
    </div>
    <div class="form-group">
      <label id="acc-label">From Account</label>
      <select name="account_id" required>
        <option value="">Select account…</option>
        {% for a in accounts %}
        <option value="{{ a.id }}">{{ a.name }} ({{ a.currency }})</option>
        {% endfor %}
      </select>
    </div>
    <div class="form-group" id="to-acc-group" style="display:none;">
      <label>To Account</label>
      <select name="to_account_id">
        <option value="">Select account…</option>
        {% for a in accounts %}
        <option value="{{ a.id }}">{{ a.name }} ({{ a.currency }})</option>
        {% endfor %}
      </select>
    </div>
    <div class="form-group" id="cat-group">
      <label>Category</label>
      <select name="category_id" id="cat-select">
        <option value="">No category</option>
        <optgroup label="Expenses">
          {% for c in categories if c.type=='expense' %}
          <option value="{{ c.id }}" data-type="expense">{{ c.icon }} {{ c.name }}</option>
          {% endfor %}
        </optgroup>
        <optgroup label="Income">
          {% for c in categories if c.type=='income' %}
          <option value="{{ c.id }}" data-type="income">{{ c.icon }} {{ c.name }}</option>
          {% endfor %}
        </optgroup>
      </select>
    </div>
    <div class="form-group">
      <label>Date</label>
      <input type="date" name="date" value="{{ today }}" required>
    </div>
    <div class="form-group">
      <label>Note (optional)</label>
      <input type="text" name="note" placeholder="Add a note…">
    </div>
    <button type="submit" class="btn" id="submit-btn">Add Expense</button>
  </form>
  {% else %}
  <div class="card" style="text-align:center; padding:36px; color:#bbb;">
    <div style="font-size:48px; margin-bottom:12px;">🏦</div>
    <div style="font-weight:600; margin-bottom:16px;">Add an account first</div>
    <a href="/accounts/add" class="btn btn-sm">+ Add Account</a>
  </div>
  {% endif %}
</div>
{{ nav }}
<script>
var currentType = 'expense';
function setType(type, el) {
  currentType = type;
  document.getElementById('txn-type').value = type;
  document.querySelectorAll('.type-tab').forEach(t => {
    t.className = 'type-tab';
  });
  el.className = 'type-tab active-' + type;
  document.getElementById('to-acc-group').style.display = type === 'transfer' ? '' : 'none';
  document.getElementById('cat-group').style.display = type === 'transfer' ? 'none' : '';
  document.getElementById('acc-label').textContent = type === 'transfer' ? 'From Account' : 'Account';
  var btn = document.getElementById('submit-btn');
  btn.textContent = 'Add ' + type.charAt(0).toUpperCase() + type.slice(1);
  btn.style.background = type === 'expense' ? '#e53935' : (type === 'income' ? '#43A047' : '#1565c0');
}
</script>
""" + FOOT

TXN_LIST_TMPL = HEAD + """
<div class="page-hdr">
  <div></div>
  <h1>Transactions</h1>
  <a href="/transactions/add" style="color:#6C63FF; text-decoration:none; font-size:28px; line-height:1;">+</a>
</div>
<div class="tabs">
  <a href="/transactions?p=today&t={{ typ }}" class="tab {% if period=='today' %}active{% endif %}">Today</a>
  <a href="/transactions?p=month&t={{ typ }}" class="tab {% if period=='month' %}active{% endif %}">Month</a>
  <a href="/transactions?p=year&t={{ typ }}"  class="tab {% if period=='year' %}active{% endif %}">Year</a>
  <a href="/transactions?p=all&t={{ typ }}"   class="tab {% if period=='all' %}active{% endif %}">All</a>
</div>
<div class="tabs" style="border-top:1px solid #f5f5f5;">
  <a href="/transactions?p={{ period }}&t=all"      class="tab {% if typ=='all' %}active{% endif %}">All</a>
  <a href="/transactions?p={{ period }}&t=expense"  class="tab {% if typ=='expense' %}active{% endif %}">Expenses</a>
  <a href="/transactions?p={{ period }}&t=income"   class="tab {% if typ=='income' %}active{% endif %}">Income</a>
  <a href="/transactions?p={{ period }}&t=transfer" class="tab {% if typ=='transfer' %}active{% endif %}">Transfers</a>
</div>
<div style="padding:12px 16px 16px;">
  {% if txns %}
  <div class="card" style="padding:4px 16px;">
    {% for t in txns %}
    <div class="txn-row">
      <div class="txn-icon {{ 'out' if t.type=='expense' else ('in' if t.type=='income' else 'tr') }}">
        {{ t.cat_icon or ('↑' if t.type=='expense' else ('↓' if t.type=='income' else '⇄')) }}
      </div>
      <div style="flex:1; min-width:0;">
        <div class="txn-desc">{{ t.cat_name or t.note or t.type.title() }}</div>
        <div class="txn-meta">{{ t.date }} · {{ t.acct_name or '' }}
          {% if t.note and t.cat_name %} · {{ t.note }}{% endif %}
        </div>
      </div>
      <div class="txn-amount {{ 'out' if t.type=='expense' else ('in' if t.type=='income' else 'tr') }}">
        {{ '-' if t.type=='expense' else ('+' if t.type=='income' else '⇄') }}{{ fmt(t.amount, t.currency or 'USD') }}
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
""" + FOOT

BUDGETS_TMPL = HEAD + """
<div class="page-hdr">
  <div></div>
  <h1>Budgets</h1>
  <span style="font-size:13px;color:#999;">{{ month }}</span>
</div>
<div style="padding:12px 16px 16px;">
  {% for cat in cats %}
  <div class="card">
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:10px;">
      <div style="display:flex; align-items:center; gap:10px;">
        <span style="font-size:24px;">{{ cat.icon }}</span>
        <div>
          <div style="font-weight:700; font-size:15px;">{{ cat.name }}</div>
          <div style="font-size:12px; color:#aaa;">
            Spent: <strong style="color:#e53935;">{{ fmt(cat.spent) }}</strong>
            {% if cat.budget_amount %}of {{ fmt(cat.budget_amount) }}{% endif %}
          </div>
        </div>
      </div>
      {% if cat.budget_id %}
      <form method="POST" action="/budgets/delete/{{ cat.budget_id }}" style="display:inline;">
        <button style="border:none;background:none;color:#ccc;font-size:18px;cursor:pointer;">✕</button>
      </form>
      {% endif %}
    </div>
    {% if cat.budget_amount %}
    <div class="progress-bar" style="margin-bottom:6px;">
      <div class="progress-fill {{ cat.cls }}" style="width:{{ cat.pct }}%;"></div>
    </div>
    <div style="font-size:12px; color:#aaa; text-align:right;">{{ cat.pct }}%{% if cat.pct >= 100 %} — over budget!{% endif %}</div>
    {% endif %}
    {% if not cat.budget_id %}
    <form method="POST" action="/budgets/set" style="display:flex; gap:8px; margin-top:8px;">
      <input type="hidden" name="category_id" value="{{ cat.id }}">
      <input type="number" name="amount" step="0.01" min="1" placeholder="Set monthly budget…"
             style="flex:1; padding:10px; border:1px solid #e0e0e0; border-radius:8px; font-size:14px; background:#fafafa; outline:none;">
      <button type="submit" class="btn btn-sm" style="padding:10px 16px;">Set</button>
    </form>
    {% else %}
    <form method="POST" action="/budgets/set" style="display:flex; gap:8px; margin-top:8px;">
      <input type="hidden" name="category_id" value="{{ cat.id }}">
      <input type="number" name="amount" step="0.01" min="1" placeholder="Update budget…"
             value="{{ cat.budget_amount }}"
             style="flex:1; padding:10px; border:1px solid #e0e0e0; border-radius:8px; font-size:14px; background:#fafafa; outline:none;">
      <button type="submit" class="btn btn-sm" style="padding:10px 16px;">Update</button>
    </form>
    {% endif %}
  </div>
  {% endfor %}
</div>
{{ nav }}
""" + FOOT

STATS_TMPL = HEAD + """
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<div class="page-hdr">
  <div></div>
  <h1>Stats</h1>
  <span style="font-size:13px;color:#999;">{{ month }}</span>
</div>
<div class="section" style="margin-top:16px;">
  <div class="summary-grid" style="margin-bottom:16px;">
    <div class="summary-box">
      <div class="lbl">Income</div>
      <div class="val green">{{ fmt(income) }}</div>
    </div>
    <div class="summary-box">
      <div class="lbl">Expenses</div>
      <div class="val red">{{ fmt(expense) }}</div>
    </div>
  </div>
</div>

<div class="section">
  <div class="section-title">Expenses by Category</div>
  <div class="card" style="padding:20px;">
    {% if pie_values != '[]' %}
    <canvas id="pieChart" height="220"></canvas>
    {% else %}
    <div style="text-align:center; color:#ccc; padding:32px 0;">No expense data this month</div>
    {% endif %}
  </div>
</div>

<div class="section" style="padding-bottom:16px;">
  <div class="section-title">Income vs Expenses (6 months)</div>
  <div class="card" style="padding:20px;">
    <canvas id="barChart" height="220"></canvas>
  </div>
</div>

{{ nav }}
<script>
{% if pie_values != '[]' %}
new Chart(document.getElementById('pieChart'), {
  type: 'doughnut',
  data: {
    labels: {{ pie_labels|safe }},
    datasets: [{ data: {{ pie_values|safe }}, backgroundColor: {{ pie_colors|safe }}, borderWidth: 2 }]
  },
  options: {
    plugins: { legend: { position: 'bottom', labels: { padding: 12, font: { size: 12 } } } },
    cutout: '60%'
  }
});
{% endif %}
new Chart(document.getElementById('barChart'), {
  type: 'bar',
  data: {
    labels: {{ bar_labels|safe }},
    datasets: [
      { label: 'Income',   data: {{ bar_income|safe }},  backgroundColor: '#43A047aa', borderRadius: 6 },
      { label: 'Expenses', data: {{ bar_expense|safe }}, backgroundColor: '#e53935aa', borderRadius: 6 }
    ]
  },
  options: {
    plugins: { legend: { position: 'bottom', labels: { padding: 12, font: { size: 12 } } } },
    scales: {
      x: { grid: { display: false } },
      y: { grid: { color: '#f0f0f0' }, ticks: { font: { size: 11 } } }
    }
  }
});
</script>
""" + FOOT

RECURRING_TMPL = HEAD + """
<div class="page-hdr">
  <a href="/" class="back-btn">&#8249;</a>
  <h1>Recurring</h1>
  <span></span>
</div>

<div style="padding:16px;">
  {% if rules %}
  {% for r in rules %}
  <div class="card" style="opacity:{{ '1' if r.active else '0.5' }};">
    <div style="display:flex; align-items:center; gap:12px;">
      <div style="font-size:24px;">{{ r.cat_icon or ('💸' if r.type=='expense' else '💰') }}</div>
      <div style="flex:1; min-width:0;">
        <div style="font-weight:700; font-size:15px;">{{ r.title }}</div>
        <div style="font-size:12px; color:#aaa;">
          {{ r.frequency.title() }} · {{ r.acct_name or '?' }} · next {{ r.next_date }}
        </div>
      </div>
      <div style="text-align:right;">
        <div style="font-weight:700; font-size:15px; color:{{ '#e53935' if r.type=='expense' else '#43A047' }};">
          {{ '-' if r.type=='expense' else '+' }}{{ r.amount }}
        </div>
        <span class="badge badge-{{ r.type }}">{{ r.type }}</span>
      </div>
    </div>
    <div style="display:flex; gap:8px; margin-top:12px;">
      <form method="POST" action="/recurring/{{ r.id }}/toggle" style="flex:1;">
        <button class="btn btn-sm" style="width:100%; background:{{ '#aaa' if r.active else '#6C63FF' }};">
          {{ 'Pause' if r.active else 'Resume' }}
        </button>
      </form>
      <form method="POST" action="/recurring/{{ r.id }}/delete"
            onsubmit="return confirm('Delete this recurring rule?');" style="flex:1;">
        <button class="btn btn-sm btn-red" style="width:100%;">Delete</button>
      </form>
    </div>
  </div>
  {% endfor %}
  {% endif %}

  <div class="card">
    <div style="font-weight:700; font-size:15px; margin-bottom:14px;">New Recurring Rule</div>
    {% if accounts %}
    <form method="POST" action="/recurring/add">
      <div class="form-group">
        <label>Title</label>
        <input type="text" name="title" placeholder="e.g. Monthly Rent, Salary" required>
      </div>
      <div class="form-group">
        <label>Type</label>
        <select name="type">
          <option value="expense">Expense</option>
          <option value="income">Income</option>
        </select>
      </div>
      <div class="form-group">
        <label>Amount</label>
        <input type="number" name="amount" step="0.01" min="0.01" placeholder="0.00" required>
      </div>
      <div class="form-group">
        <label>Account</label>
        <select name="account_id" required>
          <option value="">Select account…</option>
          {% for a in accounts %}
          <option value="{{ a.id }}">{{ a.name }} ({{ a.currency }})</option>
          {% endfor %}
        </select>
      </div>
      <div class="form-group">
        <label>Category (optional)</label>
        <select name="category_id">
          <option value="">No category</option>
          {% for c in cats %}
          <option value="{{ c.id }}">{{ c.icon }} {{ c.name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="form-group">
        <label>Frequency</label>
        <select name="frequency">
          <option value="monthly">Monthly</option>
          <option value="weekly">Weekly</option>
          <option value="daily">Daily</option>
        </select>
      </div>
      <div class="form-group">
        <label>First occurrence</label>
        <input type="date" name="next_date" value="{{ today }}" required>
      </div>
      <button type="submit" class="btn">Add Rule</button>
    </form>
    {% else %}
    <div style="text-align:center; color:#bbb; padding:24px 0;">
      <a href="/accounts/add" class="btn">Add an account first</a>
    </div>
    {% endif %}
  </div>
</div>

<a href="/recurring" style="position:fixed;bottom:90px;right:20px;font-size:13px;color:#6C63FF;text-decoration:none;font-weight:600;background:white;padding:8px 14px;border-radius:20px;box-shadow:0 2px 8px rgba(0,0,0,0.1);">⟳ Recurring</a>
{{ nav }}
""" + FOOT

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
