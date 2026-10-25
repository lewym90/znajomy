"""Profil stylu pisania rozmówcy. Aktualizowany po każdej wiadomości, adaptacja powolna."""
import re

VULGAR = ("kurw", "chuj", "jeb", "pierdol", "spierdal", "pizd", "skurw", "wkurw", "gówn", "zajeb")
FORMAL = ("szanown", "proszę", "uprzejmie", "dziękuję bardzo", "dzień dobry", "witam", "z poważaniem",
          "pozdrawiam serdecznie", "pan ", "pani ")
SLANG = ("mordo", "stary", "ziom", "elo", "siema", "nara", "luzik", "spoko", "typie", "sztos", "bracie",
         "brachu", "ej ", "no weź", "jakoś tam")
_EMO = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def features(text):
    low = text.lower()
    words = re.findall(r"\w+", low)
    n = len(words)
    return {
        "len": n,
        "emoji": len(_EMO.findall(text)),
        "vulgar": sum(1 for w in words if w.startswith(VULGAR)),
        "formal": 1.0 if any(m in low for m in FORMAL) else 0.0,
        "slang": 1.0 if any(m in low for m in SLANG) else 0.0,
        "exclam": 1.0 if "!" in text else 0.0,
        "caps": 1.0 if text[:1].isupper() else 0.0,
        "question": 1.0 if "?" in text else 0.0,
    }


def update(profile, feats, n):
    a = max(0.08, 1.0 / (n + 1))
    for k, v in feats.items():
        profile[k] = (1 - a) * profile.get(k, v) + a * v
    return profile


def register(profile):
    if profile.get("formal", 0) > 0.45 and profile.get("slang", 0) < 0.3:
        return "formal"
    if profile.get("slang", 0) > 0.35 or profile.get("vulgar", 0) > 0.25:
        return "street"
    return "neutral"


def vulgarity_level(profile, persona, n):
    """0..1: mieszanka natywnego poziomu postaci i poziomu rozmówcy, adaptacja powolna."""
    a = min(0.7, n / 120.0)
    native = persona["traits"]["vulgarity"]
    user = min(1.0, profile.get("vulgar", 0) / 0.8)
    v = native * (1 - a) + user * a
    if register(profile) == "formal":
        v = min(v, 0.08)
    return v


def describe(profile, persona, n):
    reg = register(profile)
    v = vulgarity_level(profile, persona, n)
    if n < 2:
        reg_txt = "Dopiero się poznajecie. Pisz naturalnie, potocznie, ale bez przesady."
    elif reg == "formal":
        reg_txt = ("Rozmówca pisze oficjalnie i starannie. Odpowiadaj kulturalnie, pełnymi zdaniami, "
                   "bez slangu i bez przekleństw, bez spoufalania się.")
    elif reg == "street":
        reg_txt = "Rozmówca pisze luźno, potocznie. Odpowiadaj w podobnym rejestrze, bez udawania."
    else:
        reg_txt = "Rozmówca pisze zwyczajnie. Odpowiadaj zwyczajnie, po ludzku."
    vul = ("bez przekleństw" if v < 0.12 else
           "przekleństwa bardzo rzadko, tylko gdy naprawdę pasują" if v < 0.4 else
           "przekleństwa od czasu do czasu, jak u zwykłego człowieka" if v < 0.7 else
           "przekleństwa dość często, to Twój naturalny styl")
    return (reg_txt + f" Przekleństwa: {vul}. Dopasowujesz się do rozmówcy powoli i nie kopiujesz jego "
            "słów ani stylu dosłownie, zachowujesz własny charakter.")


def typo_rate(profile, n):
    return 0.004 if register(profile) == "formal" else 0.03
