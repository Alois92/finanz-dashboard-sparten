import {api} from './api.js';
import {esc} from './format.js';
import {toast,drill,sheet,closeSheet} from './ui.js';

const routes={uebersicht:['Übersicht','uebersicht'],sparte:['Sparte','sparte'],erfassen:['Erfassen','erfassen'],buchungen:['Buchungen','buchungen'],konten:['Konten','konten'],kredit:['Kredit','kredit'],kategorien:['Kategorien','kategorien'],belege:['Belege','belege'],bankimport:['Bankimport','bankimport'],export:['Export','export'],betrieb:['Betrieb','betrieb']};

const initialSparteId=localStorage.getItem('neu-sparte')||'';
const initialJahr=localStorage.getItem('neu-jahr')||'';
const initialKategorieId=localStorage.getItem('neu-kategorie')||'';

const state={
  bereichId:Number(localStorage.getItem('neu-bereich')||1),
  theme:localStorage.getItem('neu-theme')||'dark',
  route:'uebersicht',
  sparteId:initialSparteId,
  year:initialJahr,
  bereiche:[],sparten:[],gruppen:[],jahre:[],
  // P30b: zentrales Filterobjekt (Jahr, Sparte, Kategorie), persistent in localStorage
  // wie neu-sparte. state.sparteId/state.year bleiben als Alias bestehen, weil die
  // bestehenden Seiten (P31 ff.) sie bereits direkt lesen; setFilter() haelt beide
  // Sichten synchron, damit keine der Seiten umgebaut werden muss.
  filter:{jahr:initialJahr,sparteId:initialSparteId,kategorieId:initialKategorieId},
};

let kategorieOptionsKey=null;
// Seiten, die Kategorien ändern (P33), melden das per Ereignis; der Optionen-Cache von #filter-kategorie wird dann beim nächsten Render neu geladen.
window.addEventListener('neu:kategorien-geaendert',()=>{kategorieOptionsKey=null});

// QA3-07: Tiefen-Link "#/sparte/<id>/<seite>" (z. B. aus der P52-Auftragskarte
// vorgeschlagen) fiel bisher auf die Sparte-Uebersicht zurueck, weil nur das
// erste Pfadsegment ausgewertet wurde. Die App fuehrt die Sparten-Auswahl
// nicht ueber URL-Segmente, sondern ueber den globalen Filter (state.filter.
// sparteId, siehe setFilter) - ein solcher Link setzt daher jetzt diesen
// Filter und loest zur eigentlichen Seite auf, statt sie zu verwerfen.
function currentRoute(){
  const raw=location.hash.replace(/^#\//,'')||'uebersicht';
  const teile=raw.split('/');
  if(teile[0]==='sparte'&&teile.length>=3&&/^\d+$/.test(teile[1])&&teile[2]!=='sparte'&&routes[teile[2]]){
    state.filter.sparteId=teile[1];
    state.sparteId=teile[1];
    localStorage.setItem('neu-sparte',teile[1]);
    return teile[2];
  }
  return routes[teile[0]]?teile[0]:'uebersicht';
}
function go(route){state.route=route;location.hash=`#/${route}`;render()}
function setTheme(theme){state.theme=theme;document.documentElement.dataset.theme=theme;localStorage.setItem('neu-theme',theme)}

// P30b: zentraler Filterwechsel. Aktualisiert state.filter und die bestehenden
// Alias-Felder state.year/state.sparteId, persistiert wie neu-sparte und rendert
// die aktive Seite neu - das war die Gerüst-Lücke (Jahr ohne onchange, Sparte ohne
// Re-Render), siehe docs/neubau/SCHULDEN.md.
function setFilter(patch){
  Object.assign(state.filter,patch);
  if('jahr' in patch){state.year=patch.jahr||'';localStorage.setItem('neu-jahr',state.year)}
  if('sparteId' in patch){
    state.sparteId=patch.sparteId||'';
    localStorage.setItem('neu-sparte',state.sparteId);
    // QA1-01: auf der Sparte-Seite die Wahl im Hash abbilden (Kopf-Dropdown/Sidebar setzten
    // bisher nie eine ID in die URL), damit sie teilbar bleibt und die Zurueck-Taste zwischen
    // Sparten wechseln kann. sparte.js liest die ID beim naechsten Render zurueck.
    if(state.route==='sparte'){
      const neuerHash=state.sparteId?`#/sparte/${state.sparteId}`:'#/sparte';
      if(location.hash!==neuerHash){location.hash=neuerHash;return}
    }
  }
  if('kategorieId' in patch){localStorage.setItem('neu-kategorie',state.filter.kategorieId||'')}
  render();
}

function drawSidebar(){
  const nav=Object.entries(routes).map(([key,[label]])=>`<button class="nav-item ${state.route===key?'active':''}" data-route="${key}"><span aria-hidden="true">${key==='erfassen'?'＋':'•'}</span>${label}</button>`).join('');
  const sparten=state.sparten.map(s=>`<button class="nav-item ${String(s.id)===String(state.sparteId)?'active':''}" data-sparte="${s.id}"><span class="dot" style="--dot:${esc(s.farbe||'var(--info)')}"></span>${esc(s.name)}</button>`).join('');
  document.querySelector('#sidebar').innerHTML=`<div class="brand"><span class="brand-mark">H</span><div><span class="brand-name">Hohenegg</span><span class="brand-sub">Finanzstudio · neu</span></div></div><div class="nav-group"><label class="nav-label">Bereich</label><select id="bereich-select" class="scope-sel" aria-label="Bereich">${state.bereiche.map(b=>`<option value="${b.id}" ${b.id===state.bereichId?'selected':''}>${esc(b.name)}</option>`).join('')}</select></div><nav class="nav-group" aria-label="Hauptnavigation">${nav}</nav><div class="nav-group"><div class="nav-label">Sparten</div>${sparten}<button class="nav-item" id="new-group">＋ Gruppe anlegen</button></div><div class="side-foot"><button class="nav-item" id="tools-toggle" aria-expanded="true">Werkzeuge⌄</button><a class="nav-item" href="/password-change.html">Passwort ändern</a><button class="nav-item" id="theme-toggle">${state.theme==='dark'?'☼':'☾'} Ansicht</button><button class="nav-item" id="logout">↪ Abmelden</button></div>`;
  document.querySelectorAll('[data-route]').forEach(b=>b.onclick=()=>go(b.dataset.route));
  // Sidebar-Sparten-Buttons setzen die Sparte zentral (vorher nur drawSidebar(), die
  // aktive Seite blieb auf dem alten Filter stehen).
  document.querySelectorAll('[data-sparte]').forEach(b=>b.onclick=()=>setFilter({sparteId:b.dataset.sparte}));
  document.querySelector('#bereich-select').onchange=async e=>{state.bereichId=Number(e.target.value);localStorage.setItem('neu-bereich',state.bereichId);await loadData();render()};
  document.querySelector('#theme-toggle').onclick=()=>setTheme(state.theme==='dark'?'light':'dark');
  document.querySelector('#logout').onclick=async()=>{await fetch('/api/auth/logout',{method:'POST',credentials:'same-origin'});location.assign('/login.html')};
  document.querySelector('#new-group').onclick=showGroupDialog;
}

function drawHeader(){
  document.querySelector('#scope').textContent=state.bereiche.find(b=>b.id===state.bereichId)?.name||'';
  document.querySelector('#sparte-select').innerHTML=`<option value="">Alle Sparten</option>${state.sparten.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('')}`;
  document.querySelector('#sparte-select').value=state.sparteId;
  document.querySelector('#year-select').innerHTML=state.jahre.map(y=>`<option value="${y}">${y}</option>`).join('');
  document.querySelector('#year-select').value=state.year||state.jahre[0]||'';
  // Sparten- und Jahreswahl in der Kopfzeile setzen zentral state.filter und rendern
  // die aktive Seite neu (vorher: Sparte löste nur drawSidebar() aus, Jahr hatte
  // gar keinen Handler).
  document.querySelector('#sparte-select').onchange=e=>setFilter({sparteId:e.target.value});
  document.querySelector('#year-select').onchange=e=>setFilter({jahr:e.target.value});
  document.querySelector('#more-filters').onclick=()=>{const f=document.querySelector('#filters');const open=f.classList.toggle('open');document.querySelector('#more-filters').setAttribute('aria-expanded',open)};
  document.querySelector('#page-title').textContent=routes[state.route][0];
}

// P30b: befüllt #filter-kategorie aus GET /api/kategorien, abhängig von der gewählten
// Sparte (state.sparteId); ohne Sparte kommen alle Kategorien des Bereichs. Lädt nur
// neu, wenn sich Bereich oder Sparte seit dem letzten Aufruf geändert haben, damit
// nicht bei jeder Seitennavigation ein zusätzlicher Aufruf entsteht.
async function drawKategorieFilter(){
  const sel=document.querySelector('#filter-kategorie');
  if(!sel)return;
  sel.onchange=e=>setFilter({kategorieId:e.target.value});
  const key=`${state.bereichId}:${state.sparteId}`;
  if(kategorieOptionsKey===key){
    if(sel.value!==(state.filter.kategorieId||''))sel.value=state.filter.kategorieId||'';
    return;
  }
  kategorieOptionsKey=key;
  const behalten=state.filter.kategorieId||'';
  try{
    // nur_aktive wie zuvor lokal in buchungen.js (P50): stillgelegte Kategorien gehören nicht in den Filter.
    const params=state.sparteId?{sparte_id:state.sparteId,nur_aktive:'true'}:{nur_aktive:'true'};
    const kategorien=await api('/kategorien',{params});
    // QA2-07: bei "Alle Sparten" sind gleichnamige Kategorien verschiedener Sparten sonst
    // nicht unterscheidbar -- Dubletten bekommen das Sparten-Kuerzel angehaengt.
    const anzahlProName=new Map();
    if(!state.sparteId){
      for(const k of kategorien){const key=k.name.toLowerCase();anzahlProName.set(key,(anzahlProName.get(key)||0)+1)}
    }
    const beschriftung=k=>{
      if(state.sparteId||(anzahlProName.get(k.name.toLowerCase())||0)<2)return esc(k.name);
      const kuerzel=state.sparten.find(s=>s.id===k.sparte_id)?.kuerzel||'';
      return kuerzel?`${esc(k.name)} (${esc(kuerzel)})`:esc(k.name);
    };
    sel.innerHTML=`<option value="">alle</option>${kategorien.map(k=>`<option value="${k.id}">${beschriftung(k)}</option>`).join('')}`;
    const gueltig=kategorien.some(k=>String(k.id)===behalten);
    sel.value=gueltig?behalten:'';
    if(!gueltig&&behalten){state.filter.kategorieId='';localStorage.setItem('neu-kategorie','')}
  }catch(error){
    toast(error.detail||error.message||'Kategorien konnten nicht geladen werden.');
  }
}

async function render(){
  state.route=currentRoute();
  drawSidebar();
  drawHeader();
  await drawKategorieFilter();
  const mod=await import(`./pages/${routes[state.route][1]}.js`);
  await mod.render(document.querySelector('#page'),state);
  document.querySelectorAll('.mobile-nav [data-route]').forEach(b=>{
    b.classList.toggle('active',b.dataset.route===state.route);
    b.onclick=b.dataset.route==='mehr'?openMoreSheet:()=>go(b.dataset.route);
  });
}

// QA5-02: Unter 760 px verschwindet die Sidebar komplett (siehe style.css), damit sind
// Sparte/Konten/Kredit/Kategorien/Export/Betrieb sowie Bereichswechsel, Theme, Passwort
// und Abmelden ohne dieses Sheet auf Mobil nicht erreichbar. Der sechste Bottom-Nav-Knopf
// "Mehr" (data-route="mehr", siehe index.html) ist keine echte Seite und wird oben in
// render() gesondert behandelt. Die Restrouten werden aus der routes-Map abzüglich der im
// Markup vorhandenen Bottom-Nav-Einträge abgeleitet, nicht hart kodiert - eine künftige
// zusätzliche Seite (weiterer routes-Eintrag) taucht dann automatisch im Sheet auf, ohne
// dass dieser Code angefasst werden muss.
function openMoreSheet(){
  const bottomRouten=new Set(Array.from(document.querySelectorAll('.mobile-nav [data-route]')).map(b=>b.dataset.route));
  const restRouten=Object.entries(routes).filter(([schluessel])=>!bottomRouten.has(schluessel));
  const routenListe=restRouten.map(([schluessel,[label]])=>`<button type="button" class="nav-item ${state.route===schluessel?'active':''}" data-route="${schluessel}"><span aria-hidden="true">•</span>${esc(label)}</button>`).join('');
  const bereichOptionen=state.bereiche.map(b=>`<option value="${b.id}" ${b.id===state.bereichId?'selected':''}>${esc(b.name)}</option>`).join('');
  const node=sheet(`<div class="sheet-head"><h2>Mehr</h2><button type="button" class="dialog-close" id="sheet-close" aria-label="Schließen">×</button></div>
    <nav class="nav-group" aria-label="Weitere Seiten">${routenListe}</nav>
    <div class="nav-group"><label class="nav-label" for="sheet-bereich-select">Bereich</label><select id="sheet-bereich-select" class="scope-sel" aria-label="Bereich">${bereichOptionen}</select></div>
    <div class="nav-group side-foot">
      <a class="nav-item" href="/password-change.html">Passwort ändern</a>
      <button type="button" class="nav-item" id="sheet-theme-toggle">${state.theme==='dark'?'☼':'☾'} Ansicht</button>
      <button type="button" class="nav-item" id="sheet-logout">↪ Abmelden</button>
    </div>`);
  node.setAttribute('role','dialog');
  node.setAttribute('aria-modal','true');
  node.setAttribute('aria-label','Mehr');
  node.querySelectorAll('[data-route]').forEach(b=>b.onclick=()=>{closeSheet();go(b.dataset.route)});
  node.querySelector('#sheet-close').onclick=closeSheet;
  node.querySelector('#sheet-bereich-select').onchange=async e=>{closeSheet();state.bereichId=Number(e.target.value);localStorage.setItem('neu-bereich',state.bereichId);await loadData();render()};
  node.querySelector('#sheet-theme-toggle').onclick=()=>{setTheme(state.theme==='dark'?'light':'dark');closeSheet()};
  node.querySelector('#sheet-logout').onclick=async()=>{await fetch('/api/auth/logout',{method:'POST',credentials:'same-origin'});location.assign('/login.html')};
  // QA5-02: Fokus beim Öffnen auf das Sheet legen, damit Tastatur-/Screenreader-Nutzung
  // sofort im Menü landet statt im zuvor fokussierten Bottom-Nav-Button.
  node.tabIndex=-1;
  node.focus();
}

function showGroupDialog(){drill('Auswertungsgruppe anlegen',`<form id="group-form"><label class="field">Name<input name="name" required maxlength="120"></label><p class="muted">Sparten können danach in der Gruppe verwaltet werden.</p><button class="btn primary" type="submit">Anlegen</button></form>`);document.querySelector('#group-form').onsubmit=async e=>{e.preventDefault();try{const name=new FormData(e.target).get('name');await api('/auswertungsgruppen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,sparte_ids:[]})});document.querySelector('#drill').close();await loadData();render();toast('Gruppe angelegt.')}catch(error){toast(error.detail||error.message)}}}

async function loadData(){
  kategorieOptionsKey=null;
  [state.bereiche,state.sparten,state.gruppen,state.jahre]=await Promise.all([api('/bereiche'),api('/sparten'),api('/auswertungsgruppen'),api('/jahre').then(x=>x.jahre)]);
  const schema=await api('/schema');
  document.querySelector('#test-banner').hidden=schema.instanz!=='test';
  if(!state.sparteId||!state.sparten.some(s=>String(s.id)===String(state.sparteId)))state.sparteId='';
  if(!state.year||!state.jahre.some(y=>String(y)===String(state.year)))state.year=state.jahre[0]!=null?String(state.jahre[0]):'';
  state.filter.sparteId=state.sparteId;
  state.filter.jahr=state.year;
  localStorage.setItem('neu-sparte',state.sparteId);
  localStorage.setItem('neu-jahr',state.year);
}

document.querySelector('#drill-close').onclick=()=>document.querySelector('#drill').close();
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeSheet()});
window.addEventListener('hashchange',render);
if(!location.hash&&window.innerWidth<760)location.hash='#/erfassen';
setTheme(state.theme);
loadData().then(render).catch(error=>{document.querySelector('#page').innerHTML=`<section class="card placeholder"><p>Initialisierung fehlgeschlagen: ${esc(error.message)}</p></section>`});
