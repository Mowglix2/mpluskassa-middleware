import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, filename):
        self.filename = filename
        self.init()

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.filename, timeout=15)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def init(self):
        with self.conn() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('''CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY, store_id TEXT, resource_href TEXT NOT NULL,
                state TEXT NOT NULL, event_id TEXT, raw_order TEXT, mplus_payload TEXT,
                mplus_result TEXT, error TEXT, created_at TEXT, updated_at TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, received_at TEXT)''')

    def ingest(self, event):
        eid = str(event['event_id'])
        meta = event['meta']
        oid = str(meta['resource_id'])
        with self.conn() as c:
            n = c.execute('INSERT OR IGNORE INTO events VALUES (?,?)', (eid, now())).rowcount
            c.execute('''INSERT OR IGNORE INTO orders(order_id,store_id,resource_href,state,event_id,created_at,updated_at)
                         VALUES (?,?,?,?,?,?,?)''', (oid, meta.get('user_id'), event['resource_href'], 'queued', eid, now(), now()))
        return bool(n), oid

    def get(self, oid):
        with self.conn() as c:
            row = c.execute('SELECT * FROM orders WHERE order_id=?', (oid,)).fetchone()
            return dict(row) if row else None

    def list(self, limit=100):
        with self.conn() as c:
            return [dict(r) for r in c.execute('SELECT * FROM orders ORDER BY created_at DESC LIMIT ?', (limit,))]

    def update(self, oid, state, **fields):
        fields = {**fields, 'state': state, 'updated_at': now()}
        with self.conn() as c:
            c.execute('UPDATE orders SET '+', '.join(k+'=?' for k in fields)+' WHERE order_id=?', (*fields.values(), oid))

    def claim(self):
        with self.conn() as c:
            c.execute('BEGIN IMMEDIATE')
            r = c.execute("SELECT order_id FROM orders WHERE state='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not r:
                return None
            c.execute("UPDATE orders SET state='processing', updated_at=? WHERE order_id=?",(now(),r['order_id']))
            return r['order_id']
