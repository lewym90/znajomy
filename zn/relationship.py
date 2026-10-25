"""Relacja jako historia zdarzeń z ciężarem, zanikiem i bliznami.
Nie ma suwaków i etykiet widocznych dla użytkownika. Kod trzyma konsekwencję poza modelem."""
import math
import random

from . import clock, db

BASE = {
    "insult": -3.0, "ignored": -1.0, "betrayal": -5.0, "disagreement": -0.6, "conflict": -1.2,
    "support": 1.2, "apology": 1.5, "joke": 0.4, "opened_up": 1.0, "thanks": 0.5, "kindness": 1.0,
}


def add_event(uid, persona, kind, severity, summary, interp, lasting=False):
    if kind not in BASE:
        return None
    sev = max(1, min(5, int(severity or 3)))
    w = BASE[kind] * (sev / 3.0)
    tr = persona["traits"]
    if w < 0:
        half = 14.0 * (1 + tr["pride"] * 1.5 + (1 - tr["forgiveness"]) * 2)
        scar = 1 if (lasting or sev >= 4) else 0
        if scar:
            half = max(half, 90.0)
    else:
        half, scar = 45.0, 0
    return db.x("INSERT INTO rel_events(user_id,ts,kind,weight,halflife,scar,summary,interp) VALUES(?,?,?,?,?,?,?,?)",
                (uid, clock.now_ts(), kind, w, half, scar, (summary or "")[:300], (interp or "")[:300]))


def metrics(uid, persona, now_ts=None):
    now_ts = now_ts or clock.now_ts()
    evs = db.q("SELECT * FROM rel_events WHERE user_id=?", (uid,))
    hurt = warm = bond_pos = 0.0
    for e in evs:
        age = (now_ts - e["ts"]) / 86400.0
        f = 0.5 ** (age / e["halflife"])
        if e["weight"] < 0:
            hurt += -e["weight"] * max(f, 0.4 if e["scar"] else 0.0)
        else:
            warm += e["weight"] * f
            bond_pos += e["weight"] * (0.5 ** (age / 150.0))
    days = db.q("SELECT COUNT(DISTINCT CAST(ts/86400 AS INTEGER)) AS n FROM messages WHERE user_id=? AND role='user'", (uid,))[0]["n"] or 0
    bond = min(12.0, 1.4 * math.sqrt(days) + 0.6 * bond_pos)
    pride = persona["traits"]["pride"]
    p_hurt = hurt * (0.8 + 0.5 * pride)
    temp = max(-1.0, min(1.0, (warm - p_hurt) / (bond + 3.0)))
    return {"hurt": hurt, "p_hurt": p_hurt, "warm": warm, "bond": bond, "temp": temp, "days": days}


def label(m, peak_bond):
    b = m["bond"]
    base = ("dopiero się poznajecie, to prawie obcy ludzie" if b < 1.5 else
            "znacie się trochę, to znajomość, a nie bliska relacja" if b < 3.5 else
            "zżywacie się, jest już sporo zaufania" if b < 6.5 else
            "to bliska, zadomowiona relacja")
    if peak_bond >= 4 and m["temp"] < -0.2:
        base += "; kiedyś byliście bliżej, ale coś się popsuło i jest dystans"
    return base


def temp_text(t):
    return ("ciepło i życzliwie" if t > 0.3 else "neutralnie" if t > -0.2 else
            "chłodno, z rezerwą" if t > -0.6 else "bardzo chłodno, z niechęcią")


def top_events(uid, n=6, now_ts=None):
    now_ts = now_ts or clock.now_ts()
    out = []
    for e in db.q("SELECT * FROM rel_events WHERE user_id=?", (uid,)):
        age = (now_ts - e["ts"]) / 86400.0
        f = 0.5 ** (age / e["halflife"])
        if e["weight"] < 0:
            f = max(f, 0.4 if e["scar"] else 0.0)
        out.append((abs(e["weight"]) * f, e))
    out.sort(key=lambda x: -x[0])
    return [e for s, e in out[:n] if s > 0.15]


def check_closure(uid, persona, st, rng=None):
    """Zamknięcie relacji, gdy nagromadzona rana przekroczy próg postaci. Zwraca True, jeśli zamknięto."""
    if st.get("closed"):
        return False
    m = metrics(uid, persona)
    tr = persona["traits"]
    thr = 5.0 + 9.0 * tr["forgiveness"] - 3.0 * tr["pride"]
    # zamknąć relację można dopiero, gdy jest co zamykać: kilka dni znajomości i realna więź.
    # Obelga od niemal obcego człowieka to zły dzień, a nie koniec świata.
    if m["p_hurt"] >= thr and m["bond"] >= 3.0 and m["days"] >= 4:
        # "na stałe" od razu tylko przy mało wybaczającym charakterze i naprawdę bliskiej relacji;
        # w pozostałych przypadkach stałość przychodzi po nieudanych próbach naprawy (try_repair)
        final = tr["forgiveness"] < 0.3 and m["bond"] >= 5.0

        def f(s):
            s["closed"] = {"ts": clock.now_ts(), "final": final, "attempts": 0}
        db.update_state(uid, f)
        return True
    return False


def try_repair(uid, persona, st, rng=None):
    """Próba naprawy po przeprosinach. Zwraca 'reopened' | 'refused' | 'final' | None."""
    c = st.get("closed")
    if not c:
        return None
    if c.get("final"):
        return "final"
    rng = rng or random.Random()
    m = metrics(uid, persona)
    tr = persona["traits"]
    p = tr["forgiveness"] * 0.7 + (0.2 if m["bond"] > 5 else 0.0) - 0.2 * tr["pride"]
    if rng.random() < max(0.05, min(0.9, p)):
        def f(s):
            s["closed"] = None
            s["reopened_ts"] = clock.now_ts()
        db.update_state(uid, f)
        return "reopened"

    def g(s):
        s["closed"]["attempts"] = s["closed"].get("attempts", 0) + 1
        if s["closed"]["attempts"] >= 2:
            s["closed"]["final"] = True
    db.update_state(uid, g)
    return "refused"
