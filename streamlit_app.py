"""
streamlit_app.py — Dashboard remoto de Polymarket Bot V4
========================================================
Muestra en la nube EXACTAMENTE la misma interfaz que el panel local (templates/index.html):
la plantilla se carga tal cual y sus llamadas a /api/... se responden con el snapshot que
publica telemetry_sync.py. Es de solo lectura: los botones que cambian el estado del bot
(modo real, reset de saldo, simulador) se ocultan.

Fuentes del snapshot (por orden):
1. Local: data/telemetry_snapshot.json (o se genera al vuelo desde trading_bot.db)
2. Nube: feed público de GitHub (srrxnogz/polymarket-dashboard, rama telemetry) o la URL de st.secrets / barra lateral.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional

import requests
import streamlit as st
import streamlit.components.v1 as components

BASE_DIR = Path(__file__).parent
TEMPLATE = BASE_DIR / "templates" / "index.html"
DEFAULT_FEED = "https://raw.githubusercontent.com/srrxnogz/polymarket-dashboard/telemetry/telemetry_snapshot.json"
REFRESH_S = 15

st.set_page_config(page_title="Polymarket Bot · V4.5", page_icon="🎯", layout="wide", initial_sidebar_state="collapsed")

# Streamlit sin cromo: el panel ocupa toda la página con el mismo fondo que el local
st.markdown("""
<style>
.stApp { background: #070b14 !important; }
header[data-testid="stHeader"] { background: transparent !important; }
.block-container { padding: 0.6rem 0.4rem 0 0.4rem !important; max-width: 100% !important; }
footer, #MainMenu, [data-testid="stToolbar"], [data-testid="stDecoration"] { visibility: hidden; }
iframe[title="st.iframe"], .element-container iframe { border: 0 !important; }
</style>
""", unsafe_allow_html=True)


def _secret(key: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(key, default) or default).strip()
    except Exception:
        return default


# ── Carga del snapshot ─────────────────────────────────────────────────────────
@st.cache_data(ttl=5)
def load_from_file(file_path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


@st.cache_data(ttl=5)
def load_from_url(url: str, auth_token: Optional[str] = None) -> tuple:
    """Carga el snapshot desde raw de GitHub, la API de contenidos, un Gist o un endpoint REST.
    Devuelve (snapshot o None, explicación del fallo o "")."""
    import base64
    try:
        sep = "&" if "?" in url else "?"
        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        if "api.github.com/repos" in url and "contents" in url:
            headers["Accept"] = "application/vnd.github.raw+json"     # contenido tal cual (sin base64 ni límite de 1 MB)
        resp = requests.get(f"{url}{sep}_cb={int(time.time())}", headers=headers, timeout=8.0)
        if resp.status_code != 200:
            why = {401: "token no válido o caducado", 403: "token sin permiso (Contents: Read-only) o límite de GitHub",
                   404: "no encontrado: falta el token o no tiene acceso a ese repositorio"}.get(resp.status_code, "")
            return None, f"GitHub respondió HTTP {resp.status_code} {why}".strip()
        data = resp.json()
        if isinstance(data, dict) and data.get("encoding") == "base64" and "content" in data:
            return json.loads(base64.b64decode(data["content"]).decode("utf-8")), ""
        if isinstance(data, dict) and "telemetry_snapshot.json" in (data.get("files") or {}):
            return json.loads(data["files"]["telemetry_snapshot.json"]["content"]), ""
        return (data, "") if isinstance(data, dict) else (None, "la respuesta no es un snapshot JSON")
    except Exception as e:
        return None, f"error al descargar: {type(e).__name__}: {str(e)[:160]}"


def get_telemetry() -> tuple:
    """Devuelve (snapshot, etiqueta de origen, url pública que el navegador puede sondear o None)."""
    local_path = BASE_DIR / "data" / "telemetry_snapshot.json"
    if local_path.exists():
        data = load_from_file(str(local_path))
        if data:
            return data, "Local (PC)", None

    url = st.session_state.get("telemetry_url", "").strip() or _secret("TELEMETRY_URL", DEFAULT_FEED)
    token = st.session_state.get("gh_token", "").strip() or _secret("GITHUB_TOKEN")
    st.session_state["_diag"] = (f"URL del feed: {url or '(vacía)'} · token: "
                                 f"{'sí (' + str(len(token)) + ' caracteres)' if token else 'NO encontrado en Secrets (GITHUB_TOKEN)'}")
    if url:
        data, err = load_from_url(url, token or None)
        if err:
            st.session_state["_diag"] += f" · {err}"
        if data:
            # Solo se sondea desde el navegador si el feed es público (nunca se expone un token en la página)
            return data, "Feed GitHub", (None if token else url)

    if (BASE_DIR / "trading_bot.db").exists():
        try:
            import telemetry_sync
            data = telemetry_sync.extract_telemetry()
            telemetry_sync.save_local_snapshot(data)
            return data, "Local (SQLite)", None
        except Exception:
            pass
    return None, "Desconectado", None


# ── Barra lateral ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📡 Telemetría")
    url_in = st.text_input("URL del feed", value=st.session_state.get("telemetry_url", "") or _secret("TELEMETRY_URL", DEFAULT_FEED),
                           help="Snapshot JSON publicado por telemetry_sync.py")
    if url_in != st.session_state.get("telemetry_url", ""):
        st.session_state["telemetry_url"] = url_in
    tok_in = st.text_input("GitHub token (solo si el feed es privado)", value=st.session_state.get("gh_token", ""), type="password")
    if tok_in != st.session_state.get("gh_token", ""):
        st.session_state["gh_token"] = tok_in
    auto_refresh = st.checkbox(f"Auto-refresco (cada {REFRESH_S} s)", value=True)
    if st.button("🔄 Refrescar ahora", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Vista de solo lectura del panel local: cambiar de modo, resetear el saldo o lanzar el simulador "
               "solo se puede hacer en http://localhost:5000.")


data, source_label, poll_url = get_telemetry()

if not data:
    st.warning("⚠️ No hay telemetría. Arranca el bot (app.py publica el snapshot cada 15 s) o ejecuta "
               "`python telemetry_sync.py`, y revisa la URL del feed en la barra lateral.")
    st.caption("Diagnóstico: " + st.session_state.get("_diag", "sin datos"))
    st.stop()

if int(data.get("schema") or 1) < 2:
    st.warning("⚠️ El bot todavía publica el formato de telemetría antiguo (métricas históricas sin reset y por "
               "estrategia). Actualiza `telemetry_sync.py` en el PC y reinicia el bot: en el siguiente envío "
               "(≤ 15 s) este panel mostrará lo mismo que el local.")
    st.stop()

if not TEMPLATE.exists():
    st.error("No se encuentra templates/index.html (la interfaz del panel local).")
    st.stop()


# ── Adaptación de la plantilla local ──────────────────────────────────────────
# 1) Se ocultan los controles que cambian el estado del bot (solo lectura).
REMOTE_CSS = """
<style>
#resetSimBtn, #modeBtn, #simBtn, #simAsset, #resetDlg { display: none !important; }
html, body { overflow: hidden; }
body { min-height: 0 !important; }
.grid > *, .mkt, .sides > *, .oracle > * { min-width: 0; }
@media (max-width: 640px) {
  body { padding: 8px; }
  .g-kpi { grid-template-columns: 1fr 1fr; }
  .sides, .oracle { grid-template-columns: 1fr; }
  .stats4, .chips, .health { grid-template-columns: 1fr 1fr !important; }
  .coins { grid-template-columns: repeat(3, 1fr); }
  .count { font-size: 24px; }
  .ring { width: 48px; height: 48px; }
  .tel-bar .r { margin-left: 0; }
}
.tel-bar { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; font-size: 12px; color: #cbd5e1;
           background: #0b1324; border: 1px dashed var(--line); border-radius: 10px; padding: 8px 12px; margin-bottom: 14px; }
.tel-bar b { color: var(--text); }
/* Datos congelados: el bot no publica (apagado, PC suspendido o sin conexión) */
.stale-banner { display: none; border-radius: 12px; padding: 14px 18px; margin-bottom: 14px; font-size: 15px; font-weight: 800; }
.stale-banner small { display: block; font-size: 12px; font-weight: 600; margin-top: 4px; opacity: .9; }
body.stale-warn .stale-banner { display: block; background: #2a1d06; border: 1px solid #a16207; color: var(--amber); }
body.stale-off .stale-banner { display: block; background: #2e0f0f; border: 1px solid #b91c1c; color: #fca5a5; }
body.stale-off .grid, body.stale-off .card { opacity: .38; filter: grayscale(.7); }
.tel-bar .r { margin-left: auto; color: var(--muted); }
.logs { max-height: 330px; overflow: auto; font-family: ui-monospace, Consolas, monospace; font-size: 11px; }
.logs div { padding: 4px 0; border-bottom: 1px solid var(--line2); color: #94a3b8; white-space: pre-wrap; word-break: break-word; }
.logs time { color: var(--dim); margin-right: 8px; }
.logs .WARNING { color: var(--amber); } .logs .ERROR, .logs .CRITICAL { color: var(--red); font-weight: 700; }
</style>
"""

# 2) Antes del script del panel: las llamadas a /api/... se responden con el snapshot.
REMOTE_BOOT = """
<script>
window.__SNAP = __SNAP_JSON__;
window.__LOADED = Date.now();   // cuándo llegaron a esta página los datos (render del servidor o sondeo)
window.__FEED = { url: __POLL_URL__, source: __SOURCE__, every: __EVERY__ };
(function () {
  const ok = (obj) => Promise.resolve(new Response(JSON.stringify(obj), {status: 200, headers: {'Content-Type': 'application/json'}}));
  const deny = () => Promise.resolve(new Response(JSON.stringify({status: 'error', ok: false,
    message: 'Panel remoto de solo lectura: usa http://localhost:5000'}), {status: 403, headers: {'Content-Type': 'application/json'}}));
  const nativeFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (!url.startsWith('/api/')) return nativeFetch(input, init);
    const S = window.__SNAP || {};
    const method = ((init && init.method) || 'GET').toUpperCase();
    if (method !== 'GET') return deny();
    const path = url.split('?')[0];
    if (path === '/api/live') {
      // Solo ventanas que siguen abiertas: el snapshot puede tener unos segundos de retraso
      const live = JSON.parse(JSON.stringify(S.live || {})), now = Date.now() / 1000;
      if (live.v4 && Array.isArray(live.v4.markets))
        live.v4.markets = live.v4.markets.filter(m => !m.window_ts || now < m.window_ts + (m.window_s || 300));
      return ok(live);
    }
    if (path === '/api/trades') return ok(S.trades || []);
    if (path === '/api/v4/equity') return ok(S.equity && S.equity.status ? S.equity : {status: 'empty'});
    if (path === '/api/debug_state') return ok(S.debug || {});
    if (path === '/api/v4/simulations') return ok(S.v4_sim ? {status: 'ok', latest: S.v4_sim} : {status: 'empty'});
    return Promise.resolve(new Response('{}', {status: 404}));
  };
})();
</script>
"""

# 3) Bloques añadidos para la vista remota (latido de la telemetría, V4 por activo y registro del bot).
REMOTE_TOP = """
<div class="stale-banner" id="staleBanner"></div>
<div class="tel-bar" id="telBar">
  <span><span class="led" id="telLed"></span> Telemetría <b id="telAge">—</b></span>
  <span>snapshot <b id="telTs">—</b></span>
  <span>origen <b id="telSrc">—</b></span>
  <span class="r">vista remota de solo lectura · los controles están en http://localhost:5000</span>
</div>
"""

REMOTE_BOTTOM = """
<div class="grid g-2">
  <div class="card">
    <div class="card-h"><h2>V4 por mercado</h2><span class="sub" id="assetSub">desde el reset</span></div>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>Mercado</th><th>Operaciones</th><th>Acierto</th><th>Profit factor</th><th>PnL</th></tr></thead>
        <tbody id="assetBody"><tr class="empty"><td colspan="5">Sin operaciones V4 desde el reset</td></tr></tbody>
      </table>
    </div>
    <div class="stats4" id="cobroStats"></div>
  </div>
  <div class="card">
    <div class="card-h"><h2>Registro del bot</h2><span class="sub" id="logSub">últimos eventos</span></div>
    <div class="logs" id="logs"><div>Sin eventos</div></div>
  </div>
</div>
"""

# 4) Después del script del panel: extras, sondeo del feed y altura automática del iframe.
REMOTE_TAIL = """
<script>
(function () {
  function ageTxt(s) { s = Math.max(0, Math.round(s)); return s < 90 ? s + ' s' : (s < 5400 ? Math.round(s / 60) + ' min' : Math.round(s / 3600) + ' h'); }
  function renderTelemetry() {
    const S = window.__SNAP || {}, age = Date.now() / 1000 - (S.timestamp_epoch || 0);
    // Dos cosas distintas: (a) el BOT no publica -> los datos ya eran viejos cuando llegaron a la página;
    // (b) la PÁGINA no se refresca (pestaña dormida, conexión con Streamlit cortada) -> el bot puede ir bien.
    const sinceFetch = (Date.now() - (window.__LOADED || Date.now())) / 1000, ageAtFetch = age - sinceFetch;
    // raw.githubusercontent.com sirve el archivo con caché de hasta 5 min: ahí el retraso normal es mayor
    const cdn = String((window.__FEED || {}).url || '').includes('raw.githubusercontent.com');
    const offAt = cdn ? 420 : 120, warnAt = cdn ? 330 : 45;
    const st = ageAtFetch >= offAt ? 'off' : ((ageAtFetch >= warnAt || sinceFetch >= 60) ? 'warn' : 'on');
    led('telLed', st);
    document.body.classList.toggle('stale-warn', st === 'warn');
    document.body.classList.toggle('stale-off', st === 'off');
    const bn = $('staleBanner');
    if (bn) bn.innerHTML = st === 'off'
      ? `⛔ BOT APAGADO O SIN CONEXIÓN — no publica datos desde hace ${ageTxt(age)}<small>Lo que ves abajo son los últimos datos que envió (${S.timestamp ? new Date(S.timestamp).toLocaleString('es-ES') : '—'}), NO está en directo. Los bots solo funcionan con sus ventanas de terminal abiertas en el PC.</small>`
      : (st !== 'warn' ? '' : (sinceFetch >= 60
          ? `⚠️ Esta página no recibe datos nuevos desde hace ${ageTxt(sinceFetch)}<small>No significa que el bot esté apagado: recarga la página (F5) para ver el estado actual.</small>`
          : `⚠️ Datos con retraso: el último envío del bot fue hace ${ageTxt(age)}<small>Si pasa de ${cdn ? '7' : '2'} minutos, el bot está apagado o sin conexión.</small>`));
    setT('telAge', 'hace ' + ageTxt(age));
    setT('telTs', S.timestamp ? new Date(S.timestamp).toLocaleString('es-ES') : '—');
    setT('telSrc', (S.source === 'panel' ? 'panel del bot' : (S.source === 'db' ? 'base de datos (panel sin respuesta)' : '—')) + ' · ' + (window.__FEED.source || ''));
  }
  function renderAssets() {
    const L = (window.__SNAP || {}).live || {}, ledger = L.ledger;
    const ls = (L.v4 || {}).live_stats || {};
    const by = (ledger && ledger.since_reset && ledger.since_reset.v4 && ledger.since_reset.v4.by_asset) || ls.by_asset || {};
    const rows = Object.entries(by).sort((a, b) => (b[1].closed || b[1].trades || 0) - (a[1].closed || a[1].trades || 0));
    setT('assetSub', L.simulation_mode ? 'desde el reset' : 'dinero real');
    const tb = $('assetBody');
    if (tb) tb.innerHTML = rows.length ? rows.map(([k, v]) => {
      const nT = v.closed ?? v.trades ?? 0, pnl = Number(v.pnl || 0), pf = v.profit_factor;
      return `<tr><td><b>${esc(k)}</b></td><td>${nT} <span class="muted">(${v.wins || 0}✓ · ${v.losses || 0}✗)</span></td>
        <td>${nT ? Number(v.win_rate || 0).toFixed(1) + '%' : '—'}</td>
        <td class="${pf == null ? '' : (pf >= 1.5 ? 'pos' : (pf >= 1 ? 'warn' : 'neg'))}">${pf != null ? Number(pf).toFixed(2) : (nT ? '∞' : '—')}</td>
        <td class="${cls(pnl)}"><b>${signed(pnl)} $</b></td></tr>`;
    }).join('') : '<tr class="empty"><td colspan="5">Sin operaciones V4 desde el reset</td></tr>';
    const cb = L.cobros || {}, lg = ledger || {};
    const cells = [['Por cobrar', cb.pending_count ? `${cb.pending_count} · $${n(cb.pending_value)}` : 'nada'],
                   ['Cobrados', String(cb.collected_count ?? '—')],
                   ['En juego', lg.open_cost != null ? '$' + n(lg.open_cost) : '—'],
                   ['Saldo libre', lg.cash != null ? '$' + n(lg.cash) : '—']];
    const cs = $('cobroStats');
    if (cs) cs.innerHTML = cells.map(c => `<div class="stat"><div class="k">${esc(c[0])}</div><div class="v" style="font-size:14px">${esc(c[1])}</div></div>`).join('');
  }
  function renderLogs() {
    const logs = (window.__SNAP || {}).recent_logs || [], box = $('logs');
    if (!box) return;
    setT('logSub', logs.length ? `últimos ${logs.length} eventos` : 'sin eventos');
    box.innerHTML = logs.length ? logs.map(l => `<div class="${esc(String(l.level || 'INFO').toUpperCase())}"><time>${esc(String(l.timestamp || '').slice(5, 19))}</time>${esc(l.message)}</div>`).join('') : '<div>Sin eventos</div>';
  }
  function renderExtras() { try { renderTelemetry(); renderAssets(); renderLogs(); } catch (e) { console.warn(e); } }

  // Altura automática del iframe de Streamlit (sin doble barra de scroll)
  function fit() {
    try {
      const wrap = document.querySelector('.wrap') || document.body;
      const h = Math.ceil(wrap.getBoundingClientRect().bottom + window.scrollY) + 24;
      if (window.frameElement && Math.abs(window.frameElement.offsetHeight - h) > 4) window.frameElement.style.height = h + 'px';
    } catch (e) { document.documentElement.style.overflow = 'auto'; document.body.style.overflow = 'auto'; }
  }
  try { new ResizeObserver(fit).observe(document.body); } catch (e) {}
  setInterval(fit, 1500);

  // Sondeo del feed público desde el navegador: datos nuevos sin recargar la página
  async function poll() {
    const F = window.__FEED;
    if (!F.url) return;
    try {
      const r = await fetch(F.url + (F.url.includes('?') ? '&' : '?') + '_cb=' + Date.now(), {cache: 'no-store'});
      if (!r.ok) return;
      const d = await r.json();
      window.__LOADED = Date.now();
      if (d && (d.timestamp_epoch || 0) > ((window.__SNAP || {}).timestamp_epoch || 0) && (d.schema || 1) >= 2) {
        window.__SNAP = d; window.__LOADED = Date.now(); _last = {trades: 0, eq: 0, dbg: 0}; fetchSim(); refresh(true);
      }
    } catch (e) {}
  }
  if (window.__FEED.url) setInterval(poll, Math.max(5, window.__FEED.every) * 1000);
  renderExtras(); setInterval(renderExtras, 1000); fit();
})();
</script>
"""


def build_page(snapshot: Dict[str, Any], source: str, url: Optional[str]) -> str:
    html = TEMPLATE.read_text(encoding="utf-8").replace("{{ bot_token }}", "")
    snap_json = json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/")
    boot = (REMOTE_BOOT.replace("__SNAP_JSON__", snap_json)
            .replace("__POLL_URL__", json.dumps(url))
            .replace("__SOURCE__", json.dumps(source))
            .replace("__EVERY__", str(REFRESH_S)))
    html = html.replace("</head>", REMOTE_CSS + "</head>", 1)
    html = html.replace('<div class="error-box" id="errorBox"></div>', REMOTE_TOP + '<div class="error-box" id="errorBox"></div>', 1)
    foot = '<div class="foot">Actualizado'
    html = html.replace(foot, REMOTE_BOTTOM + foot, 1) if foot in html else html
    # El arranque va justo antes del script principal del panel (el primero sin src dentro del body)
    body_at = html.find("<body")
    script_at = html.find("<script>", body_at)
    html = html[:script_at] + boot + html[script_at:]
    return html.replace("</body>", REMOTE_TAIL + "</body>", 1)


components.html(build_page(data, source_label, poll_url if auto_refresh else None), height=2200, scrolling=False)

# Si el navegador no puede sondear el feed (archivo local o feed privado), se refresca desde el servidor
if auto_refresh and not poll_url:
    time.sleep(REFRESH_S)
    st.cache_data.clear()
    st.rerun()
