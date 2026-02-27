import decimal
import uuid

import psycopg2
import psycopg2.extras
from flask import g

from config import DATABASE_URL, CUR_SYM


# ── Connection ──────────────────────────────────────────────────────────────

def get_conn():
    if 'conn' not in g:
        url = DATABASE_URL
        if 'sslmode' not in url:
            url += ('&' if '?' in url else '?') + 'sslmode=require'
        g.conn = psycopg2.connect(url)
    return g.conn


def _close_conn(e=None):
    conn = g.pop('conn', None)
    if conn:
        conn.close()


# ── Query helpers ────────────────────────────────────────────────────────────

def gen_id():
    return str(uuid.uuid4())[:8]


def _dictify(row):
    if not row:
        return None
    return {k: (float(v) if isinstance(v, decimal.Decimal) else v) for k, v in dict(row).items()}


def fetch_one(sql, p=()):
    with get_conn().cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
        c.execute(sql, p)
        return _dictify(c.fetchone())


def fetch_all(sql, p=()):
    with get_conn().cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
        c.execute(sql, p)
        return [_dictify(r) for r in c.fetchall()]


def execute(sql, p=(), commit=True):
    conn = get_conn()
    with conn.cursor() as c:
        c.execute(sql, p)
    if commit:
        conn.commit()


# ── Formatting ───────────────────────────────────────────────────────────────

def fmt(amount, currency='USD'):
    sym = CUR_SYM.get(currency, currency)
    if currency in ('UZS', 'KZT', 'JPY'):
        return f"{sym} {amount:,.0f}"
    return f"{sym}{amount:,.2f}"


# ── Schema ───────────────────────────────────────────────────────────────────

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
        # Migrate existing tables: add columns that may not exist yet
        c.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'USD'")
        c.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category_id VARCHAR(8)")
        c.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS to_account_id VARCHAR(8)")
        c.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS note TEXT")
        c.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS recurring_id VARCHAR(8)")

        c.execute("SELECT COUNT(*) FROM categories")
        if c.fetchone()[0] == 0:
            cats = [
                ('expense', 'Food & Dining',   '🍔', '#FF6B6B'),
                ('expense', 'Transport',        '🚗', '#45B7D1'),
                ('expense', 'Shopping',         '🛍', '#A29BFE'),
                ('expense', 'Entertainment',    '🎬', '#F7B731'),
                ('expense', 'Health',           '💊', '#96CEB4'),
                ('expense', 'Bills',            '💡', '#FD79A8'),
                ('expense', 'Education',        '📚', '#4ECDC4'),
                ('expense', 'Other',            '💸', '#bbb'),
                ('income',  'Salary',           '💼', '#43A047'),
                ('income',  'Freelance',        '💻', '#6C63FF'),
                ('income',  'Investment',       '📈', '#F7B731'),
                ('income',  'Other Income',     '💰', '#4ECDC4'),
            ]
            for typ, name, icon, color in cats:
                c.execute(
                    "INSERT INTO categories(id,name,type,icon,color) VALUES(%s,%s,%s,%s,%s)",
                    (gen_id(), name, typ, icon, color),
                )
    conn.commit()
    _initialized = True


# ── Flask integration ────────────────────────────────────────────────────────

def init_app(app):
    """Register DB teardown with the Flask app."""
    app.teardown_appcontext(_close_conn)
