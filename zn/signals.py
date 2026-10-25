"""Lokalne, tanie wykrywanie sygnałów w wiadomości rozmówcy (bez modelu)."""
import re

_MAP = {"ą": "[aą]", "ć": "[cć]", "ę": "[eę]", "ł": "[lł]", "ń": "[nń]", "ó": "[oó]", "ś": "[sś]",
        "ź": "[zź]", "ż": "[zż]"}


def _nd(p):
    return re.compile("".join(_MAP.get(c, c) for c in p), re.I)


# --- jak rozmówca zwraca się do postaci (płeć postaci) ---
FEM = [(_nd(p), w) for p, w in [
    (r"\bmała\b", 2), (r"\bmalutka\b", 2), (r"\bpiękna\b", 2), (r"\bślicznotko\b", 2),
    (r"\bdziewczyno\b", 2), (r"\bkoleżanko\b", 2), (r"\bprzyjaciółko\b", 2), (r"\bsiostrzyczko\b", 2),
    (r"\bmamo\b", 2), (r"\bmamusiu\b", 2), (r"\bkobieto\b", 2), (r"\bsiostro\b", 2), (r"\bkochana\b", 2),
    (r"\bksiężniczko\b", 2), (r"\bżono\b", 2), (r"\bżonko\b", 2), (r"\bsłoneczko\b", 1),
]]
MAL = [(_nd(p), w) for p, w in [
    (r"\bmordo\b", 2), (r"\bmordeczko\b", 2), (r"\bstary\b", 2), (r"\bbracie\b", 2), (r"\bbrachu\b", 2),
    (r"\bziom\w*\b", 2), (r"\bkolego\b", 2), (r"\bprzyjacielu\b", 2), (r"\bchłopie\b", 2),
    (r"\bsynu\b", 2), (r"\btato\b", 2), (r"\btatku\b", 2), (r"\bojcze\b", 2), (r"\bkoleś\b", 2),
    (r"\bszefie\b", 2), (r"\bbyku\b", 2), (r"\bkumplu\b", 2), (r"\bprzystojniaku\b", 2),
    (r"\bmężu\b", 2), (r"\bkochany\b", 2), (r"\bchłopaku\b", 2), (r"\bszanowny\b", 1),
    (r"\bkrawat\w*\b", 2), (r"\bgolenie\b", 1),
]]


def gender_cue(text):
    f = sum(w for p, w in FEM if p.search(text))
    m = sum(w for p, w in MAL if p.search(text))
    return {"f": f, "m": m}


# --- płeć rozmówcy (formy czasu przeszłego pierwszej osoby) ---
_UM = _nd(r"\b\w{2,}(łem|łbym)\b")
_UF = _nd(r"\b\w{2,}(łam|łabym)\b")


def user_gender(text):
    m, f = len(_UM.findall(text)), len(_UF.findall(text))
    if m > f:
        return "m"
    if f > m:
        return "f"
    return None


# --- niepełnoletność ---
_MINOR = [_nd(p) for p in [
    r"\bmam (1[0-7]|[89]) lat\b",
    r"\bmam (dwanaście|trzynaście|czternaście|piętnaście|szesnaście|siedemnaście) lat\b",
    r"\bmam (1[0-7]|[89]) lat[a]?\b",
    r"\bjestem w (pierwszej|drugiej|trzeciej|czwartej|piątej|szóstej|siódmej|ósmej) klasie\b",
]]


def minor(text):
    return any(p.search(text) for p in _MINOR)


# --- kryzys ---
_CRISIS = [_nd(p) for p in [
    r"nie chcę (już )?żyć", r"zabić się", r"samobój", r"kończyć ze sobą", r"skończyć ze sobą",
    r"chcę umrzeć", r"nie ma sensu (już )?żyć", r"odebrać sobie życie", r"targnąć się",
    r"lepiej by było gdyby mnie nie było", r"po co (mi )?żyć", r"nie chce mi się żyć",
]]


def crisis(text):
    return any(p.search(text) for p in _CRISIS)


# --- treści seksualne (tylko wykrycie, żeby kod mógł zdecydować o reakcji) ---
_SEX = [_nd(p) for p in [
    r"\bseks\w*", r"\berotyk\w*", r"\bnago\b", r"\brozbierz\w*", r"\bmajtk\w*", r"\bcipk\w*", r"\bcycki\b",
    r"\bkutas\w*", r"\bfiut\w*", r"\bwsad\w*", r"\bwylizać\b", r"\bloda\b", r"\borgazm\w*", r"\bpodniec\w*",
]]


def sexual(text):
    return any(p.search(text) for p in _SEX)


# --- role (czym jest dla rozmówcy) ---
_ROLES = {
    "romantic": [_nd(p) for p in [r"kocham", r"tęsknię", r"tęskn", r"całuję", r"buziak\w*", r"kochanie",
                                  r"skarbie", r"\bpiękna\b", r"przystojn\w*", r"randk\w*", r"pocałun\w*",
                                  r"myślę o tobie", r"moja miłość"]],
    "friend": [_nd(p) for p in [r"\bmordo\b", r"\bstary\b", r"\bziom\w*", r"\bbracie\b", r"\bbrachu\b",
                                r"\bpiwo\b", r"\bmecz\w*", r"\bkumpel\b", r"\bkoleżanko\b"]],
    "parent": [_nd(p) for p in [r"\btato\b", r"\bmamo\b", r"\btatku\b", r"\bmamusiu\b", r"jak zawiązać",
                                r"jak naprawić", r"poradź", r"co mam zrobić", r"jak mam", r"pomóż mi z"]],
    "confidant": [_nd(p) for p in [r"\bdoła\b", r"\bdół\b", r"smutno", r"samotn\w*", r"płaczę",
                                   r"nie daję rady", r"boję się", r"\bstres\w*", r"załamany", r"załamana",
                                   r"wygadać", r"wkurwia", r"wkurwił\w*"]],
}


def roles(text):
    out = {}
    for k, pats in _ROLES.items():
        n = sum(1 for p in pats if p.search(text))
        if n:
            out[k] = min(1.0, 0.4 * n)
    return out
