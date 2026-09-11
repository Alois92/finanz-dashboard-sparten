// P32: Seite Sparte. Zeigt eine einzelne Sparte oder eine Auswertungsgruppe mehrerer
// Sparten: Kennzahlen-Zeile, eigene Kennzahlen (nur Anzeige, kein Editor), Barkassa,
// offene Auslagen, Kategorien im Jahresvergleich (Matrix), größte Ausgabenkategorien,
// Jahresverlauf. Alle Daten aus bestehenden Endpoints (P20 Auswertungen, P15 Kennzahlen,
// P12 Auslagen, P13 Kassa), keine Demo-Daten, keine eigene Rechenlogik - Kennzahlen-Werte
// und die Jahresmatrix-Erwartung kommen fertig gerechnet vom Server.
import {api} from '../api.js';
import {esc, fmtEur, fmtDate, fmtPct} from '../format.js';
import {toast, drill} from '../ui.js';
import {monthlyChart, sparklineCompare} from '../charts.js';

let cssLoaded = false;
function ensureCss() {
  if (cssLoaded || document.querySelector('#sparte-css')) { cssLoaded = true; return; }
  const link = document.createElement('link');
  link.id = 'sparte-css';
  link.rel = 'stylesheet';
  link.href = new URL('./sparte.css', import.meta.url).href;
  document.head.appendChild(link);
  cssLoaded = true;
}

// Jahres-Chips der Matrix sind reiner Seitenzustand (kein Teil von state.filter, siehe
// P32-Karte Abschnitt 3: "kein reines Client-Filtern... da der Server die Erwartung nur
// für angefragte Jahre liefert"). Wird zurückgesetzt, sobald sich die gewählte
// Sparte/Gruppe ändert.
let jahreZustand = {schluessel: null, verfuegbar: [], aktiv: new Set()};

// P32b: merkt sich den zuletzt betretenen Gruppen-Hash-Suffix (z. B. "gruppe-2"), damit
// render() zwischen "Gruppe gerade betreten" (Sparte im Kopf ggf. noch aus einem
// vorherigen Besuch gesetzt, muss geräumt werden) und "Nutzer wählt jetzt aktiv im
// Kopf eine Sparte, während die Gruppe schon offen ist" (Hash-Suffix muss weichen)
// unterscheiden kann - beide Fälle sehen an state.sparteId allein gleich aus.
let gruppenZustand = {suffix: null};

function hashSuffix() {
  const raw = location.hash.replace(/^#\//, '');
  const parts = raw.split('/');
  return parts[1] || '';
}

function parseGruppeId(suffix) {
  const m = /^gruppe-(\d+)$/.exec(suffix || '');
  return m ? Number(m[1]) : null;
}

// Ein #/sparte/<id>-Hash setzt die Sparte wie ein Wechsel im Kopf-Select: state.filter.sparteId
// (und die Alias-Felder state.sparteId/localStorage, siehe app.js aus P30b) nachziehen, dann den
// Hash-Suffix wieder entfernen und die Seite über hashchange neu rendern lassen - so zeichnet
// app.js Kopf-Select und Sidebar beim nächsten Durchlauf korrekt. app.js selbst bleibt
// unverändert (Konfliktregel NACHTRAG Abschnitt 3, kein exportiertes setFilter() dort).
function syncSparteAusHash(state, suffix) {
  if (!suffix || parseGruppeId(suffix) != null || !/^\d+$/.test(suffix)) return false;
  if (String(state.sparteId || '') === suffix) return false;
  state.sparteId = suffix;
  if (state.filter) state.filter.sparteId = suffix;
  localStorage.setItem('neu-sparte', suffix);
  location.hash = '#/sparte';
  return true;
}

// Setzt die Sparte wie ein Wechsel im Kopf-Select und rendert die Seite direkt neu. Ein reines
// location.hash='#/sparte' reicht hier nicht aus: von der Auswahlkachel aus ist der Hash bereits
// '#/sparte' (keine ID im Suffix), eine Zuweisung desselben Werts löst also kein hashchange in
// app.js aus - anders als goSparte() in uebersicht.js, das immer von einer anderen Route kommt.
function waehleSparte(root, state, id) {
  state.sparteId = String(id);
  if (state.filter) state.filter.sparteId = state.sparteId;
  localStorage.setItem('neu-sparte', state.sparteId);
  if (location.hash !== '#/sparte') { location.hash = '#/sparte'; return; }
  // Kopf-Nachzug: nicht nur die Seite, sondern ueber app.js auch Kopf-Select und Sidebar
  // neu zeichnen (gleiches Muster wie refresh() in uebersicht.js).
  window.dispatchEvent(new Event('hashchange'));
}

function sparteName(state, id) {
  return state.sparten?.find(s => String(s.id) === String(id))?.name || `Sparte ${id}`;
}

// P32b: ein expliziter Gruppen-Hash (#/sparte/gruppe-<id>) gewinnt jetzt auch dann, wenn
// im Kopf-Select noch eine Sparte steht. Beim Betreten der Gruppe wird die Sparte im
// Kopf/Sidebar wie bei einem echten Wechsel geräumt ("Alle Sparten"); wählt der Nutzer
// danach aktiv eine Sparte im Kopf, verlässt die Seite beim nächsten Render die Gruppe
// und zeigt die gewählte Einzelsparte (Hash-Suffix entfernt).
export function render(root, state) {
  ensureCss();
  const suffix = hashSuffix();
  if (syncSparteAusHash(state, suffix)) return;
  const gruppeId = parseGruppeId(suffix);
  if (gruppeId != null) {
    if (gruppenZustand.suffix !== suffix) {
      gruppenZustand.suffix = suffix;
      if (state.sparteId) {
        state.sparteId = '';
        if (state.filter) state.filter.sparteId = '';
        localStorage.setItem('neu-sparte', '');
        window.dispatchEvent(new Event('hashchange'));
        return;
      }
    } else if (state.sparteId) {
      gruppenZustand.suffix = null;
      location.hash = '#/sparte';
      return;
    }
    return renderGruppe(root, state, gruppeId);
  }
  gruppenZustand.suffix = null;
  const sparteId = state.sparteId || (state.filter && state.filter.sparteId) || '';
  if (!sparteId) return renderAuswahl(root, state);
  return renderEinzelsparte(root, state, sparteId);
}

/* ---------- Auswahlbildschirm ohne gewählte Sparte ---------- */

function renderAuswahl(root, state) {
  const sparten = state.sparten || [];
  const gruppen = state.gruppen || [];
  root.innerHTML = `
    <div class="card">
      <div class="card-head"><h2>Bitte Sparte wählen</h2><span class="hint muted">oder eine Auswertungsgruppe für mehrere Sparten zusammen</span></div>
      <div class="tiles" id="s-auswahl-sparten"></div>
      ${gruppen.length ? '<div class="card-head" style="margin-top:16px"><h2>Auswertungsgruppen</h2></div><div class="tiles" id="s-auswahl-gruppen"></div>' : ''}
    </div>
  `;
  const sp = root.querySelector('#s-auswahl-sparten');
  sp.innerHTML = sparten.length
    ? sparten.map(s => `<button type="button" class="tile" data-sparte="${s.id}" style="--dot:${esc(s.farbe || 'var(--info)')}"><div class="tn"><span class="sdot"></span>${esc(s.name)}</div></button>`).join('')
    : '<p class="muted">Keine Sparten im Bereich.</p>';
  sp.querySelectorAll('[data-sparte]').forEach(b => b.onclick = () => waehleSparte(root, state, b.dataset.sparte));
  if (gruppen.length) {
    const gr = root.querySelector('#s-auswahl-gruppen');
    gr.innerHTML = gruppen.map(g => `<button type="button" class="tile" data-gruppe="${g.id}"><div class="tn">${esc(g.name)}</div><div class="muted" style="font-size:12px">${g.sparte_ids.length} Sparte(n)</div></button>`).join('');
    gr.querySelectorAll('[data-gruppe]').forEach(b => b.onclick = () => { location.hash = '#/sparte/gruppe-' + b.dataset.gruppe; });
  }
}

/* ---------- Gemeinsamer Aufbau für Einzelsparte und Auswertungsgruppe ---------- */

async function renderEinzelsparte(root, state, sparteId) {
  const sparte = (state.sparten || []).find(s => String(s.id) === String(sparteId));
  await renderZiel(root, state, {
    kind: 'sparte', id: sparteId, name: sparte ? sparte.name : `Sparte ${sparteId}`,
    filterParam: {sparte_id: sparteId}, memberIds: [Number(sparteId)],
  });
}

async function renderGruppe(root, state, gruppeId) {
  const gruppe = (state.gruppen || []).find(g => String(g.id) === String(gruppeId));
  if (!gruppe) {
    renderAuswahl(root, state);
    toast('Auswertungsgruppe nicht gefunden.');
    return;
  }
  await renderZiel(root, state, {
    kind: 'gruppe', id: gruppeId, name: gruppe.name,
    filterParam: {auswertungsgruppe_id: gruppeId}, memberIds: gruppe.sparte_ids,
  });
}

function skeletonHtml(ziel) {
  return `
    <div class="card-head" style="margin:-4px 0 -6px"><h2>${esc(ziel.name)}</h2>${ziel.kind === 'gruppe' ? '<span class="hint muted">Auswertungsgruppe</span>' : ''}</div>
    <div class="grid g3" id="s-kpis"></div>
    ${ziel.kind === 'sparte' ? `
    <div class="card">
      <div class="card-head"><h2>Eigene Kennzahlen</h2><span class="hint muted">frei definierbar: Kategorien addieren und abziehen</span></div>
      <div class="kz" id="s-kz"></div>
    </div>` : ''}
    <div class="grid g1-2">
      <div class="card">
        <div class="card-head"><h2>Barkassa</h2><span class="hint muted">gerechnet, nicht gezählt</span></div>
        <div class="konten" id="s-kassa"></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>Auslagen</h2><span class="hint muted">privat bezahlt, Geld noch nicht zurück</span></div>
        <div class="konten" id="s-auslagen"></div>
      </div>
    </div>
    <div class="card">
      <div class="card-head"><h2>Kategorien im Jahresvergleich</h2><div class="yearpick" id="s-years"></div></div>
      <div class="tscroll"><table class="tbl sticky" id="s-matrix"></table></div>
    </div>
    <div class="grid g2">
      <div class="card">
        <div class="card-head"><h2>Wohin das Geld geht</h2></div>
        <div class="hbars" id="s-top-aus"></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>Verlauf über das Jahr</h2></div>
        <div class="chart" id="s-verlauf"></div>
        <div class="legend"><span class="ein">Einnahmen</span><span class="aus">Ausgaben</span></div>
      </div>
    </div>
  `;
}

async function renderZiel(root, state, ziel) {
  root.innerHTML = skeletonHtml(ziel);
  const jahr = (state.filter && state.filter.jahr) || state.year || '';

  let uebersicht;
  try {
    uebersicht = await api('/uebersicht', {params: {...ziel.filterParam, ...(jahr ? {jahr} : {})}});
  } catch (error) {
    root.querySelector('#s-kpis').innerHTML = `<div class="card"><p class="muted">Übersicht konnte nicht geladen werden: ${esc(error.detail || error.message)}</p></div>`;
    toast(error.detail || error.message);
    return;
  }
  root.querySelector('#s-kpis').innerHTML =
    kpiCard('Einnahmen', 'einnahmen_cent', uebersicht, 'var(--ein)', false) +
    kpiCard('Ausgaben', 'ausgaben_cent', uebersicht, 'var(--aus)', false) +
    kpiCard('Saldo', 'saldo_cent', uebersicht, 'var(--ink)', true);

  renderTop(root, ziel, uebersicht);
  renderVerlauf(root, ziel, uebersicht);

  if (ziel.kind === 'sparte') {
    renderKennzahlen(root, ziel, jahr).catch(error => {
      const el = root.querySelector('#s-kz');
      if (el) el.innerHTML = '<p class="muted">Kennzahlen konnten nicht geladen werden.</p>';
      toast(error.detail || error.message || 'Kennzahlen konnten nicht geladen werden.');
    });
  }
  renderKassa(root, state, ziel).catch(error => toast(error.detail || error.message || 'Kassa konnte nicht geladen werden.'));
  renderAuslagen(root, state, ziel).catch(error => toast(error.detail || error.message || 'Auslagen konnten nicht geladen werden.'));

  await renderMatrix(root, state, ziel, jahr);
}

/* ---------- KPI-Zeile (wie P31: Werte kommen fertig vom Server) ---------- */

function kpiCard(label, key, data, color, isSaldo) {
  const jahr = data.jahr;
  const laufend = data.erwartung != null;
  const ist = data.ist[key];
  const erwartung = laufend ? data.erwartung[key] : null;
  const wert = laufend ? erwartung : ist;
  const vorjahr = data.vorjahr_gesamt[key];
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

/* ---------- Drilldown: Buchungen zu einem Filter ---------- */

async function drillBuchungen(filterParams, title) {
  try {
    const data = await api('/buchungen', {params: {...filterParams, limit: 50}});
    const rows = data.buchungen || [];
    const list = rows.length ? rows.map(b => `<div class="hint-row" style="--hc:var(--info)">
        <div><b>${esc(b.text || '(ohne Text)')}</b><div class="muted" style="font-size:12px">${fmtDate(b.datum)} · ${esc(b.sparte_name || '')}${b.zahlungsart ? ' · ' + esc(b.zahlungsart) : ''}</div></div>
        <div class="${b.typ === 'einnahme' ? 'ein' : 'aus'}">${fmtEur(b.betrag_cent)}</div>
      </div>`).join('') : '<p class="muted">Keine Buchungen im Zeitraum.</p>';
    const summe = data.summen || {};
    const fuss = `<p class="muted" style="font-size:12px;margin-top:10px">${summe.anzahl ?? rows.length} Buchung(en) insgesamt${rows.length < (summe.anzahl ?? rows.length) ? `, ${rows.length} angezeigt` : ''} · Saldo ${fmtEur(summe.saldo_cent, true)}</p>`;
    drill(title, list + fuss);
  } catch (error) {
    toast(error.detail || error.message || 'Buchungen konnten nicht geladen werden.');
  }
}

/* ---------- Wohin das Geld geht (aus dem uebersicht-Aufruf, kein Zusatzaufruf) ---------- */

function renderTop(root, ziel, data) {
  const list = data.top?.ausgaben || [];
  const el = root.querySelector('#s-top-aus');
  el.innerHTML = list.length ? list.map(c => {
    const max = list[0].betrag_cent || 1;
    return `<div class="hbar" data-kat="${c.kategorie_id}" tabindex="0" role="button" aria-label="${esc(c.name)}, ${fmtEur(c.betrag_cent)}, Buchungen zeigen">
      <div class="name"><span>${esc(c.name)}</span></div>
      <div class="track"><div class="fill" style="width:${c.betrag_cent / max * 100}%;background:var(--aus)"></div></div>
      <div class="v">${fmtEur(c.betrag_cent)}</div><div class="p">${fmtPct(c.anteil)}</div>
    </div>`;
  }).join('') : '<p class="muted">Keine Ausgaben im Zeitraum.</p>';
  el.querySelectorAll('.hbar').forEach(h => {
    const open = () => drillBuchungen({...ziel.filterParam, kategorie_id: h.dataset.kat, richtung: 'ausgabe'}, 'Ausgaben · Buchungen');
    h.onclick = open;
    h.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } };
  });
}

/* ---------- Verlauf über das Jahr (aus dem uebersicht-Aufruf) ---------- */

function renderVerlauf(root, ziel, data) {
  const monate = data.monate || {einnahmen: [], ausgaben: []};
  const reihen = monate.einnahmen.map((v, i) => ({monat: i + 1, einnahmen_cent: v, ausgaben_cent: monate.ausgaben[i]}));
  const el = root.querySelector('#s-verlauf');
  el.innerHTML = monthlyChart(reihen);
  const jahr = data.jahr;
  el.querySelectorAll('.chart-bars > div').forEach((node, i) => {
    node.setAttribute('role', 'button');
    node.setAttribute('tabindex', '0');
    const open = () => drillBuchungen({...ziel.filterParam, monat: `${jahr}-${String(i + 1).padStart(2, '0')}`}, `Buchungen · Monat ${i + 1}/${jahr}`);
    node.onclick = open;
    node.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } };
  });
}

/* ---------- Eigene Kennzahlen (nur Anzeige, kein Editor - P15 liefert die API) ---------- */

async function renderKennzahlen(root, ziel, jahr) {
  const el = root.querySelector('#s-kz');
  if (!el) return;
  if (!jahr) { el.innerHTML = '<p class="muted">Kein Jahr gewählt.</p>'; return; }
  const [kennzahlen, kategorien] = await Promise.all([
    api('/kennzahlen', {params: {sparte_id: ziel.id, jahr}}),
    api('/kategorien', {params: {sparte_id: ziel.id}}),
  ]);
  const kategorieName = id => kategorien.find(k => String(k.id) === String(id))?.name || `Kategorie ${id}`;
  const formel = terme => terme.length
    ? terme.map((t, i) => `${i === 0 ? (t.vorzeichen < 0 ? '− ' : '') : (t.vorzeichen < 0 ? ' − ' : ' + ')}${esc(kategorieName(t.kategorie_id))}`).join('')
    : '–';
  el.innerHTML = (kennzahlen.length
    ? kennzahlen.map(k => `<div class="kzc">
        <div class="n">${esc(k.name)}</div>
        <div class="f">${formel(k.terme)}</div>
        <div class="v" style="color:${k.wert_cent < 0 ? 'var(--aus)' : 'var(--ein)'}">${fmtEur(k.wert_cent, true)}</div>
        <div class="f">Ø ${fmtEur(k.monatsdurchschnitt_cent, true)} je Monat</div>
      </div>`).join('')
    : '<p class="muted">Keine eigenen Kennzahlen angelegt.</p>')
    + '<div class="kzc hinweis"><span class="muted" style="font-size:12px">Kennzahl anlegen kommt in einem späteren Ausbauschritt.</span></div>';
}

/* ---------- Barkassa (client-seitig gefiltert, /api/konten liefert alle Konten des Bereichs) ---------- */

async function renderKassa(root, state, ziel) {
  const el = root.querySelector('#s-kassa');
  const konten = await api('/konten');
  const kassen = konten.filter(k => k.art === 'kassa' && ziel.memberIds.some(id => String(id) === String(k.sparte_id)));
  el.innerHTML = kassen.length ? kassen.map(k => `<div class="konto">
      <div><div class="kn">${ziel.kind === 'gruppe' ? esc(sparteName(state, k.sparte_id)) + ' · ' : ''}${esc(k.name)}</div>
        <div class="ks">${k.hinweis ? esc(k.hinweis) : (k.datenstand === 'aktuell' ? 'aktuell' : k.datenstand === 'veraltet' ? 'veraltet' : 'kein Anker')}</div></div>
      <div><div class="kv">${k.stand_cent == null ? '<span class="muted">kein Anker</span>' : fmtEur(k.stand_cent)}</div></div>
    </div>`).join('') : '<p class="muted">Keine Kassa angelegt.</p>';
}

/* ---------- Offene Auslagen (Sparte als Ziel oder als Zahler, beide Rollen) ---------- */
// P32-Karte Abschnitt 3 nennt die Rollen "schuldet" = Sparte ist zahler_sparte_id und
// "wird geschuldet" = Sparte ist Ziel. Das ist mit den Feldnamen aus app/routers/auslagen.py
// vertauscht: eine Auslage entsteht per POST /api/buchungen mit bezahlt_von_sparte_id (der
// Zahler), buchhalterisch gehört die Ausgabe zur Ziel-Sparte (sparte_id). Diese schuldet dem
// Zahler das Geld zurück (siehe tests/test_auslagen.py: der Zahler zahlt privat vor; und
// static-neu/pages/konten.js: "<Zahler> hat für <Ziel> ausgelegt" - das Ziel schuldet). Diese
// Seite verwendet deshalb die fachlich richtige Zuordnung (Ziel-Sparte "schuldet", Zahler-
// Sparte "wird geschuldet") statt der im Kartentext vertauschten Bezeichnung; siehe Bericht.
async function ladeAuslagenFuerSparten(sparteIds) {
  const calls = [];
  for (const id of sparteIds) {
    calls.push(api('/auslagen', {params: {sparte_id: id}}).then(rows => rows.map(r => ({...r, rolle: 'schuldet'}))));
    calls.push(api('/auslagen', {params: {zahler_sparte_id: id}}).then(rows => rows.map(r => ({...r, rolle: 'wird_geschuldet'}))));
  }
  const alle = (await Promise.all(calls)).flat();
  const gesehen = new Map();
  for (const r of alle) {
    const key = r.rolle + ':' + r.zahler_sparte_id + ':' + r.sparte_id;
    if (!gesehen.has(key)) gesehen.set(key, r);
  }
  return [...gesehen.values()];
}

async function renderAuslagen(root, state, ziel) {
  const el = root.querySelector('#s-auslagen');
  const rows = await ladeAuslagenFuerSparten(ziel.memberIds);
  if (!rows.length) { el.innerHTML = '<p class="muted">Keine offenen Auslagen.</p>'; return; }
  el.innerHTML = rows.map((g, i) => `<div class="konto" data-i="${i}" role="button" tabindex="0">
      <div><div class="kn">${g.rolle === 'schuldet'
        ? `${esc(sparteName(state, g.sparte_id))} schuldet ${esc(sparteName(state, g.zahler_sparte_id))}`
        : `${esc(sparteName(state, g.zahler_sparte_id))} bekommt von ${esc(sparteName(state, g.sparte_id))}`}</div>
        <div class="ks">${g.anzahl} Buchung(en)</div></div>
      <div><div class="kv aus">${fmtEur(g.offen_cent)}</div></div>
    </div>`).join('');
  el.querySelectorAll('[data-i]').forEach(node => {
    const g = rows[+node.dataset.i];
    const open = () => {
      const list = g.auslagen || [];
      const html = list.length ? list.map(a => `<div class="hint-row"><div><b>${esc(a.text || '')}</b><div class="muted" style="font-size:12px">${fmtDate(a.datum)}${a.kategorie ? ' · ' + esc(a.kategorie) : ''}</div></div><div class="aus">${fmtEur(a.offen_cent)}</div></div>`).join('') : '<p class="muted">Keine offenen Einzelposten.</p>';
      drill(`${esc(sparteName(state, g.zahler_sparte_id))} → ${esc(sparteName(state, g.sparte_id))}`, html);
    };
    node.onclick = open;
    node.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } };
  });
}

/* ---------- Kategorien im Jahresvergleich (Matrix), Jahres-Chips mit Server-Neuabruf ---------- */

function zielSchluessel(ziel) { return ziel.kind + ':' + ziel.id; }

function defaultAktiv(verfuegbar, basisJahr) {
  const sorted = [...verfuegbar].sort((a, b) => a - b);
  const bis = sorted.filter(y => y <= basisJahr);
  const auswahl = (bis.length ? bis : sorted).slice(-4);
  return new Set(auswahl.length ? auswahl : sorted.slice(-1));
}

async function renderMatrix(root, state, ziel, jahr) {
  const schluessel = zielSchluessel(ziel);
  const basisJahr = Number(jahr) || new Date().getFullYear();
  const verfuegbar = [...new Set([...(state.jahre || []).map(Number), basisJahr])];
  if (jahreZustand.schluessel !== schluessel) {
    jahreZustand = {schluessel, verfuegbar, aktiv: defaultAktiv(verfuegbar, basisJahr)};
  } else {
    jahreZustand.verfuegbar = verfuegbar;
  }
  await ladeUndZeichneMatrix(root, state, ziel);
}

async function ladeUndZeichneMatrix(root, state, ziel) {
  const tabelle = root.querySelector('#s-matrix');
  const yearsEl = root.querySelector('#s-years');
  const jahre = [...jahreZustand.aktiv].sort((a, b) => a - b);
  let data;
  try {
    data = await api('/jahresmatrix', {params: {...ziel.filterParam, jahre: jahre.join(',')}});
  } catch (error) {
    toast(error.detail || error.message || 'Jahresmatrix konnte nicht geladen werden.');
    return;
  }
  yearsEl.innerHTML = `<span class="muted" style="font-size:12px;align-self:center;margin-right:4px">Jahre:</span>` +
    [...jahreZustand.verfuegbar].sort((a, b) => a - b).map(y => `<button type="button" class="chip ${jahreZustand.aktiv.has(y) ? 'on' : ''}" data-y="${y}" aria-pressed="${jahreZustand.aktiv.has(y)}">${y}</button>`).join('');
  yearsEl.querySelectorAll('.chip').forEach(c => c.onclick = () => {
    const y = Number(c.dataset.y);
    if (jahreZustand.aktiv.has(y)) {
      if (jahreZustand.aktiv.size <= 1) { toast('Mindestens ein Jahr muss aktiv bleiben.'); return; }
      jahreZustand.aktiv.delete(y);
    } else {
      jahreZustand.aktiv.add(y);
    }
    ladeUndZeichneMatrix(root, state, ziel);
  });
  tabelle.innerHTML = matrixHtml(data);
  tabelle.querySelectorAll('.cell').forEach(c => {
    const open = () => drillBuchungen(
      {...ziel.filterParam, jahr: c.dataset.y, kategorie_id: c.dataset.kat, richtung: c.dataset.typ},
      `${c.dataset.typ === 'einnahme' ? 'Einnahmen' : 'Ausgaben'} · ${c.dataset.y}`,
    );
    c.onclick = open;
    c.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } };
  });
}

function matrixHtml(data) {
  const jahre = data.jahre || [];
  const summen = data.summen || {};
  const rows = data.zeilen || [];
  const letztesJahr = jahre[jahre.length - 1];
  const stichtagJahr = data.stichtag ? Number(data.stichtag.slice(0, 4)) : null;

  const block = (typ, titel) => {
    const feld = typ === 'einnahme' ? 'einnahmen_cent' : 'ausgaben_cent';
    const liste = rows.filter(r => (r.richtung === typ || r.richtung === 'beides') &&
      jahre.some(y => ((r.werte[String(y)] || {})[feld] || 0) !== 0));
    if (!liste.length) return '';
    let html = `<tr class="group"><td colspan="${jahre.length + 2}">${esc(titel)}</td></tr>`;
    for (const r of liste) {
      const still = r.aktiv ? '' : ' <span class="pill est">stillgelegt</span>';
      html += `<tr class="${r.aktiv ? '' : 'inactive'}"><td><span class="cat">${esc(r.name)}</span>${still}</td>`;
      for (const y of jahre) {
        const wert = (r.werte[String(y)] || {})[feld] || 0;
        const schaetzung = y === stichtagJahr && r.erwartung_cent ? r.erwartung_cent[typ === 'einnahme' ? 'einnahmen' : 'ausgaben'] : null;
        html += `<td class="cell" data-kat="${r.kategorie_id}" data-y="${y}" data-typ="${typ}" tabindex="0" role="button" aria-label="${esc(r.name)} ${y}, ${wert ? fmtEur(wert) : 'keine Buchungen'}, Buchungen zeigen">${wert ? fmtEur(wert) : '<span class="muted">–</span>'}${schaetzung != null ? `<span class="est" title="Hochrechnung fürs ganze Jahr, vom Server berechnet">≈ ${fmtEur(schaetzung)}</span>` : ''}</td>`;
      }
      const letzterDurchschnitt = letztesJahr != null ? (r.monatsdurchschnitt_cent || {})[String(letztesJahr)]?.[feld] : null;
      html += `<td>${letzterDurchschnitt != null ? fmtEur(letzterDurchschnitt) : '–'}</td></tr>`;
    }
    html += `<tr class="sum"><td>${esc(titel)} gesamt</td>${jahre.map(y => `<td>${fmtEur((summen[String(y)] || {})[feld] || 0)}</td>`).join('')}<td></td></tr>`;
    return html;
  };

  const kopf = `<thead><tr><th>Kategorie</th>${jahre.map(y => `<th>${y}</th>`).join('')}<th>Ø/Monat${letztesJahr != null ? ' ' + letztesJahr : ''}</th></tr></thead>`;
  const koerper = block('einnahme', 'Einnahmen') + block('ausgabe', 'Ausgaben');
  return kopf + `<tbody>${koerper || `<tr><td colspan="${jahre.length + 2}" class="muted">Keine Buchungen in den gewählten Jahren.</td></tr>`}</tbody>`;
}
