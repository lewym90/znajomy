"""Dzień postaci: nastrój, sen, zdarzenia, dostępność, opóźnienia odpowiedzi.
Wszystko liczone w kodzie, model tylko to wypowiada."""
import math
import random

from . import clock, config


def _fmt(h):
    h = h % 24
    return "%d:%02d" % (int(h), int(round((h - int(h)) * 60)) % 60)


def _lognormal(r, median, sigma=0.7):
    return median * math.exp(r.gauss(0, sigma))


# kind, etykiety (zdania bezosobowe, bez rodzaju), wpływ na nastrój, czas trwania (h), okno (h), busy, waga
def _events(ctx):
    works, weekend, pet, kids, team, fan = ctx["works"], ctx["weekend"], ctx["pet"], ctx["kids"], ctx["team"], ctx["fan"]
    people = ctx["people"]
    p1 = people[0]
    out = [
        dict(id="bad_sleep", labels=["noc była kiepska, mało snu", "obudzenie o 4 i brak powrotu do snu"],
             mood=-0.35, dur=(0, 0), win=("WAKE", "WAKE"), busy=False, w=1.0),
        dict(id="headache", labels=["ból głowy, ogólnie gorsze samopoczucie"], mood=-0.3, dur=(0, 0),
             win=(9, 18), busy=False, w=0.6),
        dict(id="good_news", labels=["dobra wiadomość, coś się udało załatwić", "miła niespodzianka"],
             mood=0.4, dur=(0, 0), win=(9, 20), busy=False, w=0.7),
        dict(id="gym", labels=["trening / ruch"], mood=0.2, dur=(1, 1.5), win=(16, 20.5), busy=True, w=0.9),
        dict(id="doctor", labels=["wizyta u lekarza"], mood=-0.1, dur=(1, 1.5), win=(9, 17), busy=True, w=0.4),
        dict(id="shopping", labels=["zakupy i sprzątanie"], mood=0.0, dur=(1, 2), win=(10, 19), busy=True, w=0.7),
        dict(id="cooking", labels=["gotowanie obiadu, spokojny wieczór"], mood=0.15, dur=(0.7, 1.2),
             win=(17, 20), busy=True, w=0.6),
        dict(id="gadget_fail", labels=["awaria: zepsuło się auto / pralka / internet"], mood=-0.45,
             dur=(0.7, 1.5), win=(8, 20), busy=True, w=0.4),
        dict(id="family_call", labels=["długa rozmowa telefoniczna z %s (%s)" % (p1["rel"], p1["name"])],
             mood=0.0, dur=(0.5, 1), win=(10, 21), busy=True, w=0.6),
        dict(id="quarrel", labels=["sprzeczka z %s (%s), nieprzyjemny osad" % (p1["rel"], p1["name"])],
             mood=-0.4, dur=(0, 0), win=(9, 21), busy=False, w=0.3),
        dict(id="friends", labels=["spotkanie ze znajomymi / rodziną"], mood=0.2, dur=(2, 3.5), win=(17, 21),
             busy=True, w=0.7 if weekend else 0.3),
        dict(id="diy", labels=["majsterkowanie / remont"], mood=0.05, dur=(2, 3), win=(10, 17), busy=True,
             w=0.6 if weekend else 0.0),
    ]
    if works:
        out += [
            dict(id="traffic", labels=["korki / spóźniony transport w drodze do pracy"], mood=-0.2, dur=(0, 0),
                 win=("WORKS", "WORKS"), busy=False, w=0.7),
            dict(id="boss", labels=["szef / klient czepia się w pracy"], mood=-0.4, dur=(0.5, 1),
                 win=("WORKS", "WORKE"), busy=False, w=0.8),
            dict(id="praise", labels=["pochwała w pracy, udany dzień"], mood=0.35, dur=(0, 0),
                 win=("WORKS", "WORKE"), busy=False, w=0.5),
            dict(id="deadline", labels=["termin w pracy, dużo na głowie"], mood=-0.15, dur=(1, 2),
                 win=("WORKS", "WORKE"), busy=True, w=0.6),
        ]
    if pet:
        out.append(dict(id="vet", labels=["wizyta u weterynarza z psem %s" % pet], mood=-0.05, dur=(1, 1.5),
                        win=(10, 18), busy=True, w=0.5))
    if kids:
        out.append(dict(id="kids", labels=["dzieci: odbiór ze szkoły / zajęcia"], mood=0.0, dur=(0.8, 1.5),
                        win=(14, 18), busy=True, w=1.0))
    if team and (weekend or True):
        out.append(dict(id="match", labels=None, mood=0.0, dur=(2, 2), win=(15, 21), busy=True,
                        w=(1.2 if weekend else 0.15) * fan, gen=True))
    return out


def _match(r, team, fan):
    x = r.random()
    if x < 0.4:
        return "mecz %s: wygrana, dobry humor" % team, 0.5 * (0.4 + fan)
    if x < 0.7:
        return "mecz %s: remis, ani to, ani to" % team, -0.05
    return "mecz %s: porażka, wkurzenie" % team, -0.5 * (0.4 + fan)


def build(persona, d, hurt=0.0):
    r = random.Random("%s|%s" % (persona["seed"], d.isoformat()))
    tr, job = persona["traits"], persona["job"]
    wd = d.weekday()
    works = wd < 5 or (wd == 5 and job["days"] >= 6)
    wake = max(4.5, persona["wake_h"] + r.gauss(0, 0.35) + (1.0 if wd >= 5 and r.random() < 0.7 else 0.0))
    bed = persona["bed_h"] + r.gauss(0, 0.45) + (0.5 if wd in (4, 5) else 0.0)
    insomnia = r.random() < 0.05
    if insomnia:
        bed = min(27.5, bed + r.uniform(2.0, 3.5))
    ctx = dict(works=works, weekend=wd >= 5, pet=persona.get("pet"), kids=persona.get("kids", 0),
               team=persona["team"], fan=persona["team_fan"], people=persona["people"])
    cands = _events(ctx)
    cands = [e for e in cands if e["w"] > 0]
    k = r.choice([1, 1, 2, 2, 3])
    chosen = []
    pool = list(cands)
    for _ in range(min(k, len(pool))):
        tot = sum(e["w"] for e in pool)
        x = r.uniform(0, tot)
        acc = 0
        for e in pool:
            acc += e["w"]
            if x <= acc:
                chosen.append(e)
                pool.remove(e)
                break
    ws, we = (job["start"], job["end"]) if works else (None, None)
    incidents = []
    mood_sum = 0.0
    for e in chosen:
        if e.get("gen"):
            label, md = _match(r, persona["team"], persona["team_fan"])
        else:
            label, md = r.choice(e["labels"]), e["mood"]
        dur = r.uniform(*e["dur"])
        lo, hi = e["win"]
        lo = {"WAKE": wake, "WORKS": ws if ws is not None else wake, "WORKE": we if we is not None else wake + 8}.get(lo, lo)
        hi = {"WAKE": wake + 0.1, "WORKS": (ws or wake) + 0.5, "WORKE": we if we is not None else wake + 8}.get(hi, hi)
        hi = max(hi, lo)
        start = r.uniform(lo, max(lo, hi - dur))
        start = max(start, wake + 0.1) if e["id"] != "bad_sleep" else wake
        incidents.append({"id": e["id"], "start": round(start, 2), "end": round(start + dur, 2),
                          "label": label, "mood": round(md, 2), "busy": e["busy"] and dur > 0})
        mood_sum += md
    incidents.sort(key=lambda i: i["start"])
    mood = ((tr["warmth"] - 0.5) * 0.5 + r.gauss(0, 0.15 + 0.35 * tr["volatility"]) + mood_sum
            - 0.04 * hurt + (0.1 if wd >= 5 else 0.0))
    mood = max(-1.0, min(1.0, mood))
    return {
        "date": d.isoformat(), "wake": round(wake, 2), "bed": round(bed, 2), "insomnia": insomnia,
        "works": works, "work_start": ws, "work_end": we, "incidents": incidents, "mood": round(mood, 2),
    }


def mood_label(m):
    return ("świetny" if m > 0.4 else "dobry" if m > 0.15 else "zwyczajny" if m > -0.15 else
            "kiepski" if m > -0.5 else "zły")


def mood_directive(plan, persona):
    m = plan["mood"]
    irr = persona["traits"]["irritability"]
    if m > 0.4:
        return "Humor masz dziś świetny: jesteś życzliwy, żartobliwy, łatwiej się godzisz i wybaczasz drobiazgi."
    if m > 0.15:
        return "Humor masz dobry: jesteś otwarty i skory do rozmowy, łatwiej ustępujesz w drobnych sprawach."
    if m > -0.15:
        return "Humor masz zwyczajny: bez szczególnych emocji, reagujesz po swojemu."
    if m > -0.5:
        return ("Dzień masz kiepski: jesteś mniej cierpliwy, odpowiadasz zwięźlej, nie zgadzasz się tak łatwo i "
                "nie łagodzisz sytuacji z automatu. Nie musisz być miły.")
    if irr > 0.55:
        return ("Wstałeś lewą nogą i jesteś zły: na nic się nie zgadzasz, jesteś szorstki i nieuprzejmy "
                "(w granicach swojego charakteru), drażni Cię głupota i gadanie bez sensu. Nie pocieszasz, "
                "nie łagodzisz, nie przepraszasz na odczepnego.")
    return ("Dzień masz zły: jesteś wycofany i zmęczony ludźmi, odpowiadasz krótko i chłodno, nie masz siły "
            "na łagodzenie ani na zgadzanie się dla świętego spokoju.")


def lines(plan, now_h):
    past, future = [], []
    for i in plan["incidents"]:
        if i["start"] <= now_h:
            past.append("%s: %s" % (_fmt(i["start"]), i["label"]))
        else:
            future.append("około %s: %s" % (_fmt(i["start"]), i["label"]))
    return past, future


def status(plan, prev_plan, next_wake_ts, now):
    """Zwraca {'state': sleeping|busy|free, 'until': ts|None, 'why': str}."""
    h = now.hour + now.minute / 60.0
    d = now.date()
    if h < plan["wake"]:
        if prev_plan and prev_plan["bed"] > 24 and h < prev_plan["bed"] - 24:
            return {"state": "free", "until": None, "why": "nie śpi, późna noc"}
        return {"state": "sleeping", "until": clock.day_ts(d, plan["wake"]), "why": "śpi"}
    if plan["bed"] < 24 and h >= plan["bed"]:
        return {"state": "sleeping", "until": next_wake_ts, "why": "śpi"}
    for i in plan["incidents"]:
        if i["busy"] and i["start"] <= h < i["end"]:
            return {"state": "busy", "until": clock.day_ts(d, i["end"]), "why": i["label"]}
    if plan["works"] and plan["work_start"] <= h < plan["work_end"] and not (12.0 <= h < 12.7):
        return {"state": "busy", "until": clock.day_ts(d, plan["work_end"]), "why": "praca"}
    return {"state": "free", "until": None, "why": ""}


def reply_delay(r, st, persona, mood, hot, bond, now_ts):
    """Opóźnienie odpowiedzi w sekundach."""
    ch = persona["traits"]["chattiness"]
    if st["state"] == "sleeping":
        base = max(0.0, (st["until"] or now_ts) - now_ts) + r.uniform(300, 2400)
        if r.random() < 0.06 + 0.1 * min(bond, 12) / 12.0:
            base = r.uniform(240, 1500)
        d = base
    elif st["state"] == "busy":
        if st["why"] == "praca":
            med = 480 if persona["job"]["phone"] > 0.6 else 1500
            d = min(_lognormal(r, med), 4 * 3600)
        else:
            remaining = max(0.0, (st["until"] or now_ts) - now_ts)
            d = remaining + r.uniform(120, 1200) if r.random() < 0.75 else r.uniform(0.3, 1.0) * remaining
    else:
        med = (25 + 40 * (1 - ch)) if hot else (120 + 600 * (1 - ch))
        d = _lognormal(r, med)
    d *= 1.0 + max(0.0, -mood) * 1.2
    if config.QUICK_REPLY:
        d = min(d, r.uniform(6, 25))
    if config.FAST:
        d = min(max(d / 120.0, 1.0), 12.0)
    return max(4.0 if not config.FAST else 1.0, d)
