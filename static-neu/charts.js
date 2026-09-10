import {fmtEur} from './format.js';
export function sparkline(values=[]){const max=Math.max(...values,1), points=values.map((v,i)=>`${i/(Math.max(values.length-1,1))*100},${38-v/max*32}`).join(' ');return `<svg viewBox="0 0 100 44" role="img" aria-label="Verlauf"><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2"/></svg>`}
export function monthlyChart(data=[]){const max=Math.max(...data.map(x=>Math.max(x.einnahmen_cent||0,x.ausgaben_cent||0)),1);return `<div class="chart-bars">${data.map(x=>`<div title="${x.monat||''}"><i class="ein" style="height:${(x.einnahmen_cent||0)/max*100}%"></i><i class="aus" style="height:${(x.ausgaben_cent||0)/max*100}%"></i></div>`).join('')}</div>`}

// P31: Sparkline mit Vorjahreslinie (Erweiterung, bestehende Exporte bleiben unveraendert).
// current/previous sind gleich lange Zahlenreihen (z. B. 12 Monatswerte in Cent).
export function sparklineCompare(current=[], previous=[], color='currentColor'){
  const all=[...current,...previous].filter(v=>typeof v==='number'&&!Number.isNaN(v));
  const max=Math.max(...all,1), min=Math.min(...all,0), span=(max-min)||1;
  const n=Math.max(current.length,previous.length,1);
  const x=i=>n>1?(i/(n-1))*100:0, y=v=>38-((v-min)/span)*32;
  const line=values=>values.map((v,i)=>`${x(i)},${y(v)}`).join(' ');
  const prev=previous.length?`<polyline points="${line(previous)}" fill="none" stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="3 2"/>`:'';
  const cur=current.length?`<polyline points="${line(current)}" fill="none" stroke="${color}" stroke-width="2"/>`:'';
  return `<svg viewBox="0 0 100 44" role="img" aria-label="Verlauf gegenüber Vorjahr">${prev}${cur}</svg>`;
}
