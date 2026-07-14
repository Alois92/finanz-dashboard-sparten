"use strict";

/* Selbstgebaute Diagramme für das Studio — Inline-SVG bzw. HTML, keine
   Fremd-Libraries. Farben kommen als var(--…)-Referenzen, damit der
   Hell/Dunkel-Umschalter ohne Neuzeichnen der Logik funktioniert. */
const Charts = (() => {

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function euro(cent) {
    return (cent / 100).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
  }
  function empty(el, text) {
    el.innerHTML = `<p class="chart-empty">${esc(text || "Keine Daten im gewählten Zeitraum.")}</p>`;
  }
  function niceMax(v) {
    if (v <= 0) return 1;
    const exp = Math.pow(10, Math.floor(Math.log10(v)));
    const f = v / exp;
    const nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
    return nice * exp;
  }
  function kLabel(cent) {
    const e = cent / 100;
    if (Math.abs(e) >= 1000) {
      return (e / 1000).toLocaleString("de-DE", { maximumFractionDigits: 1 }) + "k";
    }
    return e.toLocaleString("de-DE", { maximumFractionDigits: 0 });
  }

  /* ---- Sparkline: fester Streifen, deckt nie Text ab -------------------- */
  function sparkline(el, values, { color } = {}) {
    const vals = values && values.length ? values : [];
    const c = color || "var(--accent)";
    if (vals.length < 2 || vals.every((v) => v === vals[0])) {
      el.innerHTML = `<svg viewBox="0 0 120 32" preserveAspectRatio="none" aria-hidden="true"><line x1="0" y1="16" x2="120" y2="16" stroke="${c}" stroke-width="1.5" vector-effect="non-scaling-stroke" opacity=".45"/></svg>`;
      return;
    }
    const W = 120, H = 32, pad = 3;
    const max = Math.max(...vals), min = Math.min(...vals);
    const span = max - min || 1;
    const x = (i) => pad + (W - 2 * pad) * (i / (vals.length - 1));
    const y = (v) => pad + (H - 2 * pad) * (1 - (v - min) / span);
    const pts = vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    const area = `${pad},${H - pad} ` + pts.join(" ") + ` ${W - pad},${H - pad}`;
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">`
      + `<polygon points="${area}" fill="${c}" opacity=".12"/>`
      + `<polyline points="${pts.join(" ")}" fill="none" stroke="${c}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>`
      + `</svg>`;
  }

  /* ---- Balkengruppen + optionale Linie (Verlauf, Jahre) ------------------ */
  function barGroup(el, { labels, series, line, empty: emptyText }) {
    if (!labels || !labels.length) { empty(el, emptyText); return; }
    const W = 900, H = 300;
    const padL = 56, padR = 16, padT = 14, padB = 34;
    const iw = W - padL - padR, ih = H - padT - padB;

    let maxV = 0;
    series.forEach((s) => s.values.forEach((v) => { if (v > maxV) maxV = v; }));
    if (line) line.values.forEach((v) => { if (v > maxV) maxV = v; });
    maxV = niceMax(maxV);

    const n = labels.length;
    const slot = iw / n;
    const barW = Math.min(26, (slot * 0.62) / series.length);
    const yOf = (v) => padT + ih * (1 - Math.max(v, 0) / maxV);

    let out = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
    // Gitter + Y-Beschriftung
    for (let g = 0; g <= 4; g++) {
      const v = maxV * g / 4, gy = yOf(v);
      out += `<line x1="${padL}" y1="${gy}" x2="${W - padR}" y2="${gy}" stroke="var(--border)" stroke-width="1"/>`;
      out += `<text x="${padL - 8}" y="${gy + 4}" text-anchor="end" font-size="11" fill="var(--muted)" font-family="var(--font-num)">${kLabel(v)}</text>`;
    }
    // Balken
    labels.forEach((lab, i) => {
      const cx = padL + slot * i + slot / 2;
      const groupW = barW * series.length + 3 * (series.length - 1);
      series.forEach((s, si) => {
        const v = Math.max(s.values[i] || 0, 0);
        const bx = cx - groupW / 2 + si * (barW + 3);
        const by = yOf(v);
        out += `<rect x="${bx.toFixed(1)}" y="${by.toFixed(1)}" width="${barW.toFixed(1)}" height="${(padT + ih - by).toFixed(1)}" rx="3" fill="${s.color}"><title>${esc(lab)} · ${esc(s.name)}: ${euro(s.values[i] || 0)}</title></rect>`;
      });
      const step = Math.ceil(n / 16);
      if (i % step === 0) {
        out += `<text x="${cx}" y="${H - 10}" text-anchor="middle" font-size="11" fill="var(--muted)">${esc(lab)}</text>`;
      }
    });
    // Saldo-Linie (kann negativ sein — auf 0 gekappt sichtbar, Wert im Tooltip)
    if (line) {
      const pts = line.values.map((v, i) => {
        const cx = padL + slot * i + slot / 2;
        return `${cx.toFixed(1)},${yOf(Math.max(v, 0)).toFixed(1)}`;
      });
      out += `<polyline points="${pts.join(" ")}" fill="none" stroke="${line.color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`;
      line.values.forEach((v, i) => {
        const cx = padL + slot * i + slot / 2;
        out += `<circle cx="${cx}" cy="${yOf(Math.max(v, 0))}" r="3.5" fill="${line.color}"><title>${esc(labels[i])} · ${esc(line.name)}: ${euro(v)}</title></circle>`;
      });
    }
    out += `</svg>`;
    // Legende
    out += `<div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;font-size:.78rem;color:var(--muted)">`;
    series.concat(line ? [line] : []).forEach((s) => {
      out += `<span style="display:inline-flex;align-items:center;gap:6px"><span style="width:10px;height:10px;border-radius:3px;background:${s.color}"></span>${esc(s.name)}</span>`;
    });
    out += `</div>`;
    el.innerHTML = out;
  }

  /* ---- Schmetterling: Ausgaben links, Einnahmen rechts (Signatur) -------- */
  function butterfly(el, rows) {
    if (!rows || !rows.length) { empty(el); return; }
    let maxV = 0;
    rows.forEach((r) => { maxV = Math.max(maxV, r.ein || 0, r.aus || 0); });
    if (maxV <= 0) { empty(el); return; }
    let out = `<div class="fly-head"><span>Sparte</span><span class="fh-track"><span>◀ Ausgaben</span><span>Einnahmen ▶</span></span><span style="text-align:right">Saldo</span></div>`;
    rows.forEach((r) => {
      const wa = (Math.max(r.aus || 0, 0) / maxV) * 50;
      const we = (Math.max(r.ein || 0, 0) / maxV) * 50;
      const saldo = (r.ein || 0) - (r.aus || 0);
      out += `<div class="fly-row">
        <span class="fly-label"><span class="dot" style="background:${r.color}"></span><span class="txt" title="${esc(r.label)}">${esc(r.label)}</span></span>
        <span class="fly-track">
          <span class="fly-bar aus" style="width:${wa.toFixed(2)}%" title="Ausgaben: ${euro(r.aus || 0)}"></span>
          <span class="fly-bar ein" style="width:${we.toFixed(2)}%" title="Einnahmen: ${euro(r.ein || 0)}"></span>
        </span>
        <span class="fly-saldo${saldo < 0 ? " neg" : ""}">${euro(saldo)}</span>
      </div>`;
    });
    el.innerHTML = out;
  }

  /* ---- Ranking mit Vorjahres-Delta --------------------------------------- */
  // rows: [{label, color, value, deltaPct|null, gut}] — gut=true: Anstieg ist
  // positiv zu werten (Einnahmen), sonst negativ (Ausgaben).
  function rankList(el, rows, { emptyText } = {}) {
    if (!rows || !rows.length) { empty(el, emptyText); return; }
    const maxV = Math.max(...rows.map((r) => r.value), 1);
    el.innerHTML = rows.map((r) => {
      let delta = `<span class="rank-delta none">–</span>`;
      if (r.deltaPct != null && isFinite(r.deltaPct)) {
        const up = r.deltaPct >= 0;
        const cls = up ? "up" : "down";
        const moral = r.gut ? (up ? "gut" : "schlecht") : "";
        const arrow = up ? "▲" : "▼";
        delta = `<span class="rank-delta ${cls} ${moral}" title="Veränderung gegenüber Vorjahr">${arrow} ${Math.abs(r.deltaPct).toLocaleString("de-DE", { maximumFractionDigits: 0 })} %</span>`;
      }
      const sub = r.sub ? ` <span class="kat-sp">${esc(r.sub)}</span>` : "";
      return `<div class="rank-row">
        <div class="rank-main">
          <div class="rank-label"><span class="dot" style="background:${r.color}"></span><span>${esc(r.label)}${sub}</span></div>
          <div class="rank-bar" style="width:${(r.value / maxV * 100).toFixed(1)}%;background:${r.color}"></div>
        </div>
        <span class="rank-value">${euro(r.value)}</span>
        ${delta}
      </div>`;
    }).join("");
  }

  return { sparkline, barGroup, butterfly, rankList, empty };
})();
