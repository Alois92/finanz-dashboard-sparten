import {api} from '../api.js';
import {esc, fmtEur, fmtDate, parseBetrag} from '../format.js';
import {toast, drill, wizard} from '../ui.js';

const HEUTE = new Date().toISOString().slice(0, 10);
const ART_LABEL = {bank: 'Bank', karte: 'Karte', kassa: 'Kassa', depot: 'Depot', wallet: 'Wallet'};
const DATENSTAND_LABEL = {aktuell: 'aktuell', veraltet: 'veraltet', unbekannt: 'unbekannt'};
const DATENSTAND_TITEL = {
  aktuell: 'Stand ist ankergestützt und aktuell.',
  veraltet: 'Letzter Import liegt mehr als 30 Tage zurück.',
  unbekannt: 'Für dieses Konto ist noch kein Anker gesetzt.',
};

function cssHref(){return new URL('./konten.css', import.meta.url).href}
function ensureCss(){
  if(!document.querySelector(`link[href="${cssHref()}"]`)){
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = cssHref();
    document.head.appendChild(link);
  }
}

function fmtBetragFeld(cent){
  return ((cent || 0) / 100).toLocaleString('de-AT', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function centFromInput(value){
  const n = parseBetrag(value);
  return n == null ? null : Math.round(n * 100);
}
function sparteName(state, id){
  const s = state.sparten.find(x => String(x.id) === String(id));
  return s ? s.name : `Sparte ${id}`;
}
function closeDrill(){document.querySelector('#drill').close()}

async function loadAll(){
  const [konten, auslagen, ausgleiche] = await Promise.all([
    api('/konten'), api('/auslagen'), api('/ausgleiche'),
  ]);
  const abgleiche = {};
  await Promise.all(konten.map(async k => {
    try{ abgleiche[k.id] = await api(`/konten/${k.id}/offene-abgleiche`) }
    catch{ abgleiche[k.id] = null }
  }));
  return {konten, auslagen, ausgleiche, abgleiche};
}

export function render(root, state){
  ensureCss();
  root.innerHTML = '<section class="card placeholder"><p class="muted">Lädt…</p></section>';
  const reload = () => render(root, state);
  loadAll().then(data => draw(root, state, data, reload))
    .catch(error => {
      root.innerHTML = `<section class="card placeholder"><p>Konten konnten nicht geladen werden: ${esc(error.detail || error.message)}</p></section>`;
      toast(error.detail || error.message);
    });
}

function draw(root, state, data, reload){
  root.innerHTML = `
    <section class="card" id="konten-card">
      <div class="card-head"><h2>Konten</h2><button class="btn primary" id="konto-neu">+ Konto anlegen</button></div>
      <div id="konten-liste"></div>
    </section>
    <section class="card" id="auslagen-card">
      <div class="card-head"><h2>Offene Auslagen</h2></div>
      <div id="auslagen-liste"></div>
    </section>
    <section class="card" id="ausgleiche-card">
      <div class="card-head"><h2>Ausgleichs-Historie</h2></div>
      <div id="ausgleiche-liste"></div>
    </section>
  `;
  drawKonten(root, state, data, reload);
  drawAuslagen(root, state, data, reload);
  drawAusgleiche(root, state, data, reload);
  root.querySelector('#konto-neu').onclick = () => openKontoDialog(state, reload);
}

/* ---------- Konten ---------- */

function gruppenReihenfolge(konten){
  const gruppen = [['bank', 'Bank'], ['karte', 'Karte'], ['kassa', 'Kassa']];
  const out = [];
  for(const [art, label] of gruppen){
    const rows = konten.filter(k => k.art === art);
    if(rows.length) out.push([label, rows]);
  }
  const depotWallet = konten.filter(k => k.art === 'depot' || k.art === 'wallet');
  if(depotWallet.length) out.push(['Depot/Wallet', depotWallet]);
  return out;
}

function drawKonten(root, state, data, reload){
  const el = root.querySelector('#konten-liste');
  const gruppen = gruppenReihenfolge(data.konten);
  if(!gruppen.length){
    el.innerHTML = '<p class="muted">Noch keine Konten angelegt.</p>';
    return;
  }
  el.innerHTML = gruppen.map(([label, rows]) => `
    <div class="kto-group">
      <div class="kto-group-label">${esc(label)}</div>
      ${rows.map(k => kontoRowHtml(k, data)).join('')}
    </div>
  `).join('');

  for(const k of data.konten){
    const row = el.querySelector(`[data-konto="${k.id}"]`);
    if(!row) continue;
    const ankerBtn = row.querySelector('[data-anker]');
    if(ankerBtn) ankerBtn.onclick = () => openAnkerDialog(k, reload);
    const zaehlBtn = row.querySelector('[data-zaehlung]');
    if(zaehlBtn) zaehlBtn.onclick = () => openZaehlungDialog(k, state, reload);
    const bearbeitenBtn = row.querySelector('[data-bearbeiten]');
    if(bearbeitenBtn) bearbeitenBtn.onclick = () => openBearbeitenDialog(k, state, reload);
  }
}

function kontoRowHtml(k, data){
  // QA3-01: fmtEur() liefert bereits das Waehrungssymbol (Intl.NumberFormat,
  // style:'currency') - der Waehrungscode wurde bisher zusaetzlich angehaengt
  // ("€ 1.600,00 EUR"). Nur noch anzeigen, wenn das Konto NICHT auf EUR
  // lautet (fmtEur formatiert ohnehin immer als €, das waere dann sonst
  // irrefuehrend und muss auffallen statt zu verschwinden).
  const stand = k.stand_cent == null
    ? '<span class="muted">kein Anker</span>'
    : `${fmtEur(k.stand_cent)}${k.waehrung !== 'EUR' ? ` <span class="muted">${esc(k.waehrung)}</span>` : ''}`;
  const badgeCls = k.datenstand === 'aktuell' ? 'badge-ok' : k.datenstand === 'veraltet' ? 'badge-warn' : 'badge-muted';
  const titel = k.hinweis || DATENSTAND_TITEL[k.datenstand] || '';
  // QA3-05: ein Abgleich mit einem Bankumsatz kann nur bei Bank-/Kartenkonten
  // vorkommen (CSV-Import ist fuer Kassakonten serverseitig ausgeschlossen,
  // Depot/Wallet haben ohnehin keinen Import) - der Hinweis wuerde dort nie
  // "abgleichbar" werden und nur verwirren, z. B. nach einer gebuchten
  // Kassadifferenz (erzeugt eine manuelle Bewegung ohne Bankumsatz-Gegenstueck).
  const abgleichFaehig = k.art === 'bank' || k.art === 'karte';
  const abgleich = abgleichFaehig ? data.abgleiche[k.id] : null;
  const offeneAbgleiche = abgleich && (abgleich.manuelle_anzahl > 0 || abgleich.umsaetze_anzahl > 0);
  const hinweisAbgleich = offeneAbgleiche
    ? `<div class="kto-hint">${abgleich.manuelle_anzahl} offene manuelle Bewegung(en), ${abgleich.umsaetze_anzahl} offene(r) Bankumsatz/Bankumsätze zum Abgleichen.</div>`
    : '';
  const aktionen = k.art === 'kassa'
    ? `<button class="btn small" data-anker>Anfangsstand ändern</button>
       <button class="btn small" data-zaehlung>Kassa gezählt, Differenz buchen</button>`
    : '';
  const karteHinweis = k.art === 'karte'
    ? '<div class="kto-hint">Der Ausgleich der Karte ist eine Umbuchung, keine Ausgabe.</div>' : '';
  // QA3-04: bisher gab es keinen Weg, ein bestehendes Konto zu bearbeiten
  // oder zu deaktivieren - PATCH /api/konten/{id} unterstuetzt das laengst
  // (name/iban/bank/sparte_id/aktiv). Deaktivierte Konten wurden ausserdem
  // von aktiven optisch nicht unterscheidbar dargestellt.
  const inaktivPille = !k.aktiv ? '<span class="badge badge-muted">inaktiv</span>' : '';
  return `
    <div class="kto-row${!k.aktiv ? ' kto-inaktiv' : ''}" data-konto="${k.id}">
      <div class="kto-main">
        <div class="kto-name">${esc(k.name)} ${inaktivPille}</div>
        <div class="kto-sub muted">${esc(ART_LABEL[k.art] || k.art)}</div>
      </div>
      <div class="kto-stand">
        <div class="kto-val">${stand}</div>
        <span class="badge ${badgeCls}" title="${esc(titel)}">${esc(DATENSTAND_LABEL[k.datenstand] || k.datenstand)}</span>
      </div>
      <div class="kto-actions">
        ${aktionen}
        <button class="btn small" data-bearbeiten>Bearbeiten</button>
      </div>
      ${karteHinweis}
      ${hinweisAbgleich}
    </div>`;
}

function openKontoDialog(state, reload){
  const sparteOptions = `<option value="">– keine –</option>` + state.sparten.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join('');
  drill('Konto anlegen', `
    <form id="konto-form">
      <label class="field">Name<input name="name" required maxlength="120"></label>
      <label class="field">Art<select name="art">
        <option value="bank">Bank</option>
        <option value="karte">Karte</option>
        <option value="kassa">Kassa</option>
        <option value="depot">Depot</option>
        <option value="wallet">Wallet</option>
      </select></label>
      <label class="field">Sparte<select name="sparte_id">${sparteOptions}</select></label>
      <label class="field">IBAN<input name="iban" maxlength="34"></label>
      <label class="field">Bank<input name="bank" maxlength="80"></label>
      <p class="field-error" id="konto-error" hidden></p>
      <button class="btn primary" type="submit">Anlegen</button>
    </form>
  `);
  const form = document.querySelector('#konto-form');
  form.onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const body = {
      name: fd.get('name'),
      art: fd.get('art'),
      sparte_id: fd.get('sparte_id') ? Number(fd.get('sparte_id')) : null,
      iban: fd.get('iban') || null,
      bank: fd.get('bank') || null,
    };
    try{
      await api('/konten', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      closeDrill();
      toast('Konto angelegt.');
      reload();
    }catch(error){
      const box = document.querySelector('#konto-error');
      box.textContent = error.detail || error.message;
      box.hidden = false;
    }
  };
}

// QA3-04: Bearbeiten-Dialog fuer ein bestehendes Konto (PATCH /api/konten/{id}).
// Bewusst nur die unkritischen Stammdaten (Name/IBAN/Bank/Sparte/Aktiv) - Art
// und Waehrung sind serverseitig gesperrt, sobald das Konto Bewegungen hat
// (409 "Konto mit Bewegungen darf Art, Währung und Sparte nicht wechseln"),
// daher hier nicht editierbar angeboten.
function openBearbeitenDialog(konto, state, reload){
  const sparteOptions = `<option value="">– keine –</option>` + state.sparten
    .map(s => `<option value="${s.id}" ${String(konto.sparte_id) === String(s.id) ? 'selected' : ''}>${esc(s.name)}</option>`)
    .join('');
  drill(`Konto bearbeiten – ${esc(konto.name)}`, `
    <form id="konto-bearb-form">
      <label class="field">Name<input name="name" required maxlength="120" value="${esc(konto.name)}"></label>
      <label class="field">Sparte<select name="sparte_id">${sparteOptions}</select></label>
      <label class="field">IBAN<input name="iban" maxlength="34" value="${esc(konto.iban || '')}"></label>
      <label class="field">Bank<input name="bank" maxlength="80" value="${esc(konto.bank || '')}"></label>
      <label class="field" style="flex-direction:row;align-items:center;gap:8px">
        <input type="checkbox" name="aktiv" style="width:auto" ${konto.aktiv ? 'checked' : ''}> Konto ist aktiv
      </label>
      <p class="field-error" id="konto-bearb-error" hidden></p>
      <button class="btn primary" type="submit">Speichern</button>
    </form>
  `);
  const form = document.querySelector('#konto-bearb-form');
  form.onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const body = {
      name: fd.get('name'),
      sparte_id: fd.get('sparte_id') ? Number(fd.get('sparte_id')) : null,
      iban: fd.get('iban') || null,
      bank: fd.get('bank') || null,
      aktiv: fd.get('aktiv') === 'on' ? 1 : 0,
    };
    try{
      await api(`/konten/${konto.id}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      closeDrill();
      toast('Konto gespeichert.');
      reload();
    }catch(error){
      const box = document.querySelector('#konto-bearb-error');
      box.textContent = error.detail || error.message;
      box.hidden = false;
    }
  };
}

function openAnkerDialog(konto, reload){
  drill('Anfangsstand ändern', `
    <p class="muted">${esc(konto.name)} · setzt den Kontostand zu einem Stichtag; spätere Bewegungen werden dazugerechnet.</p>
    <form id="anker-form">
      <label class="field">Stichtag<input type="date" name="stichtag" value="${HEUTE}" max="${HEUTE}" required></label>
      <label class="field">Stand in €<input name="saldo" inputmode="decimal" required placeholder="0,00"></label>
      <label class="field">Quelle<select name="quelle">
        <option value="manuell">manuell</option>
        <option value="auszug">Auszug</option>
        <option value="import">Import</option>
      </select></label>
      <p class="field-error" id="anker-error" hidden></p>
      <div id="anker-ergebnis" hidden></div>
      <button class="btn primary" type="submit">Anker setzen</button>
    </form>
  `);
  const form = document.querySelector('#anker-form');
  form.onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const saldo = centFromInput(fd.get('saldo'));
    if(saldo == null){
      const box = document.querySelector('#anker-error');
      box.textContent = 'Betrag ist ungültig.';
      box.hidden = false;
      return;
    }
    const body = {stichtag: fd.get('stichtag'), saldo_cent: saldo, quelle: fd.get('quelle')};
    try{
      const res = await api(`/konten/${konto.id}/anker`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      const ergebnis = document.querySelector('#anker-ergebnis');
      if(res.differenz_cent != null){
        ergebnis.hidden = false;
        ergebnis.innerHTML = `<p>Bisher gerechneter Stand: ${fmtEur(res.gerechnet_cent)}. Differenz zum neuen Anker: <b>${fmtEur(res.differenz_cent)}</b>. Der Anker wird ungeschönt gesetzt, keine automatische Korrektur.</p>`;
        toast(`Anker gesetzt, Differenz ${fmtEur(res.differenz_cent)}.`);
      }else{
        toast('Anker gesetzt.');
        closeDrill();
      }
      reload();
    }catch(error){
      const box = document.querySelector('#anker-error');
      box.textContent = error.detail || error.message;
      box.hidden = false;
    }
  };
}

// P30b: nutzt den ins Gerüst gezogenen wizard() aus ui.js statt eines lokal gebauten
// Zwei-Schritt-Formulars. Schritt 1 zählt die Kassa und bucht bei Differenz 0 sofort ab
// (ctx.finishNow, kein Schritt 2); bei Differenz kommt Schritt 2 zur Kategoriewahl.
// lockBack:true auf Schritt 1, weil ein erneutes "Weiter" sonst eine zweite Zählung anlegen
// würde (wie zuvor: kein Zurück zum ausgefüllten Formular).
function openZaehlungDialog(konto, state, reload){
  wizard({
    title: 'Kassa gezählt, Differenz buchen',
    steps: [
      {
        lockBack: true,
        render: () => `
          <p class="muted">${esc(konto.name)}</p>
          <label class="field">Datum<input type="date" id="wz-datum" value="${HEUTE}" max="${HEUTE}" required></label>
          <label class="field">Gezählter Betrag in €<input id="wz-gezaehlt" inputmode="decimal" required placeholder="0,00"></label>
        `,
        validate: async ctx => {
          const datum = document.querySelector('#wz-datum').value;
          const gezaehlt = centFromInput(document.querySelector('#wz-gezaehlt').value);
          if(gezaehlt == null) throw new Error('Betrag ist ungültig.');
          let res;
          try{
            res = await api(`/konten/${konto.id}/zaehlung`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({datum, gezaehlt_cent: gezaehlt})});
          }catch(error){
            throw new Error(error.detail || error.message);
          }
          ctx.data.zaehlung = res;
          if(res.differenz_cent === 0){
            ctx.finishNow = true;
            ctx.data.keineDifferenz = true;
            return;
          }
          const richtung = res.differenz_cent > 0 ? 'einnahme' : 'ausgabe';
          let kategorien = [];
          try{
            kategorien = await api('/kategorien', {params: {sparte_id: konto.sparte_id, nur_aktive: true}});
          }catch{ kategorien = [] }
          ctx.data.kategorien = kategorien.filter(k => k.richtung === richtung || k.richtung === 'beides');
        },
      },
      {
        render: ctx => {
          const z = ctx.data.zaehlung;
          const passend = ctx.data.kategorien || [];
          const vorauswahl = passend.find(k => k.name === 'Kassadifferenz') || passend[0];
          return `
            <p>Differenz: <b>${fmtEur(z.differenz_cent)}</b> (gerechnet ${fmtEur(z.gerechnet_cent)}, gezählt ${fmtEur(z.gezaehlt_cent)})</p>
            <label class="field">Kategorie<select id="wz-kategorie">
              ${passend.map(k => `<option value="${k.id}" ${vorauswahl && k.id === vorauswahl.id ? 'selected' : ''}>${esc(k.name)}</option>`).join('') || '<option value="">– keine passende Kategorie –</option>'}
            </select></label>
          `;
        },
        validate: async ctx => {
          const kategorieId = document.querySelector('#wz-kategorie').value;
          if(!kategorieId) throw new Error('Keine Kategorie ausgewählt.');
          try{
            await api(`/konten/${konto.id}/zaehlung/${ctx.data.zaehlung.id}/buchen`, {
              method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({kategorie_id: Number(kategorieId)}),
            });
          }catch(error){
            throw new Error(error.detail || error.message);
          }
          ctx.data.gebucht = true;
        },
      },
    ],
    onFinish: ctx => {
      toast(ctx.data.keineDifferenz ? 'Kassa gezählt: keine Differenz.' : 'Kassadifferenz gebucht.');
      reload();
    },
  });
}

/* ---------- Offene Auslagen ---------- */

function drawAuslagen(root, state, data, reload){
  const el = root.querySelector('#auslagen-liste');
  if(!data.auslagen.length){
    el.innerHTML = '<p class="muted">Keine offenen Auslagen. Alles ausgeglichen.</p>';
    return;
  }
  el.innerHTML = data.auslagen.map((g, i) => {
    const rows = [...g.auslagen].sort((a, b) => a.datum.localeCompare(b.datum) || a.id - b.id);
    const aeltestes = rows[0]?.datum;
    return `
      <div class="ausl-row" data-gruppe="${i}">
        <div class="ausl-main">
          <div class="ausl-titel">${esc(sparteName(state, g.zahler_sparte_id))} hat für ${esc(sparteName(state, g.sparte_id))} ausgelegt</div>
          <div class="ausl-sub muted">${g.anzahl} Buchung(en) · älteste vom ${fmtDate(aeltestes)}</div>
        </div>
        <div class="ausl-summe">${fmtEur(g.offen_cent)}</div>
        <div class="ausl-actions">
          <button class="btn small" data-buchungen="${i}">Buchungen</button>
          <button class="btn small primary" data-ausgleich="${i}">Ausgleich buchen</button>
        </div>
      </div>`;
  }).join('');
  data.auslagen.forEach((g, i) => {
    el.querySelector(`[data-buchungen="${i}"]`).onclick = () => {
      const rows = [...g.auslagen].sort((a, b) => a.datum.localeCompare(b.datum) || a.id - b.id);
      drill('Offene Auslagen', `
        <p class="muted">${esc(sparteName(state, g.zahler_sparte_id))} für ${esc(sparteName(state, g.sparte_id))} · noch nicht ausgeglichen</p>
        <div class="table-wrap"><table class="tbl"><thead><tr><th>Datum</th><th>Text</th><th>Kategorie</th><th>offen</th></tr></thead><tbody>
          ${rows.map(r => `<tr><td class="muted">${fmtDate(r.datum)}</td><td>${esc(r.text || '')}</td><td>${esc(r.kategorie)}</td><td>${fmtEur(r.offen_cent)}</td></tr>`).join('')}
        </tbody></table></div>
      `);
    };
    el.querySelector(`[data-ausgleich="${i}"]`).onclick = () => openAusgleichDialog(g, state, data, reload);
  });
}

function openAusgleichDialog(gruppe, state, data, reload){
  const rows = [...gruppe.auslagen].sort((a, b) => a.datum.localeCompare(b.datum) || a.id - b.id);
  const vonSparteId = gruppe.sparte_id;
  const nachSparteId = gruppe.zahler_sparte_id;
  const bankKontenVon = data.konten.filter(k => k.art === 'bank' && String(k.sparte_id) === String(vonSparteId));
  const bankKontenNach = data.konten.filter(k => k.art === 'bank' && String(k.sparte_id) === String(nachSparteId));
  drill('Ausgleich buchen', `
    <p class="muted">${esc(sparteName(state, nachSparteId))} zahlt an ${esc(sparteName(state, vonSparteId))} · Teilbeträge sind erlaubt, der Rest bleibt offen</p>
    <div class="table-wrap"><table class="tbl" id="ausgl-tabelle"><thead><tr><th><input type="checkbox" id="ausgl-alle" checked aria-label="alle"></th><th>Datum</th><th>Text</th><th>Kategorie</th><th>offen</th></tr></thead><tbody>
      ${rows.map(r => `<tr><td><input type="checkbox" checked data-id="${r.id}" data-offen="${r.offen_cent}" aria-label="Buchung ${esc(r.text || '')} ${fmtEur(r.offen_cent)} auswählen"></td><td class="muted">${fmtDate(r.datum)}</td><td>${esc(r.text || '')}</td><td>${esc(r.kategorie)}</td><td>${fmtEur(r.offen_cent)}</td></tr>`).join('')}
    </tbody></table></div>
    <form id="ausgleich-form">
      <label class="field">Zahlungsart<select name="zahlungsart" id="ausgl-zahlungsart">
        <option value="bar" selected>Bar übergeben</option>
        <option value="bank">Überweisung</option>
      </select></label>
      <label class="field">Datum<input type="date" name="datum" value="${HEUTE}" max="${HEUTE}" required></label>
      <label class="field">Betrag in €<input name="betrag" id="ausgl-betrag" inputmode="decimal" required></label>
      <div class="field" id="ausgl-summe-feld"><span>offen, angehakt</span><b id="ausgl-summe">${fmtEur(gruppe.offen_cent)}</b></div>
      <div id="ausgl-bankfelder" hidden>
        <label class="field">Quellkonto (${esc(sparteName(state, vonSparteId))})<select name="von_konto_id">
          ${bankKontenVon.map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join('') || '<option value="">– kein Bankkonto –</option>'}
        </select></label>
        <label class="field">Zielkonto (${esc(sparteName(state, nachSparteId))})<select name="nach_konto_id">
          ${bankKontenNach.map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join('') || '<option value="">– kein Bankkonto –</option>'}
        </select></label>
      </div>
      <p class="field-error" id="ausgleich-error" hidden></p>
      <div id="ausgleich-warn" class="warn-box" hidden></div>
      <button class="btn primary" type="submit" id="ausgleich-go">Ausgleich buchen</button>
    </form>
  `);
  const table = document.querySelector('#ausgl-tabelle');
  const zahlungsartSel = document.querySelector('#ausgl-zahlungsart');
  const bankfelder = document.querySelector('#ausgl-bankfelder');
  const betragInput = document.querySelector('#ausgl-betrag');
  const summeEl = document.querySelector('#ausgl-summe');

  const selected = () => [...table.querySelectorAll('tbody input:checked')].map(cb => ({id: Number(cb.dataset.id), offen: Number(cb.dataset.offen)}));
  const update = () => {
    const s = selected();
    const summe = s.reduce((sum, r) => sum + r.offen, 0);
    summeEl.textContent = fmtEur(summe);
    betragInput.value = summe > 0 ? fmtBetragFeld(summe) : '';
    document.querySelector('#ausgleich-go').disabled = !s.length;
    bankfelder.hidden = zahlungsartSel.value !== 'bank';
  };
  table.querySelectorAll('tbody input').forEach(cb => cb.onchange = update);
  document.querySelector('#ausgl-alle').onchange = e => {
    table.querySelectorAll('tbody input').forEach(cb => cb.checked = e.target.checked);
    update();
  };
  zahlungsartSel.onchange = update;
  update();

  const form = document.querySelector('#ausgleich-form');
  form.onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const auslageIds = selected().map(r => r.id);
    if(!auslageIds.length){
      toast('Keine Auslage ausgewählt.');
      return;
    }
    const betragCent = centFromInput(fd.get('betrag'));
    if(betragCent == null || betragCent <= 0){
      const box = document.querySelector('#ausgleich-error');
      box.textContent = 'Betrag ist ungültig.';
      box.hidden = false;
      return;
    }
    const zahlungsart = fd.get('zahlungsart');
    const body = {
      von_sparte_id: vonSparteId, nach_sparte_id: nachSparteId,
      auslage_ids: auslageIds, datum: fd.get('datum'), betrag_cent: betragCent,
      zahlungsart, client_request_id: crypto.randomUUID(),
    };
    if(zahlungsart === 'bank'){
      body.von_konto_id = fd.get('von_konto_id') ? Number(fd.get('von_konto_id')) : null;
      body.nach_konto_id = fd.get('nach_konto_id') ? Number(fd.get('nach_konto_id')) : null;
    }
    try{
      const res = await api('/ausgleiche', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      if(res.warnungen && res.warnungen.length){
        const warnBox = document.querySelector('#ausgleich-warn');
        warnBox.hidden = false;
        warnBox.innerHTML = res.warnungen.map(w => `<p>${esc(w)}</p>`).join('');
        form.querySelectorAll('input,select,button').forEach(f => f.disabled = true);
        toast('Ausgleich gebucht, mit Warnung.');
      }else{
        toast('Ausgleich gebucht.');
        closeDrill();
      }
      reload();
    }catch(error){
      const box = document.querySelector('#ausgleich-error');
      box.textContent = error.detail || error.message;
      box.hidden = false;
    }
  };
}

/* ---------- Ausgleichs-Historie ---------- */

function drawAusgleiche(root, state, data, reload){
  const el = root.querySelector('#ausgleiche-liste');
  const aktive = data.ausgleiche.filter(a => !a.aufgehoben_am);
  if(!aktive.length){
    el.innerHTML = '<p class="muted">Noch keine Ausgleiche gebucht.</p>';
    return;
  }
  el.innerHTML = `<div class="table-wrap"><table class="tbl"><thead><tr><th>Datum</th><th>Von</th><th>Nach</th><th>Betrag</th><th>Zahlungsart</th><th></th></tr></thead><tbody>
    ${aktive.map(a => `<tr data-ausgleich="${a.id}">
      <td class="muted">${fmtDate(a.datum)}</td>
      <td>${esc(sparteName(state, a.von_sparte_id))}</td>
      <td>${esc(sparteName(state, a.nach_sparte_id))}</td>
      <td>${fmtEur(a.betrag_cent)}</td>
      <td>${a.zahlungsart === 'bar' ? 'bar' : 'Überweisung'}</td>
      <td><button class="btn small" data-ruecknahme="${a.id}">zurücknehmen</button></td>
    </tr>`).join('')}
  </tbody></table></div>`;
  aktive.forEach(a => {
    el.querySelector(`[data-ruecknahme="${a.id}"]`).onclick = () => confirmRuecknahme(a, state, reload);
  });
}

function confirmRuecknahme(ausgleich, state, reload){
  drill('Ausgleich zurücknehmen', `
    <p>Ausgleich vom ${fmtDate(ausgleich.datum)} über ${fmtEur(ausgleich.betrag_cent)} von ${esc(sparteName(state, ausgleich.von_sparte_id))} an ${esc(sparteName(state, ausgleich.nach_sparte_id))} wirklich zurücknehmen?</p>
    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button class="btn" id="ruecknahme-abbrechen">Abbrechen</button>
      <button class="btn primary" id="ruecknahme-bestaetigen">Zurücknehmen</button>
    </div>
    <p class="field-error" id="ruecknahme-error" hidden></p>
  `);
  document.querySelector('#ruecknahme-abbrechen').onclick = () => closeDrill();
  document.querySelector('#ruecknahme-bestaetigen').onclick = async () => {
    try{
      await api(`/ausgleiche/${ausgleich.id}`, {method: 'DELETE'});
      toast('Ausgleich zurückgenommen.');
      closeDrill();
      reload();
    }catch(error){
      const box = document.querySelector('#ruecknahme-error');
      box.textContent = error.detail || error.message;
      box.hidden = false;
    }
  };
}
