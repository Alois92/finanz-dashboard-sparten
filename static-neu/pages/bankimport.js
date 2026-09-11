// P42 – Bankimport mit Zuordnung zu Bewegungen.
// Endpunkte: POST /api/import/csv, GET /api/bankumsaetze, POST .../verbuchen,
// PATCH /api/bankumsaetze/{id}, POST /api/bankumsaetze/vorschlaege-uebernehmen,
// GET .../kandidaten, POST .../zuordnen, POST .../zuordnung-loesen (N4),
// GET /api/konten/{id}/offene-abgleiche (N4), GET /api/konten, GET /api/kategorien.
import {api} from '../api.js';
import {esc, fmtEur, fmtDate} from '../format.js';
import {toast, drill} from '../ui.js';

// Modul-Zustand bleibt über Re-Renders derselben Seite erhalten (das ES-Modul
// wird beim Routenwechsel nur beim ersten Aufruf importiert).
const M = {
  cssGeladen: false,
  konten: [],
  kategorien: [],
  uploadKontoId: '',
  filterKontoId: '',
  bericht: null,           // letzte Antwort von POST /api/import/csv
  abgleichVorschlaege: [], // {umsatz, kandidaten:[...]} fuer "Zusammenfuehren?"
  ausgeblendet: new Set(), // clientseitig "Getrennt lassen"
  umsaetze: [],
  ladeFehler: null,
};

function ladeCss() {
  if (M.cssGeladen || document.querySelector('link[data-bi-css]')) { M.cssGeladen = true; return; }
  const link = document.createElement('link');
  link.rel = 'stylesheet'; link.href = './pages/bankimport.css'; link.dataset.biCss = '1';
  document.head.appendChild(link);
  M.cssGeladen = true;
}

const KONTO_ARTEN = new Set(['bank', 'karte']);

function bankKonten() { return M.konten.filter(k => KONTO_ARTEN.has(k.art)); }
function kontoName(id) { return M.konten.find(k => String(k.id) === String(id))?.name || `Konto ${id}`; }
function sparteName(state, id) { return state.sparten.find(s => String(s.id) === String(id))?.name || `Sparte ${id}`; }
function katName(id) { return M.kategorien.find(k => String(k.id) === String(id))?.name || `Kategorie ${id}`; }
function kategorienFuerSparte(sparteId) { return M.kategorien.filter(k => String(k.sparte_id) === String(sparteId) && k.aktiv); }

async function ladeStammdaten() {
  const [konten, kategorien] = await Promise.all([
    api('/konten'),
    api('/kategorien', {params: {nur_aktive: 'true'}}),
  ]);
  M.konten = konten;
  M.kategorien = kategorien;
  if (!M.uploadKontoId && bankKonten().length) M.uploadKontoId = String(bankKonten()[0].id);
  if (!M.filterKontoId && bankKonten().length) M.filterKontoId = String(bankKonten()[0].id);
}

async function ladeUmsaetze() {
  if (!M.filterKontoId) { M.umsaetze = []; return; }
  M.umsaetze = await api('/bankumsaetze', {params: {bankkonto_id: M.filterKontoId}});
}

async function ladeAbgleichVorschlaege() {
  if (!M.filterKontoId) { M.abgleichVorschlaege = []; return; }
  try {
    const uebersicht = await api(`/konten/${M.filterKontoId}/offene-abgleiche`);
    const offene = uebersicht.offene_umsaetze.filter(u => !M.ausgeblendet.has(u.bankumsatz_id));
    M.abgleichVorschlaege = await Promise.all(offene.map(async u => ({
      umsatz: u,
      kandidaten: (await api(`/bankumsaetze/${u.bankumsatz_id}/kandidaten`)).kandidaten,
    })));
  } catch (error) {
    M.abgleichVorschlaege = [];
  }
}

async function ladeAlles() {
  await ladeStammdaten();
  await Promise.all([ladeUmsaetze(), ladeAbgleichVorschlaege()]);
}

// ---------------------------------------------------------------------------
// Konten-Karte (lesend)
// ---------------------------------------------------------------------------

function renderKontenKarte() {
  const liste = bankKonten();
  const body = liste.length
    ? liste.map(k => `<div class="a"><div class="an">${esc(k.name)}<span class="kind">${esc(k.art)}</span></div>` +
        `<div class="ai">${k.iban ? esc(k.iban) : (k.kartenendnummer ? `Kartenendnummer ${esc(k.kartenendnummer)}` : 'keine IBAN hinterlegt')}</div>` +
        `<div class="av ${k.stand_cent < 0 ? 'aus' : 'ein'}">${k.stand_cent == null ? '–' : fmtEur(k.stand_cent)}</div>` +
        `<div class="ai">${k.letzter_import ? `letzter Import ${fmtDate(k.letzter_import)}` : 'noch kein Import'} · Datenstand ${esc(k.datenstand)}</div></div>`).join('')
    : '<p class="empty">Noch kein Bank- oder Kartenkonto angelegt.</p>';
  return `<div class="card"><div class="card-head"><h2>Konten</h2><a class="btn small" href="#/konten">Verwalten → Konten</a></div>` +
    `<div class="bi-acct">${body}</div></div>`;
}

// ---------------------------------------------------------------------------
// Upload-Karte
// ---------------------------------------------------------------------------

function renderUploadKarte() {
  const liste = bankKonten();
  const optionen = liste.map(k => `<option value="${k.id}" ${String(k.id) === M.uploadKontoId ? 'selected' : ''}>${esc(k.name)}</option>`).join('');
  const kannHochladen = liste.length > 0;
  const bericht = M.bericht ? renderBericht(M.bericht) : '';
  const merge = M.abgleichVorschlaege.length ? renderMergeListe() : '';
  return `<div class="card"><div class="card-head"><h2>Kontoauszug einspielen</h2>` +
    `<span class="hint">Kodierung, Trennzeichen und Spalten werden erkannt · du siehst zuerst den Prüfbericht</span></div>` +
    `<div class="bi-upload-row"><label class="field">Konto<select id="bi-upload-konto" ${kannHochladen ? '' : 'disabled'}>${optionen || '<option>kein Konto</option>'}</select></label></div>` +
    (kannHochladen
      ? `<div class="bi-drop" id="bi-drop" tabindex="0" role="button">Datei hierher ziehen oder klicken<br><span class="hint">CSV-Kontoauszug, wird erst nach der Prüfung eingespielt</span><input type="file" id="bi-file" accept=".csv,text/csv" hidden></div>`
      : `<p class="empty">Zuerst unter <a href="#/konten">Konten</a> ein Bank- oder Kartenkonto anlegen.</p>`) +
    bericht + merge + `</div>`;
}

function renderBericht(b) {
  const fehler = b.erkannt.zeilen_ungueltig || [];
  return `<div class="bi-report">` +
    `<div class="row"><span>Kodierung <b>${esc(b.erkannt.kodierung)}</b></span><span>Trennzeichen <b>${esc(b.erkannt.trennzeichen)}</b></span>` +
    `<span>Zeilen gesamt <b>${b.erkannt.zeilen_gesamt}</b></span></div>` +
    `<div class="row"><span>neu <b>${b.neu}</b></span><span>Dubletten <b>${b.dubletten}</b></span>` +
    `<span>ungültig <b class="${fehler.length ? 'bad' : ''}">${fehler.length}</b></span></div>` +
    (b.saldo_hinweis ? `<div class="row ${b.saldo_ok === false ? 'bad' : ''}">${esc(b.saldo_hinweis)}</div>` : '') +
    (fehler.length ? `<ul class="fehlerliste">${fehler.map(f => `<li>Zeile ${f.zeile}: ${esc(f.grund)}</li>`).join('')}</ul>` : '') +
    `</div>`;
}

function renderMergeListe() {
  const rows = M.abgleichVorschlaege.map(({umsatz, kandidaten}) => {
    const options = kandidaten.map(k => `<option value="${k.buchung_id}">${fmtDate(k.datum)} · ${esc(k.text || '(ohne Text)')} · ${fmtEur(k.betrag_cent)} · ${k.abstand_tage} Tag(e) Abstand</option>`).join('');
    return `<div class="bi-merge-row" data-umsatz="${umsatz.bankumsatz_id}">` +
      `<div class="info"><span>${fmtDate(umsatz.datum)} · ${esc(umsatz.text || '(ohne Text)')} · <b class="${umsatz.betrag_cent < 0 ? 'aus' : 'ein'}">${fmtEur(umsatz.betrag_cent)}</b></span>` +
      `<span class="muted">${kandidaten.length} möglicherweise passende Buchung(en) bereits erfasst</span></div>` +
      `<div class="actions">${kandidaten.length > 1 ? `<select class="bi-merge-select" aria-label="Buchung wählen">${options}</select>` : `<input type="hidden" class="bi-merge-select" value="${kandidaten[0]?.buchung_id ?? ''}">`}` +
      `<button class="btn small" data-merge-go="${umsatz.bankumsatz_id}">Zusammenführen</button>` +
      `<button class="btn small" data-merge-skip="${umsatz.bankumsatz_id}">Getrennt lassen</button></div></div>`;
  }).join('');
  return `<div class="bi-merge"><h3>Diese Zahlungen wurden schon erfasst — zusammenführen?</h3>${rows}</div>`;
}

// ---------------------------------------------------------------------------
// Umsätze-Karte
// ---------------------------------------------------------------------------

const STATUS_LABEL = {auto: 'automatisch verbucht', vor: 'Vorschlag', offen: 'offen', umb: 'Umbuchung', ignoriert: 'ignoriert', verbucht: 'verbucht'};

function statusVon(u) {
  if (u.importstatus === 'verbucht') return {css: 'auto', label: 'verbucht'};
  if (u.importstatus === 'ignoriert') return {css: 'ignoriert', label: 'ignoriert'};
  if (u.vorschlag) return {css: 'vor', label: 'Vorschlag'};
  return {css: 'offen', label: 'offen'};
}

function zuordnungZelle(u, state) {
  if (u.importstatus === 'verbucht') return '<span class="muted">siehe Buchungsliste</span>';
  if (u.importstatus === 'ignoriert') return '<span class="muted">–</span>';
  if (u.vorschlag) {
    const regel = u.vorschlag.regel_name ? ` · Regel „${esc(u.vorschlag.regel_name)}“` : '';
    return `<span class="zk">${esc(sparteName(state, u.vorschlag.sparte_id))} · ${esc(katName(u.vorschlag.kategorie_id))}${regel}</span>`;
  }
  return '<span class="muted">Kategorie wählen …</span>';
}

function aktionenZelle(u) {
  if (u.importstatus === 'verbucht') {
    return `<span class="bi-act"><button data-open="${u.id}">öffnen</button><button data-loesen="${u.id}">Zuordnung lösen</button></span>`;
  }
  if (u.importstatus === 'ignoriert') {
    return `<span class="bi-act"><button data-reopen="${u.id}">wieder öffnen</button></span>`;
  }
  const basis = u.vorschlag
    ? `<button data-uebernehmen="${u.id}">übernehmen</button><button data-form="${u.id}">ändern</button>`
    : `<button data-form="${u.id}">zuordnen</button>`;
  return `<span class="bi-act">${basis}<button data-kandidaten="${u.id}">bestehender Buchung zuordnen</button><button data-ignorieren="${u.id}">ignorieren</button></span>`;
}

function renderUmsaetzeKarte(state) {
  const liste = bankKonten();
  const optionen = liste.map(k => `<option value="${k.id}" ${String(k.id) === M.filterKontoId ? 'selected' : ''}>${esc(k.name)}</option>`).join('');
  const offenMitVorschlag = M.umsaetze.filter(u => u.importstatus === 'offen' && u.vorschlag).length;
  const rows = M.umsaetze.map(u => {
    const st = statusVon(u);
    return `<tr data-row="${u.id}"><td class="muted">${fmtDate(u.datum)}</td>` +
      `<td style="text-align:left;white-space:normal">${esc(u.text || u.gegenpartei || '(ohne Text)')}</td>` +
      `<td class="${u.betrag_cent < 0 ? 'aus' : 'ein'}" style="font-weight:500">${fmtEur(u.betrag_cent)}</td>` +
      `<td style="text-align:left"><span class="st ${st.css}">${esc(st.label)}</span></td>` +
      `<td style="text-align:left">${zuordnungZelle(u, state)}</td>` +
      `<td>${aktionenZelle(u)}</td></tr>`;
  }).join('');
  return `<div class="card"><div class="card-head"><h2>Umsätze</h2>` +
    `<span class="hint">gelernte Regeln verbuchen automatisch · Stichwort-Treffer sind nur Vorschläge · Unsicheres bleibt offen</span></div>` +
    `<div class="bi-upload-row"><label class="field">Konto<select id="bi-filter-konto">${optionen || '<option>kein Konto</option>'}</select></label>` +
    `<button class="btn small" id="bi-sammel" ${offenMitVorschlag ? '' : 'disabled'}>Alle Vorschläge übernehmen (${offenMitVorschlag})</button></div>` +
    (M.ladeFehler ? `<p class="empty bad">${esc(M.ladeFehler)}</p>` : '') +
    `<div class="table-wrap"><table class="tbl"><thead><tr><th>Datum</th><th style="text-align:left">Text der Bank</th><th>Betrag</th>` +
    `<th style="text-align:left">Status</th><th style="text-align:left">Zuordnung</th><th></th></tr></thead>` +
    `<tbody>${rows || '<tr><td colspan="6" class="muted">Keine Umsätze für dieses Konto.</td></tr>'}</tbody></table></div></div>`;
}

// ---------------------------------------------------------------------------
// Verbuchen-Formular (übernehmen / ändern / zuordnen)
// ---------------------------------------------------------------------------

function formularHtml(u, state, prefill) {
  // Vorbelegung: Regel-Vorschlag > Sparte des Bankkontos. Ist keines von beidem
  // vorhanden (Konto "gemischt genutzt", sparte_id = null), bleibt die Sparte
  // bewusst leer — nie eine geratene Sparte stillschweigend vorauswählen (QA3-02).
  const konto = M.konten.find(k => String(k.id) === String(u.bankkonto_id));
  const ersteSparte = prefill?.sparte_id ?? konto?.sparte_id ?? null;
  const sparteOptionen = (ersteSparte == null ? '<option value="" selected disabled>Sparte wählen …</option>' : '') +
    state.sparten.map(s => `<option value="${s.id}" ${ersteSparte === s.id ? 'selected' : ''}>${esc(s.name)}</option>`).join('');
  const kategorieOptionen = ersteSparte == null
    ? '<option value="" selected disabled>zuerst Sparte wählen</option>'
    : kategorienFuerSparte(ersteSparte).map(k => `<option value="${k.id}" ${prefill?.kategorie_id === k.id ? 'selected' : ''}>${esc(k.name)}</option>`).join('');
  const typ = prefill?.typ || (u.betrag_cent < 0 ? 'ausgabe' : 'einnahme');
  return `<form class="bi-form" id="bi-verbuchen-form" data-umsatz="${u.id}">` +
    `<p class="muted">${fmtDate(u.datum)} · ${esc(u.text || '(ohne Text)')} · <b class="${u.betrag_cent < 0 ? 'aus' : 'ein'}">${fmtEur(u.betrag_cent)}</b></p>` +
    `<label>Sparte<select name="sparte_id" required>${sparteOptionen}</select></label>` +
    `<label>Kategorie<select name="kategorie_id" required>${kategorieOptionen}</select></label>` +
    `<label>Typ<select name="typ"><option value="ausgabe" ${typ === 'ausgabe' ? 'selected' : ''}>Ausgabe</option>` +
    `<option value="einnahme" ${typ === 'einnahme' ? 'selected' : ''}>Einnahme</option>` +
    `<option value="umbuchung" ${typ === 'umbuchung' ? 'selected' : ''}>Umbuchung</option></select></label>` +
    `<label>Text (überschreibt den Banktext)<input name="text" maxlength="200" value="${esc(prefill?.text || '')}"></label>` +
    `<label style="flex-direction:row;align-items:center;gap:8px"><input type="checkbox" name="regel_merken" style="width:auto"> Zuordnung als Regel für die Zukunft merken</label>` +
    `<p class="err" id="bi-form-err"></p><button class="btn primary" type="submit">Speichern</button></form>`;
}

function oeffneFormular(u, state, prefill) {
  drill(u.vorschlag && prefill ? 'Vorschlag übernehmen' : 'Umsatz zuordnen', formularHtml(u, state, prefill));
  const form = document.querySelector('#bi-verbuchen-form');
  const sparteSel = form.querySelector('[name=sparte_id]');
  const katSel = form.querySelector('[name=kategorie_id]');
  sparteSel.onchange = () => {
    katSel.innerHTML = kategorienFuerSparte(sparteSel.value).map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join('');
  };
  form.onsubmit = async (e) => {
    e.preventDefault();
    const daten = new FormData(form);
    const body = {
      sparte_id: Number(daten.get('sparte_id')),
      kategorie_id: Number(daten.get('kategorie_id')),
      typ: daten.get('typ') || undefined,
      text: daten.get('text') || undefined,
      regel_merken: daten.get('regel_merken') === 'on',
    };
    try {
      await api(`/bankumsaetze/${u.id}/verbuchen`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      document.querySelector('#drill').close();
      toast('Umsatz verbucht.');
      await ladeUmsaetze();
      neuZeichnen(state);
    } catch (error) {
      form.querySelector('#bi-form-err').textContent = error.detail || error.message;
    }
  };
}

function oeffneKandidaten(u, state) {
  api(`/bankumsaetze/${u.id}/kandidaten`).then(({kandidaten}) => {
    const liste = kandidaten.length
      ? kandidaten.map(k => `<div class="k"><span>${fmtDate(k.datum)} · ${esc(k.text || '(ohne Text)')} · <b class="${k.betrag_cent < 0 ? 'aus' : 'ein'}">${fmtEur(k.betrag_cent)}</b><br><span class="muted">${k.abstand_tage} Tag(e) Abstand</span></span><button class="btn small" data-zuordnen-buchung="${k.buchung_id}">zuordnen</button></div>`).join('')
      : '<p class="muted">Keine passende bestehende Buchung gefunden.</p>';
    drill('Bestehender Buchung zuordnen', `<div class="bi-kandidaten">${liste}</div>`);
    document.querySelectorAll('[data-zuordnen-buchung]').forEach(btn => btn.onclick = async () => {
      try {
        await api(`/bankumsaetze/${u.id}/zuordnen`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({buchung_id: Number(btn.dataset.zuordnenBuchung)})});
        document.querySelector('#drill').close();
        toast('Umsatz zugeordnet.');
        await Promise.all([ladeUmsaetze(), ladeAbgleichVorschlaege()]);
        neuZeichnen(state);
      } catch (error) { toast(error.detail || error.message); }
    });
  }).catch(error => toast(error.detail || error.message));
}

function oeffneInfo(u) {
  drill('Umsatz', `<p>${fmtDate(u.datum)}</p><p>${esc(u.text || '(ohne Text)')}${u.gegenpartei ? ` · ${esc(u.gegenpartei)}` : ''}</p>` +
    `<p class="${u.betrag_cent < 0 ? 'aus' : 'ein'}" style="font-weight:600">${fmtEur(u.betrag_cent)}</p>` +
    `<p class="muted">Status: verbucht. Details zur Buchung siehe Buchungsliste.</p>`);
}

// ---------------------------------------------------------------------------
// Verdrahtung
// ---------------------------------------------------------------------------

function bindeUpload(state) {
  const konto = document.querySelector('#bi-upload-konto');
  if (konto) konto.onchange = () => { M.uploadKontoId = konto.value; };
  const drop = document.querySelector('#bi-drop');
  const datei = document.querySelector('#bi-file');
  if (!drop || !datei) return;
  drop.onclick = () => datei.click();
  drop.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); datei.click(); } };
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('drag'); };
  drop.ondragleave = () => drop.classList.remove('drag');
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove('drag'); if (e.dataTransfer.files[0]) hochladen(e.dataTransfer.files[0], state); };
  datei.onchange = () => { if (datei.files[0]) hochladen(datei.files[0], state); };
}

async function hochladen(file, state) {
  const form = new FormData();
  form.set('bankkonto_id', M.uploadKontoId);
  form.set('datei', file);
  try {
    M.bericht = await api('/import/csv', {method: 'POST', body: form});
    M.filterKontoId = M.uploadKontoId;
    toast(`Import fertig: ${M.bericht.neu} neu, ${M.bericht.dubletten} Dubletten.`);
    await Promise.all([ladeUmsaetze(), ladeAbgleichVorschlaege()]);
    neuZeichnen(state);
  } catch (error) {
    toast(error.detail || error.message);
  }
}

function bindeMerge(state) {
  document.querySelectorAll('[data-merge-go]').forEach(btn => btn.onclick = async () => {
    const row = btn.closest('.bi-merge-row');
    const buchungId = Number(row.querySelector('.bi-merge-select').value);
    if (!buchungId) return;
    try {
      await api(`/bankumsaetze/${btn.dataset.mergeGo}/zuordnen`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({buchung_id: buchungId})});
      toast('Zusammengeführt.');
      await Promise.all([ladeUmsaetze(), ladeAbgleichVorschlaege()]);
      neuZeichnen(state);
    } catch (error) { toast(error.detail || error.message); }
  });
  document.querySelectorAll('[data-merge-skip]').forEach(btn => btn.onclick = () => {
    M.ausgeblendet.add(Number(btn.dataset.mergeSkip));
    M.abgleichVorschlaege = M.abgleichVorschlaege.filter(v => v.umsatz.bankumsatz_id !== Number(btn.dataset.mergeSkip));
    neuZeichnen(state);
  });
}

function bindeUmsaetze(state) {
  const filter = document.querySelector('#bi-filter-konto');
  if (filter) filter.onchange = async () => { M.filterKontoId = filter.value; await Promise.all([ladeUmsaetze(), ladeAbgleichVorschlaege()]); neuZeichnen(state); };
  const sammel = document.querySelector('#bi-sammel');
  if (sammel) sammel.onclick = async () => {
    const ids = M.umsaetze.filter(u => u.importstatus === 'offen' && u.vorschlag).map(u => u.id);
    try {
      const r = await api('/bankumsaetze/vorschlaege-uebernehmen', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({umsatz_ids: ids})});
      toast(`${r.verbucht} übernommen, ${r.uebersprungen} übersprungen.`);
      await ladeUmsaetze();
      neuZeichnen(state);
    } catch (error) { toast(error.detail || error.message); }
  };
  document.querySelectorAll('[data-uebernehmen]').forEach(btn => btn.onclick = () => {
    const u = M.umsaetze.find(x => x.id === Number(btn.dataset.uebernehmen));
    oeffneFormular(u, state, u.vorschlag);
  });
  document.querySelectorAll('[data-form]').forEach(btn => btn.onclick = () => {
    const u = M.umsaetze.find(x => x.id === Number(btn.dataset.form));
    oeffneFormular(u, state, null);
  });
  document.querySelectorAll('[data-kandidaten]').forEach(btn => btn.onclick = () => {
    const u = M.umsaetze.find(x => x.id === Number(btn.dataset.kandidaten));
    oeffneKandidaten(u, state);
  });
  document.querySelectorAll('[data-ignorieren]').forEach(btn => btn.onclick = async () => {
    try {
      await api(`/bankumsaetze/${btn.dataset.ignorieren}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({importstatus: 'ignoriert'})});
      toast('Umsatz ignoriert.');
      await ladeUmsaetze();
      neuZeichnen(state);
    } catch (error) { toast(error.detail || error.message); }
  });
  document.querySelectorAll('[data-reopen]').forEach(btn => btn.onclick = async () => {
    try {
      await api(`/bankumsaetze/${btn.dataset.reopen}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({importstatus: 'offen'})});
      toast('Umsatz wieder offen.');
      await Promise.all([ladeUmsaetze(), ladeAbgleichVorschlaege()]);
      neuZeichnen(state);
    } catch (error) { toast(error.detail || error.message); }
  });
  document.querySelectorAll('[data-loesen]').forEach(btn => btn.onclick = async () => {
    try {
      await api(`/bankumsaetze/${btn.dataset.loesen}/zuordnung-loesen`, {method: 'POST'});
      toast('Zuordnung gelöst.');
      await Promise.all([ladeUmsaetze(), ladeAbgleichVorschlaege()]);
      neuZeichnen(state);
    } catch (error) { toast(error.detail || error.message); }
  });
  document.querySelectorAll('[data-open]').forEach(btn => btn.onclick = () => {
    oeffneInfo(M.umsaetze.find(x => x.id === Number(btn.dataset.open)));
  });
}

function neuZeichnen(state) {
  const root = document.querySelector('#page');
  if (!root) return;
  root.innerHTML = renderKontenKarte() + renderUploadKarte() + renderUmsaetzeKarte(state);
  bindeUpload(state);
  bindeMerge(state);
  bindeUmsaetze(state);
}

export async function render(root, state) {
  ladeCss();
  root.innerHTML = '<section class="card placeholder"><p>Lade Bankimport …</p></section>';
  try {
    await ladeAlles();
    M.ladeFehler = null;
  } catch (error) {
    M.ladeFehler = error.detail || error.message;
    toast(M.ladeFehler);
  }
  neuZeichnen(state);
}
