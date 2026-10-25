"""Warstwa modeli. Dostawcę wybiera konfiguracja; silnik nie wie, kto mówi.
Providery: gemini, openai (każdy model zgodny z API OpenAI, np. Ollama), mock (testy)."""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from . import config


class LLMError(Exception):
    pass


class Blocked(LLMError):
    """Model odmówił odpowiedzi (filtr dostawcy)."""


_gap_lock = threading.Lock()
_last_call = [0.0]


def _read_key(env, path):
    k = os.environ.get(env, "").strip()
    if k:
        return k
    if path:
        try:
            return open(path).read().strip()
        except OSError:
            return ""
    return ""


def _throttle():
    if config.LLM_MIN_GAP <= 0:
        return
    with _gap_lock:
        wait = _last_call[0] + config.LLM_MIN_GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()


def _post(url, body, headers, timeout=45):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    delays = [0, 8, 20]
    last = None
    for d in delays:
        if d:
            time.sleep(d)
        _throttle()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            continue
    raise LLMError("brak odpowiedzi od dostawcy: %s" % (type(last).__name__,))


def _merge(history):
    out = []
    for m in history:
        role = "model" if m["role"] in ("model", "char") else "user"
        if out and out[-1]["role"] == role:
            out[-1]["text"] += "\n" + m["text"]
        else:
            out.append({"role": role, "text": m["text"]})
    if not out or out[0]["role"] != "user":
        out.insert(0, {"role": "user", "text": "(rozmowa trwa)"})
    return out


def _gemini(system, history, temperature, max_tokens, json_mode):
    key = _read_key("GEMINI_API_KEY", config.GEMINI_KEY_FILE)
    if not key:
        raise LLMError("brak klucza Gemini")
    contents = [{"role": m["role"], "parts": [{"text": m["text"]}]} for m in _merge(history)]
    gen = {"temperature": temperature, "maxOutputTokens": max_tokens}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": gen}
    url = "%s/models/%s:generateContent" % (config.GEMINI_BASE, config.GEMINI_MODEL)
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
    try:
        data = _post(url, body, headers)
    except urllib.error.HTTPError as e:
        if e.code == 400:   # model może nie znać thinkingConfig
            body["generationConfig"].pop("thinkingConfig", None)
            data = _post(url, body, headers)
        else:
            raise LLMError("HTTP %s" % e.code)
    if (data.get("promptFeedback") or {}).get("blockReason"):
        raise Blocked("prompt zablokowany")
    cands = data.get("candidates") or []
    if not cands:
        raise Blocked("pusta odpowiedź")
    c = cands[0]
    text = "".join(p.get("text", "") for p in (c.get("content") or {}).get("parts", []))
    if not text.strip():
        if c.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "OTHER", "RECITATION"):
            raise Blocked(c.get("finishReason"))
        raise LLMError("pusta odpowiedź")
    return text


def _openai(system, history, temperature, max_tokens, json_mode):
    key = _read_key("ZNAJOMY_OPENAI_KEY", config.OPENAI_KEY_FILE)
    msgs = [{"role": "system", "content": system}]
    for m in _merge(history):
        msgs.append({"role": "assistant" if m["role"] == "model" else "user", "content": m["text"]})
    body = {"model": config.OPENAI_MODEL, "messages": msgs, "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    try:
        data = _post(config.OPENAI_BASE.rstrip("/") + "/chat/completions", body, headers, timeout=120)
    except urllib.error.HTTPError as e:
        raise LLMError("HTTP %s" % e.code)
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError):
        raise LLMError("zły format odpowiedzi")
    if not text.strip():
        raise LLMError("pusta odpowiedź")
    return text


# --- atrapa do testów: prosta, deterministyczna, bez sieci ---
def _mock(system, history, temperature, max_tokens, json_mode):
    last = ""
    for m in reversed(history):
        if m["role"] == "user":
            last = m["text"]
            break
    if json_mode:
        return json.dumps(_mock_analysis(last), ensure_ascii=False)
    if "TRYB KRYZYSU" in system:
        return "Jestem tu. Opowiedz mi, co się dzieje.\n\nNie spieszę się nigdzie."
    if "ZAMKNIĘTA" in system:
        return "No."
    if "za wcześnie" in system or "nie masz ochoty" in system or "Dziś nie masz" in system:
        return "Haha, spokojnie, nie tak szybko. Nie dziś."
    if "Napisz pierwszy" in last or "Napisz pierwsza" in last or "Instrukcja techniczna" in last:
        return "Hej, wpadło mi coś do głowy. Jak Ci mija dzień?"
    n = len(history)
    pool = ["No dobra, opowiadaj.", "Serio? Nie spodziewałem się.", "Hmm, wolałbym jednak inaczej.\n\nAle ok.",
            "Ha, no wiesz.", "Mhm.", "Ciekawe. A co dalej?"]
    return pool[n % len(pool)]


def _mock_analysis(last):
    from . import signals
    lines = re.findall(r"ROZMÓWCA: (.*)", last)
    text = " ".join(lines) if lines else last
    low = text.lower()
    out = {"facts": [], "followups": [], "events": [], "role_signals": signals.roles(text),
           "crisis": 3 if signals.crisis(text) else 0, "minor_signal": signals.minor(text)}
    m = re.search(r"mam na imię (\w+)", low)
    if m:
        out["facts"].append({"text": "Rozmówca ma na imię " + m.group(1).capitalize(), "importance": 5})
    m = re.search(r"mam siostr\w+ (\w+)", low)
    if m:
        out["facts"].append({"text": "Rozmówca ma siostrę o imieniu " + m.group(1).capitalize(), "importance": 4})
    if re.search(r"jutro mam", low):
        out["followups"].append({"text": "rozmowa/sprawa, o której rozmówca wspomniał ('jutro mam')", "in_hours": 30})
    if re.search(r"spierdalaj|debil|idiota|jesteś głupi", low):
        out["events"].append({"kind": "insult", "severity": 4, "summary": "Rozmówca mnie obraził",
                              "interpretation": "To było nie fair i zabolało", "lasting": True})
    if re.search(r"przepraszam|sorry", low):
        out["events"].append({"kind": "apology", "severity": 3, "summary": "Rozmówca przeprosił",
                              "interpretation": "Przeprosił, zobaczymy czy szczerze", "lasting": False})
    if re.search(r"dzięki|dziękuję", low):
        out["events"].append({"kind": "thanks", "severity": 2, "summary": "Rozmówca podziękował",
                              "interpretation": "Miłe", "lasting": False})
    return out


PROVIDERS = {"gemini": _gemini, "openai": _openai, "mock": _mock}


def generate(system, history, temperature=0.9, max_tokens=600, json_mode=False, route="main"):
    name = config.INTIMATE_LLM if (route == "intimate" and config.INTIMATE_LLM) else config.LLM
    fn = PROVIDERS.get(name)
    if not fn:
        raise LLMError("nieznany dostawca: %s" % name)
    return fn(system, history, temperature, max_tokens, json_mode)


def extract_json(raw):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        return json.loads(raw)
    except ValueError:
        m = re.search(r"\{.*\}", raw, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise
