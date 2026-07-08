"use strict";

// ---------- Helfer ----------
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function euroToCent(str) {
  if (str == null) return 0;
  const s = String(str).trim().replace(/\s|€/g, "").replace(/\./g, "").replace(",", ".");
  // Achtung: obige Zeile behandelt "1.234,56" korrekt (Tausenderpunkt weg, Komma -> Punkt)
  const val = parseFloat(s);
  if (isNaN(val)) return 0;
  return Math.round(val * 100);
}
function centToEuro(cent) {
  return (cent / 100).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
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
let kategorienCache = {}; // sparte_id -> [kategorien]

async function ladeKategorien(sparteId) {
  if (!sparteId) return [];
  if (!kategorienCache[sparteId]) {
    kategorienCache[sparteId] = await api("/kategorien?sparte_id=" + sparteId);
  }
  return kategorienCache[sparteId];
}
function invalidateKategorien(sparteId) { delete kategorienCache[sparteId]; }

// ---------- Tabs ----------
$$(".tab").forEach((btn) => btn.addEventListener("click", () => {
  $$(".tab").forEach((b) => b.classList.remove("active"));
  $$(".tab-panel").forEach((p) => p.classList.remove("active"));
  btn.classList.add("active");
  $("#tab-" + btn.dataset.tab).classList.add("active");
  if (btn.dataset.tab === "dashboard") ladeDashboard();
  if (btn.dataset.tab === "liste") ladeBuchungen();
  if (btn.dataset.tab === "kategorien") ladeKategorienTabelle();
}));

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
  if (active === "dashboard") ladeDashboard();
  else if (active === "liste") ladeBuchungen();
});

// ---------- Init ----------
async function init() {
  sparten = await api("/sparten");
  const opt = (s) => `<option value="${s.id}">${s.name}${s.geschuetzt ? " 🔒" : ""}</option>`;
  $("#f-sparte").insertAdjacentHTML("beforeend", sparten.map(opt).join(""));
  $("#b-sparte").innerHTML = sparten.map(opt).join("");
  $("#k-sparte").innerHTML = sparten.map(opt).join("");
  $("#b-datum").value = todayISO();
  await erneuereZeilenKategorien();
  addZeile();
  ladeDashboard();
}

// ---------- Dashboard ----------
async function ladeDashboard() {
  const data = await api("/dashboard?" + filterQuery());
  $("#kpi-ein").textContent = centToEuro(data.einnahmen_cent);
  $("#kpi-aus").textContent = centToEuro(data.ausgaben_cent);
  $("#kpi-saldo").textContent = centToEuro(data.saldo_cent);
  $("#kpi-saldo").style.color = data.saldo_cent < 0 ? "var(--aus)" : "var(--ein)";

  $("#tbl-sparte tbody").innerHTML = data.per_sparte.map((r) =>
    `<tr><td>${r.sparte}</td><td class="num">${centToEuro(r.einnahmen_cent)}</td>
     <td class="num">${centToEuro(r.ausgaben_cent)}</td>
     <td class="num">${centToEuro(r.einnahmen_cent - r.ausgaben_cent)}</td></tr>`).join("")
    || `<tr><td colspan="4" class="hint">Keine Daten.</td></tr>`;

  $("#tbl-kat tbody").innerHTML = data.per_kategorie.slice(0, 10).map((r) =>
    `<tr><td>${r.kategorie}</td><td><span class="badge ${r.typ}">${r.typ}</span></td>
     <td class="num">${centToEuro(r.betrag_cent)}</td></tr>`).join("")
    || `<tr><td colspan="3" class="hint">Keine Daten.</td></tr>`;
}

// ---------- Buchung erfassen ----------
function kategorieOptions(kats) {
  return kats.map((k) => `<option value="${k.id}">${k.name} (${k.richtung})</option>`).join("");
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

  if (zeilen.length === 0) { msg.className = "msg err"; msg.textContent = "Mindestens eine Zeile mit Betrag > 0 noetig."; return; }

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
    const kats = (b.zeilen || []).map((z) => z.kategorie_name + (b.zeilen.length > 1 ? " (" + centToEuro(z.betrag_cent) + ")" : "")).join(", ");
    return `<tr>
      <td>${b.datum}</td><td>${b.sparte_name}</td>
      <td><span class="badge ${b.typ}">${b.typ}</span></td>
      <td>${b.text || ""}</td><td>${kats}</td>
      <td class="num">${centToEuro(b.betrag_cent)}</td>
      <td><button class="link" data-del="${b.id}">löschen</button></td></tr>`;
  }).join("");
  $$("#tbl-buchungen [data-del]").forEach((btn) => btn.addEventListener("click", async () => {
    if (!confirm("Buchung wirklich loeschen?")) return;
    await api("/buchungen/" + btn.dataset.del, { method: "DELETE" });
    ladeBuchungen();
  }));
}

// ---------- Kategorien ----------
async function ladeKategorienTabelle() {
  const kats = await api("/kategorien?sparte_id=" + $("#k-sparte").value);
  const byId = Object.fromEntries(kats.map((k) => [k.id, k.name]));
  $("#tbl-kategorien tbody").innerHTML = kats.map((k) =>
    `<tr><td>${k.name}</td><td>${k.richtung}</td><td>${k.parent_id ? (byId[k.parent_id] || "") : ""}</td></tr>`).join("")
    || `<tr><td colspan="3" class="hint">Noch keine Kategorien.</td></tr>`;
  $("#k-parent").innerHTML = '<option value="">– keine –</option>' +
    kats.map((k) => `<option value="${k.id}">${k.name}</option>`).join("");
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

init().catch((e) => { document.body.insertAdjacentHTML("afterbegin", `<p class="msg err" style="padding:12px">Init-Fehler: ${e.message}</p>`); });
