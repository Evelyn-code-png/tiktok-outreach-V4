'use strict';
(() => {
 const panel=document.createElement('section');
 panel.className='space-top';
 panel.innerHTML='<h3>Open and click tracking</h3><p>Only new emails sent directly by this app can be tracked. Earlier emails and Gmail browser sends are excluded. Open events are estimates, not proof of reading.</p><form id="cloud-tracking-form"><div class="columns"><label>Dedicated service address<input id="cloud-tracking-origin" type="url" required placeholder="https://your-tracking-service.pages.dev"></label><label>Tracking access token<input id="cloud-tracking-token" type="password" autocomplete="new-password" placeholder="Leave blank to keep the saved token"></label></div><div class="actions"><button type="submit">Test connection and enable</button><button type="button" class="secondary" id="cloud-tracking-stop">Pause new tracking</button></div></form><p id="cloud-tracking-status" role="status"></p>';
 $('settings').querySelector('.status-grid').after(panel);
 // Preserve the old input for configuration-form compatibility, but use verified setup above.
 $('tracking_base_url').closest('label').hidden=true;
 const sync=document.createElement('button');sync.type='button';sync.className='secondary';sync.textContent='Sync opens and clicks';
 $('tracking-note').before(sync);
 let enabled=false,busy=false,timer;
 function render(s){enabled=s.enabled;$('cloud-tracking-origin').value=s.origin||'';$('cloud-tracking-status').textContent=s.error||(s.enabled?'Connected. New app-sent emails will include tracking.':'Not enabled. Existing email and account settings are unchanged.');sync.disabled=!s.enabled;}
 async function synchronize(){if(!enabled||busy)return;busy=true;sync.disabled=true;try{render(await api('/api/tracking/sync',{}));await refreshMetrics();}catch(e){$('cloud-tracking-status').textContent=e.message;notice(e.message,true);}finally{busy=false;sync.disabled=!enabled;}}
 $('cloud-tracking-form').onsubmit=e=>{e.preventDefault();action(e.submitter,async()=>{render(await api('/api/tracking/config',{origin:$('cloud-tracking-origin').value,token:$('cloud-tracking-token').value,enabled:true}));$('cloud-tracking-token').value='';await refreshMetrics();});};
 $('cloud-tracking-stop').onclick=e=>action(e.target,async()=>{render(await api('/api/tracking/config',{enabled:false}));await refreshMetrics();});
 sync.onclick=()=>action(sync,synchronize);
 function schedule(){clearTimeout(timer);timer=setTimeout(async()=>{if(enabled&&document.visibilityState==='visible')await synchronize();schedule();},120000);}
 api('/api/tracking/status').then(s=>{render(s);schedule();}).catch(e=>{$('cloud-tracking-status').textContent=e.message;});
})();
