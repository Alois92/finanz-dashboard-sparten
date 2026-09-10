export function toast(message){const node=document.querySelector('#toast');node.textContent=message;node.classList.add('show');clearTimeout(node._timer);node._timer=setTimeout(()=>node.classList.remove('show'),2400)}
export function drill(title,content){const dialog=document.querySelector('#drill');document.querySelector('#drill-title').textContent=title;document.querySelector('#drill-content').innerHTML=content;dialog.showModal();document.querySelector('#drill-close').focus()}
export function sheet(content){const node=document.querySelector('#sheet');node.innerHTML=content;node.hidden=false;return node}
export function closeSheet(){document.querySelector('#sheet').hidden=true}

// P30b: wiederverwendbarer Mehrschritt-Dialog auf dem bestehenden <dialog id="drill">-
// Mechanismus. steps ist eine Liste aus {render(ctx), validate(ctx), afterRender(container,ctx),
// lockBack}. render(ctx) liefert das HTML des Schritts. validate(ctx) läuft beim Klick auf
// "Weiter"/"Abschließen", darf async sein (z. B. API-Aufruf), wirft bei Fehlern eine Error mit
// verständlicher message (wird im Dialog angezeigt) und darf ctx.data füllen, das folgenden
// Schritten zur Verfügung steht. Setzt validate() ctx.finishNow, springt der Dialog sofort zu
// onFinish(ctx), auch wenn noch Schritte übrig sind (z. B. "keine Differenz, nichts zu buchen").
// lockBack:true auf einem Schritt blendet "Zurück" für alle folgenden Schritte aus - für
// Schritte, die bereits eine serverseitige Wirkung hatten und bei denen ein erneutes
// "Weiter" einen zweiten Datensatz anlegen würde. Escape schließt den Dialog über den
// bestehenden <dialog>-Mechanismus (nativ plus #drill-close, siehe app.js).
export function wizard({title,steps,onFinish}){
  const dialog=document.querySelector('#drill');
  const content=document.querySelector('#drill-content');
  document.querySelector('#drill-title').textContent=title;
  let index=0;
  let backAllowed=true;
  const ctx={data:{}};

  function draw(){
    const step=steps[index];
    const isLast=index===steps.length-1;
    content.innerHTML=`<div class="wizard-step">${step.render(ctx)||''}</div>
      <p class="field-error" id="wizard-error" hidden></p>
      <div class="wizard-nav">
        <button type="button" class="btn" id="wizard-back" ${index===0||!backAllowed?'hidden':''}>Zurück</button>
        <button type="button" class="btn primary" id="wizard-next">${isLast?'Abschließen':'Weiter'}</button>
      </div>`;
    if(step.afterRender)step.afterRender(content.querySelector('.wizard-step'),ctx);
    const backBtn=document.querySelector('#wizard-back');
    if(backBtn)backBtn.onclick=()=>{index-=1;draw()};
    document.querySelector('#wizard-next').onclick=async()=>{
      const nextBtn=document.querySelector('#wizard-next');
      const errBox=document.querySelector('#wizard-error');
      errBox.hidden=true;
      nextBtn.disabled=true;
      try{
        if(step.validate)await step.validate(ctx);
        if(step.lockBack)backAllowed=false;
        if(ctx.finishNow||isLast){
          if(onFinish)await onFinish(ctx);
          dialog.close();
          return;
        }
        index+=1;
        draw();
      }catch(error){
        errBox.textContent=(error&&error.message)?error.message:String(error);
        errBox.hidden=false;
      }finally{
        nextBtn.disabled=false;
      }
    };
  }
  draw();
  dialog.showModal();
  document.querySelector('#drill-close').focus();
}
