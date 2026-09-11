// P50: Buchungsliste mit Suche/Filtern, Bearbeiten-Dialog mit Zeilen und Versionssperre.
// P50b: Historie (GET /api/buchungen/{id}/verlauf) ist seit Migration 016 im Backend vorhanden.
// P51: Stornieren/Entstornieren und Erstattungen (Migration 017).
import {api} from '../api.js';
import {esc, fmtEur, fmtDate, parseBetrag} from '../format.js';
import {toast, drill} from '../ui.js';

const CSS_ID = 'buchungen-css';
const LIMIT = 100;

function ensureCss() {
  if (document.getElementById(CSS_ID)) return;
  const link = document.createElement('link');
  link.id = CSS_ID;
  link.rel = 'stylesheet';
  link.href = './pages/buchungen.css';
  document.head.appendChild(link);
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

export function render(root, state) {
  ensureCss();

  // Eigener Zustand je Seitenaufruf - wird bei jeder Navigation zur Seite frisch gebildet,
  // damit keine veralteten Filter/Cursor aus einem vorherigen Besuch überleben.
  const local = {
    q: '', gruppeId: '', von: '', bis: '',
    cursor: null, rows: [], summen: null, kategorien: {},
  };

  root.innerHTML = `
    <div class="card">
      <div class="bfilters">
        <label class="field">Suche<input id="bu-q" placeholder="Text, Notiz oder Kategorie" autocomplete="off"></label>
        <label class="field">Von<input id="bu-von" type="date"></label>
        <label class="field">Bis<input id="bu-bis" type="date"></label>
        <label class="field">Gruppe<select id="bu-gruppe"><option value="">Alle</option></select></label>
        <button class="btn" id="bu-reset" type="button">Filter zurücksetzen</button>
      </div>
      <div class="bu-active" id="bu-active" aria-live="polite"></div>
      <p class="muted" id="bu-count">Lädt …</p>
    </div>
    <div class="card">
      <div class="tscroll"><table class="tbl btable" id="bu-table"></table></div>
      <div class="bu-more-wrap"><button class="btn" id="bu-more" hidden>Weitere laden</button></div>
    </div>`;

  const elQ = root.querySelector('#bu-q');
  const elVon = root.querySelector('#bu-von');
  const elBis = root.querySelector('#bu-bis');
  const elGruppe = root.querySelector('#bu-gruppe');
  const elActive = root.querySelector('#bu-active');
  const elCount = root.querySelector('#bu-count');
  const elTable = root.querySelector('#bu-table');
  const elMore = root.querySelector('#bu-more');
  const elReset = root.querySelector('#bu-reset');

  const filterRichtung = document.querySelector('#filter-richtung');
  const filterZahlungsart = document.querySelector('#filter-zahlungsart');
  const filterKategorie = document.querySelector('#filter-kategorie');

  elGruppe.innerHTML = '<option value="">Alle</option>' +
    (state.gruppen || []).map(g => `<option value="${g.id}">${esc(g.name)}</option>`).join('');

  function currentFilter() {
    const f = {bereich_id: state.bereichId};
    if (state.sparteId) f.sparte_id = state.sparteId;
    if (local.gruppeId) f.auswertungsgruppe_id = local.gruppeId;
    if (local.von) f.von = local.von;
    if (local.bis) f.bis = local.bis;
    if (!local.von && !local.bis && state.year) f.jahr = state.year;
    if (filterRichtung && filterRichtung.value) f.richtung = filterRichtung.value;
    if (filterZahlungsart && filterZahlungsart.value) f.zahlungsart = filterZahlungsart.value;
    if (filterKategorie && filterKategorie.value) f.kategorie_id = filterKategorie.value;
    if (local.q) f.q = local.q;
    return f;
  }

  // P30b: #filter-kategorie wird zentral in app.js befüllt (abhängig von state.sparteId)
  // und ein Wechsel löst dort bereits ein volles Re-Render dieser Seite aus - der frühere
  // lokale Ersatz (eigenes Laden + eigener change-Listener) ist entfallen, sonst würde
  // die Seite die Optionen doppelt laden und der zentrale Filterwechsel griffe nicht.

  function zeichneTabelle() {
    const rows = local.rows;
    const kopf = '<thead><tr><th>Datum</th><th>Text</th><th>Kategorie</th><th>Zahlung</th>'
      + '<th>Beleg</th><th>Betrag</th><th></th></tr></thead>';
    const body = rows.map(b => {
      const sign = b.typ === 'einnahme' ? '+' : b.typ === 'ausgabe' ? '−' : '⇄';
      const cls = b.typ === 'einnahme' ? 'ein' : b.typ === 'ausgabe' ? 'aus' : 'muted';
      const zahlung = {bank: 'Bank', bar: 'Bar', karte: 'Karte', sonstiges: 'Sonstiges'}[b.zahlungsart] || b.zahlungsart;
      const belegAn = (b.belege || []).length > 0;
      const kats = b.zeilen.map(z => esc(z.kategorie_name)).join(', ');
      const storniert = !!b.storniert_am;
      const bearbeiten = b.typ === 'umbuchung'
        ? ''
        : `<button class="lnk" data-edit="${b.id}">bearbeiten</button>`;
      // P51: Stornieren/Entstornieren als Zeilenaktion; Umbuchungen bleiben unveraendert
      // (nur über DELETE entfernbar, siehe Backend-Karte P51 Regeln).
      const storno = b.typ === 'umbuchung'
        ? ''
        : `<button class="lnk" data-storno="${b.id}">${storniert ? 'Storno zurücknehmen' : 'stornieren'}</button>`;
      return `<tr class="${storniert ? 'storniert' : ''}"><td class="muted">${fmtDate(b.datum)}</td><td class="t">${esc(b.text || '')}${storniert ? ' <span class="pill">storniert</span>' : ''}</td>`
        + `<td>${kats}</td><td class="muted">${esc(zahlung)}</td>`
        + `<td class="belegic ${belegAn ? 'has' : ''}" title="${belegAn ? 'Beleg vorhanden' : 'kein Beleg'}">${belegAn ? '▣' : '·'}</td>`
        + `<td class="${cls}">${sign} ${fmtEur(b.betrag_cent)}</td><td>${bearbeiten} ${storno}</td></tr>`;
    }).join('');
    elTable.innerHTML = kopf + '<tbody>' + (body || '<tr><td colspan="7" class="muted">Keine Buchungen gefunden.</td></tr>') + '</tbody>';
    elTable.querySelectorAll('[data-edit]').forEach(btn => {
      btn.onclick = () => openEditDialog(Number(btn.dataset.edit));
    });
    elTable.querySelectorAll('[data-storno]').forEach(btn => {
      btn.onclick = () => stornoAktion(local.rows.find(r => r.id === Number(btn.dataset.storno)));
    });
  }

  // P51b: Bestätigung und Grund im App-Dialog (#drill) statt nativer confirm/prompt-Popups.
  function stornoAktion(b) {
    if (!b) return;
    const zuruecknehmen = !!b.storniert_am;
    const titel = zuruecknehmen ? 'Storno zurücknehmen' : 'Buchung stornieren';
    const frage = zuruecknehmen ? 'Storno dieser Buchung wirklich zurücknehmen?' : 'Buchung wirklich stornieren?';
    drill(titel, `
      <p>${frage}</p>
      <p class="muted">${fmtDate(b.datum)} · ${esc(b.text || '')} · ${fmtEur(b.betrag_cent)}</p>
      <label>Grund (optional)<br><input id="storno-grund" type="text" maxlength="200" style="width:100%"></label>
      <div class="row" style="margin-top:12px;display:flex;gap:8px;justify-content:flex-end">
        <button class="lnk" id="storno-abbrechen" type="button">Abbrechen</button>
        <button class="primary" id="storno-ok" type="button">${titel}</button>
      </div>`);
    const dialog = document.querySelector('#drill');
    const grundFeld = dialog.querySelector('#storno-grund');
    grundFeld.focus();
    dialog.querySelector('#storno-abbrechen').onclick = () => dialog.close();
    const ausfuehren = async () => {
      const grund = grundFeld.value.trim();
      const okBtn = dialog.querySelector('#storno-ok');
      okBtn.disabled = true;
      try {
        await api(`/buchungen/${b.id}/${zuruecknehmen ? 'entstornieren' : 'stornieren'}`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({grund: grund || null}),
          bereichId: state.bereichId,
        });
        dialog.close();
        toast(zuruecknehmen ? 'Storno zurückgenommen.' : 'Buchung storniert.');
        ladeSeite(true);
      } catch (error) {
        okBtn.disabled = false;
        toast(error.detail || error.message || 'Aktion fehlgeschlagen.');
      }
    };
    dialog.querySelector('#storno-ok').onclick = ausfuehren;
    grundFeld.onkeydown = (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); ausfuehren(); } };
  }

  function zeichneAktiveFilter() {
    const chips = [];
    if (local.q) chips.push(['Suche: ' + local.q, () => { local.q = ''; elQ.value = ''; ladeSeite(true); }]);
    if (local.von) chips.push(['Von ' + fmtDate(local.von), () => { local.von = ''; elVon.value = ''; ladeSeite(true); }]);
    if (local.bis) chips.push(['Bis ' + fmtDate(local.bis), () => { local.bis = ''; elBis.value = ''; ladeSeite(true); }]);
    if (local.gruppeId) {
      const g = (state.gruppen || []).find(x => String(x.id) === String(local.gruppeId));
      chips.push(['Gruppe: ' + (g ? g.name : local.gruppeId), () => { local.gruppeId = ''; elGruppe.value = ''; ladeSeite(true); }]);
    }
    if (filterRichtung && filterRichtung.value) {
      const label = filterRichtung.value === 'einnahme' ? 'Einnahmen' : 'Ausgaben';
      chips.push(['Richtung: ' + label, () => { filterRichtung.value = ''; ladeSeite(true); }]);
    }
    if (filterZahlungsart && filterZahlungsart.value) {
      chips.push(['Zahlungsart: ' + filterZahlungsart.value, () => { filterZahlungsart.value = ''; ladeSeite(true); }]);
    }
    if (filterKategorie && filterKategorie.value) {
      const opt = filterKategorie.selectedOptions[0];
      chips.push(['Kategorie: ' + (opt ? opt.textContent : filterKategorie.value), () => { filterKategorie.value = ''; ladeSeite(true); }]);
    }
    elActive.innerHTML = chips.length
      ? chips.map((c, i) => `<button class="pill filter-chip" data-chip="${i}">${esc(c[0])} ×</button>`).join('')
      : '';
    elActive.querySelectorAll('[data-chip]').forEach(btn => {
      btn.onclick = () => chips[Number(btn.dataset.chip)][1]();
    });
  }

  async function ladeSeite(reset) {
    if (reset) { local.cursor = null; local.rows = []; }
    elCount.textContent = 'Lädt …';
    try {
      const filter = currentFilter();
      if (local.cursor) filter.cursor = local.cursor;
      filter.limit = LIMIT;
      const antwort = await api('/buchungen', {params: filter, bereichId: state.bereichId});
      local.rows = reset ? antwort.buchungen : local.rows.concat(antwort.buchungen);
      local.summen = antwort.summen;
      local.cursor = antwort.naechster_cursor;
      elMore.hidden = !local.cursor;
      const s = local.summen;
      elCount.textContent = `${s.anzahl} Buchungen · Einnahmen ${fmtEur(s.einnahmen_cent)} · `
        + `Ausgaben ${fmtEur(s.ausgaben_cent)} · Saldo ${fmtEur(s.einnahmen_cent - s.ausgaben_cent)}`;
      zeichneTabelle();
      zeichneAktiveFilter();
    } catch (error) {
      elCount.textContent = '';
      toast(error.detail || error.message || 'Buchungen konnten nicht geladen werden.');
    }
  }

  const debouncedSuche = debounce(() => { local.q = elQ.value.trim(); ladeSeite(true); }, 350);
  elQ.oninput = debouncedSuche;
  elVon.onchange = () => { local.von = elVon.value; ladeSeite(true); };
  elBis.onchange = () => { local.bis = elBis.value; ladeSeite(true); };
  elGruppe.onchange = () => { local.gruppeId = elGruppe.value; ladeSeite(true); };
  elReset.onclick = () => {
    local.q = ''; local.von = ''; local.bis = ''; local.gruppeId = '';
    elQ.value = ''; elVon.value = ''; elBis.value = ''; elGruppe.value = '';
    if (filterRichtung) filterRichtung.value = '';
    if (filterZahlungsart) filterZahlungsart.value = '';
    if (filterKategorie) filterKategorie.value = '';
    // Kategorie ist Teil des zentralen state.filter (P30b) - sonst stellt app.js beim
    // nächsten Re-Render die alte Auswahl wieder her.
    if (state.filter) state.filter.kategorieId = '';
    localStorage.setItem('neu-kategorie', '');
    ladeSeite(true);
  };
  elMore.onclick = () => ladeSeite(false);
  if (filterRichtung) filterRichtung.onchange = () => ladeSeite(true);
  if (filterZahlungsart) filterZahlungsart.onchange = () => ladeSeite(true);

  // ---------- Bearbeiten-Dialog ----------

  async function ladeKategorienFuerSparte(sparteId) {
    if (!sparteId) return [];
    if (local.kategorien[sparteId]) return local.kategorien[sparteId];
    try {
      const kats = await api('/kategorien', {params: {sparte_id: sparteId, nur_aktive: 'true'}, bereichId: state.bereichId});
      local.kategorien[sparteId] = kats;
      return kats;
    } catch (error) {
      toast(error.detail || error.message);
      return [];
    }
  }

  function zeilenHtml(zeilen, kats) {
    return zeilen.map((z, i) => zeileHtml(z, i, kats, zeilen.length)).join('');
  }

  function zeileHtml(z, i, kats, total) {
    const opts = kats.map(k => `<option value="${k.id}" ${String(k.id) === String(z.kategorie_id) ? 'selected' : ''}>${esc(k.name)}</option>`).join('');
    return `<div class="bu-zeile" data-row="${i}" data-id="${z.id != null ? z.id : ''}">
      <label class="field">Kategorie<select data-f="kategorie_id">${opts}</select></label>
      <label class="field">Betrag (€)<input data-f="betrag_cent" inputmode="decimal" value="${((z.betrag_cent || 0) / 100).toFixed(2).replace('.', ',')}"></label>
      <label class="field">Notiz<input data-f="notiz" value="${esc(z.notiz || '')}"></label>
      <button type="button" class="btn danger" data-remove="${i}" ${total <= 1 ? 'disabled' : ''}>Zeile entfernen</button>
    </div>`;
  }

  async function openEditDialog(id) {
    const listRow = local.rows.find(r => r.id === id);
    if (!listRow) { toast('Buchung nicht mehr in der Liste.'); return; }
    // P51: original_id/storniert_am/erstattungen/netto_cent liefert nur der Einzel-Endpunkt
    // (GET /api/buchungen/{id}), die Liste (_lade_buchungen) berechnet das nicht mit.
    let buchung;
    try {
      buchung = await api(`/buchungen/${id}`, {bereichId: state.bereichId});
    } catch (error) {
      toast(error.detail || error.message || 'Buchung konnte nicht geladen werden.');
      return;
    }
    const sparten = state.sparten || [];
    let zeilen = buchung.zeilen.map(z => ({...z}));
    let kats = await ladeKategorienFuerSparte(buchung.sparte_id);

    const html = `
      <form id="bu-edit-form" class="bu-edit">
        <div class="grid g2">
          <label class="field">Sparte<select name="sparte_id">${sparten.map(s => `<option value="${s.id}" ${s.id === buchung.sparte_id ? 'selected' : ''}>${esc(s.name)}</option>`).join('')}</select></label>
          <label class="field">Datum<input name="datum" type="date" value="${buchung.datum}" required></label>
          <label class="field">Typ<select name="typ"><option value="ausgabe" ${buchung.typ === 'ausgabe' ? 'selected' : ''}>Ausgabe</option><option value="einnahme" ${buchung.typ === 'einnahme' ? 'selected' : ''}>Einnahme</option></select></label>
          <label class="field">Zahlungsart<select name="zahlungsart">${['bar', 'bank', 'karte', 'sonstiges'].map(z => `<option value="${z}" ${z === buchung.zahlungsart ? 'selected' : ''}>${z}</option>`).join('')}</select></label>
        </div>
        <label class="field">Text<input name="text" value="${esc(buchung.text || '')}" maxlength="200"></label>
        <label class="field">Notiz<input name="notiz" value="${esc(buchung.notiz || '')}" maxlength="500"></label>
        <h3>Zeilen</h3>
        <div id="bu-zeilen">${zeilenHtml(zeilen, kats)}</div>
        <button type="button" class="btn" id="bu-zeile-add">+ Zeile hinzufügen</button>
        <label class="field">Grund der Änderung (Vorschlag, nicht Pflicht)<input name="grund" maxlength="200" placeholder="z. B. Tippfehler"></label>
        <p class="muted" id="bu-edit-hint"></p>
        <div class="bu-edit-actions">
          <button type="submit" class="btn primary">Änderung speichern</button>
          <button type="button" class="btn danger" id="bu-delete">Buchung löschen</button>
        </div>
      </form>
      ${buchung.typ !== 'umbuchung' ? `
      <section class="bu-erstattungen">
        <h3>Erstattungen${buchung.netto_cent != null ? ' · netto ' + fmtEur(buchung.netto_cent) : ''}</h3>
        <div id="bu-erstattungen-liste"></div>
        <div id="bu-erstattungen-formulare"></div>
      </section>` : ''}
      <section class="bu-historie">
        <h3>Historie</h3>
        <div id="bu-historie-content" class="muted">Lädt …</div>
      </section>`;
    drill('Buchung bearbeiten', html);

    const dialogRoot = document.querySelector('#drill-content');
    const form = dialogRoot.querySelector('#bu-edit-form');
    const zeilenBox = dialogRoot.querySelector('#bu-zeilen');
    const sparteSel = form.elements['sparte_id'];
    const typSel = form.elements['typ'];

    function readZeilenFromForm() {
      return [...zeilenBox.querySelectorAll('.bu-zeile')].map(row => ({
        id: row.dataset.id ? Number(row.dataset.id) : null,
        kategorie_id: Number(row.querySelector('[data-f="kategorie_id"]').value),
        betrag_cent: Math.round((parseBetrag(row.querySelector('[data-f="betrag_cent"]').value) || 0) * 100),
        notiz: row.querySelector('[data-f="notiz"]').value || null,
      }));
    }

    function neuZeichnenZeilen() {
      zeilenBox.innerHTML = zeilenHtml(zeilen, kats);
      verdrahteZeilen();
    }

    function verdrahteZeilen() {
      zeilenBox.querySelectorAll('[data-remove]').forEach(btn => {
        btn.onclick = () => {
          zeilen = readZeilenFromForm();
          zeilen.splice(Number(btn.dataset.remove), 1);
          neuZeichnenZeilen();
        };
      });
    }
    verdrahteZeilen();

    dialogRoot.querySelector('#bu-zeile-add').onclick = () => {
      zeilen = readZeilenFromForm();
      zeilen.push({id: null, kategorie_id: kats[0] ? kats[0].id : '', betrag_cent: 0, notiz: ''});
      neuZeichnenZeilen();
    };

    sparteSel.onchange = async () => {
      const neueSparteId = Number(sparteSel.value);
      kats = await ladeKategorienFuerSparte(neueSparteId);
      zeilen = readZeilenFromForm();
      neuZeichnenZeilen();
    };

    dialogRoot.querySelector('#bu-delete').onclick = async () => {
      if (!window.confirm('Diese Buchung wirklich löschen?')) return;
      try {
        await api(`/buchungen/${buchung.id}`, {method: 'DELETE', bereichId: state.bereichId});
        document.querySelector('#drill').close();
        toast('Buchung gelöscht.');
        ladeSeite(true);
      } catch (error) {
        toast(error.detail || error.message || 'Löschen fehlgeschlagen.');
      }
    };

    form.onsubmit = async (ev) => {
      ev.preventDefault();
      const fd = new FormData(form);
      const payload = {
        sparte_id: Number(fd.get('sparte_id')),
        datum: fd.get('datum'),
        typ: typSel.value,
        zahlungsart: fd.get('zahlungsart'),
        text: fd.get('text') || null,
        notiz: fd.get('notiz') || null,
        zeilen: readZeilenFromForm(),
        version: buchung.version,
        grund: fd.get('grund') || null,
      };
      const hint = dialogRoot.querySelector('#bu-edit-hint');
      hint.textContent = '';
      try {
        await api(`/buchungen/${buchung.id}`, {
          method: 'PUT',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload),
          bereichId: state.bereichId,
        });
        document.querySelector('#drill').close();
        toast('Änderung gespeichert.');
        ladeSeite(true);
      } catch (error) {
        if (error.status === 409) {
          hint.textContent = 'Die Buchung wurde inzwischen geändert. Bitte Dialog schließen und neu laden.';
          toast('Inzwischen geändert - bitte neu laden.');
        } else {
          toast(error.detail || error.message || 'Speichern fehlgeschlagen.');
        }
      }
    };

    // P51: Erstattungen-Abschnitt - Liste bestehender Erstattungen, je Zeile ein
    // Formular mit dem offenen Rest vorbelegt (Server liefert rest_cent je Zeile).
    if (buchung.typ !== 'umbuchung') {
      const listeBox = dialogRoot.querySelector('#bu-erstattungen-liste');
      const formulareBox = dialogRoot.querySelector('#bu-erstattungen-formulare');
      const beidesKats = kats.filter(k => k.richtung === 'beides');

      const eintraege = buchung.erstattungen || [];
      listeBox.innerHTML = eintraege.length
        ? '<ul class="bu-erst-list">' + eintraege.map(e =>
            `<li>${fmtDate(e.datum)} · ${fmtEur(e.betrag_cent)}${e.storniert_am ? ' <span class="pill">storniert</span>' : ''}</li>`).join('') + '</ul>'
        : '<p class="muted">Noch keine Erstattung erfasst.</p>';

      formulareBox.innerHTML = zeilen.filter(z => z.id != null).map(z => {
        const restCent = z.rest_cent != null ? z.rest_cent : z.betrag_cent;
        const katOpts = beidesKats.map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join('');
        return `<div class="bu-erst-zeile">
          <button type="button" class="lnk" data-erfassen="${z.id}">Erstattung erfassen für „${esc(z.kategorie_name || '')}" (Rest ${fmtEur(restCent)})</button>
          <form class="bu-erst-form" data-form="${z.id}" hidden>
            <label class="field">Betrag (€)<input data-ef="betrag_cent" inputmode="decimal" value="${(restCent / 100).toFixed(2).replace('.', ',')}"></label>
            <label class="field">Datum<input data-ef="datum" type="date" value="${new Date().toISOString().slice(0, 10)}"></label>
            <label class="field">Kategorie<select data-ef="kategorie_id"><option value="">wie Original</option>${katOpts}</select></label>
            <button type="submit" class="btn primary">Erstattung speichern</button>
            <button type="button" class="btn" data-abbrechen="${z.id}">Abbrechen</button>
          </form>
        </div>`;
      }).join('') || '<p class="muted">Zeile erst speichern, bevor eine Erstattung erfasst werden kann.</p>';

      formulareBox.querySelectorAll('[data-erfassen]').forEach(btn => {
        btn.onclick = () => {
          formulareBox.querySelectorAll('.bu-erst-form').forEach(f => { f.hidden = true; });
          formulareBox.querySelector(`[data-form="${btn.dataset.erfassen}"]`).hidden = false;
        };
      });
      formulareBox.querySelectorAll('[data-abbrechen]').forEach(btn => {
        btn.onclick = () => { formulareBox.querySelector(`[data-form="${btn.dataset.abbrechen}"]`).hidden = true; };
      });
      formulareBox.querySelectorAll('.bu-erst-form').forEach(erstForm => {
        erstForm.onsubmit = async (ev) => {
          ev.preventDefault();
          const zeileId = Number(erstForm.dataset.form);
          const betragCent = Math.round((parseBetrag(erstForm.querySelector('[data-ef="betrag_cent"]').value) || 0) * 100);
          const datum = erstForm.querySelector('[data-ef="datum"]').value;
          const kategorieVal = erstForm.querySelector('[data-ef="kategorie_id"]').value;
          try {
            await api(`/buchungen/${buchung.id}/erstatten`, {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                datum,
                zeilen: [{
                  original_zeile_id: zeileId,
                  betrag_cent: betragCent,
                  kategorie_id: kategorieVal ? Number(kategorieVal) : null,
                }],
              }),
              bereichId: state.bereichId,
            });
            toast('Erstattung erfasst.');
            document.querySelector('#drill').close();
            ladeSeite(true);
          } catch (error) {
            toast(error.detail || error.message || 'Erstattung fehlgeschlagen.');
          }
        };
      });
    }

    // Historie: seit Migration 016 / P50b im Backend vorhanden.
    const histBox = dialogRoot.querySelector('#bu-historie-content');
    try {
      const eintraege = await api(`/buchungen/${buchung.id}/verlauf`, {bereichId: state.bereichId});
      histBox.innerHTML = eintraege.length
        ? '<ul class="bu-hist-list">' + eintraege.map(e =>
            `<li><b>${esc(e.feld)}</b>: ${esc(e.alt ?? '–')} → ${esc(e.neu ?? '–')}`
            + `<span class="muted"> · ${esc(e.zeitpunkt)}${e.grund ? ' · ' + esc(e.grund) : ''}</span></li>`).join('') + '</ul>'
        : '<p class="muted">Noch keine Änderungen protokolliert.</p>';
    } catch (error) {
      histBox.innerHTML = '<p class="muted">Historie konnte nicht geladen werden.</p>';
    }
  }

  ladeSeite(true);
}
