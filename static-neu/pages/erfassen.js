import {api} from '../api.js';
import {esc, fmtEur, fmtDate, parseBetrag} from '../format.js';
import {toast, drill} from '../ui.js';
import {pruefeErreichbarkeit, ladeBelegUndAuswerten, erreichbarkeitsHinweis} from './belege.js';

// P40 Erfassen-Fluss. Laedt sein eigenes CSS beim ersten Render nach
// Nachtrag-Regel (Konfliktregel 3): nur eigene Datei, kein Eingriff in
// style.css.
let cssGeladen = false;
function ladeCss(){
  if(cssGeladen) return;
  cssGeladen = true;
  if(document.querySelector('link[data-p40-erfassen]')) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = './pages/erfassen.css';
  link.dataset.p40Erfassen = '1';
  document.head.appendChild(link);
}

const LS_SPARTE = 'neu-erfassen-sparte';
const LS_ZAHLUNGSART = 'neu-erfassen-zahlungsart';

// Modul-weiter Zustand: bleibt beim erneuten Rendern der Seite innerhalb
// derselben Sitzung erhalten (ES-Modul wird von app.js nur einmal geladen),
// wird aber bei jedem render() neu verdrahtet.
const M = {
  kategorienCache: new Map(),  // sparte_id -> Array
  konten: [],
  kontenGeladen: false,
  parseTimer: null,
  manuellSparte: false,
  manuellKategorie: false,
  letzterVorschlag: null,
};

function heute(){
  return new Date().toISOString().slice(0, 10);
}

async function ladeKategorien(sparteId){
  if(!sparteId) return [];
  if(M.kategorienCache.has(sparteId)) return M.kategorienCache.get(sparteId);
  const liste = await api(`/kategorien?sparte_id=${sparteId}&nur_aktive=true`);
  M.kategorienCache.set(sparteId, liste);
  return liste;
}

async function ladeKonten(){
  if(M.kontenGeladen) return M.konten;
  M.konten = await api('/konten');
  M.kontenGeladen = true;
  return M.konten;
}

export async function render(root, state){
  ladeCss();
  M.kategorienCache.clear();
  M.kontenGeladen = false;
  M.manuellSparte = false;
  M.manuellKategorie = false;
  M.letzterVorschlag = null;

  const sparten = (state.sparten || []).slice();
  const privatSparten = sparten.filter(s => s.typ === 'privat');

  root.innerHTML = `
    <div class="page erfassen-page">
      <div class="grid g2-1" style="grid-template-columns:1.3fr 1fr">
        <div class="grid">
          <div class="card quick-card">
            <div class="card-head">
              <h2>Erfassen</h2>
              <span class="muted" style="font-size:12.5px">Bar ist die Vorgabe.</span>
            </div>
            <form id="ef-form" novalidate>
              <div class="ef-amount-row">
                <div class="field">
                  Richtung
                  <div class="segmented" role="radiogroup" aria-label="Richtung">
                    <button type="button" class="seg-btn aus active" data-typ="ausgabe" aria-pressed="true">Ausgabe</button>
                    <button type="button" class="seg-btn ein" data-typ="einnahme" aria-pressed="false">Einnahme</button>
                  </div>
                </div>
                <label class="field ef-betrag-field">Betrag in €
                  <input id="ef-betrag" inputmode="decimal" autocomplete="off" placeholder="0,00" required>
                </label>
              </div>
              <label class="field">Sparte
                <select id="ef-sparte" required>
                  ${sparten.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join('')}
                </select>
              </label>
              <label class="field">Was hast du bezahlt oder bekommen?
                <textarea id="ef-text" rows="2" placeholder="z. B. Mittagessen Gasthof 14,80"></textarea>
              </label>
              <div class="ef-sugg" id="ef-sugg" aria-live="polite" hidden></div>
              <div class="grid g2">
                <label class="field">Zahlungsart
                  <select id="ef-zahlungsart">
                    <option value="bar">Bar</option>
                    <option value="bank">Bank</option>
                    <option value="karte">Karte</option>
                    <option value="sonstiges">Sonstiges</option>
                  </select>
                </label>
                <label class="field" id="ef-konto-field" hidden>Konto
                  <select id="ef-konto"></select>
                </label>
              </div>
              <div class="grid g2">
                <label class="field">Datum
                  <input type="date" id="ef-datum" value="${heute()}">
                </label>
                <label class="field">Kategorie
                  <div class="ef-katline">
                    <select id="ef-kategorie"><option value="">Bitte wählen</option></select>
                    <button type="button" class="btn small" id="ef-newcat">+ Neue</button>
                  </div>
                </label>
              </div>
              <label class="ef-toggle-field" id="ef-auslage-label" hidden>
                <input type="checkbox" id="ef-auslage-toggle">
                Auslage für andere Sparte (privat bezahlt)
              </label>
              <div class="field" id="ef-von-field" hidden>
                Bezahlt von
                <select id="ef-von">
                  ${privatSparten.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join('')}
                </select>
                <span class="muted ef-hint">Privat bezahlt für eine andere Sparte? Dann steht es unter „Offene Auslagen“ und kommt per Ausgleich zurück. Die Kosten bleiben bei der Sparte.</span>
              </div>
              <div class="ef-beleg-hint muted">Beleg fotografieren kommt mit der Foto-Übernahme — für jetzt reicht „später“.</div>
              <div class="ef-actions">
                <button type="submit" class="btn primary" id="ef-save">Buchung speichern</button>
                <span class="muted" id="ef-status" aria-live="polite" style="font-size:12.5px"></span>
              </div>
            </form>
          </div>
        </div>
        <div class="grid">
          <div class="card">
            <div class="card-head"><h2>Rechnung fotografieren</h2></div>
            <div class="ef-photo-placeholder">
              <input type="file" id="ef-photo-input" accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp,.pdf,.heic" capture="environment" hidden>
              <button type="button" class="btn" id="ef-photo-btn">Beleg fotografieren</button>
              <p class="muted">Foto wird lokal ausgewertet, ohne Cloud. Ergebnis erscheint unter „Belege".</p>
            </div>
          </div>
          <div class="card">
            <div class="card-head"><h2>Zuletzt erfasst</h2></div>
            <div class="ef-recent" id="ef-recent"><p class="ef-empty">Lädt …</p></div>
          </div>
        </div>
      </div>
    </div>
  `;

  const el = sel => root.querySelector(sel);
  const form = el('#ef-form');
  const betragInput = el('#ef-betrag');
  const sparteSelect = el('#ef-sparte');
  const textArea = el('#ef-text');
  const suggBox = el('#ef-sugg');
  const zahlungsartSelect = el('#ef-zahlungsart');
  const kontoField = el('#ef-konto-field');
  const kontoSelect = el('#ef-konto');
  const datumInput = el('#ef-datum');
  const kategorieSelect = el('#ef-kategorie');
  const auslageLabel = el('#ef-auslage-label');
  const auslageToggle = el('#ef-auslage-toggle');
  const vonField = el('#ef-von-field');
  const vonSelect = el('#ef-von');
  const saveBtn = el('#ef-save');
  const statusSpan = el('#ef-status');
  const recentBox = el('#ef-recent');

  let typ = 'ausgabe';

  function gewaehlteSparte(){
    const v = sparteSelect.value;
    return v ? Number(v) : null;
  }

  function aktualisiereAuslageSichtbarkeit(){
    const zeigen = typ === 'ausgabe' && privatSparten.length > 0 &&
      privatSparten.some(s => String(s.id) !== sparteSelect.value);
    auslageLabel.hidden = !zeigen;
    if(!zeigen){
      auslageToggle.checked = false;
      vonField.hidden = true;
    }
  }

  function aktualisiereVonOptionen(){
    const sid = sparteSelect.value;
    const optionen = privatSparten.filter(s => String(s.id) !== sid);
    vonSelect.innerHTML = optionen.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join('');
  }

  function setTyp(neu){
    typ = neu;
    root.querySelectorAll('.seg-btn').forEach(b => {
      const aktiv = b.dataset.typ === typ;
      b.classList.toggle('active', aktiv);
      b.setAttribute('aria-pressed', String(aktiv));
    });
    aktualisiereAuslageSichtbarkeit();
    ladeKategorieOptionen();
  }

  async function ladeKategorieOptionen(){
    const sid = gewaehlteSparte();
    if(!sid){
      kategorieSelect.innerHTML = '<option value="">Bitte wählen</option>';
      return;
    }
    let liste;
    try{
      liste = await ladeKategorien(sid);
    }catch(error){
      toast(error.detail || error.message);
      return;
    }
    const passend = liste.filter(k => k.richtung === typ || k.richtung === 'beides');
    const vorherWert = kategorieSelect.value;
    kategorieSelect.innerHTML = '<option value="">Bitte wählen</option>' +
      passend.map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join('');
    if(passend.some(k => String(k.id) === vorherWert)){
      kategorieSelect.value = vorherWert;
    }
  }

  async function aktualisiereKontoFeld(){
    const art = zahlungsartSelect.value;
    if(art !== 'bank' && art !== 'karte'){
      kontoField.hidden = true;
      kontoSelect.innerHTML = '';
      return;
    }
    kontoField.hidden = false;
    let konten;
    try{
      konten = await ladeKonten();
    }catch(error){
      toast(error.detail || error.message);
      return;
    }
    const sid = gewaehlteSparte();
    const passend = konten.filter(k => k.aktiv && k.sparte_id === sid && k.art === art);
    if(!passend.length){
      kontoSelect.innerHTML = '<option value="">Kein Konto hinterlegt</option>';
      return;
    }
    kontoSelect.innerHTML = passend.map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join('');
  }

  async function ladeZuletztErfasst(){
    const sid = gewaehlteSparte();
    if(!sid){
      recentBox.innerHTML = '<p class="ef-empty">Bitte zuerst eine Sparte wählen.</p>';
      return;
    }
    try{
      const antwort = await api(`/buchungen?sparte_id=${sid}&limit=7`);
      const zeilen = antwort.buchungen || [];
      if(!zeilen.length){
        recentBox.innerHTML = '<p class="ef-empty">Noch keine Buchungen in dieser Sparte.</p>';
        return;
      }
      recentBox.innerHTML = zeilen.map(b => {
        const kategorien = (b.zeilen || []).map(z => z.kategorie_name).filter(Boolean).join(', ');
        const vorzeichen = b.typ === 'einnahme' ? 'ein' : 'aus';
        const symbol = b.typ === 'einnahme' ? '+' : '−';
        let badge = '';
        if(b.auslage){
          badge = b.auslage.ausgeglichen
            ? '<span class="ef-badge ok">ausgeglichen</span>'
            : '<span class="ef-badge">Auslage</span>';
        }
        return `<div class="ef-recent-row">
          <div class="ef-recent-main">
            <span class="ef-recent-text">${esc(b.text || kategorien || '–')}${badge}</span>
            <span class="ef-recent-meta">${esc(kategorien || '–')} · ${fmtDate(b.datum)}</span>
          </div>
          <div class="ef-recent-amount ${vorzeichen}">${symbol} ${fmtEur(b.betrag_cent)}</div>
        </div>`;
      }).join('');
    }catch(error){
      recentBox.innerHTML = `<p class="ef-empty">Konnte nicht geladen werden: ${esc(error.detail || error.message)}</p>`;
    }
  }

  function zeigeVorschlag(v){
    if(!v || (!v.sparte_name && !v.kategorie_name)){
      suggBox.hidden = true;
      suggBox.innerHTML = '';
      return;
    }
    const teile = [];
    if(v.sparte_name) teile.push(`Sparte <b>${esc(v.sparte_name)}</b>`);
    if(v.kategorie_name) teile.push(`Kategorie <b>${esc(v.kategorie_name)}</b>`);
    suggBox.hidden = false;
    suggBox.innerHTML = `Vorschlag: ${teile.join(' · ')}`;
  }

  async function parseText(){
    const text = textArea.value.trim();
    if(!text){
      suggBox.hidden = true;
      suggBox.innerHTML = '';
      return;
    }
    let vorschlag;
    try{
      vorschlag = await api('/parse', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text})});
    }catch(error){
      return; // Vorschlag ist optional, Fehler hier nicht stoeren
    }
    M.letzterVorschlag = vorschlag;
    zeigeVorschlag(vorschlag);
    if(vorschlag.sparte_id && !M.manuellSparte){
      sparteSelect.value = String(vorschlag.sparte_id);
      await ladeKategorieOptionen();
      await aktualisiereKontoFeld();
      aktualisiereAuslageSichtbarkeit();
      aktualisiereVonOptionen();
      await ladeZuletztErfasst();
    }
    if(vorschlag.kategorie_id && !M.manuellKategorie){
      const liste = await ladeKategorien(gewaehlteSparte()).catch(() => []);
      if(liste.some(k => k.id === vorschlag.kategorie_id)){
        kategorieSelect.value = String(vorschlag.kategorie_id);
      }
    }
    if(vorschlag.betrag_cent && !betragInput.value.trim()){
      betragInput.value = (vorschlag.betrag_cent / 100).toFixed(2).replace('.', ',');
    }
  }

  textArea.addEventListener('input', () => {
    clearTimeout(M.parseTimer);
    M.parseTimer = setTimeout(parseText, 300);
  });

  root.querySelectorAll('.seg-btn').forEach(b => {
    b.addEventListener('click', () => setTyp(b.dataset.typ));
  });

  sparteSelect.addEventListener('change', async () => {
    M.manuellSparte = true;
    M.manuellKategorie = false;
    localStorage.setItem(LS_SPARTE, sparteSelect.value);
    await ladeKategorieOptionen();
    await aktualisiereKontoFeld();
    aktualisiereAuslageSichtbarkeit();
    aktualisiereVonOptionen();
    await ladeZuletztErfasst();
  });

  kategorieSelect.addEventListener('change', () => { M.manuellKategorie = true; });

  zahlungsartSelect.addEventListener('change', () => {
    localStorage.setItem(LS_ZAHLUNGSART, zahlungsartSelect.value);
    aktualisiereKontoFeld();
  });

  auslageToggle.addEventListener('change', () => {
    vonField.hidden = !auslageToggle.checked;
  });

  const photoInput = el('#ef-photo-input');
  el('#ef-photo-btn').addEventListener('click', async () => {
    const status = await pruefeErreichbarkeit();
    if(!status || !status.erreichbar || !status.modell_vorhanden){
      toast(erreichbarkeitsHinweis(status));
      return;
    }
    photoInput.click();
  });
  photoInput.addEventListener('change', async () => {
    const datei = photoInput.files[0];
    photoInput.value = '';
    if(!datei) return;
    try{
      await ladeBelegUndAuswerten(datei, gewaehlteSparte());
      // Die Auswertung laeuft im Hintergrund und dauert Minuten (P43) - die
      // Erfassung wird dadurch nicht blockiert, "die App darf zu sein".
      toast('Beleg wird lokal ausgewertet, das dauert ein paar Minuten. Ergebnis erscheint unter „Belege".');
    }catch(error){
      toast(error.detail || error.message || 'Hochladen fehlgeschlagen.');
    }
  });

  el('#ef-newcat').addEventListener('click', () => {
    const sid = gewaehlteSparte();
    if(!sid){
      toast('Bitte zuerst eine Sparte wählen.');
      return;
    }
    drill('Neue Kategorie', `
      <form id="ef-newcat-form">
        <label class="field">Name der neuen Kategorie<input name="name" required maxlength="120"></label>
        <label class="field">Richtung
          <select name="richtung">
            <option value="ausgabe" ${typ === 'ausgabe' ? 'selected' : ''}>Ausgabe</option>
            <option value="einnahme" ${typ === 'einnahme' ? 'selected' : ''}>Einnahme</option>
            <option value="beides">Beides</option>
          </select>
        </label>
        <button class="btn primary" type="submit">Kategorie anlegen</button>
      </form>
    `);
    document.querySelector('#ef-newcat-form').onsubmit = async e => {
      e.preventDefault();
      const daten = new FormData(e.target);
      try{
        const neu = await api('/kategorien', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({sparte_id: sid, name: daten.get('name'), richtung: daten.get('richtung')}),
        });
        M.kategorienCache.delete(sid);
        await ladeKategorieOptionen();
        kategorieSelect.value = String(neu.id);
        M.manuellKategorie = true;
        document.querySelector('#drill').close();
        toast('Kategorie angelegt.');
      }catch(error){
        toast(error.detail || error.message);
      }
    };
  });

  function formularZuruecksetzen(){
    betragInput.value = '';
    textArea.value = '';
    suggBox.hidden = true;
    suggBox.innerHTML = '';
    kategorieSelect.value = '';
    auslageToggle.checked = false;
    vonField.hidden = true;
    datumInput.value = heute();
    M.manuellKategorie = false;
    M.letzterVorschlag = null;
    betragInput.focus();
  }

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const sid = gewaehlteSparte();
    const betrag = parseBetrag(betragInput.value);
    const kategorieId = kategorieSelect.value ? Number(kategorieSelect.value) : null;
    if(!sid){ toast('Bitte eine Sparte wählen.'); return; }
    if(betrag === null || betrag <= 0){ toast('Bitte einen gültigen Betrag eingeben.'); return; }
    if(!kategorieId){ toast('Bitte eine Kategorie wählen.'); return; }
    if(!datumInput.value){ toast('Bitte ein Datum wählen.'); return; }

    saveBtn.disabled = true;
    statusSpan.textContent = 'Speichert …';

    const payload = {
      sparte_id: sid,
      datum: datumInput.value,
      typ,
      zahlungsart: zahlungsartSelect.value,
      text: textArea.value.trim() || null,
      zeilen: [{kategorie_id: kategorieId, betrag_cent: Math.round(betrag * 100)}],
      client_request_id: crypto.randomUUID(),
    };
    if(!kontoField.hidden && kontoSelect.value){
      payload.bankkonto_id = Number(kontoSelect.value);
    }
    if(typ === 'ausgabe' && auslageToggle.checked && vonSelect.value){
      payload.bezahlt_von_sparte_id = Number(vonSelect.value);
    }

    try{
      await api('/buchungen', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
      toast('Buchung gespeichert.');
      formularZuruecksetzen();
      await ladeZuletztErfasst();
    }catch(error){
      toast(error.detail || error.message || 'Speichern fehlgeschlagen.');
    }finally{
      saveBtn.disabled = false;
      statusSpan.textContent = '';
    }
  });

  // Anfangszustand herstellen.
  const gemerkt = localStorage.getItem(LS_SPARTE);
  if(gemerkt && sparten.some(s => String(s.id) === gemerkt)){
    sparteSelect.value = gemerkt;
    M.manuellSparte = true;
  } else if(state.sparteId && sparten.some(s => String(s.id) === String(state.sparteId))){
    sparteSelect.value = String(state.sparteId);
  } else if(sparten.length){
    sparteSelect.value = String(sparten[0].id);
  }
  const gemerkteZahlungsart = localStorage.getItem(LS_ZAHLUNGSART);
  if(gemerkteZahlungsart){
    zahlungsartSelect.value = gemerkteZahlungsart;
  }

  await ladeKategorieOptionen();
  await aktualisiereKontoFeld();
  aktualisiereAuslageSichtbarkeit();
  aktualisiereVonOptionen();
  await ladeZuletztErfasst();
}
