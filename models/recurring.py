from datetime import date, datetime, timedelta

from db import fetch_all, fetch_one, execute, gen_id, get_conn

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
            (r['id'], r['next_date']),
        )
        if existing:
            continue
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO transactions(id,date,amount,type,account_id,category_id,note,recurring_id)"
                " VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                (gen_id(), r['next_date'], r['amount'], r['type'],
                 r['account_id'], r['category_id'], r['title'], r['id']),
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
