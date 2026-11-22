/* AH Kassabon card — upload AH receipt PDFs and see which products got more expensive.
 * Served by the ah_kassabon integration; styled with the Thuis theme tokens (falls back to HA defaults).
 *
 *   type: custom:ah-kassabon-card
 *   title: Boodschappenprijzen      # optional
 *   filter: up                      # up | down | all | variable  (default up)
 *   limit: 10                       # rows before "Toon alles"
 */
const DOMAIN = 'ah_kassabon';
const VERSION = '0.1.0';

const CSS = `
:host {
  --akc-fg: var(--primary-text-color, #F4F5F7);
  --akc-fg-2: var(--secondary-text-color, rgba(244,245,247,.62));
  --akc-fg-3: var(--thuis-ink-dim, rgba(244,245,247,.52));
  --akc-surface: var(--thuis-surface, rgba(255,255,255,.045));
  --akc-hi: var(--thuis-surface-raised, rgba(255,255,255,.07));
  --akc-active: var(--thuis-surface-active, rgba(255,255,255,.1));
  --akc-divider: var(--divider-color, rgba(255,255,255,.08));
  --akc-icon: var(--thuis-effect-ink, #FF9C40);
  --akc-tile: var(--thuis-effect-tile, rgba(255,119,20,.26));
  --akc-up: var(--error-color, #F94F54);
  --akc-down: var(--success-color, #3BDD7E);
  --akc-sans: var(--ha-font-family-body, 'Space Grotesk', system-ui, sans-serif);
  --akc-mono: var(--ha-font-family-code, 'IBM Plex Mono', ui-monospace, monospace);
  display: block;
}
ha-card { background: var(--akc-surface); border-radius: var(--thuis-radius-card, 22px); padding: 14px; font-family: var(--akc-sans); color: var(--akc-fg); }
.head { display: flex; align-items: center; gap: 12px; }
.tile { flex: none; width: 40px; height: 40px; border-radius: var(--thuis-radius-control, 12px); background: var(--akc-tile); color: var(--akc-icon); display: grid; place-items: center; }
.tile ha-icon { --mdc-icon-size: 22px; }
.titles { flex: 1; min-width: 0; }
.title { font-size: 16px; font-weight: 600; line-height: 1.2; }
.sub { font-size: 13px; color: var(--akc-fg-2); margin-top: 2px; }
button { font: inherit; color: inherit; border: 0; cursor: pointer; }
.upload { flex: none; display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px; border-radius: var(--thuis-radius-full, 9999px); background: var(--akc-hi); font-size: 14px; font-weight: 600; }
.upload:hover { background: var(--akc-active); }
.upload[disabled] { opacity: .6; cursor: progress; }
.upload ha-icon { --mdc-icon-size: 18px; }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 14px; }
.stat { background: var(--akc-hi); border-radius: var(--thuis-radius-control, 12px); padding: 10px 12px; min-width: 0; }
.stat .v { font-family: var(--akc-mono); font-size: 18px; font-weight: 600; }
.stat .l { font-size: 12px; color: var(--akc-fg-2); margin-top: 2px; }
.up { color: var(--akc-up); } .down { color: var(--akc-down); }
.banner { margin-top: 12px; padding: 10px 12px; border-radius: var(--thuis-radius-control, 12px); background: var(--akc-hi); font-size: 13px; line-height: 1.45; }
.banner.err { color: var(--akc-up); }
.banner b { font-weight: 600; }
.chips { display: flex; gap: 6px; margin: 14px 0 6px; overflow-x: auto; scrollbar-width: none; }
.chip { flex: none; height: 30px; padding: 0 12px; border-radius: var(--thuis-radius-full, 9999px); background: transparent; color: var(--akc-fg-2); font-size: 13px; box-shadow: inset 0 0 0 1px var(--akc-divider); }
.chip.on { background: var(--akc-active); color: var(--akc-fg); box-shadow: none; }
.row { display: flex; align-items: center; gap: 10px; padding: 9px 4px; border-top: 1px solid var(--akc-divider); cursor: pointer; }
.row:first-child { border-top: 0; }
.row .n { flex: 1; min-width: 0; }
.row .name { font-size: 14px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row .meta { font-size: 12px; color: var(--akc-fg-2); margin-top: 1px; font-family: var(--akc-mono); }
.pct { flex: none; font-family: var(--akc-mono); font-size: 13px; font-weight: 600; padding: 3px 8px; border-radius: var(--thuis-radius-full, 9999px); background: var(--akc-hi); }
.pct.up { background: color-mix(in srgb, var(--akc-up) 16%, transparent); }
.pct.down { background: color-mix(in srgb, var(--akc-down) 16%, transparent); }
.detail { padding: 4px 4px 12px; }
.detail svg { width: 100%; height: 56px; display: block; }
.detail .line { stroke: var(--akc-icon); stroke-width: 2; fill: none; }
.detail .dot { fill: var(--akc-icon); }
.detail .axis { display: flex; justify-content: space-between; font-size: 11px; color: var(--akc-fg-3); font-family: var(--akc-mono); }
.toggle { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; font-size: 13px; color: var(--akc-fg-2); }
.empty { padding: 18px 4px 6px; font-size: 13px; color: var(--akc-fg-2); text-align: center; line-height: 1.5; }
.more { display: block; width: 100%; margin-top: 6px; height: 34px; border-radius: var(--thuis-radius-control, 12px); background: transparent; color: var(--akc-fg-2); font-size: 13px; }
.more:hover { background: var(--akc-hi); }
input[type=file] { display: none; }
`;

const eur = (v) => (v == null ? '–' : '€' + v.toFixed(2).replace('.', ','));
const signedEur = (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + eur(Math.abs(v));
const pct = (v) => (v == null ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(1).replace('.', ',') + '%');
const day = (iso) => (iso ? new Date(iso).toLocaleDateString('nl-NL', { day: 'numeric', month: 'short' }).replace('.', '') : '');
const nice = (name) => {
  const ah = name.startsWith('AH ');
  const rest = (ah ? name.slice(3) : name).toLowerCase();
  return (ah ? 'AH ' : '') + rest.charAt(0).toUpperCase() + rest.slice(1);
};
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

class AhKassabonCard extends HTMLElement {
  setConfig(config) {
    this._config = { title: 'Boodschappenprijzen', filter: 'up', limit: 10, ...config };
    this._filter = this._config.filter;
    this._open = null;
    this._showAll = false;
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._load();
      hass.connection
        .subscribeEvents(() => this._load(), `${DOMAIN}_imported`)
        .then((unsub) => (this._unsub = unsub))
        .catch(() => {});
    }
  }

  disconnectedCallback() {
    if (this._unsub) { this._unsub(); this._unsub = null; this._hass = null; }
  }

  async _load() {
    try {
      this._data = await this._hass.connection.sendMessagePromise({ type: `${DOMAIN}/products` });
      this._error = null;
    } catch (e) {
      this._error = e.message || 'AH Kassabon is niet geladen';
    }
    this._render();
  }

  async _upload(files) {
    if (!files.length) return;
    this._busy = true; this._banner = null; this._render();
    const form = new FormData();
    for (const f of files) form.append('file', f, f.name);
    try {
      const resp = await this._hass.fetchWithAuth(`/api/${DOMAIN}/upload`, { method: 'POST', body: form });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.message || resp.statusText);
      this._banner = this._describe(body.results);
    } catch (e) {
      this._banner = { err: true, html: `Uploaden mislukt: ${esc(e.message)}` };
    }
    this._busy = false;
    await this._load();
  }

  _describe(results) {
    const parts = results.map((r) => {
      if (!r.ok) return `<b>${esc(r.file || 'Bestand')}</b>: ${esc(r.error)}`;
      const when = day(r.when);
      if (r.duplicate) return `Bon van <b>${when}</b> stond er al in.`;
      const up = r.increases.length, down = r.decreases.length;
      let s = `Bon van <b>${when}</b> ingelezen (${r.items} producten). `;
      if (!r.compared) return s + 'Nog niks om mee te vergelijken; dat komt bij de volgende bon.';
      s += up ? `<span class="up"><b>${up} duurder</b></span>` : 'Niks duurder';
      if (down) s += `, <span class="down">${down} goedkoper</span>`;
      if (up) s += ': ' + r.increases.slice(0, 3).map((c) => `${esc(nice(c.product))} ${signedEur(c.diff)}`).join(', ') + (up > 3 ? ' …' : '');
      return s + '.';
    });
    return { err: results.every((r) => !r.ok), html: parts.join('<br>') };
  }

  _rows() {
    const products = (this._data && this._data.products) || [];
    const tracked = products.filter((p) => !p.variable && p.times >= 2);
    switch (this._filter) {
      case 'up': return tracked.filter((p) => p.diff > 0).sort((a, b) => b.pct - a.pct);
      case 'down': return tracked.filter((p) => p.diff < 0).sort((a, b) => a.pct - b.pct);
      case 'variable': return products.filter((p) => p.variable).sort((a, b) => a.name.localeCompare(b.name));
      default: return products.slice().sort((a, b) => (b.pct || 0) - (a.pct || 0) || a.name.localeCompare(b.name));
    }
  }

  _spark(history) {
    if (history.length < 2) return '';
    const w = 300, h = 56, pad = 6;
    const t = history.map(([d]) => new Date(d).getTime());
    const v = history.map(([, p]) => p);
    const [t0, t1] = [Math.min(...t), Math.max(...t)];
    const [v0, v1] = [Math.min(...v), Math.max(...v)];
    const x = (i) => pad + ((t[i] - t0) / (t1 - t0 || 1)) * (w - 2 * pad);
    const y = (i) => h - pad - ((v[i] - v0) / (v1 - v0 || 1)) * (h - 2 * pad);
    const pts = history.map((_, i) => `${x(i).toFixed(1)},${y(i).toFixed(1)}`);
    // step line: a price holds until the next receipt
    let d = `M${pts[0]}`;
    for (let i = 1; i < pts.length; i++) d += ` H${x(i).toFixed(1)} V${y(i).toFixed(1)}`;
    const dots = history.map((_, i) => `<circle class="dot" cx="${x(i).toFixed(1)}" cy="${y(i).toFixed(1)}" r="2.5"/>`).join('');
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><path class="line" d="${d}"/>${dots}</svg>
      <div class="axis"><span>${day(history[0][0])} · ${eur(v[0])}</span><span>${eur(v0)}–${eur(v1)}</span><span>${day(history[history.length - 1][0])} · ${eur(v[v.length - 1])}</span></div>`;
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const c = this._config;
    const data = this._data;
    const products = (data && data.products) || [];
    const receipts = (data && data.receipts) || [];
    const tracked = products.filter((p) => !p.variable && p.times >= 2);
    const up = tracked.filter((p) => p.diff > 0).length;
    const down = tracked.filter((p) => p.diff < 0).length;
    const avg = tracked.length ? tracked.reduce((s, p) => s + (p.pct || 0), 0) / tracked.length : null;
    const oldest = receipts.length ? receipts[receipts.length - 1].when : null;
    const sub = receipts.length
      ? `${receipts.length} ${receipts.length === 1 ? 'bon' : 'bonnen'} · laatste ${day(receipts[0].when)}`
      : 'Nog geen kassabonnen';

    const rows = this._rows();
    const limit = this._showAll ? rows.length : c.limit;
    const filters = [['up', 'Duurder'], ['down', 'Goedkoper'], ['all', 'Alles'], ['variable', 'Wisselend gewicht']];

    let list;
    if (this._error) list = `<div class="empty">${esc(this._error)}</div>`;
    else if (!data) list = `<div class="empty">Laden…</div>`;
    else if (!receipts.length) list = `<div class="empty">Deel een kassabon in de AH-app als PDF<br>en voeg hem hier toe met <b>Bon toevoegen</b>.</div>`;
    else if (!rows.length) list = `<div class="empty">${this._filter === 'up' ? (receipts.length < 2 ? 'Voeg nog een bon toe om prijzen te vergelijken.' : 'Niks duurder geworden. 🎉') : 'Geen producten in deze lijst.'}</div>`;
    else list = rows.slice(0, limit).map((p) => {
      const cls = p.variable ? '' : p.diff > 0 ? 'up' : p.diff < 0 ? 'down' : '';
      const meta = p.variable
        ? `${eur(p.price)} · ${p.times}× gekocht`
        : p.times < 2
          ? `${eur(p.price)} · 1× gekocht`
          : p.diff
            ? `${eur(p.first_price)} → ${eur(p.price)} · sinds ${day(p.first_when)} · ${p.times}×`
            : `${eur(p.price)} · ${p.times}× gekocht`;
      const open = this._open === p.name;
      return `<div class="row" data-name="${esc(p.name)}">
          <div class="n"><div class="name">${esc(nice(p.name))}</div><div class="meta">${meta}</div></div>
          ${p.variable ? '<span class="pct">gewicht</span>' : p.times >= 2 ? `<span class="pct ${cls}">${pct(p.pct)}</span>` : ''}
        </div>
        ${open ? `<div class="detail">${this._spark(p.history)}
          <div class="toggle"><span>Wisselend gewicht${p.variable_auto ? ' (automatisch herkend)' : ''}</span>
          <ha-switch data-var="${esc(p.name)}" ${p.variable ? 'checked' : ''}></ha-switch></div></div>` : ''}`;
    }).join('');

    this.shadowRoot.innerHTML = `<style>${CSS}</style>
      <ha-card>
        <div class="head">
          <div class="tile"><ha-icon icon="mdi:receipt-text-outline"></ha-icon></div>
          <div class="titles"><div class="title">${esc(c.title)}</div><div class="sub">${sub}</div></div>
          <button class="upload" ${this._busy ? 'disabled' : ''}><ha-icon icon="${this._busy ? 'mdi:loading' : 'mdi:plus'}"></ha-icon>${this._busy ? 'Inlezen…' : 'Bon toevoegen'}</button>
          <input type="file" accept="application/pdf,.pdf" multiple>
        </div>
        ${receipts.length >= 2 ? `<div class="stats">
          <div class="stat"><div class="v ${avg > 0 ? 'up' : avg < 0 ? 'down' : ''}">${pct(avg)}</div><div class="l">mandje sinds ${day(oldest)}</div></div>
          <div class="stat"><div class="v ${up ? 'up' : ''}">${up}</div><div class="l">duurder</div></div>
          <div class="stat"><div class="v ${down ? 'down' : ''}">${down}</div><div class="l">goedkoper</div></div>
        </div>` : ''}
        ${this._banner ? `<div class="banner ${this._banner.err ? 'err' : ''}">${this._banner.html}</div>` : ''}
        ${receipts.length ? `<div class="chips">${filters.map(([k, l]) => `<button class="chip ${this._filter === k ? 'on' : ''}" data-f="${k}">${l}</button>`).join('')}</div>` : ''}
        <div class="list">${list}</div>
        ${rows.length > limit ? `<button class="more">Toon alles (${rows.length})</button>` : ''}
      </ha-card>`;

    const root = this.shadowRoot;
    const input = root.querySelector('input[type=file]');
    root.querySelector('.upload').addEventListener('click', () => input.click());
    input.addEventListener('change', () => this._upload([...input.files]));
    root.querySelectorAll('.chip').forEach((b) => b.addEventListener('click', () => { this._filter = b.dataset.f; this._showAll = false; this._open = null; this._render(); }));
    root.querySelectorAll('.row').forEach((r) => r.addEventListener('click', () => { this._open = this._open === r.dataset.name ? null : r.dataset.name; this._render(); }));
    const more = root.querySelector('.more');
    if (more) more.addEventListener('click', () => { this._showAll = true; this._render(); });
    root.querySelectorAll('ha-switch').forEach((s) => s.addEventListener('change', async (ev) => {
      ev.stopPropagation();
      await this._hass.connection.sendMessagePromise({ type: `${DOMAIN}/set_variable`, product: s.dataset.var, variable: s.checked });
      await this._load();
    }));
  }

  getCardSize() { return 6; }
  getGridOptions() { return { columns: 12, min_columns: 6, rows: 'auto' }; }
  static getStubConfig() { return { title: 'Boodschappenprijzen' }; }
}

if (!customElements.get('ah-kassabon-card')) {
  customElements.define('ah-kassabon-card', AhKassabonCard);
  window.customCards = window.customCards || [];
  window.customCards.push({ type: 'ah-kassabon-card', name: 'AH Kassabon', description: 'Kassabonnen uploaden en zien welke boodschappen duurder zijn geworden.' });
  console.info(`%c AH-KASSABON-CARD %c ${VERSION} `, 'background:#FF7714;color:#1A1006;font-weight:600', '');
}
