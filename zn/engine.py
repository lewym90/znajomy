"""Silnik: odbiór wiadomości, czas odpowiedzi, generowanie, analiza, inicjatywa postaci.
Zasada: stan i konsekwencję liczy kod. Model tylko wypowiada decyzję głosem postaci.
Zasada blokad: wywołań modelu NIGDY nie robimy pod LOCK."""
import hashlib
import logging
import math
import random
import re
import secrets
import threading
from datetime import timedelta

from . import (clock, config, day as D, db, humanize as H, llm, memory as M, persona as P, prompts as PR,
               push, relationship as R, signals as G, style as S)

log = logging.getLogger("znajomy")
LOCK = threading.RLock()

WEEKDAYS = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
BLOCK_FALLBACK = ["hm, nie wiem co na to powiedzieć", "dobra, zostawmy ten temat", "eee, no nie wiem", "ok"]
ROLE_TXT = {
    "parent": "kogoś w rodzaju rodzica lub starszego opiekuna (szuka rady i oparcia)",
    "friend": "kumpla lub przyjaciela",
    "romantic": "bliską osobę, między wami może iskrzyć",
    "confidant": "osobę, przed którą można się wygadać",
    "sibling": "rodzeństwo",
}


def _sha(t):
    return hashlib.sha256(t.encode()).hexdigest()


def _lognormal(r, median, sigma=0.6):
    return median * math.exp(r.gauss(0, sigma))


# ---------------------------------------------------------------- użytkownicy
def create_user(adult_ok):
    token = secrets.token_hex(24)
    with LOCK:
        uid = db.x("INSERT INTO users(token_hash,created_ts,adult_ok) VALUES(?,?,?)",
                   (_sha(token), clock.now_ts(), 1 if adult_ok else 0))
        db.save_persona(uid, P.birth())
        db.set_state(uid, dict(db.DEFAULT_STATE))
    return uid, token


def user_by_token(token):
    if not token:
        return None
    r = db.q1("SELECT id FROM users WHERE token_hash=?", (_sha(token),))
    return r["id"] if r else None


def forget(uid):
    with LOCK:
        db.wipe_user(uid)


# ---------------------------------------------------------------- dzień i sytuacja
def _plan(uid, persona, d):
    key = d.isoformat()
    st = db.get_state(uid)
    if key in st["day_cache"]:
        return st["day_cache"][key]
    m = R.metrics(uid, persona)
    plan = D.build(persona, d, m["p_hurt"])

    def f(s):
        s["day_cache"][key] = plan
        for k in sorted(s["day_cache"])[:-4]:
            del s["day_cache"][k]
    db.update_state(uid, f)
    return plan


def _situation(uid, persona, now_ts):
    now = clock.at(now_ts)
    d = now.date()
    plan = _plan(uid, persona, d)
    prev = _plan(uid, persona, d - timedelta(days=1))
    nxt = _plan(uid, persona, d + timedelta(days=1))
    nw = clock.day_ts(d + timedelta(days=1), nxt["wake"])
    return plan, D.status(plan, prev, nw, now)


# ---------------------------------------------------------------- wiadomość od użytkownika
def handle_user_message(uid, text):
    text = (text or "").strip()[:4000]
    if not text:
        return None
    with LOCK:
        now = clock.now_ts()
        persona = db.get_persona(uid)
        if persona is None:
            return None
        st = db.get_state(uid)
        first_ever = db.q1("SELECT COUNT(*) n FROM messages WHERE user_id=?", (uid,))["n"] == 0
        mid = db.x("INSERT INTO messages(user_id,ts,role,text) VALUES(?,?,?,?)", (uid, now, "user", text))
        st["msg_count"] += 1
        S.update(st["style"], S.features(text), st["msg_count"])
        cue = G.gender_cue(text)
        gs = st["gender_score"]
        gs["f"] += cue["f"]
        gs["m"] += cue["m"]
        if persona["gender"] is None:
            g = None
            if gs["f"] - gs["m"] >= 2:
                g = "f"
            elif gs["m"] - gs["f"] >= 2:
                g = "m"
            elif st["msg_count"] >= 4:
                g = random.choice(["m", "f"])
            if g:
                P.assign_gender(persona, g)
                db.save_persona(uid, persona)
        ug = G.user_gender(text)
        if ug:
            st["user_gender"] = ug
        if G.minor(text):
            st["minor"] = True
        if G.crisis(text):
            st["crisis_until"] = now + 6 * 3600
        for k in list(st["role"]):
            st["role"][k] *= 0.97
        for k, v in G.roles(text).items():
            st["role"][k] = min(1.0, st["role"].get(k, 0.0) + 0.15 * v)
        prev_user = st["last_user_ts"]
        st["last_user_ts"] = now
        st["unanswered_char"] = 0
        M.touch(uid, text)
        if st["reply_due"] is None:
            rng = random.Random()
            if first_ever:
                delay, rd = rng.uniform(5, 40), rng.uniform(2, 8)
            elif now < st["crisis_until"]:
                delay, rd = rng.uniform(10, 45), rng.uniform(2, 8)
            else:
                plan, status = _situation(uid, persona, now)
                m = R.metrics(uid, persona, now)
                hot = (now - st["last_char_ts"]) < 600
                delay = D.reply_delay(rng, status, persona, plan["mood"], hot, m["bond"], now)
                if st["closed"]:
                    delay *= 2
                if status["state"] == "free":
                    rd = rng.uniform(3, 40)
                elif status["state"] == "busy":
                    rd = rng.uniform(60, 900)
                else:
                    rd = max(0, (status["until"] or now) - now) + rng.uniform(60, 900)
                if config.FAST:
                    rd = min(rd, 3.0)
                rd = max(2.0, min(rd, delay - 2.0))
            st["reply_due"] = now + delay
            st["read_due"] = now + rd
        db.set_state(uid, st)
    return mid


# ---------------------------------------------------------------- tick
def tick():
    for u in db.q("SELECT id FROM users"):
        uid = u["id"]
        try:
            _deliver(uid)
            _reads(uid)
            now = clock.now_ts()
            st = db.get_state(uid)
            if st["reply_due"] and now >= st["reply_due"]:
                respond(uid)
            else:
                _ignored_check(uid)
                _proactive(uid)
        except Exception:
            log.exception("tick uid=%s", uid)


def _deliver(uid):
    now = clock.now_ts()
    rows = db.q("SELECT * FROM outbox WHERE user_id=? AND deliver_at<=? ORDER BY deliver_at,id", (uid, now))
    for r in rows:
        with LOCK:
            db.x("DELETE FROM outbox WHERE id=?", (r["id"],))
            db.x("INSERT INTO messages(user_id,ts,role,text,kind) VALUES(?,?,?,?,?)",
                 (uid, r["deliver_at"], "char", r["text"], r["kind"]))

            def f(s, r=r):
                s["last_char_ts"] = r["deliver_at"]
                s["last_seen"] = r["deliver_at"]
                if r["kind"] == "proactive":
                    s["unanswered_char"] += 1
            db.update_state(uid, f)
            persona = db.get_persona(uid)
        title = persona["name"] if (persona and persona["name"] and db.get_state(uid)["name_told"]) else "Znajomy"
        try:
            push.notify(uid, title, r["text"])
        except Exception:
            log.exception("push")


def _reads(uid):
    now = clock.now_ts()
    with LOCK:
        st = db.get_state(uid)
        if st["read_due"] and now >= st["read_due"]:
            db.x("UPDATE messages SET read_ts=? WHERE user_id=? AND role='user' AND read_ts IS NULL", (now, uid))

            def f(s):
                s["read_due"] = None
                s["last_seen"] = max(s["last_seen"], now)
            db.update_state(uid, f)


# ---------------------------------------------------------------- kontekst dla modelu
def _intimacy(uid, persona, st, m, mood, text_all, now):
    if not G.sexual(text_all):
        return None
    u = db.q1("SELECT adult_ok FROM users WHERE id=?", (uid,))
    if st["minor"] or not (u and u["adult_ok"]):
        return "minor"
    tr = persona["traits"]
    if m["bond"] < 3.0 + 4.0 * (1 - tr["romantic_openness"]):
        return "too_early"
    if st["role"].get("romantic", 0.0) < 0.25:
        return "not_that_way"
    if m["temp"] < -0.1:
        return "cold"
    if mood < -0.3:
        return "not_today"
    day = clock.at(now).date().isoformat()
    rr = random.Random("%s|%s|intim" % (persona["seed"], day)).random()
    p = 0.25 + 0.6 * tr["romantic_openness"] * (0.5 + mood / 2.0)
    return "open" if rr < p else "not_today"


def _history(uid, limit=40):
    rows = db.q("SELECT role,text FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit))
    rows.reverse()
    return [{"role": "user" if r["role"] == "user" else "model", "text": r["text"]} for r in rows]


def _build_ctx(uid, persona, st, now, un, mode, reason=None):
    plan, status = _situation(uid, persona, now)
    m = R.metrics(uid, persona, now)
    if m["bond"] > st["peak_bond"]:
        db.update_state(uid, lambda s: s.__setitem__("peak_bond", max(s["peak_bond"], m["bond"])))
        st["peak_bond"] = max(st["peak_bond"], m["bond"])
    nd = clock.at(now)
    h = nd.hour + nd.minute / 60.0
    past, future = D.lines(plan, h)
    facts, forgot = M.select(uid, persona, now)
    rng = random.Random()
    text_all = " ".join(x["text"] for x in un)
    crisis = now < st["crisis_until"] or G.crisis(text_all)
    mood = plan["mood"]
    closed = bool(st["closed"])
    directives = []
    if st["msg_count"] <= 1 and mode == "reply":
        directives.append("To Wasz pierwszy kontakt, dopiero kogoś poznajesz. Przywitaj się naturalnie.")
    decision = _intimacy(uid, persona, st, m, mood, text_all, now) if mode == "reply" else None
    if decision == "minor" or st["minor"]:
        directives.append(PR.MINOR)
    elif decision:
        directives.append(PR.INTIMACY[decision])
    if crisis:
        directives.append(PR.CRISIS)
    if closed and not crisis:
        directives.append("Relacja jest zamknięta. Odpowiedz bardzo krótko, chłodno i rzeczowo, bez ciepła.")
    if mode == "proactive":
        directives.append("Piszesz pierwszy z własnej inicjatywy. " + (reason or ""))
    emotional = crisis or G.roles(text_all).get("confidant", 0) > 0
    long_user = len(text_all.split()) > 40
    if crisis:
        lh = "tyle, ile trzeba, ale po ludzku i bez wykładu"
    elif closed:
        lh = H.LEN_HINTS[0][0]
    else:
        lh = H.length_hint(rng, st["style"], mood, emotional, long_user)
    role_text = ""
    roles = {k: v for k, v in st["role"].items() if v >= 0.25 and not (st["minor"] and k == "romantic")}
    if roles:
        top = max(roles, key=roles.get)
        role_text = ("Rozmówca zaczyna Cię traktować jak: %s. Nie ogłaszaj tego, po prostu reaguj stosownie, "
                     "w takim zakresie, w jakim to naturalne i zasłużone." % ROLE_TXT.get(top, top))
    recent_char = [r["text"] for r in db.q("SELECT text FROM messages WHERE user_id=? AND role='char' ORDER BY id DESC LIMIT 8", (uid,))]
    openers = []
    for t in recent_char[:6]:
        o = H.opener(t)
        if o and o not in openers:
            openers.append(o)
    if status["state"] == "sleeping":
        status_text = "wyrwany ze snu powiadomieniem, zaspany"
    elif status["state"] == "busy":
        status_text = "jesteś w trakcie: %s; zerkasz w telefon" % status["why"]
    else:
        status_text = ""
    gap_text = ""
    if un:
        prev = db.q1("SELECT ts FROM messages WHERE user_id=? AND id<? ORDER BY id DESC", (uid, un[0]["id"]))
        if prev and un[0]["ts"] - prev["ts"] > 6 * 3600 and not first_msg(uid, un[0]["id"]):
            gap_text = "Rozmówca odpisał dopiero po %d godz." % int((un[0]["ts"] - prev["ts"]) / 3600)
    if st["last_user_ts"] and mode == "proactive" and now - st["last_user_ts"] > 2 * 86400:
        gap_text = "Rozmówca nie odzywał się od %d dni." % int((now - st["last_user_ts"]) / 86400)
    rel_events = [{"summary": e["summary"], "interp": e["interp"]} for e in R.top_events(uid, 6, now) if e["summary"]]
    trans = db.q("SELECT role,text FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 14", (uid,))
    trans.reverse()
    transcript = "\n".join("%s: %s" % ("ROZMÓWCA" if t["role"] == "user" else "POSTAĆ", t["text"]) for t in trans)
    ctx = dict(
        persona=persona, persona_sum=P.summary(persona), name=persona["name"], gender=persona["gender"],
        name_told=st["name_told"],
        now_str="%s, %s" % (WEEKDAYS[nd.weekday()], nd.strftime("%d.%m.%Y, %H:%M")),
        mood_label=D.mood_label(mood), mood_dir=D.mood_directive(plan, persona),
        day_past=past, day_future=future, status_text=status_text,
        rel_label=R.label(m, st["peak_bond"]), rel_temp=R.temp_text(m["temp"]), rel_events=rel_events,
        closed=closed, reopened=bool(st["reopened_ts"] and now - st["reopened_ts"] < 14 * 86400),
        gap_text=gap_text, user_gender=st["user_gender"], role_text=role_text,
        style_text=S.describe(st["style"], persona, st["msg_count"]),
        facts=facts, forgot=forgot, threads=[], length_hint=lh, directives=directives,
        avoid_openers=openers[:4], known_facts=facts, transcript=transcript,
    )
    ctx["_decision"] = decision
    ctx["_crisis"] = crisis
    ctx["_recent_char"] = recent_char
    return ctx


def first_msg(uid, mid):
    r = db.q1("SELECT COUNT(*) n FROM messages WHERE user_id=? AND id<?", (uid, mid))
    return r["n"] == 0


# ---------------------------------------------------------------- odpowiedź
def _queue(uid, bubbles, kind, start_ts, rng):
    t = start_ts
    for i, b in enumerate(bubbles):
        typing = min(25.0, 1.0 + 0.05 * len(b)) + rng.uniform(0.3, 1.5)
        if config.FAST:
            typing = min(typing, 2.0) * 0.3
        deliver = t + typing
        db.x("INSERT INTO outbox(user_id,text,typing_from,deliver_at,kind) VALUES(?,?,?,?,?)",
             (uid, b, t, deliver, kind if i == 0 else "chat"))
        t = deliver + rng.uniform(0.5, 2.5) * (0.3 if config.FAST else 1.0)


def _generate(ctx, history, rng, extra=None):
    system = PR.system_prompt(ctx)
    if extra:
        system += "\n" + extra
    route = "intimate" if ctx.get("_decision") == "open" and config.INTIMATE_LLM else "main"
    return llm.generate(system, history, temperature=rng.uniform(0.85, 1.1), max_tokens=500, route=route)


def respond(uid):
    now = clock.now_ts()
    with LOCK:
        persona = db.get_persona(uid)
        st = db.get_state(uid)
        un = db.q("SELECT * FROM messages WHERE user_id=? AND role='user' AND answered=0 ORDER BY id", (uid,))
        if not un:
            db.update_state(uid, lambda s: s.__setitem__("reply_due", None))
            return
    rng = random.Random()
    crisis_now = now < st["crisis_until"] or G.crisis(" ".join(x["text"] for x in un))
    if st["closed"] and not crisis_now:
        analyze(uid)   # przeprosiny mogą otworzyć relację
        with LOCK:
            st = db.get_state(uid)
        if st["closed"]:
            p_ignore = 0.85 if st["closed"].get("final") else 0.6
            if rng.random() < p_ignore:
                with LOCK:
                    _mark_answered(uid, un)
                    db.update_state(uid, lambda s: s.__setitem__("reply_due", None))
                return
    with LOCK:
        ctx = _build_ctx(uid, persona, st, now, un, "reply")
    history = _history(uid)
    try:
        raw = _generate(ctx, history, rng)
    except llm.Blocked:
        raw = rng.choice(BLOCK_FALLBACK)
    except llm.LLMError as e:
        log.warning("llm: %s", e)
        with LOCK:
            def f(s):
                s["fail"] += 1
                s["reply_due"] = None if s["fail"] >= 5 else clock.now_ts() + (3 if config.FAST else 120)
            db.update_state(uid, f)
        return
    text = H.clean(raw)
    if H.too_similar(text, ctx["_recent_char"]):
        try:
            text = H.clean(_generate(ctx, history, rng, "Zacznij wypowiedź inaczej niż zwykle."))
        except llm.LLMError:
            pass
    bubbles = H.bubbles(text)
    if not bubbles:
        bubbles = [rng.choice(BLOCK_FALLBACK)]
    rate = S.typo_rate(st["style"], st["msg_count"]) if not ctx["_crisis"] else 0.0
    out = []
    for b in bubbles:
        out += H.maybe_typo(rng, b, rate)
    with LOCK:
        _queue(uid, out, "chat", clock.now_ts(), rng)
        _mark_answered(uid, un)

        def f(s):
            s["reply_due"] = None
            s["fail"] = 0
            s["next_proactive"] = None
            s["recent_openers"] = (s["recent_openers"] + [H.opener(text)])[-8:]
            if persona["name"] and persona["name"].lower() in text.lower():
                s["name_told"] = True
        db.update_state(uid, f)
    analyze(uid)


def _mark_answered(uid, un):
    ids = [x["id"] for x in un]
    db.x("UPDATE messages SET answered=1 WHERE user_id=? AND id<=?", (uid, max(ids)))


# ---------------------------------------------------------------- analiza
def analyze(uid):
    with LOCK:
        persona = db.get_persona(uid)
        st = db.get_state(uid)
        new_user = db.q("SELECT id FROM messages WHERE user_id=? AND role='user' AND id>?", (uid, st["analyzed_id"]))
        if not new_user:
            return
        now = clock.now_ts()
        un = db.q("SELECT * FROM messages WHERE user_id=? AND role='user' ORDER BY id DESC LIMIT 1", (uid,))
        ctx = _build_ctx(uid, persona, st, now, [], "analysis")
        last_id = db.q1("SELECT MAX(id) m FROM messages WHERE user_id=?", (uid,))["m"]
    payload = PR.analysis_payload(ctx)
    try:
        raw = llm.generate(PR.ANALYSIS_SYSTEM, [{"role": "user", "text": payload}], temperature=0.2,
                           max_tokens=1200, json_mode=True)
        data = llm.extract_json(raw)
    except Exception as e:
        log.warning("analiza: %s", type(e).__name__)
        with LOCK:
            db.update_state(uid, lambda s: s.__setitem__("analyzed_id", last_id))
        return
    now = clock.now_ts()
    with LOCK:
        st = db.get_state(uid)
        for f in data.get("facts") or []:
            M.add_fact(uid, f.get("text"), f.get("importance"))
        for f in data.get("followups") or []:
            try:
                hrs = float(f.get("in_hours", 24))
            except (TypeError, ValueError):
                hrs = 24.0
            hrs = max(1.0, min(24 * 14.0, hrs))
            M.add_thread(uid, f.get("text"), now + hrs * 3600 + random.uniform(0, 3600))
        for ev in data.get("events") or []:
            kind = ev.get("kind")
            if kind == "apology" and st["closed"]:
                R.try_repair(uid, persona, db.get_state(uid))
            R.add_event(uid, persona, kind, ev.get("severity", 3), ev.get("summary"),
                        ev.get("interpretation"), bool(ev.get("lasting")))
        rs = data.get("role_signals") or {}

        def f(s):
            for k, v in rs.items():
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    continue
                s["role"][k] = max(0.0, min(1.0, 0.8 * s["role"].get(k, 0.0) + 0.2 * v))
            try:
                if int(data.get("crisis", 0)) >= 2:
                    s["crisis_until"] = max(s["crisis_until"], now + 6 * 3600)
            except (TypeError, ValueError):
                pass
            if data.get("minor_signal") is True:
                s["minor"] = True
            s["analyzed_id"] = last_id
        db.update_state(uid, f)
        R.check_closure(uid, persona, db.get_state(uid))


# ---------------------------------------------------------------- inicjatywa postaci
def _ignored_check(uid):
    now = clock.now_ts()
    with LOCK:
        persona = db.get_persona(uid)
        st = db.get_state(uid)
        if st["unanswered_char"] < 1 or st["closed"]:
            return
        if now - st["last_char_ts"] < 36 * 3600 or now - st["last_ignored_event"] < 36 * 3600:
            return
        m = R.metrics(uid, persona, now)
        if m["bond"] < 3:
            return
        R.add_event(uid, persona, "ignored", 2, "Odezwałem się, a w odpowiedzi cisza",
                    "Zabolało, że zostałem zlany, choć byliśmy blisko", False)
        db.update_state(uid, lambda s: s.__setitem__("last_ignored_event", now))
        R.check_closure(uid, persona, db.get_state(uid))


def _proactive(uid):
    now = clock.now_ts()
    reason = None
    thread_id = None
    with LOCK:
        persona = db.get_persona(uid)
        if persona is None or persona["gender"] is None:
            return
        st = db.get_state(uid)
        if st["reply_due"] or st["closed"] or st["msg_count"] < 3:
            return
        if db.q1("SELECT COUNT(*) n FROM outbox WHERE user_id=?", (uid,))["n"]:
            return
        if now - st["last_user_ts"] < 1200:
            return
        rng = random.Random()
        m = R.metrics(uid, persona, now)
        due = M.due_threads(uid, now)
        if st["next_proactive"] is None and not due:
            med = max(6.0, 22.0 - m["bond"] * 1.2) * 3600
            if config.FAST:
                med = 30.0
            db.update_state(uid, lambda s: s.__setitem__("next_proactive", now + _lognormal(rng, med)))
            return
        if not due and now < st["next_proactive"]:
            return
        plan, status = _situation(uid, persona, now)

        def push_next(sec):
            db.update_state(uid, lambda s: s.__setitem__("next_proactive", now + sec))
        if status["state"] == "sleeping":
            push_next(max(0, (status["until"] or now) - now) + rng.uniform(600, 7200))
            return
        if status["state"] == "busy" and rng.random() < 0.7:
            push_next(rng.uniform(1800, 7200))
            return
        if st["unanswered_char"] >= 2 and now - st["last_char_ts"] < 24 * 3600:
            push_next(12 * 3600)
            return
        if m["p_hurt"] > 3 and persona["traits"]["pride"] > 0.6 and not due:
            push_next(24 * 3600)
            return
        nd = clock.at(now)
        h = nd.hour + nd.minute / 60.0
        past, future = D.lines(plan, h)
        if due:
            reason = "Zapytaj naturalnie, jak poszła ta sprawa: %s." % due[0]["text"]
            thread_id = due[0]["id"]
        elif status["state"] == "free" and plan["insomnia"] and (h < 4 or h > 23):
            reason = "Nie możesz zasnąć, jest późno. Napisz coś krótkiego, zaspanego."
        elif now - st["last_user_ts"] > 2 * 86400:
            if m["p_hurt"] > 3:
                reason = "Rozmówca długo milczy, a między wami jest chłodno. Odezwij się krótko i z dystansem."
            else:
                reason = "Rozmówca dawno się nie odzywał. Zagadnij go naturalnie, bez wyrzutów."
        elif (past or future) and rng.random() < 0.5:
            reason = "Napisz o czymś, co dziś Ci się przydarzyło: %s." % rng.choice(past or future)
        else:
            reason = "Napisz coś zwyczajnego: pytanie, myśl, drobiazg z dnia. Nie pytaj 'co słychać' schematycznie."
        db.update_state(uid, lambda s: s.__setitem__("next_proactive", now + 3600))
    _send_proactive(uid, reason, thread_id)


def _send_proactive(uid, reason, thread_id):
    now = clock.now_ts()
    rng = random.Random()
    with LOCK:
        persona = db.get_persona(uid)
        st = db.get_state(uid)
        ctx = _build_ctx(uid, persona, st, now, [], "proactive", reason)
    history = _history(uid)
    history.append({"role": "user", "text": "[Instrukcja techniczna, nie od rozmówcy: Napisz pierwszy/a. %s]" % reason})
    try:
        text = H.clean(_generate(ctx, history, rng))
    except llm.LLMError as e:
        log.warning("proactive llm: %s", type(e).__name__)
        return
    bubbles = H.bubbles(text)
    if not bubbles:
        return
    with LOCK:
        _queue(uid, bubbles, "proactive", clock.now_ts(), rng)
        if thread_id:
            M.close_thread(thread_id)
        m = R.metrics(uid, persona)
        med = max(6.0, 22.0 - m["bond"] * 1.2) * 3600
        if config.FAST:
            med = 60.0
        db.update_state(uid, lambda s: s.__setitem__("next_proactive", clock.now_ts() + _lognormal(rng, med)))


# ---------------------------------------------------------------- dla klienta
def visible_messages(uid, after=0):
    rows = db.q("SELECT id,role,text,ts,read_ts FROM messages WHERE user_id=? AND id>? ORDER BY id LIMIT 200",
                (uid, after))
    return [{"id": r["id"], "role": "me" if r["role"] == "user" else "them", "text": r["text"], "ts": r["ts"],
             "read": bool(r["read_ts"])} for r in rows]


def presence(uid):
    now = clock.now_ts()
    persona = db.get_persona(uid)
    st = db.get_state(uid)
    name = persona["name"] if (persona and persona["name"] and st["name_told"]) else (
        "Znajomy" if (persona and persona["gender"]) else "Nowy znajomy")
    typing = bool(db.q1("SELECT 1 FROM outbox WHERE user_id=? AND typing_from<=? AND deliver_at>?", (uid, now, now)))
    if typing:
        status = "pisze…"
    elif st["last_seen"] and now - st["last_seen"] < 120:
        status = "online"
    elif st["last_seen"]:
        status = "ostatnio: " + clock.fmt_last_seen(st["last_seen"])
    else:
        status = ""
    return {"name": name, "initial": (name or "Z")[0].upper(), "status": status, "typing": typing}
