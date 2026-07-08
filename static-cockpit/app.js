"use strict";

// ---------- Helfer ----------
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function euroToCent(str) {
  if (str == null) return 0;
  const s = String(str).trim().replace(/\s|€/g, "").replace(/\./g, "").replace(",", ".");
  const val = parseFloat(s);
  if (isNaN(val)) return 0;
  return Math.round(val * 100);
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

// ---------- Zustand ----------
let sparten = [];
let bankkonten = null;
let kategorienCache = {};

// ---------- Sparten-Farben (Signatur des Cockpits) ----------
const SPARTEN_PALETTE = ["#6AA9FF", "#2DD4BF", "#C084FC", "#F472B6", "#FB923C", "#818CF8"];
let sparteColorById = {};
let sparteColorByName = {};
let sparteKuerzelByName = {};
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

// ---------- Theme (Hell/Dunkel) ----------
function effectiveTheme() {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "dark" || attr === "light") return attr;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
function renderThemeIcon() {
  const icon = $("#theme-toggle .theme-icon");
  icon.textContent = effectiveTheme() === "dark" ? "☀️" : "🌙";
}
$("#theme-toggle").addEventListener("click", () => {
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("theme", next); } catch (e) {}
  renderThemeIcon();
  // Charts neu zeichnen, damit CSS-Variablen-Farben passen
  if ($(".tab.active").dataset.tab === "dashboard") ladeDashboard();
  else if ($(".tab.active").dataset.tab === "jahre") ladeJahresvergleich();
});
renderThemeIcon();

// ---------- Tabs ----------
function activateTab(name) {
  $$(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + name));
  if (name === "dashboard") ladeDashboard();
  if (name === "jahre") ladeJahresvergleich();
  if (name === "liste") ladeBuchungen();
  if (name === "kategorien") ladeKategorienTabelle();
  if (name === "belege") ladeBelege();
  if (name === "bankimport") initBankimport();
}
$$(".tab").forEach((btn) => btn.addEventListener("click", () => activateTab(btn.dataset.tab)));

// ---------- Globaler Filter ----------
function filterQuery() {
  const p = new URLSearchParams();
  if ($("#f-sparte").value) p.set("sparte_id", $("#f-sparte").value);
  if ($("#f-von").value) p.set("von", $("#f-von").value);
  if ($("#f-bis").value) p.set("bis", $("#f-bis").value);
  return p.toString();
}
$("#f-apply").addEventListener("click", () => {
  const active = $(".tab.active").dataset.tab;
  renderSpartenStrip();
  if (active === "dashboard") ladeDashboard();
  else if (active === "jahre") ladeJahresvergleich();
  else if (active === "liste") ladeBuchungen();
});
$("#f-sparte").addEventListener("change", renderSpartenStrip);

// ---------- Sparten-Leiste ----------
function renderSpartenStrip() {
  const el = $("#sparten-strip");
  if (!el) return;
  const cur = $("#f-sparte").value;
  const pills = [
    `<button type="button" class="sp-pill all${cur === "" ? " active" : ""}" data-sp="" title="Alle Sparten"><span class="dot"></span>Alle</button>`,
  ].concat(sparten.map((s) => {
    const c = sparteColorById[s.id];
    const label = escapeHtml(s.kuerzel || s.name);
    return `<button type="button" class="sp-pill${String(s.id) === cur ? " active" : ""}" data-sp="${s.id}" style="--c:${c}" title="${escapeHtml(s.name)}"><span class="dot"></span>${label}</button>`;
  }));
  el.innerHTML = pills.join("");
  $$("#sparten-strip .sp-pill").forEach((b) => b.addEventListener("click", () => {
    $("#f-sparte").value = b.dataset.sp;
    renderSpartenStrip();
    ladeDashboard();
  }));
}

// ---------- Schnellerfassung ----------
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
    msg.textContent = "Übernommen: " + teile.join(" · ") + " – bitte prüfen und speichern.";
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
  activateTab("erfassen");
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

// ---------- Init ----------
async function init() {
  sparten = await api("/sparten");
  buildSparteColors();
  const opt = (s) => `<option value="${s.id}">${escapeHtml(s.name)}${s.geschuetzt ? " 🔒" : ""}</option>`;
  const optionen = sparten.map(opt).join("");
  $("#f-sparte").insertAdjacentHTML("beforeend", optionen);
  $("#b-sparte").innerHTML = optionen;
  $("#k-sparte").innerHTML = optionen;
  $("#beleg-sparte").insertAdjacentHTML("beforeend", optionen);
  $("#beleg-filter-sparte").insertAdjacentHTML("beforeend", optionen);
  $("#konto-sparte").insertAdjacentHTML("beforeend", optionen);
  $("#b-datum").value = todayISO();
  renderSpartenStrip();
  await erneuereZeilenKategorien();
  addZeile();
  ladeDashboard();
}

// ---------- Monats-Label ----------
function monatLabel(ym) {
  // "2026-03" -> "Mrz 26"
  const M = ["Jän", "Feb", "Mrz", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
  const [y, m] = String(ym).split("-");
  const idx = parseInt(m, 10) - 1;
  return (M[idx] || m) + " " + String(y).slice(2);
}

// ---------- Dashboard ----------
async function ladeDashboard() {
  const q = filterQuery();
  const [data, verlauf] = await Promise.all([
    api("/dashboard?" + q),
    api("/verlauf?" + q).catch(() => ({ monate: [] })),
  ]);

  // KPIs
  $("#kpi-ein").textContent = centToEuro(data.einnahmen_cent);
  $("#kpi-aus").textContent = centToEuro(data.ausgaben_cent);
  $("#kpi-saldo").textContent = centToEuro(data.saldo_cent);
  $("#kpi-saldo").style.color = data.saldo_cent < 0 ? "var(--aus)" : "var(--text)";

  const monate = verlauf.monate || [];
  const sub = $("#kpi-saldo-sub");
  if (monate.length) {
    const avg = Math.round(data.saldo_cent / monate.length);
    sub.textContent = `Ø ${centToEuro(avg)} / Monat · ${monate.length} Monate`;
  } else { sub.textContent = ""; }

  // Sparklines
  Charts.sparkline($("#spark-ein"), monate.map((m) => m.einnahmen_cent), { color: "var(--ein)" });
  Charts.sparkline($("#spark-aus"), monate.map((m) => m.ausgaben_cent), { color: "var(--aus)" });
  Charts.sparkline($("#spark-saldo"), monate.map((m) => m.saldo_cent), { color: "var(--accent)" });

  // Verlauf-Diagramm
  Charts.barGroup($("#chart-verlauf"), {
    labels: monate.map((m) => monatLabel(m.monat)),
    series: [
      { name: "Einnahmen", color: "var(--ein)", values: monate.map((m) => m.einnahmen_cent) },
      { name: "Ausgaben", color: "var(--aus)", values: monate.map((m) => m.ausgaben_cent) },
    ],
    line: { name: "Saldo", color: "var(--accent)", values: monate.map((m) => m.saldo_cent) },
  });

  // Donut: Ausgaben je Sparte
  Charts.donut($("#chart-sparte"),
    data.per_sparte.map((r) => ({ label: r.sparte, value: r.ausgaben_cent, color: colorForSparteName(r.sparte) })),
    { centerLabel: "Ausgaben" });

  // Ausgaben nach Kategorie (Top 10)
  Charts.hbars($("#chart-kategorie"),
    data.per_kategorie.filter((r) => r.typ === "ausgabe").slice(0, 10)
      .map((r) => ({ label: r.kategorie, value: r.betrag_cent, color: "var(--aus)" })));

  // Detailtabellen
  $("#tbl-sparte tbody").innerHTML = data.per_sparte.map((r) => {
    const saldo = r.einnahmen_cent - r.ausgaben_cent;
    return `<tr><td><span class="sp-tag"><span class="dot" style="background:${colorForSparteName(r.sparte)}"></span>${escapeHtml(r.sparte)}</span></td>
     <td class="num">${centToEuro(r.einnahmen_cent)}</td>
     <td class="num">${centToEuro(r.ausgaben_cent)}</td>
     <td class="num" style="color:${saldo < 0 ? "var(--aus)" : "var(--ein)"}">${centToEuro(saldo)}</td></tr>`;
  }).join("") || `<tr><td colspan="4" class="hint">Keine Daten.</td></tr>`;

  $("#tbl-kat tbody").innerHTML = data.per_kategorie.slice(0, 10).map((r) =>
    `<tr><td>${escapeHtml(r.kategorie)}</td><td><span class="badge ${r.typ}">${r.typ}</span></td>
     <td class="num">${centToEuro(r.betrag_cent)}</td></tr>`).join("")
    || `<tr><td colspan="3" class="hint">Keine Daten.</td></tr>`;
}

// ---------- Jahresvergleich ----------
async function ladeJahresvergleich() {
  const data = await api("/jahresvergleich?" + filterQuery());

  Charts.barGroup($("#chart-jahre"), {
    labels: data.gesamt.map((g) => g.jahr),
    series: [
      { name: "Einnahmen", color: "var(--ein)", values: data.gesamt.map((g) => g.einnahmen_cent) },
      { name: "Ausgaben", color: "var(--aus)", values: data.gesamt.map((g) => g.ausgaben_cent) },
    ],
    line: { name: "Saldo", color: "var(--accent)", values: data.gesamt.map((g) => g.saldo_cent) },
    empty: "Noch keine Buchungen — sobald du erfasst, erscheint hier der Jahresvergleich.",
  });

  $("#tbl-jahre tbody").innerHTML = data.gesamt.map((g) =>
    `<tr><td>${g.jahr}</td>
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
    return;
  }
  thead.innerHTML = "<tr><th>Sparte</th>" +
    jahre.map((j) => `<th class="num">${j}</th>`).join("") + "</tr>";
  tbody.innerHTML = data.per_sparte.map((r) =>
    `<tr><td><span class="sp-tag"><span class="dot" style="background:${colorForSparteName(r.sparte)}"></span>${escapeHtml(r.sparte)}</span></td>` +
    jahre.map((j) => {
      const v = r.werte[j];
      return `<td class="num"${v != null && v < 0 ? ' style="color:var(--aus)"' : ""}>${v != null ? centToEuro(v) : "–"}</td>`;
    }).join("") + "</tr>").join("");

  // Matrix Kategorie x Jahr
  const kthead = $("#tbl-jahre-kat thead");
  const ktbody = $("#tbl-jahre-kat tbody");
  const kat = data.per_kategorie || [];
  if (!jahre.length || !kat.length) {
    kthead.innerHTML = "";
    ktbody.innerHTML = `<tr><td class="hint">Keine Daten.</td></tr>`;
  } else {
    kthead.innerHTML = "<tr><th>Kategorie</th>" +
      jahre.map((j) => `<th class="num">${j}</th>`).join("") + "</tr>";
    ktbody.innerHTML = kat.map((r) => {
      const kuerzel = sparteKuerzelByName[r.sparte] || r.sparte;
      return `<tr><td><span class="sp-tag"><span class="dot" style="background:${colorForSparteName(r.sparte)}"></span>${escapeHtml(r.kategorie)} <span class="muted kat-sp">${escapeHtml(kuerzel)}</span></span></td>` +
        jahre.map((j) => {
          const v = r.werte[j];
          return `<td class="num"${v != null && v < 0 ? ' style="color:var(--aus)"' : ""}>${v != null ? centToEuro(v) : "–"}</td>`;
        }).join("") + "</tr>";
    }).join("");
  }
}

// ---------- Buchung erfassen ----------
function kategorieOptions(kats) {
  return kats.map((k) => `<option value="${k.id}">${escapeHtml(k.name)} (${k.richtung})</option>`).join("");
}
async function erneuereZeilenKategorien() {
  const kats = await ladeKategorien($("#b-sparte").value);
  $$("#zeilen .zeile select").forEach((sel) => {
    const cur = sel.value;
    sel.innerHTML = kategorieOptions(kats);
    if (cur) sel.value = cur;
  });
  if (kats.length === 0) $("#b-msg").innerHTML = '<span class="err">Diese Sparte hat noch keine Kategorien. Erst unter "Kategorien" anlegen.</span>';
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
    const created = await api("/buchungen", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    msg.className = "msg ok";
    msg.textContent = `Gespeichert: ${centToEuro(created.betrag_cent)} (${created.typ}).`;
    $("#b-text").value = "";
    $("#zeilen").innerHTML = "";
    addZeile();
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = "Fehler: " + err.message;
  }
});

// ---------- Buchungen-Liste ----------
async function ladeBuchungen() {
  const rows = await api("/buchungen?" + filterQuery());
  $("#liste-leer").hidden = rows.length > 0;
  $("#tbl-buchungen tbody").innerHTML = rows.map((b) => {
    const kats = (b.zeilen || []).map((z) => escapeHtml(z.kategorie_name) + (b.zeilen.length > 1 ? " (" + centToEuro(z.betrag_cent) + ")" : "")).join(", ");
    return `<tr>
      <td>${b.datum}</td>
      <td><span class="sp-tag"><span class="dot" style="background:${colorForSparteName(b.sparte_name)}"></span>${escapeHtml(b.sparte_name)}</span></td>
      <td><span class="badge ${b.typ}">${b.typ}</span></td>
      <td>${escapeHtml(b.text || "")}</td><td>${kats}</td>
      <td class="num">${centToEuro(b.betrag_cent)}</td>
      <td><button class="link" data-del="${b.id}">löschen</button></td></tr>`;
  }).join("");
  $$("#tbl-buchungen [data-del]").forEach((btn) => btn.addEventListener("click", async () => {
    if (!confirm("Buchung wirklich löschen?")) return;
    await api("/buchungen/" + btn.dataset.del, { method: "DELETE" });
    ladeBuchungen();
  }));
}

// ---------- Kategorien ----------
async function ladeKategorienTabelle() {
  const kats = await api("/kategorien?sparte_id=" + $("#k-sparte").value);
  const byId = Object.fromEntries(kats.map((k) => [k.id, k.name]));
  $("#tbl-kategorien tbody").innerHTML = kats.map((k) =>
    `<tr><td>${escapeHtml(k.name)}</td><td>${k.richtung}</td><td>${escapeHtml(k.parent_id ? (byId[k.parent_id] || "") : "")}</td></tr>`).join("")
    || `<tr><td colspan="3" class="hint">Noch keine Kategorien.</td></tr>`;
  $("#k-parent").innerHTML = '<option value="">– keine –</option>' +
    kats.map((k) => `<option value="${k.id}">${escapeHtml(k.name)}</option>`).join("");
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
    msg.className = "msg ok"; msg.textContent = `Kategorie "${body.name}" angelegt.`;
    $("#k-name").value = "";
    invalidateKategorien(body.sparte_id);
    ladeKategorienTabelle();
    if (String(body.sparte_id) === $("#b-sparte").value) erneuereZeilenKategorien();
  } catch (err) {
    msg.className = "msg err"; msg.textContent = "Fehler: " + err.message;
  }
});

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
    msg.className = "msg ok"; msg.textContent = `Beleg "${datei.name}" hochgeladen.`;
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
    $("#belege-leer").textContent = "Belege-API noch nicht verfügbar (" + err.message + ").";
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
      $("#import-msg").textContent = "Bankkonten-API noch nicht verfügbar (" + err.message + ").";
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
    msg.className = "msg ok"; msg.textContent = `Konto "${konto.name}" angelegt.`;
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
async function ladeUmsaetze() {
  const kontoId = $("#umsatz-konto").value;
  const tbody = $("#tbl-umsaetze tbody");
  if (!kontoId) { tbody.innerHTML = ""; $("#umsaetze-leer").hidden = false; return; }
  let rows;
  try {
    rows = await api("/bankumsaetze?bankkonto_id=" + kontoId);
  } catch (err) {
    tbody.innerHTML = "";
    $("#umsaetze-leer").hidden = false;
    $("#umsaetze-leer").textContent = "Bankumsätze-API noch nicht verfügbar (" + err.message + ").";
    return;
  }
  $("#umsaetze-leer").hidden = rows.length > 0;
  $("#umsaetze-leer").textContent = "Keine Umsätze.";
  tbody.innerHTML = rows.map((u) => {
    const neg = (u.betrag_cent || 0) < 0;
    return `<tr>
      <td>${u.datum || ""}</td>
      <td>${escapeHtml(u.text || "")}</td>
      <td>${escapeHtml(u.gegenpartei || "")}</td>
      <td class="num ${neg ? "neg" : "pos"}">${centToEuro(u.betrag_cent || 0)}</td>
      <td><span class="badge ${u.importstatus || "offen"}">${u.importstatus || "offen"}</span></td>
    </tr>`;
  }).join("");
}

init().catch((e) => { document.body.insertAdjacentHTML("afterbegin", `<p class="msg err" style="padding:12px">Init-Fehler: ${e.message}</p>`); });
