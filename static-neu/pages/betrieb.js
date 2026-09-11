// P72 – Betriebsseite: Überblick über Schema/Sicherung/Foto-Auswertung/KI-Vorschlag/
// Instanz aus GET /api/betrieb/uebersicht (app/routers/betrieb.py) sowie ein Knopf,
// der POST /api/betrieb/sicherung auslöst. Rein lesend bis auf diesen einen Knopf.
import {api} from '../api.js';
import {esc} from '../format.js';
import {toast} from '../ui.js';

let cssGeladen = false;
function ladeCss() {
  if (cssGeladen) return;
  cssGeladen = true;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = './pages/betrieb.css';
  document.head.appendChild(link);
}

export async function render(root, state) {
  ladeCss();
  const ctx = {root, state, daten: null, sichernLaeuft: false};
  root.innerHTML = '<section class="card"><p class="muted">Betriebsstatus wird geladen …</p></section>';
  await ladeUebersicht(ctx);
}

async function ladeUebersicht(ctx) {
  try {
    ctx.daten = await api('/betrieb/uebersicht', {bereichId: ctx.state.bereichId});
  } catch (error) {
    ctx.root.innerHTML = `<section class="card"><p class="muted">Betriebsstatus konnte nicht geladen werden: ${esc(error.detail || error.message)}</p></section>`;
    toast(error.detail || error.message);
    return;
  }
  zeichne(ctx);
}

function zweitzielText(zweitziel) {
  if (zweitziel === 'ok') return 'in Ordnung';
  if (zweitziel === 'nicht konfiguriert' || zweitziel === 'nicht_konfiguriert') return 'nicht konfiguriert';
  if (zweitziel === 'fehlt') return 'fehlt';
  if (zweitziel && typeof zweitziel === 'object' && zweitziel.fehler) return `Fehler: ${zweitziel.fehler}`;
  return String(zweitziel ?? '–');
}

function zeichne(ctx) {
  const d = ctx.daten;
  const {schema, sicherung, ollama, ki_vorschlag_aktiv: kiAktiv, frontend, instanz, auswertungswarteschlange: warteschlange} = d;

  const belegeText = sicherung.belege_fehlend > 0
    ? `<span class="bt-schlecht">${sicherung.belege_fehlend} fehlend</span>`
    : `<span class="bt-gut">${sicherung.belege_ok} ok</span>`;

  ctx.root.innerHTML = `
    <div class="bt-grid">
      <section class="card bt-card">
        <div class="card-head"><h2>Datenbank</h2></div>
        <p class="bt-row"><span>Schema</span><b>Version ${schema.aktuell}</b></p>
        <p class="bt-row"><span>Ausstehende Migrationen</span><b>${schema.anstehend.length ? esc(schema.anstehend.join(', ')) : 'keine'}</b></p>
        <p class="bt-row"><span>Zugriff</span>${d.schreibgeschuetzt
          ? '<b class="bt-schlecht">schreibgeschützt</b>'
          : '<b class="bt-gut">Lesen/Schreiben</b>'}</p>
      </section>

      <section class="card bt-card">
        <div class="card-head"><h2>Sicherung</h2></div>
        <p class="bt-row"><span>Letzte Sicherung</span><b>${sicherung.letzte ? esc(sicherung.letzte) : 'noch keine'}</b></p>
        <p class="bt-row"><span>Datenbank</span>${sicherung.db_ok ? '<b class="bt-gut">ok</b>' : '<b class="bt-schlecht">nicht ok</b>'}</p>
        <p class="bt-row"><span>Belege</span>${belegeText}</p>
        <p class="bt-row"><span>Zweitziel</span><b>${esc(zweitzielText(sicherung.zweitziel))}</b></p>
        <button class="btn primary" id="bt-sichern-jetzt" type="button" ${ctx.sichernLaeuft ? 'disabled' : ''}>
          ${ctx.sichernLaeuft ? 'Sicherung läuft …' : 'Jetzt sichern'}
        </button>
      </section>

      <section class="card bt-card">
        <div class="card-head"><h2>Foto-Auswertung</h2></div>
        <p class="bt-row"><span>Modell</span><b>${esc(ollama.modell)}</b></p>
        <p class="bt-row"><span>Ollama erreichbar</span>${ollama.erreichbar
          ? '<b class="bt-gut">ja</b>'
          : '<b class="bt-schlecht">nein</b>'}</p>
        <p class="bt-row"><span>Warteschlange</span><b>${warteschlange.offen} offen · ${warteschlange.laeuft} laufend${warteschlange.fehler ? ` · <span class="bt-schlecht">${warteschlange.fehler} Fehler</span>` : ''}</b></p>
      </section>

      <section class="card bt-card">
        <div class="card-head"><h2>KI-Vorschlag</h2></div>
        <p class="bt-row"><span>Status</span>${kiAktiv ? '<b class="bt-gut">an</b>' : '<b class="bt-schlecht">aus</b>'}</p>
      </section>

      <section class="card bt-card">
        <div class="card-head"><h2>Instanz</h2></div>
        <p class="bt-row"><span>Instanz</span><b>${esc(instanz)}</b></p>
        <p class="bt-row"><span>Frontend</span><b>${esc(frontend)}</b></p>
      </section>
    </div>`;

  document.querySelector('#bt-sichern-jetzt').onclick = () => sicherungAusloesen(ctx);
}

async function sicherungAusloesen(ctx) {
  ctx.sichernLaeuft = true;
  zeichne(ctx);
  try {
    await api('/betrieb/sicherung', {method: 'POST', bereichId: ctx.state.bereichId});
    toast('Sicherung abgeschlossen.');
  } catch (error) {
    if (error.status === 409) {
      toast('Es läuft bereits eine Sicherung.');
    } else if (error.status === 503) {
      toast('Datenbank ist schreibgeschützt – Sicherung nicht möglich.');
    } else {
      toast(error.detail || error.message);
    }
  } finally {
    ctx.sichernLaeuft = false;
    await ladeUebersicht(ctx);
  }
}
