"""Konfiguracja. Wszystko przez zmienne środowiskowe. Żadnych sekretów w kodzie."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("ZNAJOMY_DATA", ROOT / "data"))
WEB_DIR = ROOT / "web"

HOST = os.environ.get("ZNAJOMY_HOST", "127.0.0.1")
PORT = int(os.environ.get("ZNAJOMY_PORT", "8095"))

DEV = os.environ.get("ZNAJOMY_DEV") == "1"      # pozwala na dowolny kod dostępu
FAST = os.environ.get("ZNAJOMY_FAST") == "1"    # skraca opóźnienia (testy)
CODES = [c.strip() for c in os.environ.get("ZNAJOMY_CODES", "").split(",") if c.strip()]
ORIGIN = os.environ.get("ZNAJOMY_ORIGIN", "")   # np. https://lewym90.github.io (CORS)

# Modele
LLM = os.environ.get("ZNAJOMY_LLM", "gemini")                 # gemini | mock | openai
INTIMATE_LLM = os.environ.get("ZNAJOMY_INTIMATE_LLM", "")     # opcjonalny osobny dostawca
GEMINI_MODEL = os.environ.get("ZNAJOMY_GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_BASE = os.environ.get("ZNAJOMY_GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta")
GEMINI_KEY_FILE = os.environ.get("ZNAJOMY_GEMINI_KEY_FILE", "/opt/typer/gemini_key")
OPENAI_BASE = os.environ.get("ZNAJOMY_OPENAI_BASE", "http://127.0.0.1:11434/v1")
OPENAI_MODEL = os.environ.get("ZNAJOMY_OPENAI_MODEL", "")
OPENAI_KEY_FILE = os.environ.get("ZNAJOMY_OPENAI_KEY_FILE", "")
LLM_MIN_GAP = float(os.environ.get("ZNAJOMY_LLM_MIN_GAP", "0" if os.environ.get("ZNAJOMY_LLM") == "mock" else "2.5"))

TICK = 1.0 if FAST else 10.0
VAPID_SUB = os.environ.get("ZNAJOMY_VAPID_SUB", "mailto:admin@example.com")
