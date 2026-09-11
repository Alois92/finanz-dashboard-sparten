// P33: Kategorienpflege. Reiter je Sparte (Seitenzustand, kein Teil von state.filter -
// siehe Auftragskarte P33, Abschnitt "Festlegungen"), Umbenennen/Stilllegen echt über
// PATCH /api/kategorien/{id}, Stichwörter als echte regel-Datensätze (quelle='stichwort',
// siehe app/regeln.py und app/routers/import_bank.py), Gruppen-Balken und Tabelle der
// gelernten Merkregeln (quelle='gelernt'), "abschalten" über PATCH /api/regeln/{id}
// {aktiv:false}. Keine Demo-Daten, kein toast("Im Prototyp nur angedeutet").
import {api} from '../api.js';
import {esc, fmtEur, fmtDate} from '../format.js';
import {toast} from '../ui.js';

function ensureCss() {
  if (document.querySelector('#kategorien-css')) return;
  const link = document.createElement('link');
  link.id = 'kategorien-css';
  link.rel = 'stylesheet';
  link.href = new URL('./kategorien.css', import.meta.url).href;
  document.head.appendChild(link);
}

function initialSparte(state) {
  const filterSparte = state.filter ? state.filter.sparteId : state.sparteId;
  if (filterSparte && (state.sparten || []).some(s => String(s.id) === String(filterSparte))) return filterSparte;
  return state.sparten && state.sparten[0] ? state.sparten[0].id : '';
}

export async function render(root, state) {
  ensureCss();
  const jahr = new Date().getFullYear();

  // Eigener Seitenzustand je Aufruf. Der aktive Reiter ist Seitenzustand, kein Teil
  // von state.filter (Festlegung der Karte: "ein Reiterwechsel ändert nur den
  // Seitenzustand, nicht state.filter - die Kategorienpflege ist kein Filter").
  const local = {
    activeSparteId: initialSparte(state),
    kategorien: [],
    matrix: {},
    stichwortRegeln: [],
    gelernteRegeln: [],
    alleKategorien: [],
    konten: [],
    gruppen: [],
    matrixBereich: {},
  };

  root.innerHTML = `
    <div class="card">
      <div class="card-head">
        <div class="kattabs" id="k-tabs"></div>
        <button class="btn primary" id="k-new" type="button">+ Neue Kategorie</button>
      </div>
      <p class="muted" style="margin-bottom:12px">Stichwörter sind Merkregeln: Steht eines davon im Buchungstext, schlägt die App diese Kategorie vor.</p>
      <div class="tscroll"><table class="tbl" id="k-table"></table></div>
    </div>
    <div class="grid g2">
      <div class="card">
        <div class="card-head"><h2>Gruppen über Sparten hinweg</h2><span class="hint muted">bündeln gleichartige Kategorien</span></div>
        <div class="hbars" id="k-gruppen"></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>Gelernte Merkregeln</h2><span class="hint muted">verbuchen Bankumsätze automatisch</span></div>
        <div class="tscroll"><table class="tbl" id="k-regeln"></table></div>
      </div>
    </div>`;

  root.querySelector('#k-new').onclick = () => {
    // "öffnet die Erfassen-Seite mit vorbelegter Sparte" (Karte, Abschnitt 3): das
    // Formular selbst kommt aus einer anderen Karte, ein Seitenwechsel mit
    // Sparten-Vorbelegung im Zustand genügt - gleiches Muster wie goSparte() in
    // pages/uebersicht.js (P31).
    if (local.activeSparteId) {
      state.sparteId = String(local.activeSparteId);
      if (state.filter) state.filter.sparteId = state.sparteId;
      try { localStorage.setItem('neu-sparte', state.sparteId); } catch { /* Storage kann fehlen */ }
    }
    location.hash = '#/erfassen';
  };

  // P30b: #filter-kategorie wird zentral in app.js befüllt und dort gecacht
  // (kategorieOptionsKey je Bereich+Sparte, nicht exportiert - siehe app.js). Nach
  // Umbenennen/Stilllegen einer Kategorie muss die Auswahl aktuell bleiben, ohne
  // app.js anzufassen; solange der aktive Reiter zur im Kopf gewählten Sparte
  // passt, patchen wir die Optionen direkt aus den frisch geladenen Kategorien
  // dieses Reiters. "Wunsch an das Gerüst": eine exportierte Invalidierungsfunktion
  // für kategorieOptionsKey würde diesen lokalen Ersatz überflüssig machen.
  function patchZentraleKategorieFilterFallsAktiv() {
    // Gerüst-Cache für #filter-kategorie ungültig machen (Ereignis aus app.js, P30b/P33), damit der
    // Kopf-Filter auch nach einem späteren Sparten-Rückwechsel frisch lädt.
    window.dispatchEvent(new CustomEvent('neu:kategorien-geaendert'));
    const sel = document.querySelector('#filter-kategorie');
    if (!sel) return;
    const globalSparte = state.filter ? state.filter.sparteId : state.sparteId;
    if (String(globalSparte || '') !== String(local.activeSparteId || '')) return;
    const behalten = sel.value;
    const aktive = local.kategorien.filter(k => k.aktiv);
    sel.innerHTML = '<option value="">alle</option>' + aktive.map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join('');
    const gueltig = aktive.some(k => String(k.id) === behalten);
    sel.value = gueltig ? behalten : '';
    if (!gueltig && behalten) {
      if (state.filter) state.filter.kategorieId = '';
      try { localStorage.setItem('neu-kategorie', ''); } catch { /* Storage kann fehlen */ }
    }
  }

  function renderTabs() {
    const el = root.querySelector('#k-tabs');
    el.innerHTML = (state.sparten || []).map(s => `<button type="button" class="${String(s.id) === String(local.activeSparteId) ? 'active' : ''}" data-sparte="${s.id}"><span class="sdot" style="--dot:${esc(s.farbe || 'var(--info)')}"></span>${esc(s.name)}</button>`).join('');
    el.querySelectorAll('[data-sparte]').forEach(btn => {
      btn.onclick = () => {
        if (String(btn.dataset.sparte) === String(local.activeSparteId)) return;
        ladeSparte(btn.dataset.sparte);
      };
    });
  }

  function renderTable() {
    const el = root.querySelector('#k-table');
    const head = `<thead><tr><th style="text-align:left">Kategorie</th><th style="text-align:left">Richtung</th><th style="text-align:left">Stichwörter</th><th>Summe ${jahr}</th><th>Ø je Monat</th><th></th></tr></thead>`;
    const body = local.kategorien.map(k => {
      const row = local.matrix[k.id];
      const werte = row ? row.werte[String(jahr)] : null;
      const summe = werte ? werte.einnahmen_cent + werte.ausgaben_cent : null;
      const avgObj = row ? row.monatsdurchschnitt_cent[String(jahr)] : null;
      const avg = avgObj ? avgObj.einnahmen_cent + avgObj.ausgaben_cent : null;
      const kws = local.stichwortRegeln.filter(r => r.aktiv && String(r.ziel_kategorie_id) === String(k.id));
      const chips = kws.map(r => `<span class="chip">${esc(r.bedingung_text)}<button type="button" class="x" data-remove-regel="${r.id}" aria-label="Stichwort ${esc(r.bedingung_text)} entfernen">×</button></span>`).join('');
      const richtungLabel = {einnahme: 'Einnahme', ausgabe: 'Ausgabe', beides: 'beides'}[k.richtung] || k.richtung;
      return `<tr class="${k.aktiv ? '' : 'inactive'}" data-id="${k.id}">
          <td style="text-align:left"><span class="cat"><span class="kname">${esc(k.name)}</span>${k.aktiv ? '' : ' <span class="pill">stillgelegt</span>'}</span></td>
          <td style="text-align:left" class="muted">${esc(richtungLabel)}</td>
          <td style="text-align:left"><div class="kwedit">${chips}<input placeholder="+ Stichwort" data-add-regel="${k.id}" maxlength="60"></div></td>
          <td>${summe != null ? fmtEur(summe) : '–'}</td>
          <td>${avg != null ? fmtEur(avg) : '–'}</td>
          <td><span class="act"><button type="button" data-rename="${k.id}">umbenennen</button><button type="button" data-toggle="${k.id}">${k.aktiv ? 'stilllegen' : 'aktivieren'}</button></span></td>
        </tr>`;
    }).join('');
    el.innerHTML = head + '<tbody>' + (body || '<tr><td colspan="6" class="muted">Keine Kategorien in dieser Sparte.</td></tr>') + '</tbody>';

    el.querySelectorAll('[data-rename]').forEach(btn => {
      btn.onclick = () => {
        const k = local.kategorien.find(x => String(x.id) === btn.dataset.rename);
        if (k) startRename(btn.closest('tr'), k);
      };
    });
    el.querySelectorAll('[data-toggle]').forEach(btn => {
      btn.onclick = () => {
        const k = local.kategorien.find(x => String(x.id) === btn.dataset.toggle);
        if (k) toggleAktiv(k);
      };
    });
    el.querySelectorAll('[data-remove-regel]').forEach(btn => {
      btn.onclick = () => stichwortEntfernen(Number(btn.dataset.removeRegel));
    });
    el.querySelectorAll('[data-add-regel]').forEach(input => {
      input.addEventListener('keydown', e => {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        const k = local.kategorien.find(x => String(x.id) === input.dataset.addRegel);
        if (k) stichwortHinzufuegen(input, k);
      });
    });
  }

  function startRename(tr, k) {
    const span = tr.querySelector('.kname');
    // QA1-05: bei schneller Doppel-Interaktion (z.B. Klick auf "umbenennen"
    // waehrend ein Blur-Speichervorgang die Zeile bereits neu rendert) kann
    // die Zelle bereits im Bearbeiten-Zustand sein oder gerade neu aufgebaut
    // werden -- dann existiert kein .kname-Element mehr.
    if (!span) return;
    const input = document.createElement('input');
    input.className = 'name-edit';
    input.value = k.name;
    span.replaceWith(input);
    input.focus();
    input.select();
    let erledigt = false;
    async function speichern() {
      if (erledigt) return;
      erledigt = true;
      const neu = input.value.trim();
      if (!neu) {
        // QA1-04: bisher verpuffte ein leeres Feld ohne jede Rueckmeldung.
        toast('Name darf nicht leer sein.');
        renderTable();
        return;
      }
      if (neu === k.name) { renderTable(); return; }
      try {
        const aktualisiert = await api(`/kategorien/${k.id}`, {
          method: 'PATCH', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({name: neu}), bereichId: state.bereichId,
        });
        k.name = aktualisiert.name;
        toast(`„${aktualisiert.name}“ gespeichert.`);
        patchZentraleKategorieFilterFallsAktiv();
      } catch (error) {
        toast(error.detail || error.message || 'Umbenennen fehlgeschlagen.');
      }
      renderTable();
    }
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); speichern(); }
      if (e.key === 'Escape') { erledigt = true; renderTable(); }
    });
    input.addEventListener('blur', speichern);
  }

  async function toggleAktiv(k) {
    try {
      const aktualisiert = await api(`/kategorien/${k.id}`, {
        method: 'PATCH', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({aktiv: !k.aktiv}), bereichId: state.bereichId,
      });
      k.aktiv = aktualisiert.aktiv;
      toast(k.aktiv ? `„${k.name}“ ist wieder aktiv.` : `„${k.name}“ stillgelegt, alte Buchungen bleiben.`);
      patchZentraleKategorieFilterFallsAktiv();
      renderTable();
    } catch (error) {
      toast(error.detail || error.message || 'Aktion fehlgeschlagen.');
    }
  }

  async function stichwortHinzufuegen(input, k) {
    const wort = input.value.trim().toLowerCase();
    if (!wort) return;
    try {
      const regel = await api('/regeln', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: wort, bedingung_text: wort, ziel_kategorie_id: k.id, quelle: 'stichwort'}),
        bereichId: state.bereichId,
      });
      local.stichwortRegeln.push(regel);
      toast(`Stichwort „${wort}“ gemerkt.`);
      renderTable();
    } catch (error) {
      toast(error.detail || error.message || 'Stichwort konnte nicht angelegt werden.');
    }
  }

  async function stichwortEntfernen(regelId) {
    try {
      await api(`/regeln/${regelId}`, {
        method: 'PATCH', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({aktiv: false}), bereichId: state.bereichId,
      });
      local.stichwortRegeln = local.stichwortRegeln.filter(r => r.id !== regelId);
      toast('Stichwort entfernt.');
      renderTable();
    } catch (error) {
      toast(error.detail || error.message || 'Stichwort konnte nicht entfernt werden.');
    }
  }

  function renderGruppen() {
    const el = root.querySelector('#k-gruppen');
    if (!local.gruppen.length) { el.innerHTML = '<p class="muted">Keine Gruppen angelegt.</p>'; return; }
    const berechnet = local.gruppen.map(g => ({
      gruppe: g,
      wert: (g.kategorie_ids || []).reduce((summe, id) => summe + (local.matrixBereich[id]?.ausgaben_cent || 0), 0),
    })).sort((a, b) => b.wert - a.wert);
    const max = (berechnet[0] && berechnet[0].wert) || 1;
    el.innerHTML = berechnet.map(({gruppe, wert}) => `
      <div class="hbar">
        <div class="name"><span>${esc(gruppe.name)}</span><span class="tag">${gruppe.kategorie_ids.length} Kat.</span></div>
        <div class="track"><div class="fill" style="width:${(wert / max * 100).toFixed(1)}%"></div></div>
        <div class="v">${fmtEur(wert)}</div>
        <div class="p">${jahr}</div>
      </div>`).join('');
  }

  function renderRegeln() {
    const el = root.querySelector('#k-regeln');
    const aktive = local.gelernteRegeln.filter(r => r.aktiv);
    const head = `<thead><tr><th style="text-align:left">Wenn der Text enthält</th><th style="text-align:left">dann</th><th style="text-align:left">Konto</th><th>gelernt am</th><th></th></tr></thead>`;
    const body = aktive.map(r => {
      const kat = local.alleKategorien.find(x => String(x.id) === String(r.ziel_kategorie_id));
      let ziel = kat ? esc(kat.name) : `Kategorie #${r.ziel_kategorie_id}`;
      if (kat && String(kat.sparte_id) !== String(local.activeSparteId)) {
        const sparte = (state.sparten || []).find(s => String(s.id) === String(kat.sparte_id));
        if (sparte) ziel += ` <span class="muted">${esc(sparte.name)}</span>`;
      }
      const konto = r.bankkonto_id ? local.konten.find(x => String(x.id) === String(r.bankkonto_id)) : null;
      const gelernt = r.erstellt_am ? fmtDate(String(r.erstellt_am).slice(0, 10)) : '–';
      return `<tr data-id="${r.id}">
          <td style="text-align:left">${esc(r.bedingung_text)}</td>
          <td style="text-align:left"><span class="zk">${ziel}</span></td>
          <td style="text-align:left" class="muted">${konto ? esc(konto.name) : '–'}</td>
          <td class="muted">${gelernt}</td>
          <td><span class="act"><button type="button" data-abschalten="${r.id}">abschalten</button></span></td>
        </tr>`;
    }).join('');
    el.innerHTML = head + '<tbody>' + (body || '<tr><td colspan="5" class="muted">Keine gelernten Merkregeln.</td></tr>') + '</tbody>';
    el.querySelectorAll('[data-abschalten]').forEach(btn => {
      btn.onclick = () => regelAbschalten(Number(btn.dataset.abschalten));
    });
  }

  async function regelAbschalten(regelId) {
    try {
      await api(`/regeln/${regelId}`, {
        method: 'PATCH', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({aktiv: false}), bereichId: state.bereichId,
      });
      local.gelernteRegeln = local.gelernteRegeln.filter(r => r.id !== regelId);
      toast('Regel abgeschaltet.');
      renderRegeln();
    } catch (error) {
      toast(error.detail || error.message || 'Regel konnte nicht abgeschaltet werden.');
    }
  }

  async function ladeSparte(sparteId) {
    local.activeSparteId = sparteId;
    renderTabs();
    if (!sparteId) { local.kategorien = []; local.matrix = {}; renderTable(); return; }
    root.querySelector('#k-table').innerHTML = '<tbody><tr><td class="muted">Lädt …</td></tr></tbody>';
    try {
      const [kategorien, matrix] = await Promise.all([
        api('/kategorien', {params: {sparte_id: sparteId, nur_aktive: 'false'}, bereichId: state.bereichId}),
        api('/jahresmatrix', {params: {sparte_id: sparteId, jahre: String(jahr)}, bereichId: state.bereichId}),
      ]);
      local.kategorien = kategorien;
      local.matrix = {};
      for (const row of matrix.zeilen) local.matrix[row.kategorie_id] = row;
      renderTable();
    } catch (error) {
      toast(error.detail || error.message || 'Kategorien konnten nicht geladen werden.');
      root.querySelector('#k-table').innerHTML = '<tbody><tr><td class="muted">Fehler beim Laden.</td></tr></tbody>';
    }
  }

  // Seitenweite Daten (Stichwörter aller Kategorien, gelernte Regeln, alle Kategorien
  // des Bereichs, Konten, Gruppen, bereichsweite Jahresmatrix) einmal beim Laden der
  // Seite, nicht je Reiterwechsel (Karte, Abschnitt 3).
  async function ladeSeiteweit() {
    try {
      const [stichwort, gelernt, alleKategorien, konten, gruppen, bereichsMatrix] = await Promise.all([
        api('/regeln', {params: {quelle: 'stichwort'}, bereichId: state.bereichId}),
        api('/regeln', {params: {quelle: 'gelernt'}, bereichId: state.bereichId}),
        api('/kategorien', {bereichId: state.bereichId}),
        api('/konten', {bereichId: state.bereichId}),
        api('/globalgruppen', {bereichId: state.bereichId}),
        api('/jahresmatrix', {params: {jahre: String(jahr)}, bereichId: state.bereichId}),
      ]);
      local.stichwortRegeln = stichwort;
      local.gelernteRegeln = gelernt;
      local.alleKategorien = alleKategorien;
      local.konten = konten;
      local.gruppen = gruppen;
      local.matrixBereich = {};
      for (const row of bereichsMatrix.zeilen) {
        local.matrixBereich[row.kategorie_id] = row.werte[String(jahr)] || {einnahmen_cent: 0, ausgaben_cent: 0};
      }
      renderTable();
      renderGruppen();
      renderRegeln();
    } catch (error) {
      toast(error.detail || error.message || 'Daten konnten nicht geladen werden.');
    }
  }

  renderTabs();
  await Promise.all([ladeSparte(local.activeSparteId), ladeSeiteweit()]);
}
