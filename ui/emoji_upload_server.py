from __future__ import annotations

import html
import os
import re
import secrets
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import discord
from aiohttp import web


_ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _detect_lan_ip() -> str:
    configured = os.getenv("SENA_LAN_IP", "").strip()
    if configured:
        return configured

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No packet needs to be sent; this only asks the OS which local interface
        # would be used for an IPv4 route.
        sock.connect(("1.1.1.1", 80))
        return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _safe_emoji_name(filename: str, existing: set[str]) -> str:
    stem = Path(filename).stem
    base = re.sub(r"[^A-Za-z0-9_]", "_", stem).strip("_") or "emoji"
    base = base[:28]
    if len(base) < 2:
        base = f"emoji_{base}"

    candidate = base
    number = 2
    while candidate in existing:
        suffix = f"_{number}"
        candidate = (base[: 32 - len(suffix)] + suffix)[:32]
        number += 1
    return candidate


@dataclass(slots=True)
class EmojiUploadResult:
    file: str
    ok: bool
    detail: str


class EmojiUploadServer:
    """Tiny LAN-only browser uploader for Discord emoji files.

    Flet's server-side web FilePicker service is currently unreliable on some web
    runtimes. This server deliberately uses the browser's native HTML file input and
    drag/drop APIs instead, while keeping Discord upload execution inside Senna's
    existing asyncio process.
    """

    def __init__(
        self,
        client: discord.Client,
        *,
        host: str,
        port: int,
        max_emoji_size: int,
    ) -> None:
        self.client = client
        self.host = host
        self.port = port
        self.max_emoji_size = max_emoji_size
        self.token = secrets.token_urlsafe(24)
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def lan_ip(self) -> str:
        return _detect_lan_ip()

    @property
    def public_url(self) -> str:
        return f"http://{self.lan_ip}:{self.port}/?token={self.token}"

    def _authorized(self, request: web.Request) -> bool:
        supplied = request.query.get("token", "")
        return bool(supplied) and secrets.compare_digest(supplied, self.token)

    async def start(self) -> None:
        if self._running:
            return

        app = web.Application(client_max_size=64 * 1024 * 1024)
        app.router.add_get("/", self._index)
        app.router.add_post("/api/upload", self._upload)
        app.router.add_get("/health", self._health)

        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        self._running = True

    async def stop(self) -> None:
        self._running = False
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._site = None

    async def _health(self, request: web.Request) -> web.Response:
        del request
        return web.json_response({"ok": True, "running": self._running})

    def _guild_options_html(self) -> str:
        options: list[str] = []
        for guild in self.client.guilds:
            options.append(
                f'<option value="{guild.id}">{html.escape(guild.name)}</option>'
            )
        if not options:
            options.append('<option value="">Discord belum ready</option>')
        return "\n".join(options)

    async def _index(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            raise web.HTTPForbidden(text="Invalid or missing uploader token")

        max_kb = self.max_emoji_size // 1024
        page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Senna Emoji Uploader</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:#050505; color:#f4f4f5; font-family:Inter,system-ui,Segoe UI,sans-serif; }}
main {{ max-width:980px; margin:0 auto; padding:32px 18px 60px; }}
.card {{ background:#101010; border:1px solid #242424; border-radius:18px; padding:20px; margin-top:18px; }}
h1 {{ margin:0 0 6px; font-size:30px; }}
p,.muted {{ color:#8e8e93; }}
label {{ display:block; font-size:13px; margin-bottom:7px; color:#cfcfd3; }}
select,button {{ background:#151515; color:#f4f4f5; border:1px solid #303034; border-radius:12px; padding:11px 13px; font:inherit; }}
select {{ width:100%; }}
button {{ cursor:pointer; font-weight:650; }}
button:disabled {{ opacity:.45; cursor:not-allowed; }}
#drop {{ margin-top:16px; min-height:250px; border:1.5px dashed #4a4a50; border-radius:18px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:28px; transition:.15s; background:#0a0a0a; }}
#drop.drag {{ border-color:#9f9fa8; background:#141414; transform:scale(1.002); }}
#drop strong {{ font-size:20px; }}
#files {{ display:none; }}
.actions {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:16px; }}
#list {{ margin-top:16px; max-height:280px; overflow:auto; font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:12px; line-height:1.6; color:#c9c9ce; }}
#result {{ white-space:pre-wrap; font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:12px; line-height:1.6; }}
.ok {{ color:#69d49d; }} .bad {{ color:#ff7070; }} .warn {{ color:#e6b85c; }}
</style>
</head>
<body>
<main>
  <h1>Senna Emoji Uploader</h1>
  <p>Native browser drag & drop · multi-file · langsung ke Discord.</p>
  <div class="card">
    <label for="guild">Discord server</label>
    <select id="guild">{self._guild_options_html()}</select>

    <div id="drop" tabindex="0">
      <strong>Drop emoji files here</strong>
      <p>atau klik area ini untuk memilih banyak file sekaligus</p>
      <div class="muted">PNG · JPG · GIF · WEBP · max {max_kb} KB per file</div>
    </div>
    <input id="files" type="file" multiple accept=".png,.jpg,.jpeg,.gif,.webp,image/png,image/jpeg,image/gif,image/webp">

    <div class="actions">
      <button id="choose">Choose files</button>
      <button id="upload" disabled>Upload selected</button>
      <button id="clear" disabled>Clear</button>
    </div>
    <div id="list" class="muted">No files selected.</div>
  </div>

  <div class="card">
    <strong>Result</strong>
    <div id="result" class="muted">Waiting.</div>
  </div>
</main>
<script>
const token = new URLSearchParams(location.search).get('token') || '';
const drop = document.getElementById('drop');
const input = document.getElementById('files');
const choose = document.getElementById('choose');
const upload = document.getElementById('upload');
const clear = document.getElementById('clear');
const list = document.getElementById('list');
const result = document.getElementById('result');
let selected = [];

function render() {{
  if (!selected.length) {{
    list.textContent = 'No files selected.';
    upload.disabled = true;
    clear.disabled = true;
    return;
  }}
  list.innerHTML = selected.map((f,i) => `${{i+1}}. ${{escapeHtml(f.name)}} · ${{(f.size/1024).toFixed(1)}} KB`).join('<br>');
  upload.disabled = false;
  clear.disabled = false;
}}
function escapeHtml(s) {{ return s.replace(/[&<>'"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}})[c]); }}
function addFiles(files) {{
  for (const f of files) {{
    const key = `${{f.name}}:${{f.size}}:${{f.lastModified}}`;
    if (!selected.some(x => `${{x.name}}:${{x.size}}:${{x.lastModified}}` === key)) selected.push(f);
  }}
  render();
}}
choose.onclick = () => input.click();
drop.onclick = () => input.click();
drop.onkeydown = e => {{ if (e.key === 'Enter' || e.key === ' ') input.click(); }};
input.onchange = () => addFiles(input.files);
['dragenter','dragover'].forEach(evt => drop.addEventListener(evt, e => {{ e.preventDefault(); drop.classList.add('drag'); }}));
['dragleave','drop'].forEach(evt => drop.addEventListener(evt, e => {{ e.preventDefault(); drop.classList.remove('drag'); }}));
drop.addEventListener('drop', e => addFiles(e.dataTransfer.files));
clear.onclick = () => {{ selected = []; input.value=''; render(); result.textContent='Waiting.'; result.className='muted'; }};

upload.onclick = async () => {{
  if (!selected.length) return;
  const guild = document.getElementById('guild').value;
  if (!guild) {{ result.textContent='No Discord server selected.'; result.className='bad'; return; }}
  const fd = new FormData();
  fd.append('guild_id', guild);
  for (const f of selected) fd.append('files', f, f.name);
  upload.disabled = true;
  choose.disabled = true;
  result.textContent = `Uploading ${{selected.length}} file(s)...`;
  result.className = 'warn';
  try {{
    const response = await fetch(`/api/upload?token=${{encodeURIComponent(token)}}`, {{ method:'POST', body:fd }});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${{response.status}}`);
    result.textContent = data.results.map(r => `${{r.ok ? 'OK' : 'FAIL'}} · ${{r.file}} · ${{r.detail}}`).join('\n') + `\n\nSuccess=${{data.success}} · Failed=${{data.failed}} · Skipped=${{data.skipped}}`;
    result.className = data.success ? 'ok' : 'bad';
    if (data.success) {{ selected = []; input.value=''; render(); }}
  }} catch (err) {{
    result.textContent = `Upload failed: ${{err}}`;
    result.className = 'bad';
  }} finally {{
    choose.disabled = false;
    upload.disabled = !selected.length;
  }}
}};
</script>
</body>
</html>"""
        return web.Response(text=page, content_type="text/html")

    async def _upload(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return web.json_response({"error": "Invalid uploader token"}, status=403)

        try:
            reader = await request.multipart()
        except Exception as error:
            return web.json_response(
                {"error": f"Invalid multipart body: {type(error).__name__}: {error}"},
                status=400,
            )

        guild_id: int | None = None
        incoming: list[tuple[str, bytes]] = []
        skipped_results: list[EmojiUploadResult] = []

        async for part in reader:
            if part.name == "guild_id":
                raw = (await part.text()).strip()
                try:
                    guild_id = int(raw)
                except ValueError:
                    guild_id = None
                continue

            if part.name != "files" or not part.filename:
                continue

            filename = Path(part.filename).name
            suffix = Path(filename).suffix.casefold()
            if suffix not in _ALLOWED_SUFFIXES:
                skipped_results.append(
                    EmojiUploadResult(filename, False, "unsupported format")
                )
                continue

            data = await part.read(decode=False)
            if len(data) > self.max_emoji_size:
                skipped_results.append(
                    EmojiUploadResult(
                        filename,
                        False,
                        f"too large ({len(data) / 1024:.1f} KB)",
                    )
                )
                continue
            if not data:
                skipped_results.append(EmojiUploadResult(filename, False, "empty file"))
                continue
            incoming.append((filename, bytes(data)))

        if guild_id is None:
            return web.json_response({"error": "Missing or invalid guild_id"}, status=400)

        guild = self.client.get_guild(guild_id)
        if guild is None:
            return web.json_response({"error": "Discord server not found"}, status=404)

        existing = {emoji.name for emoji in guild.emojis}
        results: list[EmojiUploadResult] = list(skipped_results)
        success = 0
        failed = 0

        for filename, data in incoming:
            emoji_name = _safe_emoji_name(filename, existing)
            try:
                emoji = await guild.create_custom_emoji(
                    name=emoji_name,
                    image=data,
                    reason="Senna browser drag-drop emoji uploader",
                )
                existing.add(emoji.name)
                success += 1
                results.append(EmojiUploadResult(filename, True, f"created as {emoji.name}"))
            except discord.Forbidden:
                failed += 1
                results.append(
                    EmojiUploadResult(filename, False, "missing Manage Expressions permission")
                )
            except discord.HTTPException as error:
                failed += 1
                detail = f"Discord HTTP {error.status}"
                if getattr(error, "text", None):
                    detail += f": {str(error.text)[:180]}"
                results.append(EmojiUploadResult(filename, False, detail))
            except Exception as error:
                failed += 1
                results.append(
                    EmojiUploadResult(filename, False, f"{type(error).__name__}: {error}")
                )

        skipped = len(skipped_results)
        return web.json_response(
            {
                "ok": True,
                "success": success,
                "failed": failed,
                "skipped": skipped,
                "results": [
                    {"file": item.file, "ok": item.ok, "detail": item.detail}
                    for item in results
                ],
            }
        )
