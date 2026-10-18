'use strict';
(() => {
 let state=null,timer=null,busy=false,automaticPromptShown=false,lastRefresh=null;
 const dialog=$('reply-consent-dialog');
 function schedule(delay,automatic=false){clearTimeout(timer);timer=setTimeout(()=>refresh(automatic).catch(()=>schedule(60000)),delay);}
 function render(s){
  state=s;const sync=$('reply-sync-now');sync.disabled=!s.authorized||s.syncing||busy;
  $('reply-sync-connect').hidden=s.authorized;$('reply-sync-disconnect').hidden=!s.authorized;
  $('reply-sync-connect').textContent=s.configured?'Enable reply tracking':'Set up Gmail first';
  $('reply-sync-panel').dataset.error=String(!!s.last_error);
  $('reply-sync-badge').textContent=s.syncing?'Syncing':s.authorized?s.last_error?'Needs attention':s.last_checked?(s.last_result?.checked_messages?'Connected':'Ready'):'Allowed':'Not connected';
  $('reply-sync-status').textContent=s.syncing?'Checking Gmail for related replies…':s.last_error||(!s.configured?'Set up your sending Gmail and Gmail app password in Account Setup.':!s.authorized?'Your permission is needed before this demo reads related replies.':s.last_checked?'Reply tracking is on. Replies are checked automatically while this page is open.':'Permission saved. Ready to sync replies.');
  const r=s.last_result;
  $('reply-sync-detail').textContent=r?'Last checked: '+new Date(s.last_checked*1000).toLocaleString()+' · '+r.new_replies+' new replies ('+r.human_replies+' human, '+r.automatic_replies+' automatic) · '+r.coverage+(r.missing_message_ids?' · '+r.missing_message_ids+' sent messages cannot be matched automatically because their message IDs are missing.':'')+(r.older_messages_not_scanned?' · Only the latest 300 sent messages were checked.':''):'Reply text stays on this computer. No AI API is used for syncing.';
 }
 async function updateResults(){await refreshMetrics();if(window.OutreachEngagement)await window.OutreachEngagement.refreshRun();renderContacts();}
 async function refresh(automatic=false){
  const s=await api('/api/mail/status');render(s);
  if(s.last_checked&&s.last_checked!==lastRefresh){lastRefresh=s.last_checked;await updateResults();}
  if(s.syncing){schedule(2000);return;}
  if(automatic&&s.authorized&&!s.last_error&&document.visibilityState==='visible'){await synchronize();return;}
  if(s.prompt_needed&&!automaticPromptShown){automaticPromptShown=true;openPermission();}
  schedule(60000,true);
 }
 function openPermission(){if(!state?.configured){location.hash='settings';notice('Set up your sending Gmail and Gmail app password first.');return;}$('reply-consent-account').textContent=state.account;$('reply-consent-error').textContent='';if(!dialog.open)dialog.showModal();}
 async function synchronize(){
  if(busy||!state?.authorized)return;busy=true;render({...state,syncing:true});
  try{render(await api('/api/mail/sync',{}));schedule(1500);}catch(error){$('reply-sync-status').textContent=error.message;$('reply-sync-panel').dataset.error='true';schedule(60000,true);}finally{busy=false;$('reply-sync-now').disabled=!state?.authorized||!!state?.syncing;}
 }
 $('reply-sync-connect').onclick=openPermission;
 $('reply-sync-now').onclick=synchronize;
 $('reply-sync-disconnect').onclick=()=>action($('reply-sync-disconnect'),async()=>{render(await api('/api/mail/consent',{allow:false}));clearTimeout(timer);notice('Gmail reply sync stopped. Previously imported replies remain saved locally.');schedule(60000,true);await refreshMetrics();});
 async function later(){render(await api('/api/mail/consent',{allow:false}));dialog.close();schedule(60000,true);}
 $('reply-consent-later').onclick=()=>action($('reply-consent-later'),later);
 dialog.addEventListener('cancel',event=>{event.preventDefault();later().catch(error=>{$('reply-consent-error').textContent=error.message;});});
 $('reply-consent-allow').onclick=()=>action($('reply-consent-allow'),async()=>{try{render(await api('/api/mail/consent',{allow:true,consent_version:1}));dialog.close();location.hash='history';await synchronize();}catch(error){$('reply-consent-error').textContent=error.message;}});
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refresh(true).catch(error=>{$('reply-sync-status').textContent=error.message;});});
 refresh(true).catch(error=>{$('reply-sync-status').textContent=error.message;schedule(60000,true);});
})();
