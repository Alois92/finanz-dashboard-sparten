import {api} from '../api.js';
import {esc, fmtEur, fmtDate, parseBetrag} from '../format.js';
import {toast, drill} from '../ui.js';

// P43 Foto-Übernahme. Eigenes Stylesheet nach Nachtrag-Regel (Konfliktregel 3):
// nur eigene Datei, kein Eingriff in style.css.
function cssHref(){return new URL('./belege.css', import.meta.url).href}
function ensureCss(){
  if(!document.querySelector(`link[href="${cssHref()}"]`)){
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = cssHref();
    document.head.appendChild(link);
  }
}

const POLL_INTERVALL_MS = 4000;
const POLL_MAX_MS = 3 * 60 * 1000;
const WORT_RE = /[0-9a-zäöüß]+/gi;

function heute(){
  return new Date().toISOString().slice(0, 10);
}

function fmtBetragFeld(cent){
  return ((cent || 0) / 100).toLocaleString('de-AT', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function centFromInput(value){
  const n = parseBetrag(value);
  return n == null ? null : Math.round(n * 100);
}
function closeDrill(){document.querySelector('#drill').close()}

// Leichte, im Client gehaltene Variante von app/routers/schnellerfassung.py::_match_name -
// die serverseitige Kategorie-Zuordnung arbeitet mit der Beleg-Sparte zum
// Auswertungszeitpunkt, die im Prüf-Dialog gewählte Sparte kann eine andere
// sein (siehe P43-Karte Abschnitt 3, Punkt 2).
function matchKategorie(text, kategorien){
  const textLower = (text || '').toLowerCase();
  const tokens = new Set(textLower.match(WORT_RE) || []);
  let best = null, bestScore = 0;
  for(const k of kategorien){
    const name = (k.name || '').trim().toLowerCase();
    if(!name) continue;
    let score;
    if(textLower.includes(name)){
      score = 100 + name.length;
    }else{
      const nameWoerter = new Set(name.match(WORT_RE) || []);
      const gemeinsam = [...nameWoerter].filter(w => tokens.has(w));
      if(!gemeinsam.length) continue;
      score = 10 * gemeinsam.length + Math.max(...gemeinsam.map(w => w.length));
    }
    if(score > bestScore){bestScore = score; best = k}
  }
  return best;
}

// ---- Foto-Upload (auch von pages/erfassen.js verwendet, P43 Karte Punkt 4) ----

export async function pruefeErreichbarkeit(){
  try{
    return await api('/auswertung/status');
  }catch{
    return null;
  }
}

export async function ladeBelegUndAuswerten(datei, sparteId){
  const form = new FormData();
  form.append('datei', datei);
  if(sparteId) form.append('sparte_id', sparteId);
  const beleg = await api('/belege', {method: 'POST', body: form});
  const auftrag = await api(`/belege/${beleg.id}/auswerten`, {method: 'POST'});
  return {beleg, auftrag};
}

export function erreichbarkeitsHinweis(){
  return 'Foto-Auswertung gerade nicht erreichbar';
}

// ---- Seite ----

export async function render(root, state){
  ensureCss();
  root.innerHTML = '<section class="card placeholder"><p class="muted">Lädt …</p></section>';
  const reload = () => render(root, state);
  const [statusInfo, fertigListe, belegListe] = await Promise.all([
    pruefeErreichbarkeit(),
    api('/beleg-auswertungen?status=fertig').catch(() => []),
    api('/belege').catch(() => []),
  ]);
  draw(root, state, {statusInfo, fertigListe, belegListe}, reload);
}

function draw(root, state, data, reload){
  const erreichbar = data.statusInfo && data.statusInfo.erreichbar && data.statusInfo.modell_vorhanden;
  root.innerHTML = `
    <section class="page">
      <div class="grid g2">
        <div class="card" id="blg-foto-card">
          <div class="card-head"><h2>Rechnung fotografieren</h2></div>
          ${erreichbar ? `
            <div class="blg-foto">
              <input type="file" id="blg-datei" accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp,.pdf,.heic" capture="environment" hidden>
              <button type="button" class="btn primary" id="blg-foto-btn">Beleg fotografieren</button>
              <p class="muted">Foto wird lokal ausgewertet, ohne Cloud.</p>
            </div>
            <div class="blg-warte" id="blg-warte" hidden></div>
          ` : `<p class="blg-nichterreichbar">${esc(erreichbarkeitsHinweis())}</p>`}
        </div>
        <div class="card" id="blg-pruefen-card">
          <div class="card-head"><h2>Belege zur Prüfung</h2></div>
          <div id="blg-pruefen-liste"></div>
        </div>
      </div>
      <div class="card" id="blg-belege-card">
        <div class="card-head"><h2>Belege</h2></div>
        <div id="blg-belege-liste"></div>
      </div>
    </section>
  `;

  if(erreichbar){
    const datei = root.querySelector('#blg-datei');
    root.querySelector('#blg-foto-btn').onclick = () => datei.click();
    datei.onchange = async () => {
      const file = datei.files[0];
      datei.value = '';
      if(!file) return;
      try{
        const {auftrag} = await ladeBelegUndAuswerten(file, state.sparteId || null);
        warteAufAuswertung(root, auftrag.id, reload);
      }catch(error){
        toast(error.detail || error.message || 'Hochladen fehlgeschlagen.');
      }
    };
  }

  drawPruefListe(root, state, data.fertigListe, reload);
  drawBelegListe(root, state, data.belegListe);
}

function warteAufAuswertung(root, auftragId, reload){
  const box = root.querySelector('#blg-warte');
  if(!box) return;
  box.hidden = false;
  box.textContent = 'wird ausgewertet, das dauert ein paar Minuten, die App darf zu sein';
  const start = Date.now();

  async function tick(){
    if(!document.body.contains(box)) return; // Seite gewechselt
    let laufend;
    try{
      laufend = await api('/beleg-auswertungen?status=laeuft');
    }catch{
      laufend = [];
    }
    const nochAktiv = laufend.some(a => a.id === auftragId);
    if(!nochAktiv){
      box.hidden = true;
      toast('Beleg ausgewertet, bitte unter „Belege zur Prüfung" prüfen.');
      reload();
      return;
    }
    if(Date.now() - start > POLL_MAX_MS){
      box.textContent = 'dauert ungewöhnlich lange — bitte später erneut prüfen';
      return;
    }
    setTimeout(tick, POLL_INTERVALL_MS);
  }
  setTimeout(tick, POLL_INTERVALL_MS);
}

function drawPruefListe(root, state, liste, reload){
  const el = root.querySelector('#blg-pruefen-liste');
  if(!liste.length){
    el.innerHTML = '<p class="muted">Keine Belege zur Prüfung.</p>';
    return;
  }
  el.innerHTML = `<div class="blg-tiles">${liste.map(a => pruefTileHtml(a)).join('')}</div>`;
  liste.forEach(a => {
    const tile = el.querySelector(`[data-auftrag="${a.id}"]`);
    if(tile) tile.onclick = () => openPruefDialog(a, state, reload);
  });
}

function pruefTileHtml(a){
  const ergebnis = a.ergebnis || {};
  const gesamt = ergebnis.gesamt_cent != null ? fmtEur(ergebnis.gesamt_cent) : '–';
  return `
    <button type="button" class="blg-tile" data-auftrag="${a.id}">
      <div class="blg-thumb">🧾</div>
      <div class="blg-tile-titel">${esc(ergebnis.haendler || 'Unbekannter Händler')}</div>
      <div class="blg-tile-sub">${ergebnis.datum ? fmtDate(ergebnis.datum) : 'ohne Datum'} · ${gesamt}</div>
    </button>`;
}

function drawBelegListe(root, state, liste){
  const el = root.querySelector('#blg-belege-liste');
  if(!liste.length){
    el.innerHTML = '<p class="muted">Noch keine Belege.</p>';
    return;
  }
  el.innerHTML = `<div class="blg-tiles">${liste.map(b => belegTileHtml(state, b)).join('')}</div>`;
  liste.forEach(b => {
    const tile = el.querySelector(`[data-beleg="${b.id}"]`);
    if(tile) tile.onclick = () => {
      const bereichId = state.bereichId || 1;
      window.open(`/api/belege/${b.id}/datei?bereich_id=${bereichId}`, '_blank');
    };
  });
}

function belegTileHtml(state, b){
  const sparte = state.sparten.find(s => String(s.id) === String(b.sparte_id));
  return `
    <button type="button" class="blg-tile" data-beleg="${b.id}">
      <div class="blg-thumb">📄</div>
      <div class="blg-tile-titel">${esc(b.dateiname)}</div>
      <div class="blg-tile-sub">${b.belegdatum ? fmtDate(b.belegdatum) : '–'} · ${esc(sparte ? sparte.name : 'ohne Sparte')}</div>
    </button>`;
}

// ---- Prüf-Dialog ----

function openPruefDialog(auftrag, state, reload){
  const ergebnis = auftrag.ergebnis || {};
  const positionen = (ergebnis.positionen || []).map(p => ({...p}));
  const privatSparten = state.sparten.filter(s => s.typ === 'privat');

  drill('Beleg prüfen', `
    <p class="prf-header">${esc(ergebnis.haendler || 'Unbekannter Händler')} · ${ergebnis.datum ? fmtDate(ergebnis.datum) : 'ohne Datum'}${ergebnis.gesamt_cent != null ? ' · ' + fmtEur(ergebnis.gesamt_cent) : ''}</p>
    ${ergebnis.hinweis ? `<p class="prf-hinweis">${esc(ergebnis.hinweis)}</p>` : ''}
    <form id="prf-form" novalidate>
      <label class="field">Sparte
        <select id="prf-sparte" required>
          <option value="">Bitte wählen</option>
          ${state.sparten.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join('')}
        </select>
      </label>
      <label class="ef-toggle-field" id="prf-auslage-label" hidden>
        <input type="checkbox" id="prf-auslage-toggle">
        Auslage für andere Sparte (privat bezahlt)
      </label>
      <label class="field" id="prf-von-feld" hidden>Bezahlt von
        <select id="prf-von"></select>
      </label>
      <div class="grid g2">
        <label class="field">Datum<input type="date" id="prf-datum" value="${esc(ergebnis.datum || heute())}"></label>
        <label class="field">Zahlungsart
          <select id="prf-zahlungsart">
            <option value="bar" selected>Bar</option>
            <option value="bank">Bank</option>
            <option value="karte">Karte</option>
            <option value="sonstiges">Sonstiges</option>
          </select>
        </label>
      </div>
      <div id="prf-positionen">
        ${positionen.map((p, i) => `
          <div class="prf-position" data-index="${i}">
            <input type="text" class="prf-text" value="${esc(p.text || '')}" placeholder="Text" required>
            <input type="text" class="prf-betrag" inputmode="decimal" value="${fmtBetragFeld(p.betrag_cent)}" required>
            <select class="prf-kategorie" required><option value="">Bitte wählen</option></select>
          </div>
        `).join('')}
      </div>
      <p class="field-error" id="prf-error" hidden></p>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:10px">
        <button type="button" class="btn" id="prf-verwerfen">Verwerfen</button>
        <button type="submit" class="btn primary" id="prf-uebernehmen">Übernehmen</button>
      </div>
    </form>
  `);

  const sparteSelect = document.querySelector('#prf-sparte');
  const auslageLabel = document.querySelector('#prf-auslage-label');
  const auslageToggle = document.querySelector('#prf-auslage-toggle');
  const vonFeld = document.querySelector('#prf-von-feld');
  const vonSelect = document.querySelector('#prf-von');
  const errBox = document.querySelector('#prf-error');
  let kategorienCache = [];

  function aktualisiereAuslageSichtbarkeit(){
    const zeigen = privatSparten.length > 0 && privatSparten.some(s => String(s.id) !== sparteSelect.value);
    auslageLabel.hidden = !zeigen;
    if(!zeigen){
      auslageToggle.checked = false;
      vonFeld.hidden = true;
    }
    vonSelect.innerHTML = privatSparten.filter(s => String(s.id) !== sparteSelect.value)
      .map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join('');
  }

  async function ladeKategorienFuerSparte(){
    const sid = sparteSelect.value;
    if(!sid){
      document.querySelectorAll('.prf-kategorie').forEach(sel => { sel.innerHTML = '<option value="">Bitte wählen</option>' });
      kategorienCache = [];
      return;
    }
    try{
      kategorienCache = await api(`/kategorien?sparte_id=${sid}&nur_aktive=true`);
    }catch(error){
      toast(error.detail || error.message);
      kategorienCache = [];
    }
    document.querySelectorAll('.prf-position').forEach(row => {
      const i = Number(row.dataset.index);
      const select = row.querySelector('.prf-kategorie');
      select.innerHTML = '<option value="">Bitte wählen</option>' +
        kategorienCache.map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join('');
      const vorschlag = matchKategorie(positionen[i]?.text, kategorienCache);
      if(vorschlag) select.value = String(vorschlag.id);
    });
  }

  sparteSelect.addEventListener('change', () => {
    aktualisiereAuslageSichtbarkeit();
    ladeKategorienFuerSparte();
  });
  auslageToggle.addEventListener('change', () => {
    vonFeld.hidden = !auslageToggle.checked;
  });

  document.querySelector('#prf-verwerfen').onclick = async () => {
    try{
      await api(`/beleg-auswertungen/${auftrag.id}/status`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({status: 'verworfen'}),
      });
      toast('Beleg verworfen.');
      closeDrill();
      reload();
    }catch(error){
      errBox.textContent = error.detail || error.message;
      errBox.hidden = false;
    }
  };

  document.querySelector('#prf-form').addEventListener('submit', async e => {
    e.preventDefault();
    errBox.hidden = true;
    if(!sparteSelect.value){
      errBox.textContent = 'Bitte eine Sparte wählen.';
      errBox.hidden = false;
      return;
    }
    const zeilen = [];
    for(const row of document.querySelectorAll('.prf-position')){
      const text = row.querySelector('.prf-text').value.trim();
      const betrag = centFromInput(row.querySelector('.prf-betrag').value);
      const kategorieId = row.querySelector('.prf-kategorie').value;
      if(!text || betrag == null || betrag <= 0 || !kategorieId){
        errBox.textContent = 'Bitte bei jeder Position Text, Betrag und Kategorie ausfüllen.';
        errBox.hidden = false;
        return;
      }
      zeilen.push({text, betrag_cent: betrag, kategorie_id: Number(kategorieId)});
    }
    const body = {
      sparte_id: Number(sparteSelect.value),
      datum: document.querySelector('#prf-datum').value || undefined,
      zahlungsart: document.querySelector('#prf-zahlungsart').value,
      positionen: zeilen,
      client_request_id: crypto.randomUUID(),
    };
    if(auslageToggle.checked && vonSelect.value){
      body.bezahlt_von_sparte_id = Number(vonSelect.value);
    }
    const submitBtn = document.querySelector('#prf-uebernehmen');
    submitBtn.disabled = true;
    try{
      await api(`/beleg-auswertungen/${auftrag.id}/uebernehmen`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      toast('Buchung angelegt.');
      closeDrill();
      reload();
    }catch(error){
      errBox.textContent = error.detail || error.message;
      errBox.hidden = false;
    }finally{
      submitBtn.disabled = false;
    }
  });
}
