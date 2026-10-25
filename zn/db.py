"""SQLite. Jedno połączenie, jeden zamek. Treści rozmów nigdy nie trafiają do logów."""
import copy
import json
import sqlite3
import threading

from . import config

_lock = threading.RLock()
_conn = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, token_hash TEXT UNIQUE, created_ts REAL, adult_ok INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS persona(user_id INTEGER PRIMARY KEY, json TEXT);
CREATE TABLE IF NOT EXISTS state(user_id INTEGER PRIMARY KEY, json TEXT);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, ts REAL, role TEXT, text TEXT, read_ts REAL, answered INTEGER DEFAULT 0, kind TEXT DEFAULT 'chat');
CREATE INDEX IF NOT EXISTS ix_msg ON messages(user_id, id);
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, text TEXT, typing_from REAL, deliver_at REAL, kind TEXT DEFAULT 'chat');
CREATE TABLE IF NOT EXISTS rel_events(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, ts REAL, kind TEXT, weight REAL, halflife REAL, scar INTEGER, summary TEXT, interp TEXT);
CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, text TEXT, importance INTEGER, created_ts REAL, last_ref_ts REAL);
CREATE TABLE IF NOT EXISTS threads(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, text TEXT, due_ts REAL, status TEXT DEFAULT 'open', created_ts REAL);
CREATE TABLE IF NOT EXISTS push_subs(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, endpoint TEXT UNIQUE, sub_json TEXT);
"""

DEFAULT_STATE = {
    "msg_count": 0,
    "style": {},
    "role": {},
    "gender_score": {"f": 0, "m": 0},
    "user_gender": None,
    "minor": False,
    "closed": None,          # {"ts":..., "final":bool, "attempts":int}
    "reopened_ts": None,
    "peak_bond": 0.0,
    "reply_due": None,
    "read_due": None,
    "fail": 0,
    "next_proactive": None,
    "unanswered_char": 0,
    "last_char_ts": 0.0,
    "last_user_ts": 0.0,
    "last_seen": 0.0,
    "last_ignored_event": 0.0,
    "crisis_until": 0.0,
    "name_told": False,
    "analyzed_id": 0,
    "day_cache": {},
    "recent_openers": [],
}

TABLES_BY_USER = ["persona", "state", "messages", "outbox", "rel_events", "facts", "threads", "push_subs"]


def init(path=None):
    global _conn
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    p = str(path or (config.DATA_DIR / "znajomy.db"))
    with _lock:
        _conn = sqlite3.connect(p, check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(SCHEMA)


def q(sql, args=()):
    with _lock:
        return [dict(r) for r in _conn.execute(sql, args).fetchall()]


def q1(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def x(sql, args=()):
    with _lock:
        return _conn.execute(sql, args).lastrowid


def get_persona(uid):
    r = q1("SELECT json FROM persona WHERE user_id=?", (uid,))
    return json.loads(r["json"]) if r else None


def save_persona(uid, p):
    x("INSERT OR REPLACE INTO persona(user_id,json) VALUES(?,?)", (uid, json.dumps(p, ensure_ascii=False)))


def get_state(uid):
    r = q1("SELECT json FROM state WHERE user_id=?", (uid,))
    s = copy.deepcopy(DEFAULT_STATE)
    if r:
        s.update(json.loads(r["json"]))
    return s


def set_state(uid, s):
    x("INSERT OR REPLACE INTO state(user_id,json) VALUES(?,?)", (uid, json.dumps(s, ensure_ascii=False)))


def update_state(uid, fn):
    """Atomowa zmiana stanu: fn(s) mutuje słownik."""
    with _lock:
        s = get_state(uid)
        fn(s)
        set_state(uid, s)
        return s


def wipe_user(uid):
    with _lock:
        for t in TABLES_BY_USER:
            _conn.execute(f"DELETE FROM {t} WHERE user_id=?", (uid,))
        _conn.execute("DELETE FROM users WHERE id=?", (uid,))
