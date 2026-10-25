(() => {
  "use strict";
  const API = (window.ZNAJOMY_API || "").replace(/\/$/, "");
  const url = p => (API ? API + "/" : "") + p;
  const $ = id => document.getElementById(id);
  const TOKEN_KEY = "zn_token";

  let token = null, lastId = 0, timer = null, busy = false, lastDay = "", lastWho = "";
  const known = new Map();   // id -> element (wiadomości moje, do znaczników odczytu)

  try { token = localStorage.getItem(TOKEN_KEY); } catch (_) {}

  async function api(path, opts = {}) {
    const headers = {"Content-Type": "application/json"};
    if (token) headers["Authorization"] = "Bearer " + token;
    const res = await fetch(url(path), {...opts, headers});
    let data = {};
    try { data = await res.json(); } catch (_) {}
    if (res.status === 401 && token) { logout(); }
    return {ok: res.ok, status: res.status, data};
  }

  function show(id) {
    for (const s of ["welcome", "chat"]) $(s).classList.toggle("hidden", s !== id);
  }

  function logout() {
    try { localStorage.removeItem(TOKEN_KEY); } catch (_) {}
    token = null; lastId = 0; lastDay = ""; lastWho = ""; known.clear();
    $("log").textContent = "";
    clearInterval(timer);
    show("welcome");
  }

  // ---------- rejestracja
  $("reg").addEventListener("submit", async e => {
    e.preventDefault();
    $("regerr").textContent = "";
    if (!$("adult").checked || !$("ai").checked) {
      $("regerr").textContent = "Zaznacz oba potwierdzenia, żeby zacząć.";
      return;
    }
    $("regbtn").disabled = true;
    try {
      const r = await api("api/register", {method: "POST", body: JSON.stringify({
        code: $("code").value, adult: true, ack_ai: true})});
      if (!r.ok) { $("regerr").textContent = r.data.error || "Nie udało się. Spróbuj ponownie."; return; }
      token = r.data.token;
      try { localStorage.setItem(TOKEN_KEY, token); } catch (_) {}
      $("code").value = "";
      startChat();
    } catch (_) {
      $("regerr").textContent = "Brak połączenia z serwerem.";
    } finally { $("regbtn").disabled = false; }
  });

  // ---------- czat
  const pad = n => String(n).padStart(2, "0");
  function dayLabel(d) {
    const now = new Date();
    const same = (a, b) => a.toDateString() === b.toDateString();
    if (same(d, now)) return "Dziś";
    const y = new Date(now); y.setDate(now.getDate() - 1);
    if (same(d, y)) return "Wczoraj";
    return pad(d.getDate()) + "." + pad(d.getMonth() + 1) + "." + d.getFullYear();
  }

  function addMessage(m) {
    const d = new Date(m.ts * 1000);
    const dk = d.toDateString();
    const log = $("log");
    if (dk !== lastDay) {
      const s = document.createElement("div");
      s.className = "day"; s.textContent = dayLabel(d);
      log.appendChild(s); lastDay = dk; lastWho = "";
    }
    const el = document.createElement("div");
    el.className = "msg " + m.role + (lastWho && lastWho !== m.role ? " gap" : "");
    lastWho = m.role;
    el.appendChild(document.createTextNode(m.text));
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = pad(d.getHours()) + ":" + pad(d.getMinutes()) + (m.role === "me" ? " " + (m.read ? "✓✓" : "✓") : "");
    el.appendChild(meta);
    el.dataset.time = pad(d.getHours()) + ":" + pad(d.getMinutes());
    log.appendChild(el);
    if (m.role === "me") known.set(m.id, el);
  }

  function setTyping(on) {
    let t = $("typing");
    if (on && !t) {
      t = document.createElement("div");
      t.id = "typing"; t.className = "typing-bubble";
      t.innerHTML = "<i></i><i></i><i></i>";
      $("log").appendChild(t);
    } else if (!on && t) { t.remove(); }
    else if (on && t) { $("log").appendChild(t); }
  }

  function nearBottom() {
    const l = $("log");
    return l.scrollHeight - l.scrollTop - l.clientHeight < 140;
  }
  function toBottom() { const l = $("log"); l.scrollTop = l.scrollHeight; }

  async function poll() {
    if (!token || busy || document.hidden) return;
    busy = true;
    try {
      const r = await api("api/messages?after=" + lastId);
      if (!r.ok) return;
      const stick = nearBottom();
      document.querySelectorAll(".msg.pending").forEach(n => n.remove());
      for (const m of r.data.messages) { addMessage(m); lastId = Math.max(lastId, m.id); }
      for (const id of r.data.read_ids || []) {
        const el = known.get(id);
        if (el) { const mt = el.querySelector(".meta"); mt.textContent = el.dataset.time + " ✓✓"; }
      }
      const p = r.data.presence || {};
      $("name").textContent = p.name || "Nowy znajomy";
      $("avatar").textContent = p.initial && p.name !== "Nowy znajomy" ? p.initial : "?";
      $("status").textContent = p.status || "";
      $("status").classList.toggle("typing", !!p.typing);
      setTyping(!!p.typing);
      if (stick || r.data.messages.length) toBottom();
    } catch (_) { /* brak sieci: spróbujemy przy następnym odpytaniu */ }
    finally { busy = false; }
  }

  function startChat() {
    show("chat");
    iosHint();
    lastId = 0; lastDay = ""; lastWho = ""; known.clear(); $("log").textContent = "";
    poll();
    clearInterval(timer);
    timer = setInterval(poll, 2500);
    registerSW();
  }

  async function send() {
    const input = $("input");
    const text = input.value.trim();
    if (!text) return;
    input.value = ""; autoGrow();
    const el = document.createElement("div");
    el.className = "msg me pending";
    el.appendChild(document.createTextNode(text));
    $("log").appendChild(el); toBottom();
    const r = await api("api/send", {method: "POST", body: JSON.stringify({text})});
    if (!r.ok) {
      el.classList.remove("pending");
      el.style.opacity = ".4";
      el.title = "Nie wysłano";
      input.value = text; autoGrow();
      return;
    }
    poll();
  }

  $("composer").addEventListener("submit", e => { e.preventDefault(); send(); });
  const input = $("input");
  function autoGrow() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 130) + "px"; }
  input.addEventListener("input", autoGrow);
  input.addEventListener("keydown", e => {
    const desktop = window.matchMedia("(pointer:fine)").matches;
    if (e.key === "Enter" && !e.shiftKey && desktop) { e.preventDefault(); send(); }
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });

  // ---------- menu
  const sheet = $("sheet");
  const msg = t => { $("sheetmsg").textContent = t || ""; };
  $("menubtn").addEventListener("click", () => { msg(""); $("about").classList.add("hidden"); sheet.classList.remove("hidden"); });
  $("sheetclose").addEventListener("click", () => sheet.classList.add("hidden"));
  sheet.addEventListener("click", e => { if (e.target === sheet) sheet.classList.add("hidden"); });
  $("aboutbtn").addEventListener("click", () => $("about").classList.toggle("hidden"));
  $("resetbtn").addEventListener("click", async () => {
    if (!confirm("Usunąć całą rozmowę i wszystko, co Znajomy o Tobie wie? Nie da się tego cofnąć. Poznasz kogoś zupełnie nowego.")) return;
    await api("api/forget", {method: "POST", body: "{}"});
    sheet.classList.add("hidden");
    logout();
  });

  // ---------- powiadomienia
  function b64(s) {
    const p = "=".repeat((4 - s.length % 4) % 4);
    const raw = atob((s + p).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
  }
  $("notifbtn").addEventListener("click", async () => {
    try {
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
        msg("Ta przeglądarka nie obsługuje powiadomień. Na iPhonie dodaj najpierw aplikację do ekranu początkowego.");
        return;
      }
      const k = await api("api/push/key");
      if (!k.data.key) { msg("Serwer nie ma jeszcze włączonych powiadomień."); return; }
      const perm = await Notification.requestPermission();
      if (perm !== "granted") { msg("Powiadomienia zostały zablokowane w ustawieniach telefonu."); return; }
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: b64(k.data.key)});
      const r = await api("api/push/subscribe", {method: "POST", body: JSON.stringify({subscription: sub.toJSON()})});
      msg(r.ok ? "Powiadomienia włączone." : "Nie udało się włączyć powiadomień.");
    } catch (e) { msg("Nie udało się włączyć powiadomień."); }
  });

  function iosHint() {
    const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
    const standalone = window.navigator.standalone === true || window.matchMedia("(display-mode: standalone)").matches;
    let dismissed = false;
    try { dismissed = localStorage.getItem("zn_hint") === "1"; } catch (_) {}
    $("iosHint").classList.toggle("hidden", !(ios && !standalone && !dismissed));
  }
  $("iosHintClose").addEventListener("click", () => {
    try { localStorage.setItem("zn_hint", "1"); } catch (_) {}
    $("iosHint").classList.add("hidden");
  });

  function registerSW() {
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
  }

  // ---------- start
  if (token) startChat(); else { show("welcome"); registerSW(); }
})();
