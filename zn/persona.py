"""Narodziny postaci: charakter losowany raz i trzymany na stałe.
Użytkownik nic nie wpisuje. Imię i płeć wychodzą z tego, jak rozmówca się zwraca."""
import random

JOBS = [
    ("pracuje w księgowości", 8, 16, 5, 0.5),
    ("pracuje w IT", 9, 17, 5, 0.9),
    ("pracuje w szkole", 8, 15, 5, 0.3),
    ("pracuje w magazynie", 6, 14, 5, 0.2),
    ("pracuje w sklepie", 10, 18, 6, 0.4),
    ("pracuje w urzędzie", 7.5, 15.5, 5, 0.6),
    ("pracuje w szpitalu na zmiany", 7, 19, 5, 0.3),
    ("pracuje na budowie", 7, 15, 6, 0.3),
    ("pracuje w biurze projektowym", 9, 17, 5, 0.8),
    ("prowadzi małą firmę", 9, 18, 6, 0.9),
    ("pracuje w obsłudze klienta", 9, 17, 5, 0.5),
    ("pracuje w logistyce", 8, 16, 5, 0.6),
]
TEAMS = ["Legia", "Lech", "Wisła Kraków", "Śląsk", "Górnik Zabrze", "Cracovia", "Pogoń", "Jagiellonia",
         "Raków", "Widzew", "Lechia", "ŁKS", "Ruch Chorzów", "Zagłębie"]
INTERESTS = ["siłownia", "bieganie", "rower", "góry", "wędkowanie", "gotowanie", "seriale", "gry komputerowe",
             "książki", "fotografia", "muzyka rockowa", "hip-hop", "majsterkowanie", "motoryzacja", "podróże",
             "kino", "planszówki", "ogród"]
PEEVES = ["ludzie spóźniający się bez uprzedzenia", "hałas", "gadanie w kółko o tym samym", "nieuczciwość",
          "bałagan", "bycie ocenianym", "gdy ktoś nie oddaje pożyczonych rzeczy", "puste obietnice", "korki",
          "zbędne spotkania w pracy"]
VALUES = ["lojalność wobec bliskich", "szczerość nawet gdy boli", "niezależność", "rodzina", "uczciwość",
          "spokój", "ambicja", "honor", "wierność swoim zasadom", "sprawiedliwość"]
TICS = ["no wiesz", "w sumie", "serio?", "ha", "eee", "ogarniam", "spoko", "no nie", "ej", "hmm", "właśnie",
        "masakra"]
GRUDGE = ["milczy i się wycofuje", "mówi wprost, co się nie podoba", "ironizuje i dogryza",
          "wybucha, ale potem długo pamięta", "udaje, że nic się nie stało, choć pamięta wszystko"]
CITIES = ["Warszawa", "Kraków", "Wrocław", "Poznań", "Gdańsk", "Łódź", "Katowice", "Lublin", "Szczecin",
          "Bydgoszcz", "Rzeszów", "Białystok"]
PETS = ["Burek", "Luna", "Max", "Rocky", "Fela", "Azor", "Pimpek", "Frania"]
M_NAMES = ["Kamil", "Marek", "Tomek", "Paweł", "Michał", "Bartek", "Darek", "Adam", "Krzysiek", "Łukasz",
           "Rafał", "Wojtek", "Piotrek", "Mateusz", "Grzesiek", "Marcin", "Sebastian", "Artur"]
F_NAMES = ["Ola", "Kasia", "Marta", "Ania", "Magda", "Ewa", "Natalia", "Karolina", "Basia", "Monika", "Agata",
           "Iza", "Justyna", "Dorota", "Paulina", "Weronika", "Joanna", "Patrycja"]
RELATIONS = [("siostra", "f"), ("brat", "m"), ("mama", "f"), ("tata", "m"), ("kumpel z pracy", "m"),
             ("koleżanka z pracy", "f"), ("szef", "m"), ("szefowa", "f"), ("sąsiad", "m"), ("sąsiadka", "f"),
             ("najlepszy kumpel", "m"), ("najlepsza przyjaciółka", "f")]


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def birth(seed=None):
    seed = seed if seed is not None else random.SystemRandom().randrange(1 << 31)
    r = random.Random(seed)

    def t():
        return round(r.uniform(0.1, 0.95), 2)

    pride = t()
    tr = {
        "warmth": t(), "irritability": t(), "pride": pride,
        "forgiveness": round(_clamp(r.uniform(0.1, 0.95) - 0.3 * (pride - 0.5), 0.05, 0.97), 2),
        "humor": t(), "stubbornness": t(), "curiosity": t(), "bluntness": t(),
        "vulgarity": t(), "formality": round(r.uniform(0.05, 0.7), 2), "chattiness": t(),
        "sociability": t(), "romantic_openness": t(), "forgetfulness": round(r.uniform(0.03, 0.35), 2),
        "volatility": t(),
    }
    j = r.choice(JOBS)
    age = r.randint(26, 52)
    rels = r.sample(RELATIONS, 4)
    people = []
    for rel, g in rels:
        people.append({"rel": rel, "name": r.choice(M_NAMES if g == "m" else F_NAMES)})
    return {
        "seed": seed,
        "gender": None,
        "name": None,
        "traits": tr,
        "age": age,
        "city": r.choice(CITIES),
        "job": {"text": j[0], "start": j[1], "end": j[2], "days": j[3], "phone": j[4]},
        "wake_h": round(_clamp(r.gauss(6.9, 1.0), 5.0, 10.0), 2),
        "bed_h": round(_clamp(r.gauss(23.0, 1.1), 21.0, 26.0), 2),
        "team": r.choice(TEAMS),
        "team_fan": round(r.uniform(0.2, 1.0), 2),
        "interests": r.sample(INTERESTS, 3),
        "peeves": r.sample(PEEVES, 2),
        "values": r.sample(VALUES, 2),
        "tics": r.sample(TICS, 2),
        "grudge": r.choice(GRUDGE),
        "people": people,
        "pet": r.choice(PETS) if r.random() < 0.4 else None,
        "kids": r.randint(1, 3) if age >= 30 and r.random() < 0.4 else 0,
    }


def assign_gender(persona, gender):
    """Ustala płeć i imię (raz, na stałe)."""
    r = random.Random(persona["seed"] + 7)
    persona["gender"] = gender
    persona["name"] = r.choice(M_NAMES if gender == "m" else F_NAMES)
    # żeby imię nie kolidowało z osobami z otoczenia
    taken = {p["name"] for p in persona["people"]}
    while persona["name"] in taken:
        persona["name"] = r.choice(M_NAMES if gender == "m" else F_NAMES)
    return persona


def summary(persona):
    """Opis charakteru dla modelu (bez liczb)."""
    tr = persona["traits"]

    def lvl(k, lo, hi):
        v = tr[k]
        return hi if v > 0.65 else lo if v < 0.35 else None

    bits = []
    for k, lo, hi in [
        ("warmth", "raczej chłodny w kontakcie", "ciepły i serdeczny"),
        ("irritability", "cierpliwy", "łatwo się irytuje"),
        ("pride", "mało dumny, łatwo przeprasza", "bardzo dumny, trudno mu zrobić pierwszy krok"),
        ("humor", "poważny", "lubi żartować i dogryzać"),
        ("stubbornness", "elastyczny", "uparty, trzyma się swojego zdania"),
        ("bluntness", "taktowny", "mówi prosto z mostu"),
        ("curiosity", "mało dociekliwy", "ciekawy ludzi, dopytuje"),
        ("forgiveness", "pamiętliwy, wybacza z trudem", "szybko wybacza"),
    ]:
        b = lvl(k, lo, hi)
        if b:
            bits.append(b)
    return {
        "traits_text": "; ".join(bits),
        "peeves": ", ".join(persona["peeves"]),
        "values": ", ".join(persona["values"]),
        "interests": ", ".join(persona["interests"]),
        "tics": ", ".join(persona["tics"]),
        "grudge": persona["grudge"],
    }
