(function () {
  'use strict';
  if(window.MZAdmin)return;
  var admin=false, enabled=false, attempt=0, session='', api='https://api.misterzine.fyi', dialog=null;
  var states=new Map();
  try {if(['localhost','127.0.0.1'].includes(location.hostname))api=localStorage.getItem('mz-api')||api;}catch(e){}
  function token(){try{return localStorage.getItem('mz-token')||'';}catch(e){return '';}}
  function preference(){try{return localStorage.getItem('mz-admin-mode')==='1';}catch(e){return false;}}
  function node(tag,text){var n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
  function active(){return admin&&enabled&&session===token();}
  window.MZAdmin={active:active};
  function notify(){window.dispatchEvent(new Event('mz-admin-mode'));}
  function close(){if(dialog){dialog.close();dialog.remove();dialog=null;}}
  async function request(path,options){
    if(!active())throw new Error('Admin mode is off.');
    var r=await fetch(api+path,{...options,cache:'no-store',headers:{Authorization:'Bearer '+session,'Content-Type':'application/json'}});
    if(!r.ok)throw new Error(r.status===409?'This list changed. Close and reopen moderation to review it.':r.status===404?'This list is no longer available.':'Could not complete the request. Check your sign-in and try again.');
    return r.status===204?null:r.json();
  }
  async function moderate(id,trigger){
    close();var d=node('dialog');dialog=d;d.className='mz-moderation';
    var title=node('h2','Moderate list'), message=node('p','Loading...'), label=node('label','Reason (visible to the author)'), reason=node('textarea'), actions=node('div'), save=node('button'), cancel=node('button','Close');
    message.setAttribute('role','status');reason.maxLength=500;reason.rows=3;label.append(reason);save.type=cancel.type='button';save.hidden=label.hidden=true;actions.append(save,cancel);d.append(title,message,label,actions);document.body.append(d);
    cancel.onclick=()=>{close();if(trigger.isConnected)trigger.focus();};d.addEventListener('cancel',()=>{close();});d.showModal();cancel.focus();var current=attempt;
    try{var row=await request('/admin/lists/'+id);if(dialog!==d||current!==attempt||!active())return;
      title.textContent=row.title;message.textContent=row.moderation_hidden?'Hidden by admin: '+row.moderation_reason:'Hide this list from browsing and shared links. Its author can still edit it.';
      reason.value=row.moderation_reason||'';save.textContent=row.moderation_hidden?'Restore list':'Hide list';save.hidden=label.hidden=false;
      save.onclick=async()=>{
        reason.setCustomValidity(!row.moderation_hidden&&!reason.value.trim()?'Enter a reason.':'');if(!reason.reportValidity())return;save.disabled=true;
        try{await request('/admin/lists/'+id,{method:'PUT',body:JSON.stringify({hidden:!row.moderation_hidden,reason:reason.value.trim(),version:row.version})});
          if(dialog!==d||current!==attempt||!active())return;row.moderation_hidden=!row.moderation_hidden;row.moderation_reason=reason.value.trim();states.set(id,row.moderation_hidden);paint();save.textContent=row.moderation_hidden?'Restore list':'Hide list';message.textContent=row.moderation_hidden?'Hidden. You can restore it here.':"Restored. The author's visibility setting applies.";
        }catch(e){if(dialog===d)message.textContent=e.message;}finally{save.disabled=false;}
      };reason.oninput=()=>reason.setCustomValidity('');
    }catch(e){if(dialog===d)message.textContent=e.message;}
  }
  function paint(){
    var menu=document.querySelector('#menudd > .mlist')||document.querySelector('#menudd .mlist'), toggle=document.getElementById('mz-admin-toggle');
    if(admin&&menu&&!toggle){toggle=node('button');toggle.id='mz-admin-toggle';toggle.type='button';menu.append(toggle);toggle.onclick=()=>{enabled=!enabled;try{localStorage.setItem('mz-admin-mode',enabled?'1':'0');}catch(e){}close();paint();notify();};}
    if(toggle&&!admin){toggle.remove();toggle=null;}
    if(toggle){var text=enabled?'Admin: on':'Admin: off';if(toggle.textContent!==text)toggle.textContent=text;toggle.setAttribute('aria-pressed',String(enabled));}
    if(!active()){document.querySelectorAll('[data-moderate]').forEach(n=>n.remove());return;}
    function add(host,id){if(!host||!id)return;var b=host.querySelector('[data-moderate]');if(b&&b.dataset.moderate!==id){b.remove();b=null;}if(!b){b=node('button');b.type='button';b.className='btn';b.dataset.moderate=id;b.onclick=()=>moderate(id,b);host.append(b);}var text=states.get(id)?'Hidden - moderate':'Moderate list';if(b.textContent!==text)b.textContent=text;}
    document.querySelectorAll('.list-card .actions').forEach(host=>{var a=host.querySelector('a[href*="?list="]');add(host,host.closest('.list-card').dataset.listId || (a && new URL(a.href).searchParams.get('list')));});
    var id=new URLSearchParams(location.search).get('list');var host=document.querySelector('.clviewactions');if(id)add(host,id);else if(host)host.querySelectorAll('[data-moderate]').forEach(n=>n.remove());
  }
  async function check(){
    var current=++attempt;session=token();admin=false;close();paint();notify();if(!session)return;
    try{var r=await fetch(api+'/me',{cache:'no-store',headers:{Authorization:'Bearer '+session}});var data=r.ok?await r.json():{};if(current!==attempt||session!==token())return;admin=data.list_admin===true;enabled=preference();paint();notify();}catch(e){}
  }
  new MutationObserver(paint).observe(document.body,{childList:true,subtree:true});
  window.addEventListener('storage',e=>{if(e.key==='mz-admin-mode'){enabled=preference();close();paint();notify();}else if(e.key==='mz-token'||e.key===null){states.clear();check();}});
  window.addEventListener('focus',()=>{if(session!==token())check();});check();
})();
