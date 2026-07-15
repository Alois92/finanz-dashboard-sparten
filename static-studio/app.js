"use strict";

/* Hohenegg Finanzstudio — App-Logik.
   Alle dynamischen Werte werden vor dem Einfügen mit escapeHtml() maskiert. */

// ---------- Helfer ----------
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function euroToCent(str) {
  if (str == null) return 0;
  const s = String(str).trim().replace(/\s|€/g, "").replace(/\./g, "").replace(",", ".");
  const val = parseFloat(s);
  return isNaN(val) ? 0 : Math.round(val * 100);
}
function centToEuro(cent) {
  return (cent / 100).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
}
function centToInput(cent) {
  return (cent / 100).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
async function api(path, opts) {
  const res = await fetch("/api" + path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? null : res.json();
}
function todayISO() { return new Date().toISOString().slice(0, 10); }
function monatLabel(ym) {
  const M = ["Jän", "Feb", "Mrz", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
  const [y, m] = String(ym).split("-");
  return (M[parseInt(m, 10) - 1] || m) + " " + String(y).slice(2);
}
function fehlerKarte(el, err) {
  el.innerHTML = `<p class="chart-empty">Daten konnten nicht geladen werden (${escapeHtml(err.message)}). Läuft der Server?</p>`;
}

// ---------- Zustand ----------
let sparten = [];
let bankkonten = null;
let kategorienCache = {};
let buchungenCache = [];
let drilldownBuchungen = [];
let editId = null;         // Buchung im Bearbeiten-Modus (null = neu anlegen)
let periode = "alles";     // jahr | vorjahr | 12m | alles
let spCur = "";            // Sparten-Filter ("" = alle)
let globalgruppeCur = "";
let globaleGruppen = [];
let verlaufModus = "monat"; // monat | jahr
let aktivePage = "uebersicht";

// ---------- Sparten-Farben ----------
const SPARTEN_PALETTE = ["#6AA9FF", "#2DD4BF", "#C084FC", "#F472B6", "#FB923C", "#818CF8"];
let sparteColorById = {}, sparteColorByName = {}, sparteKuerzelByName = {};
function buildSparteColors() {
  sparteColorById = {}; sparteColorByName = {}; sparteKuerzelByName = {};
  sparten.forEach((s, i) => {
    const c = s.farbe || SPARTEN_PALETTE[i % SPARTEN_PALETTE.length];
    sparteColorById[s.id] = c;
    sparteColorByName[s.name] = c;
    sparteKuerzelByName[s.name] = s.kuerzel || s.name;
  });
}
function colorForSparteName(name) { return sparteColorByName[name] || "var(--muted)"; }
function sparteName(id) {
  const s = sparten.find((x) => String(x.id) === String(id));
  return s ? s.name : "";
}

async function ladeKategorien(sparteId) {
  if (!sparteId) return [];
  if (!kategorienCache[sparteId]) {
    kategorienCache[sparteId] = await api("/kategorien?sparte_id=" + sparteId);
  }
  return kategorienCache[sparteId];
}
function invalidateKategorien(sparteId) { delete kategorienCache[sparteId]; }

// ---------- Theme ----------
function effectiveTheme() {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "dark" || attr === "light") return attr;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
function renderThemeIcons() {
  const icon = effectiveTheme() === "dark" ? "☀️" : "🌙";
  $$(".theme-icon").forEach((el) => { el.textContent = icon; });
}
function toggleTheme() {
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("studio-theme", next); } catch (e) {}
  renderThemeIcons();
  ladePage(aktivePage); // Graphen mit neuen Variablenfarben neu zeichnen
}
$("#theme-toggle").addEventListener("click", toggleTheme);
$("#theme-toggle-m").addEventListener("click", toggleTheme);
renderThemeIcons();

// ---------- Zeitraum ----------
function periodeRange() {
  const now = new Date();
  const y = now.getFullYear();
  if (periode === "jahr") return { von: `${y}-01-01`, bis: `${y}-12-31` };
  if (periode === "vorjahr") return { von: `${y - 1}-01-01`, bis: `${y - 1}-12-31` };
  if (periode === "12m") {
    const d = new Date(now); d.setDate(d.getDate() - 365);
    return { von: d.toISOString().slice(0, 10), bis: todayISO() };
  }
  return {};
}
function dimensionQuery() {
  const p = new URLSearchParams();
  if (globalgruppeCur) p.set("globalgruppe_id", globalgruppeCur);
  else if (spCur) p.set("sparte_id", spCur);
  return p.toString();
}
function filterQuery() {
  const p = new URLSearchParams(dimensionQuery());
  const r = periodeRange();
  if (r.von) p.set("von", r.von);
  if (r.bis) p.set("bis", r.bis);
  return p.toString();
}
$$("#periode .pill").forEach((b) => b.addEventListener("click", () => {
  periode = b.dataset.periode;
  $$("#periode .pill").forEach((x) => x.classList.toggle("active", x === b));
  ladePage(aktivePage);
}));

// ---------- Sparten-Pills ----------
function renderDashboardFilter() {
  const select = $("#dashboard-filter");
  const wert = globalgruppeCur ? "gg:" + globalgruppeCur : (spCur ? "sp:" + spCur : "");
  select.innerHTML = '<option value="">Alle Sparten</option>' + '<optgroup label="Sparten">' + sparten.map((s) => `<option value="sp:${s.id}">Sparte: ${escapeHtml(s.name)}</option>`).join("") + '</optgroup>' + '<optgroup label="Gruppen">' + globaleGruppen.map((g) => `<option value="gg:${g.id}">Gruppe: ${escapeHtml(g.name)}</option>`).join("") + '</optgroup>';
  select.value = wert;
}
$("#dashboard-filter").addEventListener("change", (e) => {
  const [art, id = ""] = e.target.value.split(":");
  spCur = art === "sp" ? id : ""; globalgruppeCur = art === "gg" ? id : "";
  renderSpartenPills(); ladePage(aktivePage);
});
function renderSpartenPills() {
  const el = $("#sp-pills");
  const pills = [
    `<button type="button" class="sp-pill all${spCur === "" ? " active" : ""}" data-sp=""><span class="dot"></span>Alle</button>`,
  ].concat(sparten.map((s) => {
    const c = sparteColorById[s.id];
    return `<button type="button" class="sp-pill${String(s.id) === spCur ? " active" : ""}" data-sp="${s.id}" style="--c:${c}" title="${escapeHtml(s.name)}"><span class="dot"></span>${escapeHtml(s.kuerzel || s.name)}</button>`;
  }));
  el.innerHTML = pills.join("");
  $$("#sp-pills .sp-pill").forEach((b) => b.addEventListener("click", () => {
    spCur = b.dataset.sp;
    globalgruppeCur = "";
    renderSpartenPills();
    renderDashboardFilter();
    ladePage(aktivePage);
  }));
}

// ---------- Navigation ----------
function activatePage(name) {
  aktivePage = name;
  $$(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + name));
  $$(".nav-item, .bb-item[data-page]").forEach((b) => b.classList.toggle("active", b.dataset.page === name));
  $("#mehr-sheet").hidden = true;
  ladePage(name);
}
function ladePage(name) {
  if (name === "uebersicht") ladeUebersicht();
  else if (name === "auswertungen") ladeAuswertungen();
  else if (name === "export") ladeExport();
  else if (name === "buchungen") ladeBuchungen();
  else if (name === "kategorien") ladeKategorienTabelle();
  else if (name === "belege") ladeBelege();
  else if (name === "bankimport") initBankimport();
}
$$("[data-page]").forEach((b) => b.addEventListener("click", () => activatePage(b.dataset.page)));
$("#bb-mehr").addEventListener("click", () => { $("#mehr-sheet").hidden = false; });
$("#mehr-close").addEventListener("click", () => { $("#mehr-sheet").hidden = true; });
$("#mehr-sheet").addEventListener("click", (e) => { if (e.target.id === "mehr-sheet") e.currentTarget.hidden = true; });

// ===========================================================================
// Übersicht
// ===========================================================================
async function ladeUebersicht() {
  const q = filterQuery();
  let data, verlauf, jahresdaten;
  try {
    [data, verlauf, jahresdaten] = await Promise.all([
      api("/dashboard?" + q),
      api("/verlauf?" + q).catch(() => ({ monate: [] })),
      // Jahresvergleich fuer Signale/Deltas: nur Sparten-Filter, volle Jahre
      api("/jahresvergleich" + (dimensionQuery() ? "?" + dimensionQuery() : "")).catch(() => null),
    ]);
  } catch (err) {
    fehlerKarte($("#chart-verlauf"), err);
    return;
  }
  const monate = verlauf.monate || [];

  renderSignale(jahresdaten, monate);

  // KPIs
  $("#kpi-ein").textContent = centToEuro(data.einnahmen_cent);
  $("#kpi-aus").textContent = centToEuro(data.ausgaben_cent);
  $("#kpi-saldo").textContent = centToEuro(data.saldo_cent);
  $("#kpi-saldo").style.color = data.saldo_cent < 0 ? "var(--aus)" : "var(--text)";
  const sub = $("#kpi-saldo-sub");
  sub.textContent = monate.length
    ? `Ø ${centToEuro(Math.round(data.saldo_cent / monate.length))} / Monat · ${monate.length} Monate`
    : "";
  Charts.sparkline($("#spark-ein"), monate.map((m) => m.einnahmen_cent), { color: "var(--ein)" });
  Charts.sparkline($("#spark-aus"), monate.map((m) => m.ausgaben_cent), { color: "var(--aus)" });
  Charts.sparkline($("#spark-saldo"), monate.map((m) => m.saldo_cent), { color: "var(--saldo)" });

  // Verlauf (Monate oder Jahre)
  if (verlaufModus === "jahr" && jahresdaten) {
    Charts.barGroup($("#chart-verlauf"), {
      labels: jahresdaten.gesamt.map((g) => g.jahr),
      series: [
        { name: "Einnahmen", color: "var(--ein)", values: jahresdaten.gesamt.map((g) => g.einnahmen_cent) },
        { name: "Ausgaben", color: "var(--aus)", values: jahresdaten.gesamt.map((g) => g.ausgaben_cent) },
      ],
      line: { name: "Saldo", color: "var(--saldo)", values: jahresdaten.gesamt.map((g) => g.saldo_cent) },
      empty: "Noch keine Buchungen — leg unter „Erfassen“ los.",
    });
  } else {
    Charts.barGroup($("#chart-verlauf"), {
      labels: monate.map((m) => monatLabel(m.monat)),
      series: [
        { name: "Einnahmen", color: "var(--ein)", values: monate.map((m) => m.einnahmen_cent) },
        { name: "Ausgaben", color: "var(--aus)", values: monate.map((m) => m.ausgaben_cent) },
      ],
      line: { name: "Saldo", color: "var(--saldo)", values: monate.map((m) => m.saldo_cent) },
      empty: "Noch keine Buchungen — leg unter „Erfassen“ los.",
      onBarClick: (label, seriesName) => {
        const eintrag = monate.find((m) => monatLabel(m.monat) === label);
        if (!eintrag) return;
        zeigeDrilldown({
          monat: eintrag.monat,
          typ: seriesName === "Einnahmen" ? "einnahme" : "ausgabe",
          titel: `${seriesName} · ${label}`,
        });
      },
    });
  }

  // Schmetterling: Sparten im Vergleich
  Charts.butterfly($("#chart-sparten"), data.per_sparte.map((r) => ({
    label: r.sparte, color: colorForSparteName(r.sparte),
    ein: r.einnahmen_cent, aus: r.ausgaben_cent,
  })));

  // Rankings mit Vorjahres-Delta (Zuordnung ueber Kategorie+Sparte, damit
  // gleichnamige Kategorien in verschiedenen Sparten getrennt bleiben)
  const deltas = kategorieDeltas(jahresdaten);
  const rank = (typ, gut) => data.per_kategorie
    .filter((r) => r.typ === typ).slice(0, 5)
    .map((r) => {
      const key = r.kategorie + "|" + (r.sparte || "");
      return {
        label: r.kategorie,
        kategorie_id: r.kategorie_id,
        typ,
        sub: r.sparte ? (sparteKuerzelByName[r.sparte] || r.sparte) : "",
        color: colorForSparteName(r.sparte),
        value: r.betrag_cent,
        deltaPct: deltas[key] != null ? deltas[key] : null,
        gut,
      };
    });
  Charts.rankList($("#rank-aus"), rank("ausgabe", false), {
    emptyText: "Keine Ausgaben im Zeitraum.",
    onRowClick: (row) => zeigeDrilldown({
      kategorie_id: row.kategorie_id, typ: row.typ,
      titel: `${row.label} · Ausgaben`,
    }),
  });
  Charts.rankList($("#rank-ein"), rank("einnahme", true), {
    emptyText: "Keine Einnahmen im Zeitraum.",
    onRowClick: (row) => zeigeDrilldown({
      kategorie_id: row.kategorie_id, typ: row.typ,
      titel: `${row.label} · Einnahmen`,
    }),
  });
}

// Veränderung je Kategorie: laufendes Jahr (aufs Gesamtjahr hochgerechnet)
// gegen das Vorjahr, in Prozent des Absolutbetrags. Frueh im Jahr (< 3 Monate)
// ist die Hochrechnung zu wackelig — dann kein Delta.
function kategorieDeltas(jahresdaten) {
  const out = {};
  if (!jahresdaten || !jahresdaten.per_kategorie) return out;
  const now = new Date();
  const y = String(now.getFullYear());
  const py = String(now.getFullYear() - 1);
  const m = now.getMonth() + 1;
  if (m < 3) return out;
  jahresdaten.per_kategorie.forEach((k) => {
    const cur = k.werte[y], prev = k.werte[py];
    if (cur == null || prev == null || prev === 0) return;
    const hochgerechnet = Math.abs(cur) / m * 12;
    out[k.kategorie + "|" + k.sparte] = (hochgerechnet - Math.abs(prev)) / Math.abs(prev) * 100;
  });
  return out;
}

function renderSignale(jahresdaten, monate) {
  const el = $("#signals");
  const cards = [];
  const y = String(new Date().getFullYear());
  const py = String(new Date().getFullYear() - 1);

  const mNow = new Date().getMonth() + 1;
  if (jahresdaten && jahresdaten.per_kategorie && mNow >= 3) {
    // Stärkster Kostenanstieg (nur Ausgabe-Kategorien: Saldo negativ);
    // laufendes Jahr aufs Gesamtjahr hochgerechnet, sonst hinkt der Vergleich.
    let worst = null;
    jahresdaten.per_kategorie.forEach((k) => {
      const cur = k.werte[y], prev = k.werte[py];
      if (cur == null || prev == null || cur >= 0 || prev >= 0) return;
      const diff = Math.abs(cur) / mNow * 12 - Math.abs(prev);
      if (diff > 0 && (!worst || diff > worst.diff)) {
        worst = { name: k.kategorie, diff, pct: diff / Math.abs(prev) * 100 };
      }
    });
    if (worst) {
      cards.push(`<div class="signal warn"><span class="s-label">Kostenanstieg (hochgerechnet)</span><span class="s-text">${escapeHtml(worst.name)}: <strong>+${centToEuro(Math.round(worst.diff))}</strong> ggü. Vorjahr (▲ ${worst.pct.toLocaleString("de-DE", { maximumFractionDigits: 0 })} %)</span></div>`);
    }
    // Größte Einnahmequelle im aktuellen Jahr
    let best = null;
    jahresdaten.per_kategorie.forEach((k) => {
      const cur = k.werte[y];
      if (cur != null && cur > 0 && (!best || cur > best.wert)) best = { name: k.kategorie, wert: cur };
    });
    if (best) {
      cards.push(`<div class="signal good"><span class="s-label">Stärkste Einnahmequelle ${escapeHtml(y)}</span><span class="s-text">${escapeHtml(best.name)}: <strong>${centToEuro(best.wert)}</strong></span></div>`);
    }
  }

  // Hochrechnung Jahresende: Ø-Monatssaldo des aktuellen Jahres × 12
  const yMonate = (monate || []).filter((m) => String(m.monat).startsWith(y));
  if (yMonate.length >= 2) {
    const summe = yMonate.reduce((a, m) => a + m.saldo_cent, 0);
    const prognose = Math.round(summe / yMonate.length * 12);
    cards.push(`<div class="signal${prognose < 0 ? " warn" : ""}"><span class="s-label">Hochrechnung Jahresende</span><span class="s-text">Saldo ≈ <strong>${centToEuro(prognose)}</strong> (aus ${yMonate.length} Monaten)</span></div>`);
  }

  el.innerHTML = cards.join("");
}

$$(".seg-btn").forEach((b) => b.addEventListener("click", () => {
  verlaufModus = b.dataset.modus;
  $$(".seg-btn").forEach((x) => x.classList.toggle("active", x === b));
  ladeUebersicht();
}));

// ===========================================================================
// Auswertungen (Jahresvergleich)
// ===========================================================================
async function ladeAuswertungen() {
  let data;
  try { data = await api("/jahresvergleich?" + filterQuery()); }
  catch (err) { fehlerKarte($("#chart-jahre"), err); return; }

  Charts.barGroup($("#chart-jahre"), {
    labels: data.gesamt.map((g) => g.jahr),
    series: [
      { name: "Einnahmen", color: "var(--ein)", values: data.gesamt.map((g) => g.einnahmen_cent) },
      { name: "Ausgaben", color: "var(--aus)", values: data.gesamt.map((g) => g.ausgaben_cent) },
    ],
    line: { name: "Saldo", color: "var(--saldo)", values: data.gesamt.map((g) => g.saldo_cent) },
    empty: "Noch keine Buchungen — sobald du erfasst, erscheint hier der Jahresvergleich.",
  });

  $("#tbl-jahre tbody").innerHTML = data.gesamt.map((g) =>
    `<tr><td>${escapeHtml(g.jahr)}</td>
     <td class="num">${centToEuro(g.einnahmen_cent)}</td>
     <td class="num">${centToEuro(g.ausgaben_cent)}</td>
     <td class="num" style="color:${g.saldo_cent < 0 ? "var(--aus)" : "var(--ein)"}">${centToEuro(g.saldo_cent)}</td></tr>`).join("")
    || `<tr><td colspan="4" class="hint">Keine Daten.</td></tr>`;

  const jahre = data.jahre;
  const thead = $("#tbl-jahre-sparte thead");
  const tbody = $("#tbl-jahre-sparte tbody");
  if (!jahre.length) {
    thead.innerHTML = "";
    tbody.innerHTML = `<tr><td class="hint">Keine Daten.</td></tr>`;
  } else {
    thead.innerHTML = "<tr><th>Sparte</th>" + jahre.map((j) => `<th class="num">${escapeHtml(j)}</th>`).join("") + "</tr>";
    tbody.innerHTML = data.per_sparte.map((r) =>
      `<tr><td><span class="sp-tag"><span class="dot" style="background:${colorForSparteName(r.sparte)}"></span>${escapeHtml(r.sparte)}</span></td>` +
      jahre.map((j) => {
        const v = r.werte[j];
        return `<td class="num"${v != null && v < 0 ? ' style="color:var(--aus)"' : ""}>${v != null ? centToEuro(v) : "–"}</td>`;
      }).join("") + "</tr>").join("");
  }

  const kthead = $("#tbl-jahre-kat thead");
  const ktbody = $("#tbl-jahre-kat tbody");
  const kat = data.per_kategorie || [];
  if (!jahre.length || !kat.length) {
    kthead.innerHTML = "";
    ktbody.innerHTML = `<tr><td class="hint">Keine Daten.</td></tr>`;
  } else {
    kthead.innerHTML = "<tr><th>Kategorie</th>" + jahre.map((j) => `<th class="num">${escapeHtml(j)}</th>`).join("") + "</tr>";
    ktbody.innerHTML = kat.map((r) => {
      const kuerzel = sparteKuerzelByName[r.sparte] || r.sparte;
      return `<tr><td><span class="sp-tag"><span class="dot" style="background:${colorForSparteName(r.sparte)}"></span>${escapeHtml(r.kategorie)} <span class="kat-sp">${escapeHtml(kuerzel)}</span></span></td>` +
        jahre.map((j) => {
          const v = r.werte[j];
          return `<td class="num"${v != null && v < 0 ? ' style="color:var(--aus)"' : ""}>${v != null ? centToEuro(v) : "–"}</td>`;
        }).join("") + "</tr>";
    }).join("");
  }
}

// ===========================================================================
// Diagramm-Drilldown
// ===========================================================================
function schliesseDrilldown() {
  $("#drilldown-modal").hidden = true;
  document.body.classList.remove("drilldown-open");
}

async function zeigeDrilldown({ monat, kategorie_id, sparte_id, typ, titel }) {
  const modal = $("#drilldown-modal");
  const msg = $("#drilldown-msg");
  const params = new URLSearchParams(filterQuery());
  if (typeof globalgruppeCur !== "undefined" && globalgruppeCur) {
    params.delete("sparte_id");
    params.set("globalgruppe_id", globalgruppeCur);
  }
  if (monat) params.set("monat", monat);
  if (kategorie_id) params.set("kategorie_id", kategorie_id);
  if (sparte_id) params.set("sparte_id", sparte_id);
  if (typ) params.set("typ", typ);

  $("#drilldown-titel").textContent = titel || "Buchungen";
  $("#tbl-drilldown tbody").innerHTML = "";
  $("#drilldown-summe").textContent = centToEuro(0);
  msg.textContent = "Buchungen werden geladen …";
  modal.hidden = false;
  document.body.classList.add("drilldown-open");

  try {
    drilldownBuchungen = await api("/buchungen?" + params.toString());
    const tbody = $("#tbl-drilldown tbody");
    tbody.innerHTML = drilldownBuchungen.map((b) => {
      const kats = (b.zeilen || []).map((z) => escapeHtml(z.kategorie_name)).join(", ");
      const bearbeiten = b.transfer_gruppe_id
        ? "" : `<button type="button" class="link" data-drilldown-edit="${b.id}">Bearbeiten</button>`;
      return `<tr><td>${escapeHtml(b.datum)}</td><td>${escapeHtml(b.text || "")}</td>`
        + `<td>${kats}</td><td>${escapeHtml(b.sparte_name)}</td>`
        + `<td class="num">${centToEuro(b.betrag_cent)}</td><td>${bearbeiten}</td></tr>`;
    }).join("");
    const summe = drilldownBuchungen.reduce((total, b) => total + b.betrag_cent, 0);
    $("#drilldown-summe").textContent = centToEuro(summe);
    msg.textContent = drilldownBuchungen.length
      ? `${drilldownBuchungen.length} Buchung${drilldownBuchungen.length === 1 ? "" : "en"}`
      : "Keine Buchungen für diese Auswahl.";
    $$("#tbl-drilldown [data-drilldown-edit]").forEach((button) => {
      button.addEventListener("click", () => {
        const buchung = drilldownBuchungen.find((b) => String(b.id) === button.dataset.drilldownEdit);
        if (buchung) { schliesseDrilldown(); starteBearbeitung(buchung); }
      });
    });
  } catch (err) {
    drilldownBuchungen = [];
    msg.textContent = "Buchungen konnten nicht geladen werden (" + err.message + ").";
  }
}

$("#drilldown-close").addEventListener("click", schliesseDrilldown);
$("#drilldown-modal").addEventListener("click", (event) => {
  if (event.target.id === "drilldown-modal") schliesseDrilldown();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("#drilldown-modal").hidden) schliesseDrilldown();
});
// ===========================================================================
// Buchungen
// ===========================================================================
async function ladeBuchungen() {
  const suche = $("#l-suche").value.trim();
  const pfad = suche
    ? "/buchungen/suche?q=" + encodeURIComponent(suche)
    : "/buchungen?" + filterQuery();
  try { buchungenCache = await api(pfad); }
  catch (err) {
    $("#tbl-buchungen tbody").innerHTML = "";
    $("#liste-leer").hidden = false;
    $("#liste-leer").textContent = "Buchungen konnten nicht geladen werden (" + err.message + ").";
    return;
  }
  renderBuchungen();
}
function renderBuchungen() {
  const typ = $("#l-typ").value;
  const rows = buchungenCache.filter((b) => {
    if (typ && b.typ !== typ) return false;
    return true;
  });
  $("#liste-leer").hidden = rows.length > 0;
  $("#liste-leer").textContent = "Keine Buchungen im gewählten Zeitraum.";
  $("#tbl-buchungen tbody").innerHTML = rows.map((b) => {
    const kats = (b.zeilen || []).map((z) => escapeHtml(z.kategorie_name) + (b.zeilen.length > 1 ? " (" + centToEuro(z.betrag_cent) + ")" : "")).join(", ");
    const belege = (b.belege || []).map((bl) =>
      `<a href="/api/belege/${bl.id}/datei" target="_blank" rel="noopener" title="${escapeHtml(bl.dateiname)}">🗎</a>`).join(" ");
    const bearbeiten = b.transfer_gruppe_id
      ? "" : `<button class="link" data-edit="${b.id}">bearbeiten</button>`;
    return `<tr>
      <td>${escapeHtml(b.datum)}</td>
      <td><span class="sp-tag"><span class="dot" style="background:${colorForSparteName(b.sparte_name)}"></span>${escapeHtml(b.sparte_name)}</span></td>
      <td><span class="badge ${escapeHtml(b.typ)}">${escapeHtml(b.typ)}</span></td>
      <td>${escapeHtml(b.text || "")}</td><td>${kats}</td>
      <td class="beleg-zelle">${belege} <button class="link" data-beleg="${b.id}" title="Beleg anhängen (Foto oder PDF)">＋</button></td>
      <td class="num">${centToEuro(b.betrag_cent)}</td>
      <td class="row-actions">${bearbeiten}
      <button class="link" data-del="${b.id}">löschen</button></td></tr>`;
  }).join("");
  $$("#tbl-buchungen [data-del]").forEach((btn) => btn.addEventListener("click", async () => {
    const b = buchungenCache.find((x) => String(x.id) === btn.dataset.del);
    const frage = b && b.transfer_gruppe_id
      ? "Umbuchung wirklich löschen? Beide Seiten werden entfernt."
      : "Buchung wirklich löschen?";
    if (!confirm(frage)) return;
    await api("/buchungen/" + btn.dataset.del, { method: "DELETE" });
    ladeBuchungen();
  }));
  $$("#tbl-buchungen [data-edit]").forEach((btn) => btn.addEventListener("click", () => {
    const b = buchungenCache.find((x) => String(x.id) === btn.dataset.edit);
    if (b) starteBearbeitung(b);
  }));
  $$("#tbl-buchungen [data-beleg]").forEach((btn) => btn.addEventListener("click", () => {
    belegZielBuchung = buchungenCache.find((x) => String(x.id) === btn.dataset.beleg);
    if (belegZielBuchung) $("#beleg-anhang").click();
  }));
}

// Beleg direkt an eine Buchung haengen (am Handy oeffnet sich die Kamera/Galerie)
let belegZielBuchung = null;
$("#beleg-anhang").addEventListener("change", async () => {
  const datei = $("#beleg-anhang").files[0];
  const b = belegZielBuchung;
  $("#beleg-anhang").value = "";
  if (!datei || !b) return;
  try {
    const fd = new FormData();
    fd.append("datei", datei);
    fd.append("sparte_id", b.sparte_id);
    const beleg = await api("/belege", { method: "POST", body: fd });
    await api("/buchungen/" + b.id + "/belege", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ beleg_id: beleg.id }),
    });
    ladeBuchungen();
  } catch (err) {
    alert("Beleg konnte nicht angehängt werden: " + err.message);
  }
});
$("#l-typ").addEventListener("change", renderBuchungen);
let buchungenSucheTimer = null;
$("#l-suche").addEventListener("input", () => {
  clearTimeout(buchungenSucheTimer);
  buchungenSucheTimer = setTimeout(ladeBuchungen, 300);
});

// ===========================================================================
// Erfassen (Schnellerfassung + Formular)
// ===========================================================================
async function schnellErfassen() {
  const input = $("#quick-input");
  const msg = $("#quick-msg");
  const text = input.value.trim();
  if (!text) return;
  msg.className = "quick-msg"; msg.textContent = "Analysiere …";
  try {
    const v = await api("/parse", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    await fuelleFormular(v);
    const teile = [];
    if (v.sparte_name) teile.push(v.sparte_name);
    if (v.kategorie_name) teile.push(v.kategorie_name);
    teile.push(centToEuro(v.betrag_cent) + " (" + v.typ + ")");
    msg.className = "quick-msg ok";
    msg.textContent = "Übernommen: " + teile.join(" · ") + " — bitte prüfen und speichern.";
    input.value = "";
  } catch (err) {
    msg.className = "quick-msg err";
    msg.textContent = "Fehler: " + err.message;
  }
}
$("#quick-btn").addEventListener("click", schnellErfassen);
$("#quick-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); schnellErfassen(); }
});

async function fuelleFormular(v) {
  if (v.sparte_id && sparten.some((s) => String(s.id) === String(v.sparte_id))) {
    $("#b-sparte").value = String(v.sparte_id);
  }
  $("#b-datum").value = v.datum || todayISO();
  if (v.typ) $("#b-typ").value = v.typ;
  $("#b-text").value = v.text || "";
  await erneuereZeilenKategorien();
  $("#zeilen").innerHTML = "";
  addZeile();
  const zeile = $("#zeilen .zeile");
  if (v.kategorie_id) {
    const sel = zeile.querySelector(".z-kat");
    if ([...sel.options].some((o) => o.value === String(v.kategorie_id))) {
      sel.value = String(v.kategorie_id);
    }
  }
  if (v.betrag_cent) zeile.querySelector(".z-betrag").value = centToInput(v.betrag_cent);
  updateSumme();
}

function kategorieOptions(kats) {
  return kats.map((k) => `<option value="${k.id}">${escapeHtml(k.name)} (${escapeHtml(k.richtung)})</option>`).join("");
}
async function erneuereZeilenKategorien() {
  const kats = await ladeKategorien($("#b-sparte").value);
  $$("#zeilen .zeile select").forEach((sel) => {
    const cur = sel.value;
    sel.innerHTML = kategorieOptions(kats);
    if (cur) sel.value = cur;
  });
  if (kats.length === 0) $("#b-msg").innerHTML = '<span class="err" style="color:var(--aus)">Diese Sparte hat noch keine Kategorien — erst unter „Kategorien“ anlegen.</span>';
  else if ($("#b-msg").textContent.includes("keine Kategorien")) $("#b-msg").textContent = "";
}
function addZeile() {
  const kats = kategorienCache[$("#b-sparte").value] || [];
  const div = document.createElement("div");
  div.className = "zeile";
  div.innerHTML = `
    <label>Kategorie<select class="z-kat">${kategorieOptions(kats)}</select></label>
    <label>Betrag (€)<input type="text" class="z-betrag" inputmode="decimal" placeholder="0,00"></label>
    <button type="button" class="del" title="Zeile entfernen">✕</button>`;
  div.querySelector(".del").addEventListener("click", () => { div.remove(); updateSumme(); });
  div.querySelector(".z-betrag").addEventListener("input", updateSumme);
  $("#zeilen").appendChild(div);
  updateSumme();
}
function updateSumme() {
  let cent = 0;
  $$("#zeilen .z-betrag").forEach((i) => cent += euroToCent(i.value));
  $("#zeilen-summe").textContent = "Summe: " + centToEuro(cent);
}
$("#add-zeile").addEventListener("click", addZeile);
$("#b-sparte").addEventListener("change", () => { erneuereZeilenKategorien(); });

// ---- Bearbeiten-Modus ----
async function starteBearbeitung(b) {
  activatePage("erfassen");
  editId = b.id;
  $("#erfassen-titel").textContent = `Buchung vom ${b.datum} bearbeiten`;
  $("#b-submit").textContent = "Änderungen speichern";
  $("#b-cancel").hidden = false;
  $("#b-msg").textContent = "";
  $("#b-sparte").value = String(b.sparte_id);
  $("#b-datum").value = b.datum;
  $("#b-typ").value = b.typ;
  $("#b-zahlungsart").value = b.zahlungsart || "bank";
  $("#b-text").value = b.text || "";
  await erneuereZeilenKategorien();
  $("#zeilen").innerHTML = "";
  (b.zeilen || []).forEach((z) => {
    addZeile();
    const zeile = $("#zeilen .zeile:last-child");
    const sel = zeile.querySelector(".z-kat");
    if ([...sel.options].some((o) => o.value === String(z.kategorie_id))) {
      sel.value = String(z.kategorie_id);
    }
    zeile.querySelector(".z-betrag").value = centToInput(z.betrag_cent);
  });
  if (!(b.zeilen || []).length) addZeile();
  updateSumme();
}
function beendeBearbeitung() {
  editId = null;
  $("#erfassen-titel").textContent = "Buchung erfassen";
  $("#b-submit").textContent = "Buchung speichern";
  $("#b-cancel").hidden = true;
  $("#b-text").value = "";
  $("#b-datum").value = todayISO();
  $("#zeilen").innerHTML = "";
  addZeile();
}
$("#b-cancel").addEventListener("click", () => { beendeBearbeitung(); $("#b-msg").textContent = ""; });

$("#form-buchung").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#b-msg");
  const zeilen = $$("#zeilen .zeile").map((z) => ({
    kategorie_id: parseInt(z.querySelector(".z-kat").value, 10),
    betrag_cent: euroToCent(z.querySelector(".z-betrag").value),
  })).filter((z) => z.betrag_cent > 0 && z.kategorie_id);
  if (zeilen.length === 0) { msg.className = "msg err"; msg.textContent = "Mindestens eine Zeile mit Betrag > 0 nötig."; return; }
  const body = {
    sparte_id: parseInt($("#b-sparte").value, 10),
    datum: $("#b-datum").value,
    typ: $("#b-typ").value,
    zahlungsart: $("#b-zahlungsart").value,
    text: $("#b-text").value || null,
    zeilen,
  };
  try {
    const pfad = editId ? "/buchungen/" + editId : "/buchungen";
    const created = await api(pfad, {
      method: editId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    msg.className = "msg ok";
    msg.textContent = (editId ? "Geändert: " : "Gespeichert: ")
      + `${centToEuro(created.betrag_cent)} (${created.typ}).`;
    beendeBearbeitung();
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = "Fehler: " + err.message;
  }
});

// ---- Umbuchung zwischen Sparten ----
$("#form-umbuchung").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#u-msg");
  const betrag = euroToCent($("#u-betrag").value);
  if (betrag <= 0) { msg.className = "msg err"; msg.textContent = "Bitte einen Betrag > 0 angeben."; return; }
  if ($("#u-von").value === $("#u-nach").value) {
    msg.className = "msg err"; msg.textContent = "Von- und Nach-Sparte müssen verschieden sein."; return;
  }
  try {
    const res = await api("/umbuchungen", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        von_sparte_id: parseInt($("#u-von").value, 10),
        nach_sparte_id: parseInt($("#u-nach").value, 10),
        datum: $("#u-datum").value,
        betrag_cent: betrag,
        text: $("#u-text").value || null,
      }),
    });
    msg.className = "msg ok";
    msg.textContent = `Umgebucht: ${centToEuro(res.betrag_cent)} (${sparteName($("#u-von").value)} → ${sparteName($("#u-nach").value)}).`;
    $("#u-betrag").value = ""; $("#u-text").value = "";
  } catch (err) {
    msg.className = "msg err"; msg.textContent = "Fehler: " + err.message;
  }
});

// ===========================================================================
// Jahres-Export (CSV mit an-/abwaehlbaren Buchungen)
// ===========================================================================
let exBuchungen = [];
let exAbgewaehlt = new Set();   // Buchungs-IDs, die NICHT exportiert werden

async function ladeExport() {
  // Jahresliste aus dem Jahresvergleich (ungefiltert)
  const sel = $("#ex-jahr");
  try {
    const jd = await api("/jahresvergleich");
    const jahre = jd.jahre || [];
    const vorher = sel.value;
    sel.innerHTML = jahre.map((j) => `<option value="${escapeHtml(j)}">${escapeHtml(j)}</option>`).join("")
      || "<option value=''>–</option>";
    sel.value = jahre.includes(vorher) ? vorher : (jahre[jahre.length - 1] || "");
  } catch (e) { /* Jahresliste optional */ }
  if (sel.value && !$("#ex-von").value) {
    $("#ex-von").value = sel.value + "-01-01";
    $("#ex-bis").value = sel.value + "-12-31";
  }
  await ladeExportListe();
}

async function ladeExportListe() {
  const jahr = $("#ex-jahr").value;
  const tbody = $("#tbl-export tbody");
  if (!jahr) { tbody.innerHTML = ""; $("#ex-leer").hidden = false; $("#ex-summe").textContent = ""; return; }
  const p = new URLSearchParams({ von: `${jahr}-01-01`, bis: `${jahr}-12-31` });
  if ($("#ex-sparte").value) p.set("sparte_id", $("#ex-sparte").value);
  try {
    exBuchungen = await api("/buchungen?" + p.toString());
  } catch (err) {
    tbody.innerHTML = ""; $("#ex-leer").hidden = false;
    $("#ex-leer").textContent = "Buchungen konnten nicht geladen werden (" + err.message + ").";
    return;
  }
  exAbgewaehlt = new Set();
  $("#ex-leer").hidden = exBuchungen.length > 0;
  $("#ex-leer").textContent = "Keine Buchungen im gewählten Jahr.";
  tbody.innerHTML = exBuchungen.map((b) => {
    const kats = (b.zeilen || []).map((z) => escapeHtml(z.kategorie_name)).join(", ");
    return `<tr>
      <td><input type="checkbox" class="ex-check" data-id="${b.id}" checked></td>
      <td>${escapeHtml(b.datum)}</td>
      <td><span class="sp-tag"><span class="dot" style="background:${colorForSparteName(b.sparte_name)}"></span>${escapeHtml(b.sparte_name)}</span></td>
      <td><span class="badge ${escapeHtml(b.typ)}">${escapeHtml(b.typ)}</span></td>
      <td>${escapeHtml(b.text || "")}</td><td>${kats}</td>
      <td class="num">${centToEuro(b.betrag_cent)}</td></tr>`;
  }).join("");
  $$("#tbl-export .ex-check").forEach((cb) => cb.addEventListener("change", () => {
    const id = parseInt(cb.dataset.id, 10);
    if (cb.checked) exAbgewaehlt.delete(id); else exAbgewaehlt.add(id);
    exSummeAnzeigen();
  }));
  exSummeAnzeigen();
}
$("#ex-jahr").addEventListener("change", ladeExportListe);
$("#ex-sparte").addEventListener("change", ladeExportListe);

$("#ex-jahr").addEventListener("change", () => {
  const jahr = $("#ex-jahr").value;
  if (jahr) {
    $("#ex-von").value = jahr + "-01-01";
    $("#ex-bis").value = jahr + "-12-31";
  }
});

function exPaketParams() {
  const von = $("#ex-von").value;
  const bis = $("#ex-bis").value;
  if (!von || !bis || von > bis) {
    const msg = $("#ex-msg");
    msg.className = "msg err";
    msg.textContent = "Bitte einen gueltigen Zeitraum waehlen.";
    return null;
  }
  const params = new URLSearchParams({ von, bis });
  if ($("#ex-sparte").value) params.set("sparte_id", $("#ex-sparte").value);
  return params;
}

$("#ex-xlsx").addEventListener("click", () => {
  const params = exPaketParams();
  if (params) window.location.assign("/api/export/xlsx?" + params.toString());
});

$("#ex-bericht").addEventListener("click", () => {
  const jahr = $("#ex-jahr").value;
  if (!jahr) {
    $("#ex-msg").className = "msg err";
    $("#ex-msg").textContent = "Bitte ein Jahr waehlen.";
    return;
  }
  const params = new URLSearchParams({ jahr });
  if ($("#ex-sparte").value) params.set("sparte_id", $("#ex-sparte").value);
  window.open("/export/bericht?" + params.toString(), "_blank", "noopener");
});

function exAusgewaehlte() {
  return exBuchungen.filter((b) => !exAbgewaehlt.has(b.id));
}
function exSummeAnzeigen() {
  const aus = exAusgewaehlte();
  const ein = aus.filter((b) => b.typ === "einnahme").reduce((a, b) => a + b.betrag_cent, 0);
  const ausg = aus.filter((b) => b.typ === "ausgabe").reduce((a, b) => a + b.betrag_cent, 0);
  $("#ex-summe").textContent = aus.length
    ? `Ausgewählt: ${aus.length} von ${exBuchungen.length} Buchungen · Einnahmen ${centToEuro(ein)} · Ausgaben ${centToEuro(ausg)} · Saldo ${centToEuro(ein - ausg)} (Umbuchungen zählen nicht mit)`
    : "Nichts ausgewählt.";
}
$("#ex-alle").addEventListener("click", () => {
  const alleAn = exAbgewaehlt.size > 0;
  exAbgewaehlt = alleAn ? new Set() : new Set(exBuchungen.map((b) => b.id));
  $$("#tbl-export .ex-check").forEach((cb) => { cb.checked = alleAn; });
  exSummeAnzeigen();
});

$("#ex-download").addEventListener("click", () => {
  const aus = exAusgewaehlte();
  const msg = $("#ex-msg");
  if (!aus.length) { msg.className = "msg err"; msg.textContent = "Keine Buchung ausgewählt."; return; }
  const feld = (v) => `"${String(v == null ? "" : v).replace(/"/g, '""')}"`;
  const eur = (cent) => (cent / 100).toFixed(2).replace(".", ",");
  const zeilen = [["Datum", "Sparte", "Typ", "Kategorie", "Text", "Zahlungsart", "Betrag EUR"].join(";")];
  aus.forEach((b) => {
    (b.zeilen && b.zeilen.length ? b.zeilen : [{ kategorie_name: "", betrag_cent: b.betrag_cent }])
      .forEach((z) => {
        zeilen.push([feld(b.datum), feld(b.sparte_name), feld(b.typ),
          feld(z.kategorie_name), feld(b.text || ""), feld(b.zahlungsart || ""),
          eur(z.betrag_cent)].join(";"));
      });
  });
  const ein = aus.filter((b) => b.typ === "einnahme").reduce((a, b) => a + b.betrag_cent, 0);
  const ausg = aus.filter((b) => b.typ === "ausgabe").reduce((a, b) => a + b.betrag_cent, 0);
  zeilen.push("", ["Summe Einnahmen", "", "", "", "", "", eur(ein)].join(";"),
    ["Summe Ausgaben", "", "", "", "", "", eur(ausg)].join(";"),
    ["Saldo", "", "", "", "", "", eur(ein - ausg)].join(";"));
  const jahr = $("#ex-jahr").value;
  const sp = $("#ex-sparte").value
    ? "-" + (sparten.find((s) => String(s.id) === $("#ex-sparte").value)?.kuerzel || "sparte") : "";
  // BOM voranstellen, damit Excel die Umlaute korrekt erkennt
  const blob = new Blob(["﻿" + zeilen.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `finanz-export-${jahr}${sp}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
  msg.className = "msg ok";
  msg.textContent = `Heruntergeladen: ${a.download} (${aus.length} Buchungen).`;
});

// ===========================================================================
// Kategorien
// ===========================================================================
async function ladeKategorienTabelle() {
  const kats = await api("/kategorien?sparte_id=" + $("#k-sparte").value);
  const byId = Object.fromEntries(kats.map((k) => [k.id, k.name]));
  $("#tbl-kategorien tbody").innerHTML = kats.map((k) =>
    `<tr><td>${escapeHtml(k.name)}</td><td>${escapeHtml(k.richtung)}</td><td>${escapeHtml(k.parent_id ? (byId[k.parent_id] || "") : "")}</td></tr>`).join("")
    || `<tr><td colspan="3" class="hint">Noch keine Kategorien.</td></tr>`;
  $("#k-parent").innerHTML = '<option value="">– keine –</option>' +
    kats.map((k) => `<option value="${k.id}">${escapeHtml(k.name)}</option>`).join("");
  ladeRegeln();
}
$("#k-sparte").addEventListener("change", ladeKategorienTabelle);
$("#form-kategorie").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#k-msg");
  const body = {
    sparte_id: parseInt($("#k-sparte").value, 10),
    name: $("#k-name").value.trim(),
    richtung: $("#k-richtung").value,
    parent_id: $("#k-parent").value ? parseInt($("#k-parent").value, 10) : null,
  };
  try {
    await api("/kategorien", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    msg.className = "msg ok"; msg.textContent = `Kategorie „${body.name}“ angelegt.`;
    $("#k-name").value = "";
    invalidateKategorien(body.sparte_id);
    ladeKategorienTabelle();
    renderGruppenCheckboxes();
    if (String(body.sparte_id) === $("#b-sparte").value) erneuereZeilenKategorien();
  } catch (err) {
    msg.className = "msg err"; msg.textContent = "Fehler: " + err.message;
  }
});

let gruppeEditId = null;
async function alleKategorien() { return (await Promise.all(sparten.map((s) => ladeKategorien(s.id)))).flat(); }
async function renderGruppenCheckboxes(selected = []) {
  const gesetzt = new Set(selected.map(String));
  const bloecke = await Promise.all(sparten.map(async (s) => {
    const kats = await ladeKategorien(s.id); if (!kats.length) return "";
    return `<fieldset style="margin:0 0 10px"><legend>${escapeHtml(s.name)}</legend>` + kats.map((k) => `<label style="display:block;margin:6px 0"><input type="checkbox" value="${k.id}"${gesetzt.has(String(k.id)) ? " checked" : ""}> ${escapeHtml(k.name)}</label>`).join("") + `</fieldset>`;
  }));
  $("#gg-kategorien").innerHTML = bloecke.join("") || '<p class="hint">Zuerst Kategorien anlegen.</p>';
}
function resetGruppenForm() {
  gruppeEditId = null; $("#gg-form-titel").textContent = "Neue Gruppe"; $("#gg-name").value = ""; $("#gg-beschreibung").value = ""; $("#gg-cancel").hidden = true; renderGruppenCheckboxes();
}
async function ladeGlobalgruppen() {
  globaleGruppen = await api("/globalgruppen");
  if (globalgruppeCur && !globaleGruppen.some((g) => String(g.id) === globalgruppeCur)) globalgruppeCur = "";
  renderDashboardFilter(); const kats = await alleKategorien(); const katName = Object.fromEntries(kats.map((k) => [k.id, k.name]));
  $("#tbl-globalgruppen tbody").innerHTML = globaleGruppen.map((g) => `<tr><td>${escapeHtml(g.name)}</td><td>${g.kategorie_ids.map((id) => escapeHtml(katName[id] || ("#" + id))).join(", ") || "&ndash;"}</td><td class="row-actions"><button class="link" data-gg-edit="${g.id}">bearbeiten</button><button class="link" data-gg-del="${g.id}">l\u00f6schen</button></td></tr>`).join("") || '<tr><td colspan="3" class="hint">Noch keine Gruppen.</td></tr>';
  $$("[data-gg-edit]").forEach((button) => button.addEventListener("click", async () => {
    const gruppe = globaleGruppen.find((g) => String(g.id) === button.dataset.ggEdit); gruppeEditId = gruppe.id; $("#gg-form-titel").textContent = "Gruppe bearbeiten"; $("#gg-name").value = gruppe.name; $("#gg-beschreibung").value = gruppe.beschreibung || ""; $("#gg-cancel").hidden = false; await renderGruppenCheckboxes(gruppe.kategorie_ids);
  }));
  $$("[data-gg-del]").forEach((button) => button.addEventListener("click", async () => {
    const gruppe = globaleGruppen.find((g) => String(g.id) === button.dataset.ggDel);
    if (!confirm(`Gruppe \u201e${gruppe.name}\u201c wirklich l\u00f6schen? Buchungen bleiben erhalten.`)) return;
    try { await api("/globalgruppen/" + gruppe.id, { method: "DELETE" }); if (String(gruppe.id) === globalgruppeCur) globalgruppeCur = ""; resetGruppenForm(); await ladeGlobalgruppen(); ladePage(aktivePage); }
    catch (err) { $("#gg-msg").className = "msg err"; $("#gg-msg").textContent = "Fehler: " + err.message; }
  }));
}
$("#gg-cancel").addEventListener("click", resetGruppenForm);
$("#form-globalgruppe").addEventListener("submit", async (e) => {
  e.preventDefault(); const msg = $("#gg-msg"); const body = { name: $("#gg-name").value.trim(), beschreibung: $("#gg-beschreibung").value.trim() || null, kategorie_ids: $$("#gg-kategorien input:checked").map((input) => parseInt(input.value, 10)) };
  try {
    if (gruppeEditId) await api("/globalgruppen/" + gruppeEditId, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    else { const erstellt = await api("/globalgruppen", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: body.name, beschreibung: body.beschreibung }) }); if (body.kategorie_ids.length) await api("/globalgruppen/" + erstellt.id, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }
    msg.className = "msg ok"; msg.textContent = "Gruppe gespeichert."; resetGruppenForm(); await ladeGlobalgruppen();
  } catch (err) { msg.className = "msg err"; msg.textContent = "Fehler: " + err.message; }
});

async function ladeRegeln() {
  const tbody = $("#tbl-regeln tbody");
  let regeln;
  try {
    regeln = await api("/regeln");
    await Promise.all([...new Set(regeln.map((r) => r.ziel_sparte_id).filter(Boolean))]
      .map((id) => ladeKategorien(id)));
  } catch (err) {
    tbody.innerHTML = "";
    $("#regeln-leer").hidden = false;
    $("#regeln-msg").className = "msg err";
    $("#regeln-msg").textContent = "Fehler: " + err.message;
    return;
  }
  $("#regeln-leer").hidden = regeln.length > 0;
  tbody.innerHTML = regeln.map((r) => {
    const kats = kategorienCache[r.ziel_sparte_id] || [];
    const kat = kats.find((k) => String(k.id) === String(r.ziel_kategorie_id));
    const ziel = [sparteName(r.ziel_sparte_id), kat ? kat.name : ("#" + r.ziel_kategorie_id)]
      .filter(Boolean).join(" / ");
    return `<tr>
      <td>${escapeHtml(r.bedingung_text || r.name)}</td>
      <td>${escapeHtml(ziel)}</td>
      <td><span class="badge ${escapeHtml(r.ziel_typ || "")}">${escapeHtml(r.ziel_typ || "")}</span></td>
      <td><input type="checkbox" data-regel-aktiv="${r.id}" ${r.aktiv ? "checked" : ""} aria-label="Regel aktiv"></td>
      <td><button type="button" class="link" data-regel-loeschen="${r.id}">loeschen</button></td>
    </tr>`;
  }).join("");
  $$("[data-regel-aktiv]").forEach((cb) => cb.addEventListener("change", async () => {
    try {
      await api("/regeln/" + cb.dataset.regelAktiv, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ aktiv: cb.checked ? 1 : 0 }),
      });
    } catch (err) {
      cb.checked = !cb.checked;
      $("#regeln-msg").className = "msg err";
      $("#regeln-msg").textContent = "Fehler: " + err.message;
    }
  }));
  $$("[data-regel-loeschen]").forEach((btn) => btn.addEventListener("click", async () => {
    if (!confirm("Regel wirklich loeschen?")) return;
    try {
      await api("/regeln/" + btn.dataset.regelLoeschen, { method: "DELETE" });
      ladeRegeln();
    } catch (err) {
      $("#regeln-msg").className = "msg err";
      $("#regeln-msg").textContent = "Fehler: " + err.message;
    }
  }));
}
// ===========================================================================
// Belege
// ===========================================================================
$("#beleg-filter-sparte").addEventListener("change", ladeBelege);
$("#form-beleg").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#beleg-msg");
  const datei = $("#beleg-datei").files[0];
  if (!datei) { msg.className = "msg err"; msg.textContent = "Bitte eine Datei wählen."; return; }
  const fd = new FormData();
  fd.append("datei", datei);
  if ($("#beleg-sparte").value) fd.append("sparte_id", $("#beleg-sparte").value);
  try {
    await api("/belege", { method: "POST", body: fd });
    msg.className = "msg ok"; msg.textContent = `Beleg „${datei.name}“ hochgeladen.`;
    $("#beleg-datei").value = "";
    ladeBelege();
  } catch (err) {
    msg.className = "msg err"; msg.textContent = "Fehler: " + err.message;
  }
});
async function ladeBelege() {
  const sp = $("#beleg-filter-sparte").value;
  const tbody = $("#tbl-belege tbody");
  let rows;
  try {
    rows = await api("/belege" + (sp ? "?sparte_id=" + sp : ""));
  } catch (err) {
    $("#belege-leer").hidden = false;
    $("#belege-leer").textContent = "Belege-API nicht verfügbar (" + err.message + ").";
    tbody.innerHTML = "";
    return;
  }
  $("#belege-leer").hidden = rows.length > 0;
  $("#belege-leer").textContent = "Noch keine Belege.";
  tbody.innerHTML = rows.map((b) => {
    const betrag = (b.betrag_erkannt_cent != null) ? centToEuro(b.betrag_erkannt_cent) : "–";
    const name = escapeHtml(b.dateiname || ("Beleg " + b.id));
    return `<tr>
      <td><a href="/api/belege/${b.id}/datei" target="_blank" rel="noopener">${name}</a></td>
      <td>${escapeHtml(sparteName(b.sparte_id))}</td>
      <td>${escapeHtml(b.belegdatum || "")}</td>
      <td class="num">${betrag}</td>
      <td>${escapeHtml(b.notiz || "")}</td>
      <td><a class="link" href="/api/belege/${b.id}/datei" download>Download</a></td>
    </tr>`;
  }).join("");
}

// ===========================================================================
// Bankimport
// ===========================================================================
function kontoLabel(k) {
  return (k.name || ("Konto " + k.id)) + (k.iban ? " · " + k.iban : "");
}
async function initBankimport() {
  if (bankkonten === null) {
    try {
      bankkonten = await api("/bankkonten");
    } catch (err) {
      bankkonten = [];
      $("#import-msg").className = "msg err";
      $("#import-msg").textContent = "Bankkonten-API nicht verfügbar (" + err.message + ").";
    }
    const opts = bankkonten.map((k) => `<option value="${k.id}">${escapeHtml(kontoLabel(k))}</option>`).join("");
    $("#import-konto").innerHTML = opts || `<option value="">Kein Konto</option>`;
    $("#umsatz-konto").innerHTML = opts || `<option value="">Kein Konto</option>`;
  }
  if (bankkonten.length) ladeUmsaetze();
}
$("#umsatz-konto").addEventListener("change", ladeUmsaetze);

$("#form-konto").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#konto-msg");
  const name = $("#konto-name").value.trim();
  if (!name) { msg.className = "msg err"; msg.textContent = "Bitte einen Namen angeben."; return; }
  const body = {
    name,
    iban: $("#konto-iban").value.trim() || null,
    bank: $("#konto-bank").value.trim() || null,
    sparte_id: $("#konto-sparte").value ? parseInt($("#konto-sparte").value, 10) : null,
  };
  try {
    const konto = await api("/bankkonten", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    msg.className = "msg ok"; msg.textContent = `Konto „${konto.name}“ angelegt.`;
    $("#konto-name").value = ""; $("#konto-iban").value = "";
    $("#konto-bank").value = ""; $("#konto-sparte").value = "";
    bankkonten = null;
    await initBankimport();
    $("#import-konto").value = String(konto.id);
    $("#umsatz-konto").value = String(konto.id);
    ladeUmsaetze();
  } catch (err) {
    msg.className = "msg err"; msg.textContent = "Fehler: " + err.message;
  }
});
$("#form-import").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#import-msg");
  const datei = $("#import-datei").files[0];
  const kontoId = $("#import-konto").value;
  if (!datei || !kontoId) { msg.className = "msg err"; msg.textContent = "Bitte Konto und CSV-Datei wählen."; return; }
  const fd = new FormData();
  fd.append("datei", datei);
  fd.append("bankkonto_id", kontoId);
  msg.className = "msg"; msg.textContent = "Importiere …";
  try {
    const res = await api("/import/csv", { method: "POST", body: fd });
    $("#imp-neu").textContent = res.neu ?? 0;
    $("#imp-dub").textContent = res.dubletten ?? 0;
    $("#imp-ges").textContent = res.gesamt ?? 0;
    $("#import-ergebnis").hidden = false;
    msg.className = "msg ok"; msg.textContent = `Import abgeschlossen: ${res.neu ?? 0} neu, ${res.dubletten ?? 0} Dubletten.`;
    $("#import-datei").value = "";
    $("#umsatz-konto").value = kontoId;
    ladeUmsaetze();
  } catch (err) {
    msg.className = "msg err"; msg.textContent = "Fehler: " + err.message;
  }
});
let umsaetzeCache = [];
async function ladeUmsaetze() {

  const kontoId = $("#umsatz-konto").value;
  const tbody = $("#tbl-umsaetze tbody");
  if (!kontoId) { tbody.innerHTML = ""; $("#umsaetze-leer").hidden = false; return; }
  const status = $("#umsatz-status").value;
  let rows;
  try {
    rows = await api("/bankumsaetze?bankkonto_id=" + kontoId + (status ? "&status=" + status : ""));
  } catch (err) {
    tbody.innerHTML = "";
    $("#umsaetze-leer").hidden = false;
    $("#umsaetze-leer").textContent = "Bankumsätze-API nicht verfügbar (" + err.message + ").";
    return;
  }
  umsaetzeCache = rows;
  $("#umsaetze-leer").hidden = rows.length > 0;
  $("#umsaetze-leer").textContent = "Keine Umsätze.";
  tbody.innerHTML = rows.map((u) => {
    const neg = (u.betrag_cent || 0) < 0;
    const st = u.importstatus || "offen";
    let aktionen = "";
    const vorschlagBadge = u.vorschlag
      ? `<div><span class="badge einnahme">Vorschlag: ${escapeHtml(u.vorschlag.regel_name)}</span></div>` : "";
    if (st === "offen") {
      aktionen = `<button class="link" data-uebernehmen="${u.id}">Übernehmen</button>
        <button class="link" data-ignorieren="${u.id}">ignorieren</button>`;
    } else if (st === "ignoriert") {
      aktionen = `<button class="link" data-oeffnen="${u.id}">wieder öffnen</button>`;
    }
    return `<tr data-uid="${u.id}">
      <td>${escapeHtml(u.datum || "")}</td>
      <td>${escapeHtml(u.text || "")}${vorschlagBadge}</td>
      <td>${escapeHtml(u.gegenpartei || "")}</td>
      <td class="num ${neg ? "neg" : "pos"}">${centToEuro(u.betrag_cent || 0)}</td>
      <td><span class="badge ${escapeHtml(st)}">${escapeHtml(st)}</span></td>
      <td class="row-actions">${aktionen}</td>
    </tr>`;
  }).join("");
  const vorschlagIds = rows.filter((u) => u.importstatus === "offen" && u.vorschlag).map((u) => u.id);
  $("#vorschlaege-alle").disabled = vorschlagIds.length === 0;
  $$("#tbl-umsaetze [data-uebernehmen]").forEach((b) => b.addEventListener("click", () =>
    oeffneUmsatzEditor(parseInt(b.dataset.uebernehmen, 10))));
  $$("#tbl-umsaetze [data-ignorieren]").forEach((b) => b.addEventListener("click", () =>
    setzeUmsatzStatus(parseInt(b.dataset.ignorieren, 10), "ignoriert")));
  $$("#tbl-umsaetze [data-oeffnen]").forEach((b) => b.addEventListener("click", () =>
    setzeUmsatzStatus(parseInt(b.dataset.oeffnen, 10), "offen")));
}
$("#vorschlaege-alle").addEventListener("click", async () => {
  const ids = umsaetzeCache
    .filter((u) => u.importstatus === "offen" && u.vorschlag)
    .map((u) => u.id);
  if (!ids.length) return;
  const btn = $("#vorschlaege-alle");
  const msg = $("#vorschlaege-msg");
  btn.disabled = true;
  try {
    const res = await api("/bankumsaetze/vorschlaege-uebernehmen", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ umsatz_ids: ids }),
    });
    msg.className = "msg ok";
    msg.textContent = `${res.verbucht} verbucht, ${res.uebersprungen} uebersprungen.`;
    await ladeUmsaetze();
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = "Fehler: " + err.message;
    btn.disabled = false;
  }
});
$("#umsatz-status").addEventListener("change", ladeUmsaetze);

async function setzeUmsatzStatus(id, status) {
  try {
    await api("/bankumsaetze/" + id, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ importstatus: status }),
    });
    ladeUmsaetze();
  } catch (err) {
    $("#import-msg").className = "msg err";
    $("#import-msg").textContent = "Fehler: " + err.message;
  }
}

// Inline-Editor: Umsatz einer Sparte/Kategorie zuordnen und verbuchen.
async function oeffneUmsatzEditor(id) {
  const u = umsaetzeCache.find((x) => x.id === id);
  if (!u) return;
  // Nur ein Editor gleichzeitig
  $$("#tbl-umsaetze .umsatz-editor").forEach((tr) => tr.remove());
  const zeile = $(`#tbl-umsaetze tr[data-uid="${id}"]`);
  const defaultTyp = (u.betrag_cent || 0) < 0 ? "ausgabe" : "einnahme";
  const v = u.vorschlag || null;
  const spartenOpts = sparten.map((s) =>
    `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join("");
  const tr = document.createElement("tr");
  tr.className = "umsatz-editor";
  tr.innerHTML = `<td colspan="6">
    <div class="ue-form">
      <label>Typ <select class="ue-typ">
        <option value="ausgabe">Ausgabe</option>
        <option value="einnahme">Einnahme</option>
        <option value="umbuchung">Umbuchung</option>
      </select></label>
      <label>Sparte <select class="ue-sparte">${spartenOpts}</select></label>
      <label>Kategorie <select class="ue-kat"></select></label>
      <button type="button" class="btn accent ue-save">Verbuchen</button>
      <button type="button" class="btn ghost ue-cancel">Abbrechen</button>
      <span class="hint ue-hint"></span>
    </div>
  </td>`;
  zeile.after(tr);

  const selSparte = tr.querySelector(".ue-sparte");
  const selTyp = tr.querySelector(".ue-typ");
  const selKat = tr.querySelector(".ue-kat");
  const hint = tr.querySelector(".ue-hint");
  async function fuelleKats() {
    const kats = await ladeKategorien(selSparte.value);
    const passend = kats.filter((k) => k.richtung === selTyp.value || k.richtung === "beides");
    selKat.innerHTML = passend.map((k) =>
      `<option value="${k.id}">${escapeHtml(k.name)}</option>`).join("")
      || `<option value="">– keine passende Kategorie –</option>`;
  }
  selSparte.addEventListener("change", fuelleKats);
  if (v) {
  selTyp.addEventListener("change", fuelleKats);
    selSparte.value = String(v.sparte_id);
    hint.textContent = v.quelle === "regel"
      ? `Vorschlag aus Regel „${v.regel_name}“` : "Vorschlag aus früheren Buchungen";
    selTyp.value = v.typ || defaultTyp;
    hint.textContent = "Vorschlag: " + v.regel_name;
  } else {
    selTyp.value = defaultTyp;
  }
  await fuelleKats();
  if (v && [...selKat.options].some((o) => o.value === String(v.kategorie_id))) {
    selKat.value = String(v.kategorie_id);
  }
  tr.querySelector(".ue-cancel").addEventListener("click", () => tr.remove());
  tr.querySelector(".ue-save").addEventListener("click", async () => {
    if (!selKat.value) { hint.textContent = "Bitte zuerst eine passende Kategorie anlegen."; return; }
    try {
      const res = await api("/bankumsaetze/" + id + "/verbuchen", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sparte_id: parseInt(selSparte.value, 10),
          kategorie_id: parseInt(selKat.value, 10),
          typ: selTyp.value,
        }),
      });
      $("#import-msg").className = "msg ok";
      $("#import-msg").textContent = `Verbucht: ${centToEuro(res.betrag_cent)} (${res.typ})`
        + (res.regel_angelegt ? " — Regel gemerkt." : ".");
      ladeUmsaetze();
      $("#import-msg").textContent = `Verbucht: ${centToEuro(res.betrag_cent)} (${res.typ}).`;
    } catch (err) {
      hint.textContent = "Fehler: " + err.message;
    }
  });
}

// ===========================================================================
// Excel-Import (Altdaten-Migration)
// ===========================================================================
// Jede Datei wird zuerst mit modus=pruefen hochgeladen (aendert nichts) und
// erst nach Klick mit modus=einspielen wirklich uebernommen.
let xlDateien = [];   // {file, status: 'prueft'|'geprueft'|'eingespielt'|'fehler', bericht|fehler}

const xlDrop = $("#xl-drop");
const xlInput = $("#xl-datei");
xlDrop.addEventListener("click", () => xlInput.click());
xlDrop.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); xlInput.click(); }
});
["dragover", "dragenter"].forEach((ev) => xlDrop.addEventListener(ev, (e) => {
  e.preventDefault(); xlDrop.classList.add("drag");
}));
["dragleave", "drop"].forEach((ev) => xlDrop.addEventListener(ev, (e) => {
  e.preventDefault(); xlDrop.classList.remove("drag");
}));
xlDrop.addEventListener("drop", (e) => xlNimmDateien(e.dataTransfer.files));
xlInput.addEventListener("change", () => { xlNimmDateien(xlInput.files); xlInput.value = ""; });

function xlNimmDateien(fileList) {
  const passend = Array.from(fileList || []).filter((f) => /\.(xls|xlsx|xlsm)$/i.test(f.name));
  if (!passend.length) {
    $("#xl-msg").className = "msg err";
    $("#xl-msg").textContent = "Keine Excel-Dateien (.xls/.xlsx) dabei.";
    $("#xl-alle-wrap").hidden = false;
    return;
  }
  passend.forEach((f) => {
    const eintrag = { file: f, status: "prueft", bericht: null, fehler: null };
    xlDateien.push(eintrag);
    xlPruefe(eintrag);
  });
  xlRender();
}

async function xlUpload(eintrag, modus) {
  const fd = new FormData();
  fd.append("datei", eintrag.file);
  fd.append("sparte_id", $("#xl-sparte").value);
  fd.append("modus", modus);
  return api("/import/excel", { method: "POST", body: fd });
}

async function xlPruefe(eintrag) {
  eintrag.status = "prueft"; eintrag.fehler = null;
  try {
    eintrag.bericht = await xlUpload(eintrag, "pruefen");
    eintrag.status = "geprueft";
  } catch (err) {
    eintrag.status = "fehler";
    eintrag.fehler = err.message;
  }
  xlRender();
}

async function xlSpieleEin(eintrag) {
  eintrag.status = "prueft";
  xlRender();
  try {
    eintrag.bericht = await xlUpload(eintrag, "einspielen");
    eintrag.status = "eingespielt";
  } catch (err) {
    eintrag.status = "fehler";
    eintrag.fehler = err.message;
  }
  xlRender();
}

function xlRender() {
  const el = $("#xl-liste");
  el.innerHTML = xlDateien.map((d, i) => {
    const b = d.bericht;
    let inhalt = "";
    if (d.status === "prueft") {
      inhalt = `<span class="hint">Wird verarbeitet …</span>`;
    } else if (d.status === "fehler") {
      inhalt = `<span class="msg err">Fehler: ${escapeHtml(d.fehler)}</span>
        <button class="link" data-xl-retry="${i}">nochmal prüfen</button>`;
    } else if (b) {
      const teile = [
        `<strong>${b.buchungen_neu}</strong> Buchungen`,
        b.zeitraum ? `${escapeHtml(b.zeitraum.von)} bis ${escapeHtml(b.zeitraum.bis)}` : null,
        `${b.monate_mit_daten} Monatsblätter`,
        `Einnahmen ${centToEuro(b.einnahmen_cent)}`,
        `Ausgaben ${centToEuro(b.ausgaben_cent)}`,
        b.duplikate ? `${b.duplikate} Duplikate übersprungen` : null,
      ].filter(Boolean).join(" · ");
      const neueKat = b.neue_kategorien.length
        ? `<div class="hint">Neue Kategorien: ${b.neue_kategorien.map(escapeHtml).join(", ")}</div>` : "";
      const warn = b.warnungen.length
        ? `<details class="xl-warn"><summary>${b.warnungen.length} Hinweise</summary>
           <ul>${b.warnungen.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul></details>` : "";
      const aktion = d.status === "eingespielt"
        ? `<span class="badge einnahme">eingespielt: ${b.eingespielt} Buchungen</span>`
        : (b.buchungen_neu > 0
          ? `<button class="btn accent xl-btn" data-xl-import="${i}">Einspielen</button>`
          : `<span class="badge umbuchung">nichts Neues</span>`);
      inhalt = `<div class="xl-zeile1">${teile}</div>${neueKat}${warn}
        <div class="xl-aktion">${aktion}</div>`;
    }
    return `<div class="xl-file ${d.status}">
      <div class="xl-name">🗎 ${escapeHtml(d.file.name)}</div>${inhalt}</div>`;
  }).join("");
  $$("#xl-liste [data-xl-import]").forEach((btn) => btn.addEventListener("click", () =>
    xlSpieleEin(xlDateien[parseInt(btn.dataset.xlImport, 10)])));
  $$("#xl-liste [data-xl-retry]").forEach((btn) => btn.addEventListener("click", () =>
    xlPruefe(xlDateien[parseInt(btn.dataset.xlRetry, 10)])));
  const bereit = xlDateien.filter((d) => d.status === "geprueft" && d.bericht
    && d.bericht.buchungen_neu > 0);
  $("#xl-alle-wrap").hidden = bereit.length < 2 && !$("#xl-msg").textContent;
  $("#xl-alle").hidden = bereit.length < 2;
}

$("#xl-alle").addEventListener("click", async () => {
  const bereit = xlDateien.filter((d) => d.status === "geprueft" && d.bericht
    && d.bericht.buchungen_neu > 0);
  for (const d of bereit) {
    await xlSpieleEin(d);
  }
  const gesamt = xlDateien.reduce((a, d) =>
    a + (d.status === "eingespielt" ? (d.bericht.eingespielt || 0) : 0), 0);
  $("#xl-msg").className = "msg ok";
  $("#xl-msg").textContent = `Fertig — ${gesamt} Buchungen eingespielt.`;
  $("#xl-alle-wrap").hidden = false;
});

// Sparte gewechselt: bereits eingespielte Dateien bleiben stehen,
// geprüfte werden fuer die neue Sparte erneut geprueft.
$("#xl-sparte") && $("#xl-sparte").addEventListener("change", () => {
  xlDateien.filter((d) => d.status !== "eingespielt").forEach((d) => xlPruefe(d));
});

// ===========================================================================
// Init
// ===========================================================================
async function init() {
  sparten = await api("/sparten");
  buildSparteColors();
  const opt = (s) => `<option value="${s.id}">${escapeHtml(s.name)}${s.geschuetzt ? " 🔒" : ""}</option>`;
  const optionen = sparten.map(opt).join("");
  $("#b-sparte").innerHTML = optionen;
  $("#k-sparte").innerHTML = optionen;
  $("#xl-sparte").innerHTML = optionen;
  $("#u-von").innerHTML = optionen;
  $("#u-nach").innerHTML = optionen;
  if (sparten.length > 1) $("#u-nach").selectedIndex = 1;
  $("#ex-sparte").insertAdjacentHTML("beforeend", optionen);
  $("#u-datum").value = todayISO();
  $("#beleg-sparte").insertAdjacentHTML("beforeend", optionen);
  $("#beleg-filter-sparte").insertAdjacentHTML("beforeend", optionen);
  $("#konto-sparte").insertAdjacentHTML("beforeend", optionen);
  $("#b-datum").value = todayISO();
  await ladeGlobalgruppen();
  renderSpartenPills();
  await erneuereZeilenKategorien();
  addZeile();
  ladeUebersicht();
}
init().catch((e) => {
  document.body.insertAdjacentHTML("afterbegin",
    `<p class="msg err" style="padding:12px">Init-Fehler: ${escapeHtml(e.message)}</p>`);
});
