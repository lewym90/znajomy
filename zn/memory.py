"""Pamięć: fakty o rozmówcy z wpadkami (zapominanie) oraz otwarte wątki do powrotu."""
import random
import re

from . import clock, db


def _tokens(s):
    return set(re.findall(r"\w{3,}", s.lower()))


def add_fact(uid, text, importance):
    text = (text or "").strip()[:240]
    if not text:
        return None
    imp = max(1, min(5, int(importance or 2)))
    new = _tokens(text)
    for f in db.q("SELECT id,text,importance FROM facts WHERE user_id=?", (uid,)):
        old = _tokens(f["text"])
        if new and old and len(new & old) / float(len(new | old)) > 0.6:
            if imp > f["importance"]:
                db.x("UPDATE facts SET importance=? WHERE id=?", (imp, f["id"]))
            return None
    now = clock.now_ts()
    return db.x("INSERT INTO facts(user_id,text,importance,created_ts,last_ref_ts) VALUES(?,?,?,?,?)",
                (uid, text, imp, now, now))


def select(uid, persona, now_ts=None, limit=25):
    """Zwraca (pamiętane, zapomniane). Los jest stały w obrębie dnia (nie zmienia się co wiadomość)."""
    now_ts = now_ts or clock.now_ts()
    today = clock.at(now_ts).date().isoformat()
    fg = persona["traits"]["forgetfulness"]
    keep, forgot = [], []
    rows = db.q("SELECT * FROM facts WHERE user_id=? ORDER BY importance DESC, created_ts DESC", (uid,))
    for f in rows:
        age = (now_ts - f["created_ts"]) / 86400.0
        base = 0.97 if f["importance"] >= 4 else 0.9 if f["importance"] == 3 else 0.75
        p = base - fg * (0.2 + 0.4 * min(1.0, age / 60.0)) * (1.2 - f["importance"] * 0.15)
        if (now_ts - f["last_ref_ts"]) < 3 * 86400:
            p += 0.15
        p = max(0.15, min(0.99, p))
        rr = random.Random("%s|%s|%s" % (persona["seed"], f["id"], today)).random()
        (keep if rr < p else forgot).append(f)
    keep = keep[:limit]
    # zapominamy głównie rzeczy mniej ważne; o ważnych mówimy tylko, gdy los tak zdecydował
    return [f["text"] for f in keep], [f["text"] for f in forgot[:4]]


def touch(uid, text):
    low = _tokens(text)
    now = clock.now_ts()
    for f in db.q("SELECT id,text FROM facts WHERE user_id=?", (uid,)):
        t = _tokens(f["text"])
        if t and len(t & low) >= 2:
            db.x("UPDATE facts SET last_ref_ts=? WHERE id=?", (now, f["id"]))


def add_thread(uid, text, due_ts):
    return db.x("INSERT INTO threads(user_id,text,due_ts,created_ts) VALUES(?,?,?,?)",
                (uid, (text or "")[:240], due_ts, clock.now_ts()))


def due_threads(uid, now_ts=None):
    now_ts = now_ts or clock.now_ts()
    return db.q("SELECT * FROM threads WHERE user_id=? AND status='open' AND due_ts<=? ORDER BY due_ts", (uid, now_ts))


def close_thread(tid):
    db.x("UPDATE threads SET status='done' WHERE id=?", (tid,))
