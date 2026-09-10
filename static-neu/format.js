const eur = new Intl.NumberFormat('de-AT',{style:'currency',currency:'EUR'});
export const fmtEur = cent => eur.format((cent||0)/100);
export const fmtDate = iso => iso ? new Intl.DateTimeFormat('de-AT').format(new Date(`${iso}T00:00:00`)) : '–';
export const fmtPct = value => `${Math.round((value||0)*100)} %`;
export const esc = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function parseBetrag(value){const s=String(value??'').trim().replace(/\s/g,'').replace(/\./g,'').replace(',','.');const n=Number(s);return Number.isFinite(n)?n:null}
