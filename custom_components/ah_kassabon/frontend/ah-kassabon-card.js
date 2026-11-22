/* AH Kassabon card — upload AH receipt PDFs and see which products got more expensive.
 * Served by the ah_kassabon integration; styled with the Thuis theme tokens (falls back to HA defaults).
 *
 *   type: custom:ah-kassabon-card
 *   title: Boodschappenprijzen      # optional
 *   filter: up                      # up | down | all | check | variable  (default up)
 *   limit: 10                       # rows before "Toon alles"
 */
const DOMAIN = 'ah_kassabon';
const VERSION = '0.2.1';

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
  --akc-warn: var(--warning-color, #FBCC2C);
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
.chip .n { font-family: var(--akc-mono); margin-left: 4px; }
.row { display: flex; align-items: center; gap: 10px; padding: 9px 4px; border-top: 1px solid var(--akc-divider); cursor: pointer; }
.row:first-child { border-top: 0; }
.thumb { flex: none; width: 34px; height: 34px; border-radius: 8px; background: #fff center/contain no-repeat; }
.thumb.none { background: var(--akc-hi); }
.row .n { flex: 1; min-width: 0; }
.row .name { font-size: 14px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row .meta { font-size: 12px; color: var(--akc-fg-2); margin-top: 1px; font-family: var(--akc-mono); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pct { flex: none; font-family: var(--akc-mono); font-size: 13px; font-weight: 600; padding: 3px 8px; border-radius: var(--thuis-radius-full, 9999px); background: var(--akc-hi); }
.pct.up { background: color-mix(in srgb, var(--akc-up) 16%, transparent); }
.pct.down { background: color-mix(in srgb, var(--akc-down) 16%, transparent); }
.pct.check { color: var(--akc-warn); background: color-mix(in srgb, var(--akc-warn) 14%, transparent); }
.detail { padding: 4px 4px 12px; }
.detail svg { width: 100%; height: 56px; display: block; }
.detail .line { stroke: var(--akc-icon); stroke-width: 2; fill: none; }
.detail .dot { fill: var(--akc-icon); }
.detail .axis { display: flex; justify-content: space-between; font-size: 11px; color: var(--akc-fg-3); font-family: var(--akc-mono); }
.toggle { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; font-size: 13px; color: var(--akc-fg-2); gap: 8px; }
.section { margin-top: 10px; font-size: 12px; color: var(--akc-fg-3); text-transform: uppercase; letter-spacing: .04em; }
.match { display: flex; align-items: center; gap: 10px; margin-top: 6px; padding: 8px; border-radius: var(--thuis-radius-control, 12px); background: var(--akc-hi); }
.match .n { flex: 1; min-width: 0; font-size: 13px; }
.match .n small { display: block; color: var(--akc-fg-2); font-family: var(--akc-mono); font-size: 11px; margin-top: 1px; }
.cand { width: 100%; text-align: left; background: transparent; }
.cand:hover { background: var(--akc-active); }
.cand .score { flex: none; font-family: var(--akc-mono); font-size: 11px; color: var(--akc-fg-3); }
.actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.btn { height: 30px; padding: 0 12px; border-radius: var(--thuis-radius-full, 9999px); background: var(--akc-hi); font-size: 13px; }
.btn:hover { background: var(--akc-active); }
.btn.primary { background: var(--akc-tile); color: var(--akc-icon); font-weight: 600; }
.searchbar { display: flex; gap: 6px; margin-top: 8px; }
.searchbar input { flex: 1; min-width: 0; height: 32px; padding: 0 10px; border-radius: var(--thuis-radius-control, 12px); border: 1px solid var(--akc-divider); background: transparent; color: var(--akc-fg); font: inherit; font-size: 13px; }
.hint { font-size: 12px; color: var(--akc-fg-2); margin-top: 6px; }
.empty { padding: 18px 4px 6px; font-size: 13px; color: var(--akc-fg-2); text-align: center; line-height: 1.5; }
.more { display: block; width: 100%; margin-top: 6px; height: 34px; border-radius: var(--thuis-radius-control, 12px); background: transparent; color: var(--akc-fg-2); font-size: 13px; }
.more:hover { background: var(--akc-hi); }
input[type=file] { display: none; }
`;

const eur = (v) => (v == null ? '–' : '€' + v.toFixed(2).replace('.', ','));
const eurP = (p, v) => eur(v) + (p.per_kg ? '/kg' : '');
const signedEur = (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + eur(Math.abs(v));
const pct = (v) => (v == null ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(1).replace('.', ',') + '%');
const day = (iso) => (iso ? new Date(iso).toLocaleDateString('nl-NL', { day: 'numeric', month: 'short' }).replace('.', '') : '');
const nice = (name) => {
  const ah = name.startsWith('AH ');
  const rest = (ah ? name.slice(3) : name).toLowerCase();
  return (ah ? 'AH ' : '') + rest.charAt(0).toUpperCase() + rest.slice(1);
};
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const needsCheck = (p) => p.match_status === 'pending' || p.match_status === 'none';
const label = (p) => p.title || nice(p.name) + (p.variants > 1 ? ` · ${eur(p.first_price)}` : '');

class AhKassabonCard extends HTMLElement {
  setConfig(config) {
    this._config = { title: 'Boodschappenprijzen', filter: 'up', limit: 10, ...config };
    this._filter = this._config.filter;
    this._open = null;
    this._showAll = false;
    this._picking = null;
    this._results = null;
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
    clearTimeout(this._poll);
  }

  async _load() {
    try {
      this._data = await this._hass.connection.sendMessagePromise({ type: `${DOMAIN}/products` });
      this._error = null;
    } catch (e) {
      this._error = e.message || 'AH Kassabon is niet geladen';
    }
    // Names are looked up in the background after an upload: refresh a few times.
    clearTimeout(this._poll);
    const products = (this._data && this._data.products) || [];
    if (products.some((p) => p.match_status === 'new') && (this._polls = (this._polls || 0) + 1) <= 12) {
      this._poll = setTimeout(() => this._load(), 5000);
    } else if (!products.some((p) => p.match_status === 'new')) {
      this._polls = 0;
    }
    this._render();
  }

  _ws(msg) { return this._hass.connection.sendMessagePromise(msg); }

  async _setProduct(key, changes) {
    await this._ws({ type: `${DOMAIN}/set_product`, key, ...changes });
    this._picking = null; this._results = null;
    await this._load();
  }

  async _search(key, query) {
    this._results = { loading: true };
    this._render();
    try {
      const r = await this._ws({ type: `${DOMAIN}/search`, key, query });
      this._results = { items: r.results };
    } catch (e) {
      this._results = { error: e.message || 'Zoeken mislukt' };
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
    this._polls = 0;
    await this._load();
  }

  _describe(results) {
    const missing = (r) => (r.missing_items ? ` <span class="up">Let op: ${r.missing_items} product${r.missing_items === 1 ? '' : 'en'} niet herkend.</span>` : '');
    const parts = results.map((r) => {
      if (!r.ok) return `<b>${esc(r.file || 'Bestand')}</b>: ${esc(r.error)}`;
      const when = day(r.when);
      if (r.duplicate) return `Bon van <b>${when}</b> stond er al in.`;
      const up = r.increases.length, down = r.decreases.length;
      let s = `Bon van <b>${when}</b> ingelezen (${r.items} producten). `;
      if (!r.compared) return s + 'Nog niks om mee te vergelijken; dat komt bij de volgende bon.' + missing(r);
      s += up ? `<span class="up"><b>${up} duurder</b></span>` : 'Niks duurder';
      if (down) s += `, <span class="down">${down} goedkoper</span>`;
      if (up) s += ': ' + r.increases.slice(0, 3).map((c) => `${esc(c.title || nice(c.product))} ${signedEur(c.diff)}`).join(', ') + (up > 3 ? ' …' : '');
      return s + '.' + missing(r);
    });
    return { err: results.every((r) => !r.ok), html: parts.join('<br>') };
  }

  _rows() {
    const products = (this._data && this._data.products) || [];
    const tracked = products.filter((p) => !p.variable && p.times >= 2);
    switch (this._filter) {
      case 'up': return tracked.filter((p) => p.diff > 0).sort((a, b) => b.pct - a.pct);
      case 'down': return tracked.filter((p) => p.diff < 0).sort((a, b) => a.pct - b.pct);
      case 'check': return products.filter(needsCheck).sort((a, b) => b.times - a.times || a.name.localeCompare(b.name));
      case 'variable': return products.filter((p) => p.variable).sort((a, b) => a.name.localeCompare(b.name));
      default: return products.slice().sort((a, b) => (b.pct || 0) - (a.pct || 0) || label(a).localeCompare(label(b)));
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
    let d = `M${x(0).toFixed(1)},${y(0).toFixed(1)}`;
    for (let i = 1; i < history.length; i++) d += ` H${x(i).toFixed(1)} V${y(i).toFixed(1)}`;
    const dots = history.map((_, i) => `<circle class="dot" cx="${x(i).toFixed(1)}" cy="${y(i).toFixed(1)}" r="2.5"/>`).join('');
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><path class="line" d="${d}"/>${dots}</svg>
      <div class="axis"><span>${day(history[0][0])} · ${eur(v[0])}</span><span>${eur(v0)}–${eur(v1)}</span><span>${day(history[history.length - 1][0])} · ${eur(v[v.length - 1])}</span></div>`;
  }

  _thumb(img) {
    return img ? `<div class="thumb" style="background-image:url('${esc(img)}')"></div>` : '<div class="thumb none"></div>';
  }

  _candidate(c, key) {
    return `<button class="match cand" data-pick="${esc(key)}" data-cand="${this._cands.push(c) - 1}">
      ${this._thumb(c.image)}
      <div class="n">${esc(c.title)}<small>${esc(c.size || '')}${c.size ? ' · ' : ''}${eur(c.price)}</small></div>
    </button>`;
  }

  _nameSection(p) {
    const key = p.key;
    let html = '<div class="section">Product</div>';
    if (p.title && this._picking !== key) {
      html += `<div class="match">${this._thumb(p.image)}<div class="n">${esc(p.title)}<small>${esc(p.size || '')}${p.match_status === 'auto' ? ' · automatisch gekozen' : ''}</small></div></div>
        <div class="actions">
          ${p.match_status === 'auto' ? `<button class="btn primary" data-confirm="${esc(key)}">Klopt</button>` : ''}
          <button class="btn" data-change="${esc(key)}">Ander product</button>
        </div>`;
      return html;
    }
    if (p.match_status === 'new') return html + '<div class="hint">Naam wordt opgezocht bij AH…</div>';
    if (p.match_status === 'skipped' && this._picking !== key) {
      return html + `<div class="hint">Geen AH-product gekoppeld.</div><div class="actions"><button class="btn" data-change="${esc(key)}">Toch zoeken</button></div>`;
    }
    const cands = this._results && this._picking === key ? this._results : { items: p.candidates || [] };
    html += `<div class="hint">Welk product is "${esc(p.name)}" (${eurP(p, p.price)} op je bon)?</div>`;
    if (cands.loading) html += '<div class="hint">Zoeken…</div>';
    else if (cands.error) html += `<div class="hint up">${esc(cands.error)}</div>`;
    else if (!cands.items.length) html += '<div class="hint">Geen suggesties gevonden. Zoek zelf hieronder.</div>';
    else html += cands.items.map((c) => this._candidate(c, key)).join('');
    html += `<div class="searchbar"><input type="search" placeholder="Zoek bij AH, bijv. italiaanse bollen" data-q="${esc(key)}" value="${esc(this._query || '')}">
      <button class="btn" data-search="${esc(key)}">Zoek</button></div>
      <div class="actions"><button class="btn" data-skip="${esc(key)}">Geen van deze</button>
      ${this._picking === key ? `<button class="btn" data-cancel="1">Annuleren</button>` : ''}</div>`;
    return html;
  }

  _render() {
    this._cands = [];
    if (!this.shadowRoot || !this._config) return;
    const c = this._config;
    const data = this._data;
    const products = (data && data.products) || [];
    const receipts = (data && data.receipts) || [];
    const tracked = products.filter((p) => !p.variable && p.times >= 2);
    const up = tracked.filter((p) => p.diff > 0).length;
    const down = tracked.filter((p) => p.diff < 0).length;
    const check = products.filter(needsCheck).length;
    const avg = tracked.length ? tracked.reduce((s, p) => s + (p.pct || 0), 0) / tracked.length : null;
    const oldest = receipts.length ? receipts[receipts.length - 1].when : null;
    const sub = receipts.length
      ? `${receipts.length} ${receipts.length === 1 ? 'bon' : 'bonnen'} · laatste ${day(receipts[0].when)}`
      : 'Nog geen kassabonnen';

    const rows = this._rows();
    const limit = this._showAll ? rows.length : c.limit;
    const filters = [['up', 'Duurder'], ['down', 'Goedkoper'], ['all', 'Alles'], ['check', 'Controleren', check], ['variable', 'Wisselend gewicht']];

    let list;
    if (this._error) list = `<div class="empty">${esc(this._error)}</div>`;
    else if (!data) list = `<div class="empty">Laden…</div>`;
    else if (!receipts.length) list = `<div class="empty">Deel een kassabon in de AH-app als PDF<br>en voeg hem hier toe met <b>Bon toevoegen</b>.</div>`;
    else if (!rows.length) list = `<div class="empty">${this._filter === 'up' ? (receipts.length < 2 ? 'Voeg nog een bon toe om prijzen te vergelijken.' : 'Niks duurder geworden. 🎉') : this._filter === 'check' ? 'Alle producten hebben een naam.' : 'Geen producten in deze lijst.'}</div>`;
    else list = rows.slice(0, limit).map((p) => {
      const cls = p.variable ? '' : p.diff > 0 ? 'up' : p.diff < 0 ? 'down' : '';
      const size = p.size ? `${p.size} · ` : '';
      const meta = p.variable || p.times < 2 || !p.diff
        ? `${size}${eurP(p, p.price)} · ${p.times}× gekocht`
        : `${eur(p.first_price)} → ${eurP(p, p.price)} · sinds ${day(p.first_when)} · ${p.times}×`;
      const badge = this._filter === 'check' || (needsCheck(p) && !(p.times >= 2 && p.diff))
        ? (needsCheck(p) ? '<span class="pct check">kiezen</span>' : '')
        : p.variable ? '<span class="pct">gewicht</span>' : p.times >= 2 ? `<span class="pct ${cls}">${pct(p.pct)}</span>` : '';
      const open = this._open === p.key;
      return `<div class="row" data-key="${esc(p.key)}">
          ${this._thumb(p.image)}
          <div class="n"><div class="name">${esc(label(p))}</div><div class="meta">${meta}</div></div>
          ${badge}
        </div>
        ${open ? `<div class="detail">${this._spark(p.history)}
          ${this._nameSection(p)}
          <div class="toggle"><span>Wisselend gewicht${p.variable_auto ? ' (automatisch herkend)' : ''}</span>
          <ha-switch data-var="${esc(p.key)}" ${p.variable ? 'checked' : ''}></ha-switch></div>
          ${p.variants > 1 ? `<div class="toggle"><span>Bon-naam "${esc(p.name)}" is ${p.variants} producten (op prijs gesplitst)</span>
          <button class="btn" data-merge="${esc(p.key)}">Samenvoegen</button></div>` : ''}
          </div>` : ''}`;
    }).join('');

    const focused = this.shadowRoot.activeElement && this.shadowRoot.activeElement.dataset && this.shadowRoot.activeElement.dataset.q;
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
        ${receipts.length ? `<div class="chips">${filters.map(([k, l, n]) => `<button class="chip ${this._filter === k ? 'on' : ''}" data-f="${k}">${l}${n ? `<span class="n">${n}</span>` : ''}</button>`).join('')}</div>` : ''}
        <div class="list">${list}</div>
        ${rows.length > limit ? `<button class="more">Toon alles (${rows.length})</button>` : ''}
      </ha-card>`;

    const root = this.shadowRoot;
    const on = (sel, fn) => root.querySelectorAll(sel).forEach((el) => el.addEventListener('click', (ev) => { ev.stopPropagation(); fn(el, ev); }));
    const input = root.querySelector('input[type=file]');
    root.querySelector('.upload').addEventListener('click', () => input.click());
    input.addEventListener('change', () => this._upload([...input.files]));
    on('.chip', (b) => { this._filter = b.dataset.f; this._showAll = false; this._open = null; this._picking = null; this._render(); });
    on('.row', (r) => { this._open = this._open === r.dataset.key ? null : r.dataset.key; this._picking = null; this._results = null; this._query = ''; this._render(); });
    on('.more', () => { this._showAll = true; this._render(); });
    on('[data-confirm]', (b) => this._setProduct(b.dataset.confirm, { status: 'confirmed' }));
    on('[data-change]', (b) => { this._picking = b.dataset.change; this._results = null; this._query = ''; this._render(); });
    on('[data-cancel]', () => { this._picking = null; this._results = null; this._render(); });
    on('[data-skip]', (b) => this._setProduct(b.dataset.skip, { status: 'skipped' }));
    on('[data-pick]', (b) => { const c = this._cands[Number(b.dataset.cand)]; if (c) this._setProduct(b.dataset.pick, { match: c }); });
    on('[data-merge]', (b) => this._setProduct(b.dataset.merge, { no_split: true }));
    on('[data-search]', (b) => {
      const q = root.querySelector(`input[data-q="${window.CSS.escape(b.dataset.search)}"]`);
      if (q && q.value.trim()) { this._picking = b.dataset.search; this._query = q.value.trim(); this._search(b.dataset.search, this._query); }
    });
    root.querySelectorAll('input[data-q]').forEach((q) => {
      q.addEventListener('click', (ev) => ev.stopPropagation());
      q.addEventListener('input', () => { this._query = q.value; });
      q.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' && q.value.trim()) { this._picking = q.dataset.q; this._query = q.value.trim(); this._search(q.dataset.q, this._query); }
      });
      if (focused) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
    });
    root.querySelectorAll('ha-switch').forEach((s) => s.addEventListener('change', async (ev) => {
      ev.stopPropagation();
      await this._setProduct(s.dataset.var, { variable: s.checked });
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
