"""Powiadomienia push (opcjonalne). Działają, jeśli zainstalowano pywebpush; inaczej cicho pomijane."""
import base64
import json
import logging

from . import config, db

log = logging.getLogger("znajomy")

try:
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid
    from cryptography.hazmat.primitives import serialization
    AVAILABLE = True
except Exception:  # biblioteka nie jest wymagana
    AVAILABLE = False

_KEY = config.DATA_DIR / "vapid_private.pem"


def _vapid():
    v = Vapid()
    if _KEY.exists():
        v = Vapid.from_file(str(_KEY))
    else:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        v.generate_keys()
        v.save_key(str(_KEY))
    return v


def public_key():
    if not AVAILABLE:
        return None
    raw = _vapid().public_key.public_bytes(serialization.Encoding.X962,
                                           serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def subscribe(uid, sub):
    ep = (sub or {}).get("endpoint")
    if not ep:
        return False
    db.x("INSERT OR REPLACE INTO push_subs(user_id,endpoint,sub_json) VALUES(?,?,?)", (uid, ep, json.dumps(sub)))
    return True


def notify(uid, title, body):
    if not AVAILABLE:
        return
    subs = db.q("SELECT * FROM push_subs WHERE user_id=?", (uid,))
    if not subs:
        return
    payload = json.dumps({"title": title, "body": body[:180]}, ensure_ascii=False)
    _vapid()   # upewnia się, że klucz istnieje
    for s in subs:
        try:
            webpush(subscription_info=json.loads(s["sub_json"]), data=payload,
                    vapid_private_key=str(_KEY), vapid_claims={"sub": config.VAPID_SUB})
        except WebPushException as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (404, 410):
                db.x("DELETE FROM push_subs WHERE id=?", (s["id"],))
            else:
                log.warning("push: %s", code)
        except Exception as e:
            log.warning("push: %s", type(e).__name__)
