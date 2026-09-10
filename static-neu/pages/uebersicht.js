// P31: Startseite. Alle Zahlen kommen aus GET /api/uebersicht (Filtervertrag P20),
// keine Demo-Daten. Aufbau/Klassen orientiert an docs/neubau/prototyp/prototyp.html
// (Abschnitt "Übersicht"), Rechenlogik kommt vollständig vom Server.
import {api} from '../api.js';
import {esc, fmtEur, fmtPct, fmtDate} from '../format.js';
import {toast, drill} from '../ui.js';
import {monthlyChart, sparklineCompare} from '../charts.js';

let cssLoaded = false;
let topTyp = 'ausgaben'; // lokaler Seitenzustand: 'ausgaben' | 'einnahmen', kein Reload

function ensureCss() {
  if (cssLoaded || document.querySelector('#uebersicht-css')) { cssLoaded = true; return; }
  const link = document.createElement('link');
  link.id = 'uebersicht-css';
  link.rel = 'stylesheet';
  link.href = new URL('./uebersicht.css', import.meta.url).href;
  document.head.appendChild(link);
  cssLoaded = true;
}

// P30 verdrahtet #year-select, #filter-richtung, #filter-zahlungsart und
// #filter-kategorie nicht (kein onchange, kein state.filter) — siehe Bericht
// "Wunsch an das Gerüst". Lokaler Ersatz: einmalig binden (dataset-Flag, die
// Elemente werden von app.js wiederverwendet, nicht neu erzeugt) und bei
// Änderung einen echten hashchange auslösen, damit app.js Sidebar, Kopfzeile
// und Seite konsistent neu zeichnet (wie bei echter Navigation).
function bindOnce(el, handler) {
  if (!el || el.dataset.p31Bound) return;
  el.dataset.p31Bound = '1';
  el.addEventListener('change', handler);
}

function refresh() { window.dispatchEvent(new Event('hashchange')); }

function bindFilterControls(state) {
  bindOnce(document.querySelector('#sparte-select'), refresh);
  bindOnce(document.querySelector('#year-select'), e => { state.year = e.target.value; refresh(); });
  bindOnce(document.querySelector('#filter-richtung'), refresh);
  bindOnce(document.querySelector('#filter-zahlungsart'), refresh);
  bindOnce(document.querySelector('#filter-kategorie'), refresh);
}

function currentYear(state) {
  return document.querySelector('#year-select')?.value || state.year || state.jahre?.[0] || '';
}

function extraFilters() {
  const richtung = document.querySelector('#filter-richtung')?.value || '';
  const zahlungsart = document.querySelector('#filter-zahlungsart')?.value || '';
  const kategorie_id = document.querySelector('#filter-kategorie')?.value || '';
  return {richtung, zahlungsart, kategorie_id};
}

function queryParams(state) {
  const jahr = currentYear(state);
  const {richtung, zahlungsart, kategorie_id} = extraFilters();
  const params = {};
  if (jahr) params.jahr = jahr;
  if (state.sparteId) params.sparte_id = state.sparteId;
  if (richtung) params.richtung = richtung;
  if (zahlungsart) params.zahlungsart = zahlungsart;
  if (kategorie_id) params.kategorie_id = kategorie_id;
  return params;
}

function filterAktivText(state) {
  const teile = [];
  const sparte = state.sparten?.find(s => String(s.id) === String(state.sparteId));
  if (sparte) teile.push(sparte.name);
  const {richtung, zahlungsart, kategorie_id} = extraFilters();
  if (richtung) teile.push(richtung === 'ausgabe' ? 'Ausgaben' : 'Einnahmen');
  if (zahlungsart) teile.push(zahlungsart);
  if (kategorie_id) teile.push(`Kategorie #${kategorie_id}`);
  return teile.join(' · ');
}

function resetFilters(state) {
  state.sparteId = '';
  localStorage.setItem('neu-sparte', '');
  for (const id of ['sparte-select', 'filter-richtung', 'filter-zahlungsart', 'filter-kategorie']) {
    const el = document.querySelector('#' + id);
    if (el) el.value = '';
  }
  refresh();
}

function kpiCard(label, key, data, color, isSaldo) {
  const jahr = data.jahr;
  const laufend = data.erwartung != null;
  const ist = data.ist[key];
  const erwartung = laufend ? data.erwartung[key] : null;
  const wert = laufend ? erwartung : ist;
  const vorjahr = data.vorjahr_gesamt[key];
  // Saldo: Prozent gegen einen kleinen Vorjahressaldo explodiert, deshalb nur der Betrag.
  const delta = vorjahr && !isSaldo ? (wert - vorjahr) / Math.abs(vorjahr) : null;
  const guenstig = isSaldo || label === 'Einnahmen' ? delta >= 0 : delta <= 0;
  const cls = delta == null ? 'flat' : (guenstig ? 'up' : 'down');
  const curSeries = key === 'saldo_cent'
    ? data.monate.einnahmen.map((v, i) => v - data.monate.ausgaben[i])
    : data.monate[key === 'einnahmen_cent' ? 'einnahmen' : 'ausgaben'];
  const prevSeries = key === 'saldo_cent'
    ? data.monate.vorjahr_einnahmen.map((v, i) => v - data.monate.vorjahr_ausgaben[i])
    : data.monate[key === 'einnahmen_cent' ? 'vorjahr_einnahmen' : 'vorjahr_ausgaben'];
  return `<div class="card kpi">
    <div class="lbl"><span>${esc(label)} ${jahr ?? ''}</span>${laufend ? '<span class="pill est">bisher + Vorjahresrest</span>' : ''}</div>
    <div class="val" style="color:${color}">${fmtEur(wert, isSaldo)}</div>
    ${laufend ? `<div class="muted" style="font-size:12px">bisher: ${fmtEur(ist, isSaldo)}</div>` : ''}
    <div class="delta">${delta == null
      ? (isSaldo && vorjahr != null ? `<span class="muted">gegenüber ${jahr != null ? jahr - 1 : ''}: <b>${fmtEur(vorjahr, true)}</b></span>` : '<span class="pill flat">kein Vorjahr</span>')
      : `<span class="pill ${cls}">${fmtPct(delta)}</span><span class="muted">gegenüber ${jahr != null ? jahr - 1 : ''}: <b>${fmtEur(vorjahr, isSaldo)}</b></span>`}</div>
    ${sparklineCompare(curSeries, prevSeries, color)}
  </div>`;
}

function tileHtml(s, laufend) {
  const tot = (s.einnahmen_cent + s.ausgaben_cent) || 1;
  return `<button type="button" class="tile" data-sparte="${s.sparte_id}" style="--dot:${esc(s.farbe || 'var(--info)')}">
    <div class="tn"><span class="sdot"></span>${esc(s.name)}</div>
    <div class="tv">${fmtEur(s.saldo_cent, true)}${laufend ? ' <small class="muted">bisher</small>' : ''}</div>
    <div class="tea"><span class="ein">+ ${fmtEur(s.einnahmen_cent)}</span><span class="aus">− ${fmtEur(s.ausgaben_cent)}</span></div>
    <div class="bar"><i style="width:${s.einnahmen_cent / tot * 100}%;background:var(--ein)"></i><i style="width:${s.ausgaben_cent / tot * 100}%;background:var(--aus)"></i></div>
  </button>`;
}

async function drillBuchungen(filterParams, title) {
  try {
    const data = await api('/buchungen', {params: {...filterParams, limit: 50}});
    const rows = data.buchungen || [];
    const list = rows.length ? rows.map(b => `<div class="hint-row" style="--hc:var(--info)">
        <div><b>${esc(b.text || '(ohne Text)')}</b><div class="muted" style="font-size:12px">${fmtDate(b.datum)} · ${esc(b.sparte_name || '')}${b.zahlungsart ? ' · ' + esc(b.zahlungsart) : ''}</div></div>
        <div class="${b.typ === 'einnahme' ? 'ein' : 'aus'}">${fmtEur(b.betrag_cent)}</div>
      </div>`).join('') : '<p class="muted">Keine Buchungen im Zeitraum.</p>';
    const summe = data.summen || {};
    const fuss = `<p class="muted" style="font-size:12px;margin-top:10px">${summe.anzahl ?? rows.length} Buchung(en) insgesamt${rows.length < (summe.anzahl ?? rows.length) ? `, ${rows.length} angezeigt` : ''} · Saldo ${fmtEur(summe.saldo_cent || 0, true)}</p>`;
    drill(title, list + fuss);
  } catch (error) {
    toast(error.detail || error.message || 'Buchungen konnten nicht geladen werden.');
  }
}

function auslagenDrill(gruppe, sparteName, zahlerName) {
  const rows = gruppe.auslagen || [];
  const list = rows.length ? rows.map(a => `<div class="hint-row">
      <div><b>${esc(a.text || '')}</b><div class="muted" style="font-size:12px">${fmtDate(a.datum)}${a.kategorie ? ' · ' + esc(a.kategorie) : ''}</div></div>
      <div class="aus">${fmtEur(a.offen_cent)}</div>
    </div>`).join('') : '<p class="muted">Keine offenen Einzelposten.</p>';
  drill(`${esc(zahlerName)} → ${esc(sparteName)}`, list);
}

function sparteName(state, id) {
  return state.sparten?.find(s => String(s.id) === String(id))?.name || `Sparte #${id}`;
}

function goSparte(state, sparteId) {
  state.sparteId = String(sparteId);
  localStorage.setItem('neu-sparte', state.sparteId);
  location.hash = '#/sparte';
}

function renderHints(root, state, data, load) {
  const el = root.querySelector('#hints');
  const hints = data.hinweise || [];
  if (!hints.length) {
    el.innerHTML = '<p class="muted">Nichts Auffälliges. Ausgeblendete Hinweise kommen wieder, sobald sich die Zahl ändert.</p>';
    return;
  }
  el.innerHTML = hints.map((h, i) => `<div class="hint-row">
      <div>${h.text}</div>
      <button type="button" class="btn small go" data-i="${i}">Buchungen zeigen</button>
      <button type="button" class="x" data-i="${i}" title="ausblenden, bis sich die Zahl ändert" aria-label="Hinweis ausblenden">×</button>
    </div>`).join('');
  el.querySelectorAll('.go').forEach(b => b.onclick = () => drillBuchungen(hints[+b.dataset.i].drill, 'Hinweis: Buchungen'));
  el.querySelectorAll('.x').forEach(b => b.onclick = async () => {
    const h = hints[+b.dataset.i];
    try {
      await api('/hinweise/aus', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({schluessel: h.schluessel, bis_wert: h.wert})});
      await load();
    } catch (error) {
      toast(error.detail || error.message);
    }
  });
}

function renderKonten(root, data) {
  const el = root.querySelector('#konten');
  const waehrungen = Object.entries(data.konten_je_waehrung || {});
  const kopf = waehrungen.length ? `<div class="ks muted" style="padding:0 2px 8px">${
    waehrungen.map(([w, g]) => `${esc(w)}: ${g.stand_cent == null ? 'kein Anker' : fmtEur(g.stand_cent)}`).join(' · ')
  }</div>` : '';
  const konten = data.konten || [];
  const liste = konten.length ? konten.map(k => `<div class="konto">
      <div><div class="kn">${esc(k.name)}</div>
        <div class="ks">${k.anker ? `Anker ${fmtDate(k.anker.stichtag)} (${esc(k.anker.quelle)})` : 'kein Anker gesetzt'}</div></div>
      <div><div class="kv">${k.stand_cent == null ? '<span class="muted">kein Anker</span>' : fmtEur(k.stand_cent)}</div>
        <div class="kd">${k.letzter_import ? `Import ${fmtDate(k.letzter_import)}` : 'kein Import'}${k.datenstand === 'veraltet' ? `<span class="pill down" title="seit ${k.import_alter_tage} Tagen kein Auszug eingespielt">Import ${k.import_alter_tage} Tage alt</span>` : ''}</div></div>
    </div>`).join('') : '<p class="muted">Keine Konten im Bereich.</p>';
  el.innerHTML = kopf + liste;
}

function renderAuslagen(root, state, data) {
  const el = root.querySelector('#auslagen');
  const gruppen = data.auslagen_offen || [];
  if (!gruppen.length) { el.innerHTML = '<p class="muted">Keine offenen Auslagen.</p>'; return; }
  el.innerHTML = gruppen.map((g, i) => `<div class="konto" data-i="${i}" role="button" tabindex="0">
      <div><div class="kn">${esc(sparteName(state, g.zahler_sparte_id))} → ${esc(sparteName(state, g.sparte_id))}</div>
        <div class="ks">${g.anzahl} Buchung(en)</div></div>
      <div><div class="kv aus">${fmtEur(g.offen_cent)}</div></div>
    </div>`).join('');
  el.querySelectorAll('[data-i]').forEach(node => {
    const g = gruppen[+node.dataset.i];
    const open = () => {
      if (g.auslagen && g.auslagen.length) auslagenDrill(g, sparteName(state, g.sparte_id), sparteName(state, g.zahler_sparte_id));
      else goSparte(state, g.zahler_sparte_id);
    };
    node.onclick = open;
    node.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } };
  });
}

function renderTop(root, state, data) {
  const jahr = currentYear(state);
  const list = data.top?.[topTyp] || [];
  const el = root.querySelector('#top');
  el.innerHTML = list.length ? list.map(c => {
    const max = list[0].betrag_cent || 1;
    return `<div class="hbar" data-kat="${c.kategorie_id}" tabindex="0" role="button" aria-label="${esc(c.name)}, ${fmtEur(c.betrag_cent)}, Buchungen zeigen">
      <div class="name"><span>${esc(c.name)}</span></div>
      <div class="track"><div class="fill" style="width:${c.betrag_cent / max * 100}%;background:${topTyp === 'ausgaben' ? 'var(--aus)' : 'var(--ein)'}"></div></div>
      <div class="v">${fmtEur(c.betrag_cent)}</div><div class="p">${fmtPct(c.anteil)}</div>
    </div>`;
  }).join('') : '<p class="muted">Keine Buchungen im Zeitraum.</p>';
  const open = kat => drillBuchungen({...queryParams(state), jahr, kategorie_id: kat, richtung: topTyp === 'ausgaben' ? 'ausgabe' : 'einnahme'},
    `${topTyp === 'ausgaben' ? 'Ausgaben' : 'Einnahmen'} · Buchungen`);
  el.querySelectorAll('.hbar').forEach(h => {
    h.onclick = () => open(h.dataset.kat);
    h.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(h.dataset.kat); } };
  });
  root.querySelectorAll('#topseg button').forEach(b => {
    b.classList.toggle('active', b.dataset.t === topTyp);
    b.setAttribute('aria-pressed', String(b.dataset.t === topTyp));
    b.onclick = () => { topTyp = b.dataset.t; renderTop(root, state, data); };
  });
}

function renderVerlauf(root, state, data) {
  const jahr = currentYear(state);
  const monate = data.monate || {einnahmen: [], ausgaben: []};
  const reihen = monate.einnahmen.map((v, i) => ({monat: i + 1, einnahmen_cent: v, ausgaben_cent: monate.ausgaben[i]}));
  const el = root.querySelector('#verlauf');
  el.innerHTML = monthlyChart(reihen);
  const monatsFilter = extraFilters();
  el.querySelectorAll('.chart-bars > div').forEach((node, i) => {
    node.setAttribute('role', 'button');
    node.setAttribute('tabindex', '0');
    const open = () => drillBuchungen({
      bereich_id: state.bereichId,
      sparte_id: state.sparteId || undefined,
      monat: `${jahr}-${String(i + 1).padStart(2, '0')}`,
      richtung: monatsFilter.richtung || undefined,
      zahlungsart: monatsFilter.zahlungsart || undefined,
    }, `Buchungen · Monat ${i + 1}/${jahr}`);
    node.onclick = open;
    node.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } };
  });
}

export function render(root, state) {
  ensureCss();
  bindFilterControls(state);

  root.innerHTML = `
    <div class="grid g3" id="kpis"></div>
    <div class="muted filter-note" id="filter-note" hidden></div>
    <div>
      <div class="card-head" style="margin-bottom:10px"><h2 id="tiles-title">Sparten</h2><span class="hint muted">Saldo im gewählten Jahr · Klick öffnet die Sparte</span></div>
      <div class="tiles" id="tiles"></div>
    </div>
    <div class="grid g2-1">
      <div class="card">
        <div class="card-head"><h2>Woran du dich kümmern solltest</h2><span class="hint muted">aus deinen Zahlen gerechnet</span></div>
        <div class="hints" id="hints"></div>
      </div>
      <div class="grid">
        <div class="card">
          <div class="card-head"><h2>Konten und Kassen</h2><span class="hint muted">Saldo laut Anker plus Umsätze seither</span></div>
          <div class="konten" id="konten"></div>
        </div>
        <div class="card">
          <div class="card-head"><h2>Offene Auslagen</h2><span class="hint muted">privat bezahlt, noch nicht ausgeglichen</span></div>
          <div class="konten" id="auslagen"></div>
        </div>
      </div>
    </div>
    <div class="grid g2">
      <div class="card">
        <div class="card-head"><h2>Verlauf über das Jahr</h2></div>
        <div class="chart" id="verlauf"></div>
        <div class="legend"><span class="ein">Einnahmen</span><span class="aus">Ausgaben</span></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>Größte Posten nach Kategorie</h2><div class="seg small" id="topseg"><button type="button" data-t="ausgaben">Ausgaben</button><button type="button" data-t="einnahmen">Einnahmen</button></div></div>
        <div class="hbars" id="top"></div>
      </div>
    </div>
    <p class="muted" id="datenstand" style="font-size:12px"></p>
  `;

  async function load() {
    let data;
    try {
      data = await api('/uebersicht', {params: queryParams(state)});
    } catch (error) {
      root.querySelector('#kpis').innerHTML = `<div class="card"><p class="muted">Übersicht konnte nicht geladen werden: ${esc(error.detail || error.message)}</p></div>`;
      toast(error.detail || error.message);
      return;
    }
    const laufend = data.erwartung != null;
    root.querySelector('#kpis').innerHTML =
      kpiCard('Einnahmen', 'einnahmen_cent', data, 'var(--ein)', false) +
      kpiCard('Ausgaben', 'ausgaben_cent', data, 'var(--aus)', false) +
      kpiCard('Saldo', 'saldo_cent', data, 'var(--ink)', true);

    const aktiv = filterAktivText(state);
    root.querySelector('#tiles-title').textContent = aktiv ? 'Sparten · gefiltert' : 'Sparten';
    const note = root.querySelector('#filter-note');
    note.hidden = !aktiv;
    if (aktiv) {
      note.innerHTML = `<span>Filter aktiv: <b>${esc(aktiv)}</b></span> <button type="button" class="lnk" id="filter-note-reset">zurücksetzen</button>`;
      note.querySelector('#filter-note-reset').onclick = () => resetFilters(state);
    }

    const tiles = data.sparten || [];
    root.querySelector('#tiles').innerHTML = tiles.length
      ? tiles.map(s => tileHtml(s, laufend)).join('')
      : '<p class="muted">Keine Sparten im Bereich.</p>';
    root.querySelectorAll('#tiles .tile').forEach(t => t.onclick = () => goSparte(state, t.dataset.sparte));

    renderHints(root, state, data, load);
    renderKonten(root, data);
    renderAuslagen(root, state, data);
    renderTop(root, state, data);
    renderVerlauf(root, state, data);

    const ds = data.datenstand || {};
    root.querySelector('#datenstand').textContent =
      `Datenstand: letzte Buchung ${ds.letzte_buchung ? fmtDate(ds.letzte_buchung) : '–'} · letzter Import ${ds.letzter_import ? fmtDate(ds.letzter_import) : '–'}`;
  }

  return load();
}
