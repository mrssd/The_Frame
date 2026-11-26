"""
Passcode-protected local web portal for The Frame V2 (Stage 2 + Live .env Settings).

Uses Python's built-in ThreadingHTTPServer (zero extra pip dependencies):
  - Passcode login with HMAC-signed HttpOnly session cookie
  - Gallery tab: view uploaded photos, upload new ones, remove, Show Now, Rotate Random
  - Settings tab: view and edit .env settings live without SSH
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse

from config import PORTAL_SETTINGS_SCHEMA, Config, update_env_file
from photos import MAX_UPLOAD_BYTES, PhotoLibrary

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "frame_v2_session"
SESSION_TTL_SECONDS = 30 * 24 * 3600  # 30 days


class _PortalAuth:
    """Stateless HMAC-signed session token helper."""

    def __init__(self, passcode: str) -> None:
        self._passcode = passcode
        self._salt = secrets.token_hex(16)
        self._secret = hashlib.sha256(f"{passcode}:{self._salt}".encode()).digest()

    def update_passcode(self, new_passcode: str) -> None:
        self._passcode = new_passcode

    def verify_passcode(self, candidate: str) -> bool:
        return hmac.compare_digest(candidate.strip(), self._passcode)

    def create_token(self) -> str:
        exp = str(int(time.time()) + SESSION_TTL_SECONDS)
        sig = hmac.new(self._secret, exp.encode(), hashlib.sha256).hexdigest()
        return f"{exp}.{sig}"

    def is_valid_token(self, token: str | None) -> bool:
        if not token or "." not in token:
            return False
        exp_str, sig = token.split(".", 1)
        try:
            if int(exp_str) < int(time.time()):
                return False
        except ValueError:
            return False
        expected = hmac.new(self._secret, exp_str.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)


_PORTAL_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>The Frame V2 — Portal</title>
<style>
  :root {
    --bg: #f6f4ef;
    --card: #ffffff;
    --ink: #181818;
    --muted: #6e6a63;
    --border: #e3dfd7;
    --accent: #1856ae;
    --danger: #b42318;
    --ok: #1b6b3a;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .serif { font-family: Georgia, "Times New Roman", Baskerville, serif; }
  .wrap { max-width: 980px; margin: 0 auto; padding: 28px 18px 60px; }
  header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 20px;
  }
  h1 { margin: 0; font-size: 28px; font-weight: 600; letter-spacing: 0.2px; }
  .sub { color: var(--muted); font-size: 14px; margin-top: 4px; }
  .actions { display: flex; gap: 10px; flex-wrap: wrap; }

  /* Tabs */
  .tabs {
    display: flex;
    gap: 8px;
    margin-bottom: 22px;
  }
  .tab-btn {
    padding: 9px 18px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--card);
    color: var(--muted);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
  }
  .tab-btn.active {
    background: var(--ink);
    color: #fff;
    border-color: var(--ink);
  }

  button {
    appearance: none;
    border: 1px solid var(--border);
    background: var(--card);
    color: var(--ink);
    padding: 10px 16px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
  }
  button:hover { border-color: #bbb4a8; background: #fbfaf7; }
  button.primary { background: var(--ink); color: #fff; border-color: var(--ink); }
  button.primary:hover { background: #333; }
  button.danger { color: var(--danger); border-color: #f0c9c6; }
  button.danger:hover { background: #fef3f2; }
  button:disabled { opacity: 0.55; cursor: not-allowed; }

  /* Login Card */
  .login-box {
    max-width: 380px;
    margin: 10vh auto;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 32px 28px;
    text-align: center;
    box-shadow: 0 8px 30px rgba(0,0,0,0.04);
  }
  .login-box h1 { font-size: 26px; margin-bottom: 8px; }
  .login-box p { color: var(--muted); font-size: 14px; margin: 0 0 22px; }
  .login-box input {
    width: 100%;
    padding: 13px 14px;
    font-size: 18px;
    text-align: center;
    letter-spacing: 4px;
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 14px;
    outline: none;
  }
  .login-box input:focus { border-color: var(--ink); }
  .login-box button { width: 100%; padding: 12px; font-size: 15px; }
  .err { color: var(--danger); font-size: 13px; min-height: 18px; margin-top: 10px; }

  /* Upload Zone */
  .dropzone {
    background: var(--card);
    border: 2px dashed #cfc9be;
    border-radius: 16px;
    padding: 28px 20px;
    text-align: center;
    cursor: pointer;
    margin-bottom: 26px;
    transition: border-color 0.15s, background 0.15s;
  }
  .dropzone.drag { border-color: var(--accent); background: #f0f5fc; }
  .dropzone strong { display: block; font-size: 16px; margin-bottom: 6px; }
  .dropzone span { color: var(--muted); font-size: 13px; }
  #status, #settingsStatus {
    font-size: 13px;
    color: var(--muted);
    min-height: 20px;
    margin-bottom: 16px;
  }
  #status { margin-top: -14px; }
  .ok-text { color: var(--ok) !important; }
  .err-text { color: var(--danger) !important; }

  /* Gallery Grid */
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
    gap: 18px;
  }
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    box-shadow: 0 2px 10px rgba(0,0,0,0.03);
  }
  .thumb-wrap {
    aspect-ratio: 3 / 4;
    background: #ece9e2;
    position: relative;
    overflow: hidden;
  }
  .thumb-wrap img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .badge {
    position: absolute;
    top: 10px;
    left: 10px;
    background: rgba(24, 24, 24, 0.86);
    color: #fff;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.4px;
    padding: 5px 9px;
    border-radius: 999px;
  }
  .card-foot { padding: 12px; display: flex; flex-direction: column; gap: 8px; }
  .fname { font-size: 12px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .card-btns { display: flex; gap: 8px; }
  .card-btns button { flex: 1; padding: 8px 10px; font-size: 12px; border-radius: 8px; }
  .empty { text-align: center; padding: 48px 20px; color: var(--muted); font-size: 15px; }

  /* Settings Form */
  .settings-group {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px;
    margin-bottom: 18px;
  }
  .settings-group h2 {
    margin: 0 0 16px;
    font-size: 17px;
    font-weight: 600;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }
  .fields {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 14px 18px;
  }
  .field label {
    display: block;
    font-size: 12px;
    font-weight: 500;
    color: var(--muted);
    margin-bottom: 6px;
  }
  .field input, .field select {
    width: 100%;
    padding: 10px 12px;
    font-size: 14px;
    border: 1px solid var(--border);
    border-radius: 9px;
    background: #fcfbf9;
    color: var(--ink);
    outline: none;
  }
  .field input:focus, .field select:focus { border-color: var(--ink); background: #fff; }
  .settings-bar {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    align-items: center;
    margin-top: 8px;
  }
  .hidden { display: none !important; }
</style>
</head>
<body>
  <div id="loginView" class="login-box hidden">
    <h1 class="serif">The Frame</h1>
    <p>Enter your passcode to manage your frame.</p>
    <form id="loginForm">
      <input id="passInput" type="password" inputmode="numeric" placeholder="Passcode" autocomplete="current-password" required />
      <button type="submit" class="primary">Unlock Portal</button>
    </form>
    <div id="loginErr" class="err"></div>
  </div>

  <div id="appView" class="wrap hidden">
    <header>
      <div>
        <h1 class="serif">The Frame V2</h1>
        <div class="sub" id="summaryText">Loading…</div>
      </div>
      <div class="actions">
        <button id="rotateBtn" class="primary">Rotate Random Now</button>
        <button id="logoutBtn">Lock</button>
      </div>
    </header>

    <div class="tabs">
      <button class="tab-btn active" data-tab="gallery">Photos</button>
      <button class="tab-btn" data-tab="settings">Settings</button>
    </div>

    <!-- Gallery Tab -->
    <section id="galleryTab">
      <div id="dropzone" class="dropzone">
        <strong>Upload Photos</strong>
        <span>Tap to choose photos or drag &amp; drop here (JPG, PNG, WebP)</span>
        <input id="fileInput" type="file" accept="image/*" multiple class="hidden" />
      </div>
      <div id="status"></div>
      <div id="gallery" class="grid"></div>
      <div id="emptyMsg" class="empty hidden">No photos uploaded yet. Add photos above to start daily rotation.</div>
    </section>

    <!-- Settings Tab -->
    <section id="settingsTab" class="hidden">
      <form id="settingsForm">
        <div id="settingsGroups"></div>
        <div id="settingsStatus"></div>
        <div class="settings-bar">
          <button type="submit" class="primary" id="saveSettingsBtn">Save Settings</button>
          <button type="button" id="refreshNowBtn">Refresh Display Now</button>
        </div>
      </form>
    </section>
  </div>

<script>
const loginView = document.getElementById("loginView");
const appView = document.getElementById("appView");
const loginForm = document.getElementById("loginForm");
const passInput = document.getElementById("passInput");
const loginErr = document.getElementById("loginErr");
const gallery = document.getElementById("gallery");
const emptyMsg = document.getElementById("emptyMsg");
const summaryText = document.getElementById("summaryText");
const statusEl = document.getElementById("status");
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");

const galleryTab = document.getElementById("galleryTab");
const settingsTab = document.getElementById("settingsTab");
const settingsGroups = document.getElementById("settingsGroups");
const settingsForm = document.getElementById("settingsForm");
const settingsStatus = document.getElementById("settingsStatus");

function setStatus(msg) { statusEl.textContent = msg || ""; }
function setSettingsStatus(msg, cls = "") {
  settingsStatus.textContent = msg || "";
  settingsStatus.className = cls;
}

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const isSettings = btn.dataset.tab === "settings";
    galleryTab.classList.toggle("hidden", isSettings);
    settingsTab.classList.toggle("hidden", !isSettings);
    if (isSettings) loadSettings();
  };
});

async function checkAndLoad() {
  const res = await fetch("/api/photos");
  if (res.status === 401) {
    appView.classList.add("hidden");
    loginView.classList.remove("hidden");
    passInput.focus();
    return;
  }
  loginView.classList.add("hidden");
  appView.classList.remove("hidden");
  const data = await res.json();
  renderGallery(data.photos || []);
}

function renderGallery(photos) {
  gallery.innerHTML = "";
  const count = photos.length;
  summaryText.textContent = `${count} photo${count === 1 ? "" : "s"} · Rotates randomly every day`;
  emptyMsg.classList.toggle("hidden", count > 0);

  for (const p of photos) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="thumb-wrap">
        <img src="/api/thumb/${encodeURIComponent(p.filename)}" alt="" loading="lazy" />
        ${p.is_current ? '<div class="badge">ON DISPLAY</div>' : ''}
      </div>
      <div class="card-foot">
        <div class="fname" title="${p.filename}">${p.filename}</div>
        <div class="card-btns">
          <button class="show-btn">${p.is_current ? 'Refresh' : 'Show Now'}</button>
          <button class="danger del-btn">Remove</button>
        </div>
      </div>
    `;
    card.querySelector(".show-btn").onclick = async () => {
      setStatus(`Sending ${p.filename} to the frame…`);
      const r = await fetch(`/api/show/${encodeURIComponent(p.filename)}`, { method: "POST" });
      if (r.ok) {
        setStatus("Frame refresh triggered (takes ~20s on E-Ink).");
        checkAndLoad();
      } else {
        setStatus("Could not trigger display refresh.");
      }
    };
    card.querySelector(".del-btn").onclick = async () => {
      if (!confirm(`Remove "${p.filename}"?`)) return;
      setStatus(`Removing ${p.filename}…`);
      const r = await fetch(`/api/photos/${encodeURIComponent(p.filename)}`, { method: "DELETE" });
      if (r.ok) {
        setStatus("Photo removed.");
        checkAndLoad();
      } else {
        setStatus("Failed to remove photo.");
      }
    };
    gallery.appendChild(card);
  }
}

async function loadSettings() {
  setSettingsStatus("Loading settings…");
  const r = await fetch("/api/settings");
  if (r.status === 401) { checkAndLoad(); return; }
  const data = await r.json();
  const values = data.values || {};
  const schema = data.schema || [];

  const grouped = {};
  for (const item of schema) {
    if (!grouped[item.group]) grouped[item.group] = [];
    grouped[item.group].push(item);
  }

  settingsGroups.innerHTML = "";
  for (const [groupName, items] of Object.entries(grouped)) {
    const box = document.createElement("div");
    box.className = "settings-group";
    box.innerHTML = `<h2 class="serif">${groupName}</h2><div class="fields"></div>`;
    const fieldsEl = box.querySelector(".fields");

    for (const item of items) {
      const f = document.createElement("div");
      f.className = "field";
      const val = values[item.key] ?? "";
      let control = "";
      if (item.type === "select") {
        const opts = (item.options || []).map((o) =>
          `<option value="${o}" ${String(val).toLowerCase() === String(o).toLowerCase() ? "selected" : ""}>${o}</option>`
        ).join("");
        control = `<select name="${item.key}">${opts}</select>`;
      } else {
        const attrs = [];
        if (item.min !== undefined) attrs.push(`min="${item.min}"`);
        if (item.max !== undefined) attrs.push(`max="${item.max}"`);
        if (item.step !== undefined) attrs.push(`step="${item.step}"`);
        control = `<input type="${item.type || "text"}" name="${item.key}" value="${String(val).replace(/"/g, "&quot;")}" ${attrs.join(" ")} />`;
      }
      f.innerHTML = `<label>${item.label}</label>${control}`;
      fieldsEl.appendChild(f);
    }
    settingsGroups.appendChild(box);
  }
  setSettingsStatus("");
}

settingsForm.onsubmit = async (e) => {
  e.preventDefault();
  setSettingsStatus("Saving to .env…");
  const fd = new FormData(settingsForm);
  const payload = {};
  for (const [k, v] of fd.entries()) payload[k] = v;

  const r = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ values: payload }),
  });
  const data = await r.json();
  if (r.ok) {
    setSettingsStatus("Saved to .env and reloaded live!", "ok-text");
  } else {
    setSettingsStatus(data.error || "Failed to save settings.", "err-text");
  }
};

document.getElementById("refreshNowBtn").onclick = async () => {
  setSettingsStatus("Triggering display refresh (~20s on E-Ink)…");
  const r = await fetch("/api/refresh", { method: "POST" });
  if (r.ok) {
    setSettingsStatus("Display refresh started with current settings.", "ok-text");
  } else {
    setSettingsStatus("Could not refresh display.", "err-text");
  }
};

loginForm.onsubmit = async (e) => {
  e.preventDefault();
  loginErr.textContent = "";
  const r = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ passcode: passInput.value }),
  });
  if (r.ok) {
    passInput.value = "";
    checkAndLoad();
  } else {
    loginErr.textContent = "Incorrect passcode.";
    passInput.select();
  }
};

document.getElementById("logoutBtn").onclick = async () => {
  await fetch("/api/logout", { method: "POST" });
  checkAndLoad();
};

document.getElementById("rotateBtn").onclick = async () => {
  setStatus("Picking a new random photo…");
  const r = await fetch("/api/rotate", { method: "POST" });
  if (r.ok) {
    const data = await r.json();
    setStatus(data.photo ? `Showing ${data.photo} (refreshing E-Ink…)` : "No photos to rotate.");
    checkAndLoad();
  }
};

async function uploadFiles(files) {
  if (!files || !files.length) return;
  let uploaded = 0;
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    setStatus(`Uploading ${i + 1} of ${files.length}: ${file.name}…`);
    const r = await fetch(`/api/upload?name=${encodeURIComponent(file.name)}`, {
      method: "POST",
      body: file,
    });
    if (r.ok) uploaded++;
  }
  setStatus(`Uploaded ${uploaded} photo${uploaded === 1 ? "" : "s"}.`);
  fileInput.value = "";
  checkAndLoad();
}

dropzone.onclick = () => fileInput.click();
fileInput.onchange = () => uploadFiles(fileInput.files);
dropzone.ondragover = (e) => { e.preventDefault(); dropzone.classList.add("drag"); };
dropzone.ondragleave = () => dropzone.classList.remove("drag");
dropzone.ondrop = (e) => {
  e.preventDefault();
  dropzone.classList.remove("drag");
  uploadFiles(e.dataTransfer.files);
};

checkAndLoad();
</script>
</body>
</html>
"""


class PhotoPortalServer:
    """Background HTTP server hosting the passcode-protected photo & settings portal."""

    def __init__(
        self,
        config: Config,
        library: PhotoLibrary,
        on_show_photo: Callable[[str], None] | None = None,
        on_rotate_random: Callable[[], str | None] | None = None,
        on_config_reloaded: Callable[[], Config] | None = None,
        on_refresh_display: Callable[[], None] | None = None,
    ) -> None:
        self.config = config
        self.library = library
        self.auth = _PortalAuth(config.portal_passcode)
        self.on_show_photo = on_show_photo
        self.on_rotate_random = on_rotate_random
        self.on_config_reloaded = on_config_reloaded
        self.on_refresh_display = on_refresh_display
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def _make_handler(self):
        portal = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                logger.debug("Portal %s - " + fmt, self.address_string(), *args)

            def _is_authenticated(self) -> bool:
                raw_cookie = self.headers.get("Cookie", "")
                if not raw_cookie:
                    return False
                jar = cookies.SimpleCookie()
                jar.load(raw_cookie)
                morsel = jar.get(SESSION_COOKIE_NAME)
                return portal.auth.is_valid_token(morsel.value if morsel else None)

            def _send_json(self, code: int, payload: dict, extra_headers: dict[str, str] | None = None) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                if extra_headers:
                    for k, v in extra_headers.items():
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def _send_bytes(self, code: int, body: bytes, content_type: str, cache: str = "no-store") -> None:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", cache)
                self.end_headers()
                self.wfile.write(body)

            def _require_auth(self) -> bool:
                if not self._is_authenticated():
                    self._send_json(401, {"error": "Unauthorized"})
                    return False
                return True

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path

                if path in ("/", "/index.html"):
                    self._send_bytes(200, _PORTAL_HTML.encode("utf-8"), "text/html; charset=utf-8")
                    return

                if path == "/api/photos":
                    if not self._require_auth():
                        return
                    items = [
                        {
                            "filename": p.filename,
                            "size_bytes": p.size_bytes,
                            "modified_ts": p.modified_ts,
                            "is_current": p.is_current,
                        }
                        for p in portal.library.list_photos()
                    ]
                    self._send_json(200, {"photos": items})
                    return

                if path == "/api/settings":
                    if not self._require_auth():
                        return
                    self._send_json(
                        200,
                        {
                            "schema": PORTAL_SETTINGS_SCHEMA,
                            "values": portal.config.to_editable_dict(),
                        },
                    )
                    return

                if path.startswith("/api/thumb/"):
                    if not self._require_auth():
                        return
                    filename = unquote(path[len("/api/thumb/"):])
                    data = portal.library.get_thumbnail_bytes(filename)
                    if data is None:
                        self._send_json(404, {"error": "Not found"})
                        return
                    self._send_bytes(200, data, "image/jpeg", cache="private, max-age=3600")
                    return

                self._send_json(404, {"error": "Not found"})

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path

                if path == "/api/login":
                    length = int(self.headers.get("Content-Length", "0") or 0)
                    raw = self.rfile.read(min(length, 4096))
                    try:
                        body = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self._send_json(400, {"error": "Invalid JSON"})
                        return

                    if not portal.auth.verify_passcode(str(body.get("passcode", ""))):
                        self._send_json(401, {"error": "Invalid passcode"})
                        return

                    token = portal.auth.create_token()
                    cookie_val = (
                        f"{SESSION_COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; "
                        f"Max-Age={SESSION_TTL_SECONDS}"
                    )
                    self._send_json(200, {"ok": True}, extra_headers={"Set-Cookie": cookie_val})
                    return

                if path == "/api/logout":
                    cookie_val = f"{SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
                    self._send_json(200, {"ok": True}, extra_headers={"Set-Cookie": cookie_val})
                    return

                if path == "/api/settings":
                    if not self._require_auth():
                        return
                    length = int(self.headers.get("Content-Length", "0") or 0)
                    raw = self.rfile.read(min(length, 32768))
                    try:
                        body = json.loads(raw.decode("utf-8"))
                        updates = body.get("values") or {}
                        if not isinstance(updates, dict):
                            raise ValueError("Invalid settings payload")
                        applied = update_env_file(portal.config.env_path, updates)
                        if portal.on_config_reloaded:
                            portal.config = portal.on_config_reloaded()
                        else:
                            portal.config = Config.load(env_path=portal.config.env_path, override=True)
                            portal.auth.update_passcode(portal.config.portal_passcode)
                    except ValueError as exc:
                        self._send_json(400, {"error": str(exc)})
                        return
                    except Exception as exc:
                        logger.error("Failed to save settings: %s", exc)
                        self._send_json(500, {"error": "Failed to save .env settings"})
                        return
                    self._send_json(200, {"ok": True, "updated": list(applied.keys())})
                    return

                if path == "/api/refresh":
                    if not self._require_auth():
                        return
                    if portal.on_refresh_display:
                        portal.on_refresh_display()
                    self._send_json(200, {"ok": True})
                    return

                if path == "/api/upload":
                    if not self._require_auth():
                        return
                    length = int(self.headers.get("Content-Length", "0") or 0)
                    if length <= 0 or length > MAX_UPLOAD_BYTES:
                        self._send_json(400, {"error": "Invalid file size"})
                        return
                    qs = parse_qs(parsed.query)
                    orig_name = (qs.get("name") or ["photo.jpg"])[0]
                    raw_bytes = self.rfile.read(length)
                    try:
                        item = portal.library.save_upload(orig_name, raw_bytes)
                    except ValueError as exc:
                        self._send_json(400, {"error": str(exc)})
                        return
                    self._send_json(200, {"ok": True, "filename": item.filename})
                    return

                if path.startswith("/api/show/"):
                    if not self._require_auth():
                        return
                    filename = unquote(path[len("/api/show/"):])
                    if portal.library.get_photo_path(filename) is None:
                        self._send_json(404, {"error": "Photo not found"})
                        return
                    if portal.on_show_photo:
                        threading.Thread(
                            target=portal.on_show_photo, args=(filename,), daemon=True
                        ).start()
                    self._send_json(200, {"ok": True, "filename": filename})
                    return

                if path == "/api/rotate":
                    if not self._require_auth():
                        return
                    chosen = None
                    if portal.on_rotate_random:
                        chosen = portal.on_rotate_random()
                    self._send_json(200, {"ok": True, "photo": chosen})
                    return

                self._send_json(404, {"error": "Not found"})

            def do_DELETE(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path

                if path.startswith("/api/photos/"):
                    if not self._require_auth():
                        return
                    filename = unquote(path[len("/api/photos/"):])
                    if portal.library.delete_photo(filename):
                        self._send_json(200, {"ok": True})
                    else:
                        self._send_json(404, {"error": "Photo not found"})
                    return

                self._send_json(404, {"error": "Not found"})

        return Handler

    def start(self) -> None:
        self._server = ThreadingHTTPServer(
            (self.config.portal_host, self.config.portal_port),
            self._make_handler(),
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="photo-portal",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Photo portal running at http://%s:%d",
            self.config.portal_host,
            self.config.portal_port,
        )

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
