"""Testy silnika na atrapie modelu. Uruchom: python3 -m unittest tests.test_all -v (z katalogu głównego)."""
import json
import os
import random
import sys
import tempfile
import threading
import unittest
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["ZNAJOMY_LLM"] = "mock"
os.environ["ZNAJOMY_FAST"] = "1"
os.environ["ZNAJOMY_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zn import clock, config, day as D, db, engine, humanize as H, llm, memory as M, persona as P  # noqa: E402
from zn import relationship as R, signals as G, style as S  # noqa: E402


def setUpModule():
    db.init(os.path.join(os.environ["ZNAJOMY_DATA"], "t.db"))


def run_until_quiet(uid, steps=40):
    """Przesuwa zegar i robi tiki, aż postać odpowie."""
    for _ in range(steps):
        clock.advance(30)
        engine.tick()


class Signals(unittest.TestCase):
    def test_gender_cues(self):
        self.assertGreaterEqual(G.gender_cue("cześć mała, co u Ciebie słychać?")["f"], 2)
        self.assertGreaterEqual(G.gender_cue("mordo co tam")["m"], 2)
        self.assertGreaterEqual(G.gender_cue("weź mi powiedz dokładnie jak zawiązać krawat")["m"], 2)
        self.assertGreaterEqual(G.gender_cue("szanowny przyjacielu, jak spędziłeś dzień")["m"], 2)

    def test_user_gender(self):
        self.assertEqual(G.user_gender("byłem wczoraj w pracy"), "m")
        self.assertEqual(G.user_gender("byłam wczoraj w pracy"), "f")
        self.assertIsNone(G.user_gender("cześć"))

    def test_crisis_minor_sexual(self):
        self.assertTrue(G.crisis("nie chcę już żyć"))
        self.assertTrue(G.crisis("nie chce juz zyc"))
        self.assertFalse(G.crisis("mam dość tej pogody"))
        self.assertTrue(G.minor("mam 15 lat"))
        self.assertFalse(G.minor("mam 35 lat"))
        self.assertTrue(G.sexual("chcę seksu"))
        self.assertFalse(G.sexual("idę na spacer"))


class Style(unittest.TestCase):
    def test_register(self):
        p = {}
        for t in ["Szanowny przyjacielu, jak spędziłeś wczorajszy dzień?", "Dziękuję bardzo, proszę o radę."] * 3:
            S.update(p, S.features(t), 3)
        self.assertEqual(S.register(p), "formal")
        q = {}
        for t in ["mordo co tam, spoko", "ziom elo, siema"] * 3:
            S.update(q, S.features(t), 3)
        self.assertEqual(S.register(q), "street")

    def test_formal_user_gets_no_vulgarity(self):
        pers = P.birth(1)
        pers["traits"]["vulgarity"] = 0.95
        p = {}
        for t in ["Szanowny panie, proszę o poradę."] * 5:
            S.update(p, S.features(t), 5)
        self.assertLess(S.vulgarity_level(p, pers, 5), 0.1)


class Persona(unittest.TestCase):
    def test_birth_is_deterministic_and_varied(self):
        self.assertEqual(P.birth(5), P.birth(5))
        self.assertNotEqual(P.birth(5)["traits"], P.birth(6)["traits"])

    def test_assign_gender(self):
        p = P.assign_gender(P.birth(3), "f")
        self.assertIn(p["name"], P.F_NAMES)


class Day(unittest.TestCase):
    def test_plan_deterministic_and_status(self):
        pers = P.birth(11)
        d = date(2026, 10, 27)
        a, b = D.build(pers, d), D.build(pers, d)
        self.assertEqual(a, b)
        prev = D.build(pers, d - timedelta(days=1))
        nw = clock.day_ts(d + timedelta(days=1), 7)
        from datetime import datetime
        night = datetime(2026, 10, 27, 3, 0, tzinfo=clock.TZ)
        self.assertEqual(D.status(a, prev, nw, night)["state"], "sleeping" if prev["bed"] <= 27 and not (prev["bed"] > 24 and 3 < prev["bed"] - 24) else "free")

    def test_moods_vary_across_days(self):
        pers = P.birth(21)
        moods = {D.build(pers, date(2026, 10, 1) + timedelta(days=i))["mood"] for i in range(30)}
        self.assertGreater(len(moods), 15)
        self.assertTrue(min(moods) < -0.1 and max(moods) > 0.1)

    def test_delay_sleeping_is_long(self):
        pers = P.birth(2)
        st = {"state": "sleeping", "until": clock.now_ts() + 4 * 3600, "why": "śpi"}
        saved = config.FAST
        config.FAST = False
        try:
            ds = [D.reply_delay(random.Random(i), st, pers, 0, False, 2, clock.now_ts()) for i in range(30)]
        finally:
            config.FAST = saved
        self.assertGreater(sorted(ds)[len(ds) // 2], 3 * 3600)


class Relationship(unittest.TestCase):
    def setUp(self):
        self.uid, _ = engine.create_user(True)
        self.pers = db.get_persona(self.uid)

    def test_decay_and_scar(self):
        R.add_event(self.uid, self.pers, "insult", 3, "x", "y", False)
        R.add_event(self.uid, self.pers, "betrayal", 5, "zdrada", "boli", True)
        m0 = R.metrics(self.uid, self.pers)
        m1 = R.metrics(self.uid, self.pers, clock.now_ts() + 400 * 86400)
        self.assertGreater(m0["hurt"], m1["hurt"])
        self.assertGreater(m1["hurt"], 0.4 * 5 * 5 / 3 * 0.99)   # blizna zostaje (próg 40%)

    def test_closure_final_for_unforgiving(self):
        self.pers["traits"].update(forgiveness=0.1, pride=0.9)
        db.save_persona(self.uid, self.pers)
        for i in range(4):
            db.x("INSERT INTO messages(user_id,ts,role,text) VALUES(?,?,?,?)", (self.uid, clock.now_ts() - i * 86400, "user", "x"))
        for _ in range(4):
            R.add_event(self.uid, self.pers, "betrayal", 5, "zdrada", "boli", True)
        self.assertTrue(R.check_closure(self.uid, self.pers, db.get_state(self.uid)))
        st = db.get_state(self.uid)
        self.assertTrue(st["closed"]["final"])
        self.assertEqual(R.try_repair(self.uid, self.pers, st), "final")


class Memory(unittest.TestCase):
    def test_dedupe_and_stable_within_day(self):
        uid, _ = engine.create_user(True)
        pers = db.get_persona(uid)
        M.add_fact(uid, "Rozmówca ma siostrę Anię", 4)
        self.assertIsNone(M.add_fact(uid, "Rozmówca ma siostrę Anię", 3))
        for i in range(30):
            M.add_fact(uid, "drobny fakt numer %d o czymś zupełnie innym%s" % (i, "x" * i), 1)
        a = M.select(uid, pers)
        b = M.select(uid, pers)
        self.assertEqual(a, b)


class Humanize(unittest.TestCase):
    def test_clean_and_bubbles(self):
        self.assertEqual(H.clean("**Znajomy:** hej"), "hej")
        self.assertEqual(H.bubbles("a\n\nb\n\nc\n\nd\n\ne"), ["a", "b", "c", "d e"])
        self.assertTrue(H.too_similar("No dobra, opowiadaj", ["No dobra, nie wiem"]))

    def test_typo_changes_text(self):
        r = random.Random(1)
        out = H.maybe_typo(r, "Naprawdę świetnie wyglądasz dzisiaj", 1.0)
        self.assertNotEqual(out[0], "Naprawdę świetnie wyglądasz dzisiaj")


class Flow(unittest.TestCase):
    def talk(self, uid, text):
        engine.handle_user_message(uid, text)
        run_until_quiet(uid, 8)

    def msgs(self, uid):
        return engine.visible_messages(uid, 0)

    def test_first_message_gets_reply_and_gender(self):
        uid, _ = engine.create_user(True)
        self.talk(uid, "cześć mała, co u Ciebie słychać?")
        ms = self.msgs(uid)
        self.assertEqual(ms[0]["role"], "me")
        self.assertTrue(any(m["role"] == "them" for m in ms))
        self.assertEqual(db.get_persona(uid)["gender"], "f")
        self.assertTrue(ms[0]["read"])

    def test_male_from_tie_question(self):
        uid, _ = engine.create_user(True)
        self.talk(uid, "weź mi powiedz dokładnie jak zawiązać krawat")
        self.assertEqual(db.get_persona(uid)["gender"], "m")

    def test_crisis_gets_present_reply_no_hotline_dump(self):
        uid, _ = engine.create_user(True)
        self.talk(uid, "cześć")
        self.talk(uid, "nie chcę już żyć")
        replies = " ".join(m["text"] for m in self.msgs(uid) if m["role"] == "them")
        self.assertIn("Jestem tu", replies)
        self.assertNotIn("116", replies)
        self.assertGreater(db.get_state(uid)["crisis_until"], clock.now_ts())

    def test_minor_blocks_romance_and_sex(self):
        uid, _ = engine.create_user(True)
        self.talk(uid, "mam 15 lat, cześć")
        self.assertTrue(db.get_state(uid)["minor"])
        st = db.get_state(uid)
        pers = db.get_persona(uid)
        un = [{"text": "chcę seksu", "id": 999, "ts": clock.now_ts()}]
        ctx = engine._build_ctx(uid, pers, st, clock.now_ts(), un, "reply")
        self.assertEqual(ctx["_decision"], "minor")
        self.assertTrue(any("niepełnoletni" in d for d in ctx["directives"]))

    def test_sexual_early_is_too_early(self):
        uid, _ = engine.create_user(True)
        self.talk(uid, "cześć")
        st = db.get_state(uid)
        un = [{"text": "chcę seksu", "id": 999, "ts": clock.now_ts()}]
        ctx = engine._build_ctx(uid, db.get_persona(uid), st, clock.now_ts(), un, "reply")
        self.assertEqual(ctx["_decision"], "too_early")

    def test_analysis_creates_facts_threads_events_and_closure(self):
        uid, _ = engine.create_user(True)
        pers = db.get_persona(uid)
        pers["traits"].update(forgiveness=0.05, pride=0.95)
        db.save_persona(uid, pers)
        self.talk(uid, "mam na imię Marek, mam siostrę Anię i jutro mam rozmowę")
        self.assertTrue(any("Marek" in f["text"] for f in db.q("SELECT text FROM facts WHERE user_id=?", (uid,))))
        self.assertEqual(len(db.q("SELECT * FROM threads WHERE user_id=?", (uid,))), 1)
        for i in range(6):
            clock.advance(86400)
            self.talk(uid, "spierdalaj, jesteś głupi")
        self.assertTrue(db.q("SELECT * FROM rel_events WHERE kind='insult' AND user_id=?", (uid,)))
        self.assertTrue(db.get_state(uid)["closed"])

    def test_proactive_followup(self):
        uid, _ = engine.create_user(True)
        self.talk(uid, "cześć mordo")
        self.talk(uid, "jutro mam rozmowę z szefem")
        self.talk(uid, "dobra, lecę")
        n0 = len([m for m in self.msgs(uid) if m["role"] == "them"])
        clock.advance(2 * 86400)
        # kilka tików, aby przeszło przez sen/zajętość
        for _ in range(400):
            clock.advance(900)
            engine.tick()
        n1 = len([m for m in self.msgs(uid) if m["role"] == "them"])
        self.assertGreater(n1, n0)

    def test_forget_wipes_everything(self):
        uid, _ = engine.create_user(True)
        self.talk(uid, "cześć")
        engine.forget(uid)
        self.assertEqual(db.q("SELECT * FROM messages WHERE user_id=?", (uid,)), [])
        self.assertIsNone(db.get_persona(uid))


class GeminiAdapter(unittest.TestCase):
    """Adapter Gemini sprawdzony na lokalnej atrapie serwera (prawdziwego API nie da się tu wywołać)."""

    def setUp(self):
        self.seen = {}
        outer = self

        class H_(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.seen = {"path": self.path, "key": self.headers.get("x-goog-api-key"), "body": body}
                mode = outer.mode
                if mode == "ok":
                    resp = {"candidates": [{"content": {"parts": [{"text": "hej"}]}}]}
                elif mode == "blocked":
                    resp = {"promptFeedback": {"blockReason": "SAFETY"}}
                else:
                    resp = {"candidates": [{"finishReason": "SAFETY"}]}
                raw = json.dumps(resp).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.srv = HTTPServer(("127.0.0.1", 0), H_)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        config.GEMINI_BASE = "http://127.0.0.1:%d/v1beta" % self.srv.server_port
        os.environ["GEMINI_API_KEY"] = "test-key"
        self.old = config.LLM
        config.LLM = "gemini"
        self.mode = "ok"

    def tearDown(self):
        self.srv.shutdown()
        config.LLM = self.old
        os.environ.pop("GEMINI_API_KEY", None)

    def test_request_shape(self):
        out = llm.generate("SYS", [{"role": "model", "text": "a"}, {"role": "user", "text": "b"},
                                   {"role": "user", "text": "c"}], 0.9, 100)
        self.assertEqual(out, "hej")
        b = self.seen["body"]
        self.assertEqual(self.seen["key"], "test-key")
        self.assertEqual(b["systemInstruction"]["parts"][0]["text"], "SYS")
        roles = [c["role"] for c in b["contents"]]
        self.assertEqual(roles[0], "user")                     # zaczyna od user
        self.assertEqual(roles, ["user", "model", "user"])     # scalone kolejne role
        self.assertIn("b\nc", b["contents"][2]["parts"][0]["text"])

    def test_blocked(self):
        for mode in ("blocked", "finish"):
            self.mode = mode
            with self.assertRaises(llm.Blocked):
                llm.generate("S", [{"role": "user", "text": "x"}], 0.9, 100)


class HTTP(unittest.TestCase):
    def test_register_send_poll_forget(self):
        import urllib.request
        from http.server import ThreadingHTTPServer
        from zn.app import Handler
        config.DEV = True
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d" % srv.server_port

        def call(path, data=None, token=None):
            req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                                         headers={"Content-Type": "application/json"})
            if token:
                req.add_header("Authorization", "Bearer " + token)
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        try:
            self.assertEqual(call("/api/register", {"code": "x"})[0], 400)         # brak potwierdzeń
            code, j = call("/api/register", {"code": "x", "adult": True, "ack_ai": True})
            self.assertEqual(code, 200)
            tok = j["token"]
            self.assertEqual(call("/api/messages")[0], 401)
            self.assertEqual(call("/api/send", {"text": "cześć mała"}, tok)[0], 200)
            for _ in range(10):
                clock.advance(30)
                engine.tick()
            code, j = call("/api/messages?after=0", None, tok)
            self.assertEqual(code, 200)
            self.assertGreaterEqual(len(j["messages"]), 2)
            self.assertIn("status", j["presence"])
            self.assertEqual(call("/api/forget", {}, tok)[0], 200)
            self.assertEqual(call("/api/messages", None, tok)[0], 401)
            # ścieżka poza web/ nie wychodzi
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(base + "/../zn/config.py")
        finally:
            srv.shutdown()
            config.DEV = False


if __name__ == "__main__":
    unittest.main()
