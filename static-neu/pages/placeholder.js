import {esc} from '../format.js';
export function render(root,state){root.innerHTML=`<section class="card placeholder"><div><h2>${esc(state.title)}</h2><p>${esc(state.coming||'Kommt in P3x')}</p></div></section>`}
