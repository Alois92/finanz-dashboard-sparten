"use strict";
/* ===========================================================================
   Finanz-Cockpit — SVG-Diagramme, komplett ohne externe Library.
   Alle Charts rendern in ein <div>-Element (viewBox-basiert, skaliert per CSS).
   Farben kommen aus CSS-Variablen des Design-Systems (fill="var(--…)").
   =========================================================================== */
const Charts = (() => {
  const NS = "http://www.w3.org/2000/svg";

  // Kompakte Betragsformatierung fuer Achsen/Labels (ohne Nachkommastellen).
  function fmtShort(cent) {
    const e = cent / 100;
    const abs = Math.abs(e);
    if (abs >= 1000) return (e / 1000).toLocaleString("de-DE", { maximumFractionDigits: 1 }) + "k";
    return e.toLocaleString("de-DE", { maximumFractionDigits: 0 });
  }
  function fmtFull(cent) {
    return (cent / 100).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  function svgOpen(vbW, vbH, extra = "") {
    return `<svg viewBox="0 0 ${vbW} ${vbH}" preserveAspectRatio="xMidYMid meet" `
      + `role="img" width="100%" ${extra}>`;
  }

  function empty(el, msg) {
    el.classList.add("chart-empty");
    el.innerHTML = `<div class="empty-state">
        <span class="empty-mark">∅</span>
        <span>${esc(msg || "Noch keine Buchungen — sobald du erfasst, erscheinen hier die Auswertungen.")}</span>
      </div>`;
  }
  function reset(el) { el.classList.remove("chart-empty"); }

  // "schoene" obere Achsengrenze
  function niceMax(v) {
    if (v <= 0) return 1;
    const pow = Math.pow(10, Math.floor(Math.log10(v)));
    const n = v / pow;
    const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
    return step * pow;
  }

  /* ---- Gruppierte Balken + optionale Saldo-Linie ------------------------- */
  // labels: string[]; series: [{name,color,values:number[]}]; line: {name,color,values}?
  function barGroup(el, { labels, series, line, empty: emptyMsg }) {
    reset(el);
    const hasData = labels.length && series.some((s) => s.values.some((v) => v > 0));
    if (!hasData) return empty(el, emptyMsg);

    const W = 820, H = 300, padL = 54, padR = 16, padT = 16, padB = 42;
    const plotW = W - padL - padR, plotH = H - padT - padB;

    let maxV = 0, minV = 0;
    series.forEach((s) => s.values.forEach((v) => { if (v > maxV) maxV = v; }));
    if (line) line.values.forEach((v) => { if (v > maxV) maxV = v; if (v < minV) minV = v; });
    const top = niceMax(maxV);
    const bot = minV < 0 ? -niceMax(-minV) : 0;
    const yOf = (v) => padT + plotH * (1 - (v - bot) / (top - bot));

    const n = labels.length;
    const groupW = plotW / n;
    // Balkenbreite deckeln, damit wenige Gruppen (z. B. nur 1 Jahr) nicht riesig werden.
    const maxBarW = 64;
    const inner = Math.min(groupW * 0.62, series.length * maxBarW);
    const barW = inner / series.length;

    let g = "";
    // Gitterlinien + y-Achsenbeschriftung (4 Schritte)
    const ticks = 4;
    for (let i = 0; i <= ticks; i++) {
      const val = bot + (top - bot) * (i / ticks);
      const y = yOf(val);
      g += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" class="grid"/>`;
      g += `<text x="${padL - 8}" y="${y + 4}" class="ax-y">${fmtShort(val)}</text>`;
    }
    // Nulllinie hervorheben, falls negative Werte
    if (bot < 0) { const y0 = yOf(0); g += `<line x1="${padL}" y1="${y0}" x2="${W - padR}" y2="${y0}" class="zero"/>`; }

    labels.forEach((lab, i) => {
      const gx = padL + groupW * i + (groupW - inner) / 2;
      series.forEach((s, si) => {
        const v = s.values[i] || 0;
        const y = yOf(v), y0 = yOf(0);
        const h = Math.max(0, y0 - y);
        const x = gx + barW * si;
        g += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(barW - 3).toFixed(1)}" height="${h.toFixed(1)}" rx="3" fill="${s.color}" class="bar">`
          + `<title>${esc(lab)} · ${esc(s.name)}: ${fmtFull(v)}</title></rect>`;
      });
      g += `<text x="${(padL + groupW * i + groupW / 2).toFixed(1)}" y="${H - padB + 20}" class="ax-x">${esc(lab)}</text>`;
    });

    // Saldo-Linie
    if (line) {
      const pts = line.values.map((v, i) => `${(padL + groupW * i + groupW / 2).toFixed(1)},${yOf(v).toFixed(1)}`);
      g += `<polyline points="${pts.join(" ")}" fill="none" stroke="${line.color}" stroke-width="2.5" class="saldo-line"/>`;
      line.values.forEach((v, i) => {
        g += `<circle cx="${(padL + groupW * i + groupW / 2).toFixed(1)}" cy="${yOf(v).toFixed(1)}" r="3.5" fill="${line.color}" class="saldo-dot">`
          + `<title>${esc(labels[i])} · ${esc(line.name)}: ${fmtFull(v)}</title></circle>`;
      });
    }

    // Legende
    const legItems = series.concat(line ? [line] : []);
    const legend = legItems.map((s) =>
      `<span class="lg-item"><span class="lg-swatch" style="background:${s.color}"></span>${esc(s.name)}</span>`).join("");

    el.innerHTML = svgOpen(W, H) + g + `</svg>` + `<div class="chart-legend">${legend}</div>`;
  }

  /* ---- Donut / Ring ------------------------------------------------------ */
  // segments: [{label,value,color}]
  function donut(el, segments, { centerLabel } = {}) {
    reset(el);
    const data = (segments || []).filter((s) => s.value > 0);
    const total = data.reduce((a, s) => a + s.value, 0);
    if (!total) return empty(el, "Keine Werte im gewählten Zeitraum.");

    const S = 240, cx = S / 2, cy = S / 2, r = 92, sw = 30;
    const C = 2 * Math.PI * r;
    let off = 0, ring = "";
    data.forEach((s) => {
      const frac = s.value / total;
      const len = frac * C;
      ring += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${s.color}" stroke-width="${sw}" `
        + `stroke-dasharray="${len.toFixed(2)} ${(C - len).toFixed(2)}" stroke-dashoffset="${(-off).toFixed(2)}" `
        + `transform="rotate(-90 ${cx} ${cy})" class="seg"><title>${esc(s.label)}: ${fmtFull(s.value)} (${(frac * 100).toFixed(0)}%)</title></circle>`;
      off += len;
    });
    const center = `<text x="${cx}" y="${cy - 4}" class="donut-total">${fmtShort(total)}</text>`
      + `<text x="${cx}" y="${cy + 16}" class="donut-cap">${esc(centerLabel || "gesamt")}</text>`;

    const legend = data.map((s) =>
      `<div class="lg-row"><span class="lg-swatch" style="background:${s.color}"></span>`
      + `<span class="lg-name">${esc(s.label)}</span>`
      + `<span class="lg-val">${fmtFull(s.value)}</span>`
      + `<span class="lg-pct">${(s.value / total * 100).toFixed(0)}%</span></div>`).join("");

    el.innerHTML = `<div class="donut-wrap">`
      + svgOpen(S, S, 'class="donut-svg"') + ring + center + `</svg>`
      + `<div class="donut-legend">${legend}</div></div>`;
  }

  /* ---- Horizontale Balken ------------------------------------------------ */
  // rows: [{label,value,color?}]
  function hbars(el, rows, { emptyMsg } = {}) {
    reset(el);
    const data = (rows || []).filter((r) => r.value > 0);
    if (!data.length) return empty(el, emptyMsg || "Keine Ausgaben im gewählten Zeitraum.");

    const max = Math.max(...data.map((r) => r.value));
    const html = data.map((r) => {
      const pct = (r.value / max) * 100;
      return `<div class="hbar-row">
          <span class="hbar-label" title="${esc(r.label)}">${esc(r.label)}</span>
          <span class="hbar-track"><span class="hbar-fill" style="width:${pct.toFixed(1)}%;background:${r.color || "var(--accent)"}"></span></span>
          <span class="hbar-val">${fmtFull(r.value)}</span>
        </div>`;
    }).join("");
    el.innerHTML = `<div class="hbars">${html}</div>`;
  }

  /* ---- Sparkline (Mini-Fläche) ------------------------------------------- */
  // Eigener <svg> mit preserveAspectRatio="none" + fester Hoehe: fuellt den
  // vollbreiten KPI-Streifen, ohne sich hochzuskalieren.
  function sparkOpen() {
    return `<svg viewBox="0 0 120 34" preserveAspectRatio="none" width="100%" height="34" role="img" aria-hidden="true">`;
  }
  function sparkline(el, values, { color } = {}) {
    reset(el);
    const vals = values && values.length ? values : [0];
    const c = color || "var(--accent)";
    if (vals.length < 2 || vals.every((v) => v === vals[0])) {
      // flache Linie mittig, wenn zu wenig Varianz
      el.innerHTML = sparkOpen() + `<line x1="0" y1="17" x2="120" y2="17" stroke="${c}" stroke-width="1.5" vector-effect="non-scaling-stroke" opacity=".5"/></svg>`;
      return;
    }
    const W = 120, H = 34, pad = 3;
    const max = Math.max(...vals), min = Math.min(...vals);
    const span = max - min || 1;
    const xOf = (i) => pad + (W - 2 * pad) * (i / (vals.length - 1));
    const yOf = (v) => pad + (H - 2 * pad) * (1 - (v - min) / span);
    const line = vals.map((v, i) => `${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`);
    const area = `${pad},${H - pad} ` + line.join(" ") + ` ${W - pad},${H - pad}`;
    el.innerHTML = sparkOpen()
      + `<polygon points="${area}" fill="${c}" opacity=".14"/>`
      + `<polyline points="${line.join(" ")}" fill="none" stroke="${c}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>`
      + `</svg>`;
  }

  return { barGroup, donut, hbars, sparkline, empty, fmtFull, fmtShort };
})();
