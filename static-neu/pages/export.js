// P60 – Export-Oberfläche für das Steuerpaket.
// Ruft ausschließlich die in P16/app/routers/export.py definierten Endpunkte auf:
// GET /api/export/profil, PUT /api/export/profil/{id}, POST .../uebernehmen-vom-vorjahr,
// POST /api/export/vorschau, POST /api/export/paket, GET /api/export/xlsx, GET /export/bericht.
// Für die Buchungsliste (inkl. bereits ausgeschlossener Zeilen, die die Vorschau nicht mehr
// liefert) wird zusätzlich GET /api/buchungen (app/routers/buchungen.py, bereits vorhanden)
// nur lesend verwendet – siehe Bericht, Abschnitt "Wunsch an das Gerüst".
import {api} from '../api.js';
import {esc, fmtEur, fmtDate} from '../format.js';
import {toast, drill} from '../ui.js';

let cssGeladen = false;
function ladeCss() {
  if (cssGeladen) return;
  cssGeladen = true;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = './pages/export.css';
  document.head.appendChild(link);
}

function bereichId(state) {
  return Number(state.bereichId || localStorage.getItem('neu-bereich') || 1);
}

function aktuellesJahr(state) {
  const sel = document.querySelector('#year-select');
  const val = sel && sel.value;
  if (val) return Number(val);
  if (state.jahre && state.jahre.length) return Number(state.jahre[0]);
  return new Date().getFullYear();
}

function aktuelleSparte(state) {
  return state.sparteId ? Number(state.sparteId) : null;
}

function sparteName(state, sparteId) {
  if (!sparteId) return 'Alle Sparten des Bereichs';
  const s = (state.sparten || []).find(s => Number(s.id) === Number(sparteId));
  return s ? s.name : `Sparte ${sparteId}`;
}

export async function render(root, state) {
  ladeCss();
  const ctx = {
    root, state,
    bereich: bereichId(state),
    jahr: aktuellesJahr(state),
    sparteId: aktuelleSparte(state),
    profil: null,
    zeilen: [],
    kategorien: [],
    unbeschraenkteListeGeladen: false,
    katAus: new Set(),
    buchAus: new Set(),
    q: '',
    nurSuchtreffer: false,
    preview: null,
    ladeFehler: null,
  };
  root.innerHTML = '<section class="card"><p class="muted">Export wird geladen …</p></section>';
  await ladeProfil(ctx);
  bindeGlobaleFilter(ctx);
}

// Sparte (Sidebar/Kopf-Select) und Jahr (#year-select) sind Teile des zentralen
// Zustands, werden aber laut Gerüst (app.js) nicht global mit einem Seiten-Rerender
// verdrahtet – jede Seite muss selbst reagieren. Siehe "Wunsch an das Gerüst".
function bindeGlobaleFilter(ctx) {
  const jahrSel = document.querySelector('#year-select');
  if (jahrSel) jahrSel.addEventListener('change', () => render(ctx.root, ctx.state));
  const sparteSel = document.querySelector('#sparte-select');
  if (sparteSel) sparteSel.addEventListener('change', () => render(ctx.root, ctx.state));
  document.querySelectorAll('#sidebar [data-sparte]').forEach(btn => {
    btn.addEventListener('click', () => render(ctx.root, ctx.state));
  });
}

async function ladeProfil(ctx) {
  try {
    const params = {jahr: ctx.jahr};
    if (ctx.sparteId) params.sparte_id = ctx.sparteId;
    ctx.profil = await api('/export/profil', {params, bereichId: ctx.bereich});
  } catch (error) {
    ctx.root.innerHTML = `<section class="card"><p class="muted">Export-Profil konnte nicht geladen werden: ${esc(error.detail || error.message)}</p></section>`;
    toast(error.detail || error.message);
    return;
  }
  ctx.katAus = new Set(ctx.profil.kategorie_ids);
  ctx.buchAus = new Set(ctx.profil.buchung_ids);
  zeichne(ctx);
  await ladeVorschau(ctx);
}

async function ladeVorschau(ctx) {
  try {
    ctx.preview = await api('/export/vorschau', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        profil_id: ctx.profil.id,
        revision: null,
        q: ctx.q || null,
        nur_suchtreffer: ctx.nurSuchtreffer,
      }),
      bereichId: ctx.bereich,
    });
  } catch (error) {
    ctx.preview = null;
    toast(error.detail || error.message);
  }
  zeichneVorschau(ctx);
}

function zeichne(ctx) {
  const {state, jahr, sparteId, profil} = ctx;
  ctx.root.innerHTML = `
    <section class="card">
      <div class="card-head"><h2>Steuerprofil „${esc(profil.name)}“</h2><span class="hint">${esc(sparteName(state, sparteId))} · ${jahr}</span></div>
      <p class="muted">Sparte und Jahr werden oben in der Kopfzeile gewählt; diese Seite lädt automatisch das passende Profil neu.</p>
      <p class="ex-meta"><span>Ausgeschlossene Kategorien: <b>${ctx.katAus.size}</b></span><span>Ausgeschlossene Buchungen: <b>${ctx.buchAus.size}</b></span></p>
      <div class="ex-actions">
        <button class="btn" id="ex-edit" type="button">Ausschlüsse bearbeiten</button>
        <button class="btn" id="ex-vorjahr" type="button">Vom Vorjahr übernehmen</button>
      </div>
      <div class="ex-search">
        <label class="field">Suche<input id="ex-q" value="${esc(ctx.q)}" placeholder="Text oder Kategorie"></label>
        <label class="ex-switch"><input type="checkbox" id="ex-nur-treffer" ${ctx.nurSuchtreffer ? 'checked' : ''}> Suche wirkt auf den Export</label>
        <p class="muted ex-hint">Ohne Schalter grenzt die Suche nur die angezeigte Vorschau ein; der Export selbst bleibt davon unberührt.</p>
      </div>
    </section>
    <section class="card" id="ex-preview-card">
      <div class="card-head"><h2>Vorschau</h2><span class="hint" id="ex-preview-hint"></span></div>
      <div id="ex-preview-body"><p class="muted">Vorschau wird geladen …</p></div>
    </section>
    <section class="card">
      <div class="card-head"><h2>Steuerpaket</h2></div>
      <p class="ex-desc">Das ZIP enthält eine Excel-Arbeitsmappe (Blätter „Buchungen“, „Monatssummen“, „Kategorien“) mit genau den Buchungen aus der Vorschau, alle dazu vorhandenen Belegdateien im Ordner „Belege/“ sowie eine Datei „INHALT.txt“ mit Erstellzeitpunkt, Bereich, Sparte, Jahr, Profilname, Revision und den Summen.</p>
      <button class="btn primary" id="ex-paket" type="button">Steuerpaket erzeugen (ZIP)</button>
    </section>
    <section class="card">
      <div class="card-head"><h2>Weitere Exporte</h2><span class="hint">unverändert, für Ablage/Kontrolle</span></div>
      <p class="muted">Nutzt dieselbe Auswahl wie das Steuerpaket, aber als reiner Rohexport ohne Belege.</p>
      <div class="ex-links">
        <a class="btn" href="/api/export/xlsx?bereich_id=${ctx.bereich}&profil_id=${profil.id}">Excel-Export (.xlsx)</a>
        <a class="btn" href="/export/bericht?bereich_id=${ctx.bereich}&profil_id=${profil.id}&jahr=${jahr}" target="_blank" rel="noopener">Jahresbericht (Druckansicht)</a>
      </div>
    </section>`;
  document.querySelector('#ex-edit').onclick = () => oeffneAusschlussDialog(ctx);
  document.querySelector('#ex-vorjahr').onclick = () => vomVorjahrUebernehmen(ctx);
  document.querySelector('#ex-paket').onclick = () => paketErzeugen(ctx);
  let suchTimer;
  const qInput = document.querySelector('#ex-q');
  qInput.oninput = () => {
    clearTimeout(suchTimer);
    suchTimer = setTimeout(() => { ctx.q = qInput.value.trim(); ladeVorschau(ctx); }, 350);
  };
  document.querySelector('#ex-nur-treffer').onchange = e => {
    ctx.nurSuchtreffer = e.target.checked;
    ladeVorschau(ctx);
  };
}

function zeichneVorschau(ctx) {
  const hint = document.querySelector('#ex-preview-hint');
  const body = document.querySelector('#ex-preview-body');
  if (!body) return;
  if (!ctx.preview) {
    if (hint) hint.textContent = '';
    body.innerHTML = '<p class="muted">Vorschau derzeit nicht verfügbar.</p>';
    return;
  }
  const {summen, ausgeschlossen, belege_fehlend: fehlend} = ctx.preview;
  if (hint) hint.textContent = ctx.nurSuchtreffer && ctx.q ? `nur Suchtreffer „${ctx.q}“` : '';
  const missing = fehlend.length
    ? `<ul class="ex-missing">${fehlend.map(f => `<li>Buchung #${f.buchung_id}: ${esc(f.dateiname)} fehlt</li>`).join('')}</ul>`
    : '<p class="muted">Keine fehlenden Belege.</p>';
  body.innerHTML = `
    <div class="grid g3">
      <div class="kpi"><span class="lbl">Buchungen</span><span class="val">${summen.anzahl}</span></div>
      <div class="kpi"><span class="lbl">Einnahmen</span><span class="val ein">${fmtEur(summen.einnahmen_cent)}</span></div>
      <div class="kpi"><span class="lbl">Ausgaben</span><span class="val aus">${fmtEur(summen.ausgaben_cent)}</span></div>
    </div>
    <p class="ex-meta"><span>Saldo: <b>${fmtEur(summen.einnahmen_cent - summen.ausgaben_cent)}</b></span><span>Ausgeschlossen: ${ausgeschlossen.kategorien} Kategorien, ${ausgeschlossen.buchungen} Buchungen</span></p>
    <h3 style="margin-top:14px">Fehlende Belege</h3>
    ${missing}`;
}

async function vomVorjahrUebernehmen(ctx) {
  try {
    ctx.profil = await api(`/export/profil/${ctx.profil.id}/uebernehmen-vom-vorjahr`, {
      method: 'POST', bereichId: ctx.bereich,
    });
    ctx.katAus = new Set(ctx.profil.kategorie_ids);
    ctx.buchAus = new Set(ctx.profil.buchung_ids);
    zeichne(ctx);
    await ladeVorschau(ctx);
    toast('Ausschlüsse vom Vorjahr übernommen (falls ein Vorjahresprofil bestand).');
  } catch (error) {
    toast(error.detail || error.message);
  }
}

// Lädt alle Buchungen des Zeitraums über /api/buchungen (lesend, bereits vorhandener
// Endpunkt aus app/routers/buchungen.py) unabhängig von den aktuellen Ausschlüssen,
// damit im Dialog auch bereits ausgeschlossene Kategorien/Buchungen wieder
// eingeschlossen werden können – die Export-Vorschau selbst liefert nur die
// (noch) nicht ausgeschlossenen Zeilen.
async function ladeBuchungszeilen(ctx) {
  if (ctx.unbeschraenkteListeGeladen) return;
  const zeilen = [];
  let cursor = null;
  const params = {jahr: ctx.jahr, limit: 1000};
  if (ctx.sparteId) params.sparte_id = ctx.sparteId;
  const seite = await api('/buchungen', {params, bereichId: ctx.bereich});
  for (const b of seite.buchungen) {
    if (b.typ !== 'einnahme' && b.typ !== 'ausgabe') continue;
    for (const z of b.zeilen) {
      if (z.neutral) continue;
      zeilen.push({
        buchung_id: b.id, datum: b.datum, text: b.text || '',
        kategorie_id: z.kategorie_id, kategorie: z.kategorie_name,
        betrag_cent: z.betrag_cent,
      });
    }
  }
  cursor = seite.naechster_cursor;
  ctx.zeilenAbgeschnitten = Boolean(cursor);
  zeilen.sort((a, b) => a.datum < b.datum ? 1 : a.datum > b.datum ? -1 : 0);
  ctx.zeilen = zeilen;
  const kats = new Map();
  for (const z of zeilen) if (z.kategorie_id != null) kats.set(z.kategorie_id, z.kategorie);
  ctx.kategorien = [...kats.entries()].map(([id, name]) => ({id, name})).sort((a, b) => a.name.localeCompare(b.name, 'de'));
  ctx.unbeschraenkteListeGeladen = true;
}

async function oeffneAusschlussDialog(ctx) {
  try {
    await ladeBuchungszeilen(ctx);
  } catch (error) {
    toast(error.detail || error.message);
    return;
  }
  const pendingKat = new Set(ctx.katAus);
  const pendingBuch = new Set(ctx.buchAus);
  let filterQ = '';

  const dialog = document.querySelector('#drill');
  dialog.classList.add('ex-drill');
  // Räumt die Größenklasse auch auf, wenn der Dialog nicht über den eigenen
  // Abbrechen/Speichern-Button, sondern per Esc oder Backdrop geschlossen wird.
  dialog.addEventListener('close', () => dialog.classList.remove('ex-drill'), {once: true});
  drill('Ausschlüsse bearbeiten', inhaltHtml());
  const content = document.querySelector('#drill-content');
  bindeDialog();

  function sichtbareZeilen() {
    if (!filterQ) return ctx.zeilen;
    const nadel = filterQ.toLowerCase();
    return ctx.zeilen.filter(z => z.text.toLowerCase().includes(nadel) || (z.kategorie || '').toLowerCase().includes(nadel));
  }

  function inhaltHtml() {
    const liste = sichtbareZeilen();
    const kats = ctx.kategorien.map(k => `<button type="button" class="${pendingKat.has(k.id) ? 'off' : ''}" data-kat="${k.id}">${esc(k.name)}</button>`).join('') || '<span class="muted">Keine Kategorien im Zeitraum.</span>';
    const rows = liste.length ? liste.map(z => {
      const katOff = pendingKat.has(z.kategorie_id);
      const buchOff = pendingBuch.has(z.buchung_id);
      const off = katOff || buchOff;
      return `<tr class="ex-row ${off ? 'ex-row-off' : ''}"><td><input type="checkbox" data-buchung="${z.buchung_id}" ${buchOff ? '' : 'checked'} ${katOff ? 'disabled title="Kategorie ganz ausgeschlossen"' : ''}></td><td class="muted">${fmtDate(z.datum)}</td><td>${esc(z.text || '–')}</td><td>${esc(z.kategorie || '–')}</td><td>${fmtEur(z.betrag_cent)}</td></tr>`;
    }).join('') : `<tr><td colspan="5" class="ex-empty">Keine Buchungen${ctx.zeilenAbgeschnitten ? ' (Liste ist auf 1000 Zeilen begrenzt)' : ''}.</td></tr>`;
    return `<div class="ex-dialog">
      <p class="muted">Kategorie anklicken schließt sie komplett aus (Zeilen darin lassen sich dann nicht mehr einzeln anhaken). Änderungen werden erst mit „Speichern“ übernommen.</p>
      <label class="field">In dieser Liste suchen<input id="ex-dlg-q" value="${esc(filterQ)}" placeholder="Text oder Kategorie"></label>
      <div class="ex-kats" id="ex-dlg-kats">${kats}</div>
      <div class="table-wrap"><table class="tbl"><thead><tr><th></th><th>Datum</th><th>Text</th><th>Kategorie</th><th>Betrag</th></tr></thead><tbody id="ex-dlg-body">${rows}</tbody></table></div>
      ${ctx.zeilenAbgeschnitten ? '<p class="muted">Es werden nur die ersten 1000 Buchungen des Zeitraums angezeigt.</p>' : ''}
      <div class="ex-savebar">
        <span class="muted">${pendingKat.size} Kategorien, ${pendingBuch.size} Buchungen ausgeschlossen</span>
        <button class="btn" type="button" id="ex-dlg-cancel">Abbrechen</button>
        <button class="btn primary" type="button" id="ex-dlg-save">Änderungen speichern</button>
      </div>
    </div>`;
  }

  function neuZeichnen() {
    content.innerHTML = inhaltHtml();
    bindeDialog();
  }

  function bindeDialog() {
    const qInput = document.querySelector('#ex-dlg-q');
    qInput.oninput = () => { filterQ = qInput.value.trim(); neuZeichnen(); document.querySelector('#ex-dlg-q').focus(); document.querySelector('#ex-dlg-q').setSelectionRange(filterQ.length, filterQ.length); };
    document.querySelectorAll('#ex-dlg-kats [data-kat]').forEach(btn => {
      btn.onclick = () => {
        const id = Number(btn.dataset.kat);
        if (pendingKat.has(id)) pendingKat.delete(id); else pendingKat.add(id);
        neuZeichnen();
      };
    });
    document.querySelectorAll('#ex-dlg-body [data-buchung]').forEach(cb => {
      cb.onchange = () => {
        const id = Number(cb.dataset.buchung);
        if (cb.checked) pendingBuch.delete(id); else pendingBuch.add(id);
        neuZeichnen();
      };
    });
    document.querySelector('#ex-dlg-cancel').onclick = () => { dialog.classList.remove('ex-drill'); dialog.close(); };
    document.querySelector('#ex-dlg-save').onclick = async () => {
      try {
        ctx.profil = await api(`/export/profil/${ctx.profil.id}`, {
          method: 'PUT', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({kategorie_ids: [...pendingKat], buchung_ids: [...pendingBuch]}),
          bereichId: ctx.bereich,
        });
        ctx.katAus = new Set(ctx.profil.kategorie_ids);
        ctx.buchAus = new Set(ctx.profil.buchung_ids);
        dialog.classList.remove('ex-drill');
        dialog.close();
        zeichne(ctx);
        await ladeVorschau(ctx);
        toast('Ausschlüsse gespeichert.');
      } catch (error) {
        toast(error.detail || error.message);
      }
    };
  }
}

function oeffneBelegeFehlenDialog(ctx, auswahl) {
  const dialog = document.querySelector('#drill');
  const fehlend = ctx.preview ? ctx.preview.belege_fehlend : [];
  const liste = fehlend.map(f => `<li>Buchung #${f.buchung_id}: ${esc(f.dateiname)}</li>`).join('');
  drill('Belege fehlen', `<p>Zu folgenden Buchungen fehlt mindestens ein Beleg:</p><ul class="ex-missing">${liste}</ul><p class="muted">Trotzdem exportieren erstellt das Steuerpaket ohne diese Belege; „INHALT.txt“ listet sie weiterhin auf.</p><div class="ex-savebar"><button class="btn" type="button" id="ex-missing-cancel">Abbrechen</button><button class="btn primary" type="button" id="ex-missing-go">Trotzdem exportieren</button></div>`);
  document.querySelector('#ex-missing-cancel').onclick = () => dialog.close();
  document.querySelector('#ex-missing-go').onclick = async () => {
    dialog.close();
    await paketAnfordern(ctx, {...auswahl, trotz_fehlender_belege: true});
  };
}

async function paketErzeugen(ctx) {
  if (!ctx.preview) { toast('Vorschau ist noch nicht geladen.'); return; }
  const auswahl = {
    profil_id: ctx.profil.id,
    revision: ctx.preview.revision,
    q: ctx.q || null,
    nur_suchtreffer: ctx.nurSuchtreffer,
    trotz_fehlender_belege: false,
  };
  await paketAnfordern(ctx, auswahl);
}

// Der ZIP-Endpunkt ist bewusst ein POST mit Revision/Fehler-Vertrag (409 bei
// veralteter Revision, 422 bei fehlenden Belegen, siehe P16/P60-Karte) und kann
// deshalb – anders als die reinen GET-Rohexporte weiter unten – nicht als
// einfacher <a href>-Link umgesetzt werden.
async function paketAnfordern(ctx, auswahl) {
  const button = document.querySelector('#ex-paket');
  if (button) { button.disabled = true; button.textContent = 'Erzeuge Paket …'; }
  try {
    const response = await fetch(`/api/export/paket?bereich_id=${ctx.bereich}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Client-Request-Id': crypto.randomUUID()},
      credentials: 'same-origin',
      body: JSON.stringify(auswahl),
    });
    if (response.status === 401) { location.assign('/login.html'); return; }
    if (response.status === 409) {
      toast('Die Daten haben sich geändert – Vorschau wird neu geladen.');
      await ladeVorschau(ctx);
      return;
    }
    if (response.status === 422) {
      await ladeVorschau(ctx);
      oeffneBelegeFehlenDialog(ctx, auswahl);
      return;
    }
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try { detail = (await response.json()).detail || detail; } catch { /* kein JSON-Body */ }
      toast(detail);
      return;
    }
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = /filename="?([^"]+)"?/.exec(disposition);
    const dateiname = match ? match[1] : 'export-paket.zip';
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = dateiname;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    toast('Steuerpaket heruntergeladen.');
  } catch (error) {
    toast(error.message);
  } finally {
    if (button) { button.disabled = false; button.textContent = 'Steuerpaket erzeugen (ZIP)'; }
  }
}
