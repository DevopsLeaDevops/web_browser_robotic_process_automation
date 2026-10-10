'use strict';
const $=(s,root=document)=>root.querySelector(s);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M14 17.5h7m-3.5-3.5v7"/></svg>';
function shell(config){
 $('#brand').innerHTML='<span class="brand-mark">'+icon+'</span><span>'+esc(config.title)+'<small>'+esc(config.subtitle)+'</small></span>';
 const path=location.hash.slice(1)||config.first;const entry=config.groups.flatMap(g=>g.pages.map(p=>({...p,group:g}))).find(p=>p.id===path)||config.groups[0].pages[0];const group=entry.group||config.groups[0];
 $('#topnav').innerHTML=config.groups.map(g=>`<a href="#${g.pages[0].id}" class="${g.id===group.id?'active':''}" ${g.id===group.id?'aria-current="true"':''}>${esc(g.name)}</a>`).join('');
 $('#side-heading').innerHTML=`<small>${esc(group.en)}</small><strong>${esc(group.name)}</strong>`;
 $('#sidenav').innerHTML=group.pages.map(p=>`<a href="#${p.id}" class="${p.id===entry.id?'active':''}" ${p.id===entry.id?'aria-current="page"':''}><span class="nav-icon">${icon}</span><span>${esc(p.name)}</span></a>`).join('');
 $('#crumb').textContent=group.name+' › '+entry.name;$('#title').textContent=entry.name;$('#description').textContent=entry.desc||'';document.title=entry.name+' · '+config.title;$('#sidebar').classList.remove('open');$('#menu-toggle').setAttribute('aria-expanded','false');$('#page-actions').innerHTML='';return entry.id;
}
$('#menu-toggle').onclick=()=>{const open=$('#sidebar').classList.toggle('open');$('#menu-toggle').setAttribute('aria-expanded',String(open));};
let toastTimer;function toast(text){$('#toast').textContent=text;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,3000)}
function modal(title,html,action){$('#dialog-title').textContent=title;$('#dialog-content').innerHTML=html;$('#dialog-action').hidden=!action;if(action){$('#dialog-action').textContent=action.label;$('#dialog-action').onclick=action.run;}$('#dialog').showModal();}
$('#dialog-close').onclick=()=>$('#dialog').close();
function download(name,text,type='application/json'){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function storeRead(key,fallback){try{return JSON.parse(localStorage.getItem(key))??fallback}catch{return fallback}}
function storeWrite(key,data){try{localStorage.setItem(key,JSON.stringify(data));return true}catch{toast('瀏覽器儲存不可用；本次資料僅保留至關閉頁面。');return false}}

$('.skip').onclick=e=>{e.preventDefault();$('#main').setAttribute('tabindex','-1');$('#main').focus();};

$('#sidenav').onclick=e=>{if(e.target.closest('a')){$('#sidebar').classList.remove('open');$('#menu-toggle').setAttribute('aria-expanded','false');}};
