"""Obróbka odpowiedzi: długość, bąbelki, literówki, kontrola powtórzeń."""
import re

LEN_HINTS = [
    ("wtręt: jedno do trzech słów (np. reakcja)", 0.20),
    ("jedno krótkie zdanie", 0.35),
    ("dwa, trzy zdania", 0.30),
    ("krótki akapit, jeśli temat tego wymaga", 0.15),
]


def length_hint(r, profile, mood, emotional=False, long_user=False):
    L = profile.get("len", 6.0) or 6.0
    w = [x[1] for x in LEN_HINTS]
    if L < 4:
        w = [w[0] * 1.6, w[1] * 1.3, w[2] * 0.7, w[3] * 0.3]
    elif L > 25:
        w = [w[0] * 0.3, w[1] * 0.6, w[2] * 1.3, w[3] * 1.8]
    if mood < -0.3:
        w = [w[0] * 1.6, w[1] * 1.3, w[2] * 0.7, w[3] * 0.4]
    if emotional or long_user:
        w = [w[0] * 0.2, w[1] * 0.6, w[2] * 1.5, w[3] * 1.4]
    tot = sum(w)
    x = r.uniform(0, tot)
    acc = 0.0
    for (txt, _), ww in zip(LEN_HINTS, w):
        acc += ww
        if x <= acc:
            return txt
    return LEN_HINTS[1][0]


def clean(text):
    t = (text or "").strip()
    t = re.sub(r"^```\w*\n?|```$", "", t).strip()
    t = re.sub(r"^\s*[\*\-•]\s+", "", t, flags=re.M)
    t = t.replace("**", "").replace("__", "").replace("#", "")
    t = re.sub(r"^(znajomy|ja|postać|asystent)\s*:\s*", "", t, flags=re.I)
    if len(t) > 1 and t[0] == '"' and t[-1] == '"':
        t = t[1:-1]
    return t.strip()


def bubbles(text, maxn=4):
    parts = [p.strip() for p in re.split(r"\n\s*\n|\|\|", text) if p.strip()]
    if not parts:
        return []
    if len(parts) > maxn:
        parts = parts[:maxn - 1] + [" ".join(parts[maxn - 1:])]
    return parts


def maybe_typo(r, text, rate):
    """Rzadka literówka, czasem z poprawką w następnej wiadomości (zwraca listę bąbelków)."""
    if r.random() >= rate:
        return [text]
    words = list(re.finditer(r"\b[a-ząćęłńóśźż]{6,}\b", text))
    if not words:
        return [text]
    m = r.choice(words)
    w = m.group(0)
    i = r.randint(1, len(w) - 3)
    bad = w[:i] + w[i + 1] + w[i] + w[i + 2:]
    out = text[:m.start()] + bad + text[m.end():]
    if r.random() < 0.5:
        return [out, "*" + w]
    return [out]


def opener(text):
    return " ".join(re.findall(r"\w+", text.lower())[:2])


def too_similar(text, recent):
    o = opener(text)
    if not o:
        return False
    return sum(1 for x in recent if opener(x) == o) >= 1
