export function toast(message){const node=document.querySelector('#toast');node.textContent=message;node.classList.add('show');clearTimeout(node._timer);node._timer=setTimeout(()=>node.classList.remove('show'),2400)}
export function drill(title,content){const dialog=document.querySelector('#drill');document.querySelector('#drill-title').textContent=title;document.querySelector('#drill-content').innerHTML=content;dialog.showModal();document.querySelector('#drill-close').focus()}
export function sheet(content){const node=document.querySelector('#sheet');node.innerHTML=content;node.hidden=false;return node}
export function closeSheet(){document.querySelector('#sheet').hidden=true}
