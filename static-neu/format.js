const eur = new Intl.NumberFormat('de-AT',{style:'currency',currency:'EUR'});
export const fmtEur = cent => eur.format((cent||0)/100);
export const fmtDate = iso => iso ? new Intl.DateTimeFormat('de-AT').format(new Date(`${iso}T00:00:00`)) : '–';
export const fmtPct = value => `${Math.round((value||0)*100)} %`;
export const esc = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function parseBetrag(value){
  // QA2-02: Punkt und Komma muessen als Dezimal- bzw. Tausendertrennzeichen unterschieden werden,
  // statt Punkte immer als Tausendertrennzeichen zu behandeln (das verfaelschte z.B. "12.50" zu 1250).
  const s=String(value??'').trim().replace(/\s/g,'');
  if(!s) return null;
  const hatKomma=s.includes(',');
  const hatPunkt=s.includes('.');
  let normalisiert;
  if(hatKomma&&hatPunkt){
    // beide vorhanden: das zuletzt stehende Zeichen ist das Dezimaltrennzeichen
    const letztesKomma=s.lastIndexOf(',');
    const letzterPunkt=s.lastIndexOf('.');
    normalisiert=letztesKomma>letzterPunkt
      ? s.replace(/\./g,'').replace(',','.')
      : s.replace(/,/g,'');
  }else if(hatPunkt){
    const punkte=(s.match(/\./g)||[]).length;
    const nachKommastellen=s.slice(s.lastIndexOf('.')+1).length;
    if(punkte===1&&(nachKommastellen===1||nachKommastellen===2)){
      // ein Punkt mit 1-2 Nachkommastellen -> Dezimalpunkt ("12.5", "12.50")
      normalisiert=s;
    }else if(punkte===1&&nachKommastellen===3){
      // ein Punkt mit genau 3 Ziffern danach -> Tausenderpunkt ("1.250")
      normalisiert=s.replace(/\./g,'');
    }else if(punkte>1){
      // mehrere Punkte -> deutsche Tausenderschreibweise ("1.234.567")
      normalisiert=s.replace(/\./g,'');
    }else{
      // z.B. "12." oder "1.2345" -> nicht eindeutig zuordenbar
      return null;
    }
  }else if(hatKomma){
    // nur Komma -> wie bisher Dezimalkomma
    normalisiert=s.replace(',','.');
  }else{
    normalisiert=s;
  }
  const n=Number(normalisiert);
  return Number.isFinite(n)?n:null;
}
