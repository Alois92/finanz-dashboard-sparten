// P52: Kredit-Oberfläche. Macht die bestehende Kredit-Logik aus P14 bedienbar
// (Anlegen, Jahresabschluss mit Zins/Restschuld, Ratentabelle mit Zins-/Tilgungsanteil,
// Zuordnen bestehender Buchungen). Ruft ausschließlich die dort definierten Endpunkte
// auf: /api/kredite, /api/kredite/{id}/jahre/{jahr}, /api/kredite/{id}/raten,
// /api/kredite/{id}/raten/zuordnen. Keine Backend-Änderung.
import {api} from '../api.js';
import {esc, fmtEur, fmtDate, parseBetrag} from '../format.js';
import {toast, drill} from '../ui.js';

const HEUTE = new Date().toISOString().slice(0, 10);
const JAHR_JETZT = new Date().getFullYear();

function cssHref(){return new URL('./kredit.css', import.meta.url).href}
function ensureCss(){
  if(!document.querySelector(`link[href="${cssHref()}"]`)){
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = cssHref();
    document.head.appendChild(link);
  }
}

function closeDrill(){document.querySelector('#drill').close()}
function centFromInput(value){
  const n = parseBetrag(value);
  return n == null ? null : Math.round(n * 100);
}
function fmtBetragFeld(cent){
  return ((cent || 0) / 100).toLocaleString('de-AT', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function jahreListe(k){
  const jahre = new Set((k.jahre || []).map(j => j.jahr));
  jahre.add(JAHR_JETZT);
  return [...jahre].sort((a, b) => b - a);
}
function statusPille(j){
  if(!j) return '<span class="badge badge-muted">geschätzt</span>';
  return j.status === 'bestaetigt'
    ? '<span class="badge badge-ok">bestätigt</span>'
    : '<span class="badge badge-muted">geschätzt</span>';
}

async function loadKredite(state){
  const alle = await api('/kredite');
  return state.sparteId ? alle.filter(k => String(k.sparte_id) === String(state.sparteId)) : alle;
}

async function kategorienFuerSparte(sparteId){
  if(!sparteId) return [];
  try{ return await api('/kategorien', {params: {sparte_id: sparteId, nur_aktive: 'true'}}) }
  catch{ return [] }
}

/* ---------- Kredit anlegen (Formular, im Leerzustand inline, sonst im Dialog) ---------- */

function kreditFormHtml(state, sparteId){
  const sparteOptions = state.sparten.map(s => `<option value="${s.id}" ${String(s.id) === String(sparteId) ? 'selected' : ''}>${esc(s.name)}</option>`).join('');
  return `
    <form id="kredit-form">
      <label class="field">Sparte<select name="sparte_id">${sparteOptions}</select></label>
      <label class="field">Name<input name="name" required maxlength="120"></label>
      <label class="field">Monatsrate in €<input name="monatsrate" inputmode="decimal" required placeholder="0,00"></label>
      <label class="field">Beginn<input type="date" name="beginn" value="${HEUTE}" required></label>
      <label class="field">Zinssatz in % (optional)<input name="zinssatz" inputmode="decimal" placeholder="z. B. 3,5"></label>
      <label class="field">Kategorie Zinsen<select name="kategorie_zins_id" id="kredit-kat-zins"></select></label>
      <label class="field">Kategorie Tilgung<select name="kategorie_rate_id" id="kredit-kat-rate"></select></label>
      <p class="field-error" id="kredit-form-error" hidden></p>
      <button class="btn primary" type="submit">Kredit anlegen</button>
    </form>`;
}

async function fuelleKategorien(form, sparteId){
  const kats = await kategorienFuerSparte(sparteId);
  const options = kats.map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join('') || '<option value="">– keine Kategorie –</option>';
  form.querySelector('#kredit-kat-zins').innerHTML = options;
  form.querySelector('#kredit-kat-rate').innerHTML = options;
}

function wireKreditForm(form, state, reload, onSuccess){
  const sparteSel = form.elements['sparte_id'];
  fuelleKategorien(form, sparteSel.value);
  sparteSel.onchange = () => fuelleKategorien(form, sparteSel.value);
  form.onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const box = form.querySelector('#kredit-form-error');
    const monatsrate = centFromInput(fd.get('monatsrate'));
    if(monatsrate == null || monatsrate <= 0){
      box.textContent = 'Monatsrate ist ungültig.'; box.hidden = false; return;
    }
    let zinssatz = null;
    const zinssatzRaw = fd.get('zinssatz');
    if(zinssatzRaw){
      const z = parseBetrag(zinssatzRaw);
      if(z == null){ box.textContent = 'Zinssatz ist ungültig.'; box.hidden = false; return; }
      zinssatz = z / 100;
    }
    const katZins = fd.get('kategorie_zins_id');
    const katRate = fd.get('kategorie_rate_id');
    if(!katZins || !katRate){
      box.textContent = 'Bitte Kategorie für Zinsen und Tilgung wählen.'; box.hidden = false; return;
    }
    const body = {
      sparte_id: Number(fd.get('sparte_id')),
      name: fd.get('name'),
      monatsrate_cent: monatsrate,
      beginn: fd.get('beginn'),
      zinssatz,
      kategorie_zins_id: Number(katZins),
      kategorie_rate_id: Number(katRate),
    };
    try{
      await api('/kredite', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      toast('Kredit angelegt.');
      if(onSuccess) onSuccess();
      reload();
    }catch(error){
      box.textContent = error.detail || error.message; box.hidden = false;
    }
  };
}

function openAnlegenDialog(state, reload){
  drill('Kredit anlegen', kreditFormHtml(state, state.sparteId));
  const form = document.querySelector('#kredit-form');
  wireKreditForm(form, state, reload, closeDrill);
}

function drawAnlegenForm(container, state, reload){
  container.innerHTML = kreditFormHtml(state, state.sparteId);
  const form = container.querySelector('#kredit-form');
  wireKreditForm(form, state, reload, null);
}

/* ---------- Jahr bestätigen ---------- */

async function openJahrDialog(k, jahr, reload){
  let belege = [];
  try{ belege = await api('/belege', {params: {sparte_id: k.sparte_id}}) }
  catch{ belege = [] }
  const belegOptions = `<option value="">– kein Beleg –</option>` + belege.map(b => `<option value="${b.id}">${esc(b.dateiname)}</option>`).join('');
  drill(`Jahr ${jahr} bestätigen`, `
    <p class="muted">${esc(k.name)} · Jahreszins und Restschuld laut Kredit-Kontoauszug. Abweichungen (fehlende Raten, andere Ratenbeträge) werden angezeigt, nie stillschweigend übernommen.</p>
    <form id="kredit-jahr-form">
      <label class="field">Jahreszins in €<input name="zins" inputmode="decimal" required placeholder="0,00"></label>
      <label class="field">Restschuld in € (optional)<input name="restschuld" inputmode="decimal" placeholder="0,00"></label>
      <label class="field">Beleg (optional)<select name="beleg_id">${belegOptions}</select></label>
      <p class="field-error" id="kredit-jahr-error" hidden></p>
      <button class="btn primary" type="submit">Bestätigen</button>
    </form>
  `);
  const form = document.querySelector('#kredit-jahr-form');
  form.onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const box = document.querySelector('#kredit-jahr-error');
    const zins = centFromInput(fd.get('zins'));
    if(zins == null){ box.textContent = 'Zins ist ungültig.'; box.hidden = false; return; }
    const restschuldRaw = fd.get('restschuld');
    const restschuld = restschuldRaw ? centFromInput(restschuldRaw) : null;
    if(restschuldRaw && restschuld == null){ box.textContent = 'Restschuld ist ungültig.'; box.hidden = false; return; }
    const body = {zins_cent: zins, restschuld_cent: restschuld, beleg_id: fd.get('beleg_id') ? Number(fd.get('beleg_id')) : null};
    try{
      const res = await api(`/kredite/${k.id}/jahre/${jahr}`, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      // QA3-06: Dialog nach erfolgreichem Speichern schließen statt liegen zu
      // lassen - er lag zuvor als Overlay über der Seite und fing Klicks auf
      // darunterliegende Elemente ohne erkennbaren Grund ab. Abweichungen
      // gehen dabei nicht verloren: der Toast nennt sie.
      document.querySelector('#drill').close();
      toast(res.abweichungen && res.abweichungen.length
        ? `Jahr bestätigt, mit Abweichung: ${res.abweichungen.join(' ')}`
        : `Jahr bestätigt: ${res.raten} Rate(n), ${fmtEur(res.verteilt_cent)} Zins verteilt.`);
      reload();
    }catch(error){
      box.textContent = error.detail || error.message; box.hidden = false;
    }
  };
}

/* ---------- Rate erfassen ---------- */

function openRateDialog(k, reload){
  drill('Rate erfassen', `
    <p class="muted">${esc(k.name)}</p>
    <form id="kredit-rate-form">
      <label class="field">Datum<input type="date" name="datum" value="${HEUTE}" max="${HEUTE}" required></label>
      <label class="field">Betrag in €<input name="betrag" inputmode="decimal" value="${fmtBetragFeld(k.monatsrate_cent)}" required></label>
      <p class="field-error" id="kredit-rate-error" hidden></p>
      <button class="btn primary" type="submit">Rate erfassen</button>
    </form>
  `);
  const form = document.querySelector('#kredit-rate-form');
  form.onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const box = document.querySelector('#kredit-rate-error');
    const betrag = centFromInput(fd.get('betrag'));
    if(betrag == null){ box.textContent = 'Betrag ist ungültig.'; box.hidden = false; return; }
    const body = {datum: fd.get('datum'), betrag_cent: betrag, client_request_id: crypto.randomUUID()};
    try{
      const res = await api(`/kredite/${k.id}/raten`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      toast(res.hinweis || 'Rate erfasst.');
      closeDrill();
      reload();
    }catch(error){
      box.textContent = error.detail || error.message; box.hidden = false;
    }
  };
}

/* ---------- Bestehende Buchungen zuordnen ---------- */

// GET /api/kredite liefert kategorie_rate_id nicht mit (siehe _listeintrag in
// app/routers/kredite.py) - dieses Paket darf den Router nicht ändern (Nicht-Ziel
// laut Karte). Die Kategorie wird deshalb aus einer bereits zugeordneten Rate
// desselben Kredits abgeleitet (buchungszeile mit neutral=1, aus derselben
// /buchungen-Antwort). Ohne mindestens eine bestehende Rate ist die Kategorie nicht
// bekannt und die Zuordnen-Liste bleibt leer (siehe Bericht, "Wunsch an das Gerüst").
async function ladeZuordnenKandidaten(state, k){
  // Explizit von/bis statt nur sparte_id: ohne Zeitraum setzt rechenbasis.auswertungsfilter
  // sonst das aktuelle Stichtagsjahr an (siehe app/rechenbasis.py), und Raten aus Vorjahren
  // ohne Kredit-Zuordnung würden in der Kandidatenliste sonst stillschweigend fehlen.
  const antwort = await api('/buchungen', {params: {sparte_id: k.sparte_id, von: k.beginn, bis: HEUTE, limit: 500}, bereichId: state.bereichId});
  const buchungen = antwort.buchungen || [];
  // Seit dem Kopf-Nachzug liefert GET /api/kredite kategorie_rate_id direkt; die Herleitung aus einer
  // bestehenden Rate bleibt nur als Rueckfall fuer aeltere Antworten.
  const vorhandeneRate = buchungen.find(b => b.kredit_id === k.id && (b.zeilen || []).some(z => z.neutral));
  const kategorieRateId = k.kategorie_rate_id ?? (vorhandeneRate ? vorhandeneRate.zeilen.find(z => z.neutral).kategorie_id : null);
  if(kategorieRateId == null) return [];
  return buchungen.filter(b =>
    b.kredit_id == null &&
    b.typ === 'ausgabe' &&
    (b.zeilen || []).some(z => String(z.kategorie_id) === String(kategorieRateId))
  );
}

/* ---------- Detailbereich (Jahr, Ratentabelle, Zuordnen) ---------- */

function detailHtml(k, jahr, raten, kandidaten){
  const jEintrag = (k.jahre || []).find(x => x.jahr === jahr);
  return `
    <div class="kredit-jahr-detail">
      <div class="kredit-jahr-kopf">
        <div>
          <b>Jahr ${jahr}</b>
          ${statusPille(jEintrag)}
          ${jEintrag && jEintrag.restschuld_cent != null ? `<span class="muted"> · Restschuld ${fmtEur(jEintrag.restschuld_cent)}</span>` : ''}
        </div>
        <div class="kredit-jahr-actions">
          <button class="btn small" data-jahr-bestaetigen>Jahr bestätigen</button>
          <button class="btn small" data-rate-erfassen>Rate erfassen</button>
        </div>
      </div>
      <div class="table-wrap"><table class="tbl"><thead><tr><th>Datum</th><th>Rate</th><th>Zins</th><th>Tilgung</th><th>Status</th></tr></thead><tbody>
        ${raten.map(r => `<tr><td class="muted">${fmtDate(r.datum)}</td><td>${fmtEur(r.betrag_cent)}</td><td>${fmtEur(r.zins_cent)}</td><td>${fmtEur(r.tilgung_cent)}</td><td>${r.status === 'bestaetigt' ? 'bestätigt' : 'geschätzt'}</td></tr>`).join('')
          || '<tr><td colspan="5" class="muted">Keine Raten in diesem Jahr.</td></tr>'}
      </tbody></table></div>
      <div class="kredit-zuordnen">
        <h3>Bestehende Buchungen zuordnen</h3>
        ${kandidaten.length ? `
          <div class="table-wrap"><table class="tbl"><thead><tr><th></th><th>Datum</th><th>Text</th><th>Betrag</th></tr></thead><tbody>
            ${kandidaten.map(b => `<tr><td><input type="checkbox" data-buchung="${b.id}" aria-label="Buchung ${esc(b.text || '')} auswählen"></td><td class="muted">${fmtDate(b.datum)}</td><td>${esc(b.text || '')}</td><td>${fmtEur(b.betrag_cent)}</td></tr>`).join('')}
          </tbody></table></div>
          <button class="btn small" data-zuordnen-go>Zuordnen</button>
        ` : '<p class="muted">Keine passenden Buchungen ohne Kredit-Zuordnung gefunden.</p>'}
      </div>
    </div>`;
}

function verdrahteDetail(detailEl, state, k, reload){
  const jahr = Number(detailEl.closest('[data-kredit]').dataset.aktivJahr);
  detailEl.querySelector('[data-jahr-bestaetigen]').onclick = () => openJahrDialog(k, jahr, reload);
  detailEl.querySelector('[data-rate-erfassen]').onclick = () => openRateDialog(k, reload);
  const goBtn = detailEl.querySelector('[data-zuordnen-go]');
  if(goBtn){
    goBtn.onclick = async () => {
      const ids = [...detailEl.querySelectorAll('[data-buchung]:checked')].map(cb => Number(cb.dataset.buchung));
      if(!ids.length){ toast('Keine Buchung ausgewählt.'); return; }
      try{
        await api(`/kredite/${k.id}/raten/zuordnen`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({buchung_ids: ids})});
        toast(`${ids.length} Buchung(en) zugeordnet.`);
        reload();
      }catch(error){
        toast(error.detail || error.message);
      }
    };
  }
}

/* ---------- Kredit-Karten ---------- */

function kreditCardHtml(k, local){
  const offen = local.openId === k.id;
  const jahre = jahreListe(k);
  const aktivesJahr = local.jahrByKredit[k.id] || jahre[0];
  const pillen = jahre.map(jahr => {
    const j = (k.jahre || []).find(x => x.jahr === jahr);
    const aktiv = offen && jahr === aktivesJahr;
    return `<button type="button" class="pill kredit-jahr-pill ${aktiv ? 'active' : ''}" data-jahr="${jahr}">
      ${jahr} ${statusPille(j)}${j && j.zins_cent != null ? ' · Zins ' + fmtEur(j.zins_cent) : ''}${j && j.restschuld_cent != null ? ' · Rest ' + fmtEur(j.restschuld_cent) : ''}
    </button>`;
  }).join('');
  return `
    <div class="kredit-card" data-kredit="${k.id}" data-aktiv-jahr="${aktivesJahr}">
      <div class="kredit-head" data-toggle role="button" tabindex="0">
        <div class="kredit-name">${esc(k.name)}</div>
        <div class="kredit-sub muted">Monatsrate ${fmtEur(k.monatsrate_cent)} · seit ${fmtDate(k.beginn)}${k.zinssatz != null ? ` · Zinssatz ${(k.zinssatz * 100).toLocaleString('de-AT', {maximumFractionDigits: 2})} %` : ''}</div>
      </div>
      <div class="kredit-jahre">${pillen}</div>
      <div class="kredit-detail" data-detail ${offen ? '' : 'hidden'}></div>
    </div>`;
}

async function draw(root, state, kredite, local, reload){
  if(local.openId && !kredite.some(k => k.id === local.openId)) local.openId = null;

  if(!kredite.length){
    root.innerHTML = `
      <section class="card">
        <div class="card-head"><h2>Kredite</h2></div>
        <p class="muted">Kein Kredit erfasst.</p>
        <div id="kredit-neu-form"></div>
      </section>`;
    drawAnlegenForm(root.querySelector('#kredit-neu-form'), state, reload);
    return;
  }

  root.innerHTML = `
    <section class="card">
      <div class="card-head"><h2>Kredite</h2><button class="btn primary" id="kredit-neu">+ Kredit anlegen</button></div>
      <div id="kredit-liste"></div>
    </section>`;
  root.querySelector('#kredit-neu').onclick = () => openAnlegenDialog(state, reload);

  const liste = root.querySelector('#kredit-liste');
  liste.innerHTML = kredite.map(k => kreditCardHtml(k, local)).join('');

  for(const k of kredite){
    const card = liste.querySelector(`[data-kredit="${k.id}"]`);
    const toggle = () => {
      local.openId = local.openId === k.id ? null : k.id;
      draw(root, state, kredite, local, reload);
    };
    card.querySelector('[data-toggle]').onclick = toggle;
    card.querySelector('[data-toggle]').onkeydown = e => { if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); toggle(); } };
    card.querySelectorAll('[data-jahr]').forEach(btn => {
      btn.onclick = () => {
        local.openId = k.id;
        local.jahrByKredit[k.id] = Number(btn.dataset.jahr);
        draw(root, state, kredite, local, reload);
      };
    });
  }

  if(local.openId){
    const k = kredite.find(x => x.id === local.openId);
    const jahr = local.jahrByKredit[k.id] || jahreListe(k)[0];
    local.jahrByKredit[k.id] = jahr;
    const detailEl = liste.querySelector(`[data-kredit="${k.id}"] [data-detail]`);
    detailEl.innerHTML = '<p class="muted">Lädt…</p>';
    try{
      const [raten, kandidaten] = await Promise.all([
        api(`/kredite/${k.id}/raten`, {params: {jahr}}),
        ladeZuordnenKandidaten(state, k),
      ]);
      detailEl.innerHTML = detailHtml(k, jahr, raten, kandidaten);
      verdrahteDetail(detailEl, state, k, reload);
    }catch(error){
      detailEl.innerHTML = `<p class="muted">Details konnten nicht geladen werden: ${esc(error.detail || error.message)}</p>`;
    }
  }
}

export function render(root, state){
  ensureCss();
  root.innerHTML = '<section class="card placeholder"><p class="muted">Lädt…</p></section>';
  const local = {openId: null, jahrByKredit: {}};
  const reload = () => loadKredite(state).then(kredite => draw(root, state, kredite, local, reload))
    .catch(error => {
      root.innerHTML = `<section class="card placeholder"><p>Kredite konnten nicht geladen werden: ${esc(error.detail || error.message)}</p></section>`;
      toast(error.detail || error.message);
    });
  reload();
}
