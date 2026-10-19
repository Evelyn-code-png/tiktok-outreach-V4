'use strict';
const fragment=new URLSearchParams(location.hash.slice(1));
if(fragment.get('token')){sessionStorage.setItem('outreachToken',fragment.get('token'));history.replaceState(null,'',location.pathname);}
const token=sessionStorage.getItem('outreachToken')||'';
const $=id=>document.getElementById(id);
let activeRun=null, campaign=null, selected=new Set(),contactPage=0,loadGeneration=0;
let contactView=localStorage.getItem('outreachContactView')==='table'?'table':'cards';
const PAGE_SIZE=100;
function notice(message,error=false){$('notice').textContent=message;$('notice').className=error?'error':'';}
async function api(path,data){const r=await fetch(path,{method:data===undefined?'GET':'POST',headers:{'X-Outreach-Token':token,'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});const result=await r.json();if(!r.ok){const e=new Error(result.error||'Request failed');e.httpStatus=r.status;throw e;}return result;}
let smtpConfigured=false,smtpFeedbackCampaign=null;
async function refreshStatus(){const d=await api('/api/status');smtpConfigured=d.gmail_configured;$('sender').value=d.sender||'';$('easykol_email').value=d.easykol_email||d.sender||'';$('easy-status').textContent=d.easykol_configured?'Configured · ready to search':'Not configured';$('gmail-status').textContent=d.google?.connected?'Google connected':d.gmail_configured?'SMTP configured':'Not connected';$('ai_gateway_url').value=d.ai_gateway_url||'';$('google-connect').disabled=!d.google?.available;if(d.google?.connected)$('google-read').checked=!!d.google.read_connected;$('google-disconnect').hidden=!d.google?.has_connection;$('google-status').textContent=d.google?.connected?'Connected: '+d.google.account+(d.google.read_connected?' · Reply access granted':' · Sending only'):d.google?.available?'Ready to connect. Choose whether to include reply access.':'Your team administrator has not enabled Google connection yet.';$('ai-status').textContent=d.ai_configured?'Configured · availability depends on provider quota':'Not configured';$('tracking-note').textContent=d.tracking_configured?'Open tracking URL saved. Gmail reply tracking is controlled separately below.':'Open tracking is not configured. Enable Gmail reply tracking above to sync replies.';}
function localFeedback(origin,message,error=true){
 let container=origin?.closest('form')||origin?.closest('.actions')||origin?.parentElement;
 if(!container||container.closest('section[hidden]'))container=document.querySelector('main>section:not([hidden])');
 if(!container){notice(message,error);return;}
 let status=[...container.children].find(e=>e.classList.contains('operation-feedback'));
 if(!status){status=element('p',undefined,'inline-feedback operation-feedback');status.tabIndex=-1;container.append(status);}
 status.setAttribute('role',error?'alert':'status');status.dataset.tone=error?'error':'info';status.textContent=message;status.hidden=false;
 status.scrollIntoView({block:'nearest',behavior:'smooth'});
}
async function action(button,fn){button.disabled=true;const container=button.closest('form')||button.closest('.actions')||button.parentElement;container?.querySelectorAll('.operation-feedback').forEach(e=>e.hidden=true);try{await fn();}catch(e){localFeedback(button,e.message);}finally{button.disabled=false;}}
// Native validation bubbles can be outside the viewport or use the browser language.
// Keep English validation beside each form instead.
document.addEventListener('invalid',e=>{
 e.preventDefault();const field=e.target;field.setAttribute('aria-invalid','true');
 const label=field.closest('label')?.childNodes[0]?.textContent.trim()||'This field';
 const message=field.validity.valueMissing?label+' is required.':field.type==='email'?'Enter a valid email address.':label+' has an invalid value. Check its format and allowed range.';
 localFeedback(field,message);
},true);
document.addEventListener('input',e=>{if(e.target.matches('input,textarea,select')){e.target.removeAttribute('aria-invalid');const hint=$(e.target.id+'-error');if(hint){hint.remove();e.target.removeAttribute('aria-describedby');}}},true);
function element(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
function table(headers,rows){const t=element('table'),thead=element('thead'),tr=element('tr');for(const h of headers)tr.append(element('th',h));thead.append(tr);t.append(thead);const b=element('tbody');for(const values of rows){const row=element('tr');for(const value of values){const cell=element('td');if(value instanceof Node)cell.append(value);else cell.textContent=value??'—';row.append(cell);}b.append(row);}t.append(b);return t;}
function formatFollowers(value){if(value==null||String(value).trim()==='')return '—';const n=Number(value);if(!Number.isFinite(n)||n<0)return '—';try{return new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1}).format(n);}catch{return String(n);}}
function englishLabel(value){return String(value||'').replaceAll('易拓客邮箱查询','EasyKOL email lookup').replaceAll('邮箱补全','Email enrichment').replaceAll('CSV 导入','CSV import').replaceAll('Excel 导入','Excel import').replaceAll('组搜索','searches').replaceAll('缺少 EasyKOL API Key 或绑定邮箱；请先运行 setup','The EasyKOL API key or account email is missing; run setup first');}
function creatorNameNode(r){const node=element('button',r.name||r.username||'Unnamed creator','crm-creator-name');node.type='button';node.setAttribute('aria-label','Open creator details for '+node.textContent);node.onclick=()=>window.OutreachEngagement?.open(r,node);return node;}
function contactCheckbox(r){const c=element('input');c.type='checkbox';c.disabled=!r.email;c.checked=!!r.email&&selected.has(r.email);c.setAttribute('aria-label',`Select ${r.name||r.username||r.email||'creator'}`);c.dataset.email=r.email||'';c.onchange=()=>{c.checked?selected.add(r.email):selected.delete(r.email);selectionCount();renderContacts();};return c;}
function creatorCard(r){
 const card=element('article',undefined,'creator-card'+(r.email&&selected.has(r.email)?' selected':''));
 const top=element('div',undefined,'creator-card-top'),avatar=element('div',Array.from(String(r.name||r.username||'?').trim())[0]||'?','creator-avatar'),identity=element('div',undefined,'creator-identity');
 identity.append(creatorNameNode(r),element('span',r.username?`@${String(r.username).replace(/^@/,'')}`:r.source==='Manual'?'Email contact':'TikTok creator','creator-username'));
 const choose=element('label',undefined,'card-select'),box=contactCheckbox(r),chooseText=element('span',r.email?'Select':'No email');choose.append(box,chooseText);top.append(avatar,identity,choose);
 const stats=element('div',undefined,'creator-stats'),followers=element('div'),region=element('div');followers.append(element('strong',formatFollowers(r.followers)),element('span','Followers'));region.append(element('strong',r.region||'—'),element('span','Country / region'));stats.append(followers,region);
 const tags=element('div',undefined,'creator-tags');tags.append(element('span',englishLabel(r.source)||'EasyKOL','creator-tag'),element('span',r.source==='Manual'&&!r.profile_url?'Email contact':'TikTok','creator-tag'));
 const email=element('p',r.email||'No contact email available','creator-card-email'),footer=element('div',undefined,'creator-card-footer');
 try{const u=new URL(r.profile_url);if(u.protocol==='https:'&&['www.tiktok.com','tiktok.com'].includes(u.hostname)){const link=element('a','View TikTok profile','card-profile-link');link.href=u.href;link.target='_blank';link.rel='noopener noreferrer';footer.append(link);}}catch{}
 const details=element('button','View details','secondary');details.type='button';details.onclick=()=>window.OutreachEngagement?.open(r,details);footer.append(details);
 const fit=window.OutreachEngagement?.badge(r);if(fit)card.append(fit);
 card.append(top,stats,tags,email,footer);
 card.tabIndex=0;card.setAttribute('aria-label','Creator card: '+(r.name||r.username||'Unnamed creator'));
 card.addEventListener('click',e=>{if(!e.target.closest('button,a,input,label,select,textarea'))window.OutreachEngagement?.open(r,card);});
 card.addEventListener('keydown',e=>{if(e.target===card&&['Enter',' '].includes(e.key)){e.preventDefault();window.OutreachEngagement?.open(r,card);}});
 return card;
}
function syncContactViewButtons(){for(const [id,view] of [['view-cards','cards'],['view-table','table']]){const b=$(id),active=contactView===view;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));}}
function selectionCount(){invalidatePreview('Recipient selection changed. Generate a new draft.');$('selection-count').textContent=`Selected ${selected.size} unique emails`;$('confirm-send').checked=false;updateRecipientHandoff();saveWorkspace();}

function updateRecipientHandoff(){
 $('outreach-selected').textContent=selected.size?`Outreach (${selected.size})`:'Outreach';
 $('outreach-recipients').textContent=selected.size?`${selected.size} recipient${selected.size===1?'':'s'} selected${activeRun?.title?' from '+englishLabel(activeRun.title):''}. Generate a draft to review each email before sending.`:'Select recipients in Contacts to prepare your outreach.';
 if(selected.size)$('outreach-selection-error').hidden=true;
}
$('outreach-selected').onclick=()=>{
 if(!selected.size){const status=$('outreach-selection-error');status.textContent='Select at least one contact with an email address before starting outreach.';status.hidden=false;status.scrollIntoView({block:'nearest',behavior:'smooth'});return;}
 updateRecipientHandoff();window.OutreachPages.go('compose');
};
function searchProgress(job){
 const running=['queued','running'].includes(job.status),panel=$('contacts-search-panel');panel.hidden=false;panel.dataset.tone=running?'progress':job.status==='completed'?'success':'error';
 $('contacts-search-title').textContent=running?'Searching for creators…':job.status==='completed'?'Search complete':job.status==='cancelled'?'Search stopped':'Search needs attention';
 $('contacts-search-detail').textContent=running?'Your search is running. Results will appear in this contact list when ready. '+(job.progress?`${job.progress.completed}/${job.progress.total} ${englishLabel(job.progress.unit)}`:'You can navigate between pages while it runs.'):job.error?englishLabel(job.error):job.status==='completed'?`${job.result?.rows??activeRun?.contacts?.length??0} contacts saved. Review profiles, select recipients, then click Outreach.`:'Any completed results have been preserved. Review the search criteria before starting again.';
 $('contacts-cancel-job').hidden=!running;
}

async function refreshRuns(){const d=await api('/api/runs'),keep=$('run-select').value,select=$('run-select'),target=$('manual-contact-list'),targetKeep=target.value;select.replaceChildren(new Option('Select a list',''));target.replaceChildren(new Option('My contacts (manual)',''));for(const r of d.runs){select.add(new Option(`${englishLabel(r.title)} · ${r.rows} rows / ${r.emails} emails`,r.id));if(r.id!=='manual-contacts')target.add(new Option(englishLabel(r.title),r.id));}if([...select.options].some(o=>o.value===keep))select.value=keep;if([...target.options].some(o=>o.value===targetKeep))target.value=targetKeep;}

function filteredContacts(){const q=$('contact-filter').value.trim().toLowerCase();const rows=(activeRun?.contacts||[]).filter(r=>(!$('only-email').checked||r.email)&&(!q||[r.name,r.username,r.email,r.region,r.source].some(v=>String(v||'').toLowerCase().includes(q))));return window.OutreachEngagement?.sort(rows)||rows;}
function renderContacts(){
 const root=$('contacts-result');root.replaceChildren();syncContactViewButtons();root.className=contactView==='cards'?'creator-grid cards-view':'table-wrap table-view';const matches=filteredContacts();
 const pages=Math.max(1,Math.ceil(matches.length/PAGE_SIZE));contactPage=Math.min(contactPage,pages-1);
 const rows=matches.slice(contactPage*PAGE_SIZE,(contactPage+1)*PAGE_SIZE);
 $('contact-pages').hidden=!matches.length;$('previous-page').disabled=contactPage===0;$('next-page').disabled=contactPage===pages-1;
 $('page-info').textContent=`Page ${contactPage+1} / ${pages} of ${matches.length} matching contacts`;
 if(!rows.length){root.append(element('p',activeRun?'No matching contacts':'Open a contact list first','empty'));return;}
 if(contactView==='cards'){root.append(...rows.map(creatorCard));return;}
 root.append(table(['Select','Creator','Followers','Country','Email','Source','Match / priority'],rows.map(r=>[contactCheckbox(r),creatorNameNode(r),r.followers||'—',r.region||'—',r.email||'Not found',englishLabel(r.source),window.OutreachEngagement?.badge(r)||'—'])));
 for(const [index,row] of [...root.querySelectorAll('tbody tr')].entries()){row.addEventListener('click',e=>{if(!e.target.closest('button,a,input,label'))window.OutreachEngagement?.open(rows[index],row.querySelector('button'));});}
}
async function loadRun(id){if(activeRun?.id!==id)window.OutreachEngagement?.close();const generation=++loadGeneration;const result=await api('/api/run/'+encodeURIComponent(id));if(generation!==loadGeneration)return;activeRun=result;selected.clear();contactPage=0;if(window.OutreachEngagement)await window.OutreachEngagement.refreshRun();if(generation!==loadGeneration)return;renderContacts();selectionCount();}
async function refreshTemplates(){const d=await api('/api/templates'),select=$('template-select');select.replaceChildren(new Option('Select a template',''));for(const t of d.templates)select.add(new Option(t.name,t.id));}
async function refreshCampaigns(){const d=await api('/api/campaigns'),select=$('campaign-select');select.replaceChildren(new Option('Select a campaign',''));for(const c of d.campaigns)select.add(new Option(`${c.subject} · ${c.recipients} recipients`,c.id));}
function renderCampaign(c,path){
 campaign={...c,path};const root=$('campaign-preview');root.replaceChildren();
 root.append(element('h3',`${c.messages.length} editable email previews`));
 for(const[i,m]of c.messages.entries()){
  const d=element('details',undefined,'email-editor');if(i===0)d.open=true;
  d.append(element('summary',`${m.to} · ${m.subject}`));
  const subjectLabel=element('label','Subject'),subjectInput=element('input');
  subjectInput.value=m.subject;subjectInput.maxLength=500;subjectInput.required=true;subjectLabel.append(subjectInput);
  const bodyLabel=element('label','Message'),bodyInput=element('textarea');
  bodyInput.value=m.body;bodyInput.rows=12;bodyInput.required=true;bodyLabel.append(bodyInput);
  const actions=element('div',undefined,'actions'),save=element('button','Save only this email','secondary'),status=element('span','','hint');
  save.type='button';
  save.onclick=()=>action(save,async()=>{
   const result=await api('/api/campaign-message',{campaign_id:campaign.id,email:m.to,subject:subjectInput.value,body:bodyInput.value});
   campaign={...result.campaign,path:result.campaign_file};
   sessionStorage.setItem('previewCampaign',campaign.id);$('confirm-send').checked=false;
   status.textContent='Saved as a new draft. Nothing was sent.';await refreshCampaigns();
  });
  subjectInput.addEventListener('input',()=>{$('confirm-send').checked=false;status.textContent='Unsaved change';});
  bodyInput.addEventListener('input',()=>{$('confirm-send').checked=false;status.textContent='Unsaved change';});
  const personal=element('details',undefined,'personalization-tools'),personalTitle=element('summary','Create 3 personalized opening options');
  const videoHelp=element('p','V2 first reads this creator\'s EasyKOL KOL profile. Video links are optional: paste up to 5 known TikTok video URLs, one per line, if you want extra detail. EasyKOL does not provide an API that automatically lists the creator\'s latest five videos.','hint');
  const videos=element('textarea');videos.rows=5;videos.placeholder='https://www.tiktok.com/@creator/video/123\nor: https://www.tiktok.com/@creator/video/456 | Real caption or transcript';
  const creditApproval=element('label',undefined,'check'),creditBox=element('input'),creditText=element('span','I approve the EasyKOL profile lookup and any optional video lookups. EasyKOL says every 50 calls use 1 task point.');
  creditBox.type='checkbox';creditApproval.append(creditBox,creditText);
  const generate=element('button','Generate 3 opening options','secondary'),ideas=element('div',undefined,'personalization-options');generate.type='button';
  generate.onclick=()=>action(generate,async()=>{
   const runId=campaign.source_run_id||activeRun?.id;if(!runId)throw new Error('Open the original contact list before personalizing this saved campaign');
   if(!creditBox.checked)throw new Error('Check the EasyKOL task-point approval box first');
   const result=await api('/api/personalize',{run_id:runId,email:m.to,recent_videos:videos.value,
    brand_name:$('brand-name').value,product:$('brand-product').value,campaign_goal:$('campaign-goal').value,
    offer:$('brand-offer').value,language:$('personalization-language').value});
   ideas.replaceChildren();
   for(const option of result.options){
    const card=element('article',undefined,'personalization-option'),paragraph=element('p',option.paragraph),reason=element('p',option.reason,'hint');
    const link=element('a','Evidence source');link.href=option.evidence_url;link.target='_blank';link.rel='noopener noreferrer';
    const use=element('button','Use this opening','secondary');use.type='button';
    use.onclick=()=>{const current=bodyInput.value,split=current.indexOf('\n\n');bodyInput.value=split>=0?current.slice(0,split+2)+option.paragraph+'\n\n'+current.slice(split+2):option.paragraph+'\n\n'+current;status.textContent='Personalized opening added — save this email';$('confirm-send').checked=false;};
    card.append(paragraph,reason,link,use);ideas.append(card);
   }
  });
  personal.append(personalTitle,videoHelp,videos,creditApproval,generate,ideas);
  actions.append(save,status);d.append(subjectLabel,bodyLabel,personal,actions);root.append(d);
 }
 $('send-controls').hidden=false;$('confirm-send').checked=false;sessionStorage.setItem('previewCampaign',c.id);
 restoreSmtpFeedback(c.id);
 $('campaign-info').textContent=`From: ${c.sender} · Campaign: ${c.id.slice(0,12)} · Save every edited email before sending. Sent or suppressed addresses will be skipped.`;
}
function showSmtpFeedback(view,focus=false){
 const root=$('smtp-feedback');root.hidden=false;root.dataset.tone=view.tone||'info';root.replaceChildren(element('h4',view.title),element('p',view.message));
 if(view.rows?.length){const wrap=element('div',undefined,'table-wrap');wrap.append(table(['Recipient','Sending result'],view.rows.map(r=>[r.email,r.label])));root.append(wrap);}
 const links=element('div',undefined,'actions');for(const [label,href]of [['View delivery log','#history'],['Open Gmail settings','#settings']]){const link=element('a',label,'crm-text-link');link.href=href;links.append(link);}root.append(links);
 $('send-smtp').disabled=!!view.busy;$('send-smtp').setAttribute('aria-busy',String(!!view.busy));$('send-smtp').textContent=view.busy?'Sending…':'Send this batch via SMTP';
 if(focus){$('smtp-panel').open=true;root.scrollIntoView({block:'nearest',behavior:'smooth'});}
}
function smtpJobMap(){try{return JSON.parse(sessionStorage.getItem('smtpJobs')||'{}');}catch{return {};}}
function showSmtpJob(job,campaignId){if(campaign?.id!==campaignId)return;showSmtpFeedback(window.OutreachSendFeedback.describe(job));}
async function restoreSmtpFeedback(campaignId){
 smtpFeedbackCampaign=campaignId;$('smtp-feedback').hidden=true;const id=smtpJobMap()[campaignId];
 try{
  const job=id?await api('/api/job/'+encodeURIComponent(id)):(await api('/api/send-status?campaign_id='+encodeURIComponent(campaignId))).job;
  if(smtpFeedbackCampaign!==campaignId||campaign?.id!==campaignId)return;
  if(!job){if(!smtpConfigured)showSmtpFeedback({tone:'warning',title:'SMTP setup required — no email sent',message:'Add a Gmail app password in Account Setup to send directly from this app. You can also use Copy Gmail send instruction with Codex.'});return;}
  const saved=smtpJobMap();saved[campaignId]=job.id;sessionStorage.setItem('smtpJobs',JSON.stringify(saved));
  showSmtpJob(job,campaignId);$('smtp-panel').open=true;
  if(['queued','running'].includes(job.status)&&sessionStorage.getItem('activeJob')!==job.id)watchJob(job.id).catch(()=>{if(campaign?.id===campaignId)showSmtpFeedback({tone:'warning',title:'Sending status unavailable',message:'Check Delivery log and Gmail Sent before submitting this batch again.'});});
 }catch{if(campaign?.id===campaignId)showSmtpFeedback({tone:'warning',title:'Sending status unavailable',message:'Check Delivery log and Gmail Sent before submitting this batch again.'});}
}

const JOB_LABELS={queued:'Queued',running:'In progress',completed:'Completed',completed_with_errors:'Partially completed',failed:'Incomplete',interrupted:'Interrupted',cancelled:'Stopped'};
async function submitJob(kind,data){
 const key='pendingSubmission';let pending;
 try{pending=JSON.parse(sessionStorage.getItem(key)||'null');}catch{}
 const signature=JSON.stringify({kind,data});
 if(pending&&pending.signature!==signature)throw new Error('Another request is awaiting confirmation. Refresh to restore it before starting a new one.');
 if(!pending){pending={id:crypto.randomUUID(),signature};sessionStorage.setItem(key,JSON.stringify(pending));}
 try{const job=await api('/api/'+kind,{...data,request_id:pending.id});sessionStorage.setItem('activeJob',job.id);sessionStorage.removeItem(key);return job;}
 catch(error){if(error.httpStatus&&error.httpStatus<500){sessionStorage.removeItem(key);throw error;}error.message+='; the request ID is preserved, so retrying the same input will reuse it.';throw error;}
}
let watchingId=null, watchGeneration=0;
async function watchJob(id){
 const generation=++watchGeneration;watchingId=id;sessionStorage.setItem('activeJob',id);let job;
 for(;;){
  job=await api('/api/job/'+encodeURIComponent(id));
  if(generation!==watchGeneration)return job;
  if(job.kind==='send'&&smtpJobMap()[campaign?.id]===id)showSmtpJob(job,campaign.id);
  if(job.kind==='search')searchProgress(job);
  $('cancel-job').hidden=!['queued','running'].includes(job.status);
  const parts=[`task ${JOB_LABELS[job.status]||job.status}`];
  if(job.progress)parts.push(`${job.progress.completed}/${job.progress.total} ${englishLabel(job.progress.unit)}`);
  if(!['queued','running'].includes(job.status)&&job.result){
   if(job.kind==='send'&&Number.isInteger(job.result.accepted))parts.push(`SMTP accepted ${job.result.accepted}, skipped ${job.result.skipped}, failed or needs review ${job.result.failed_or_unknown}`);
   else if(Number.isInteger(job.result.rows))parts.push(`Saved ${job.result.rows} contacts`);
  }
  if(job.error)parts.push(englishLabel(job.error));
  if(job.provider_task_id)parts.push('Provider task: '+job.provider_task_id);
  $('job-result').textContent=parts.join(' · ');
  if(!['queued','running'].includes(job.status))break;
  await new Promise(r=>setTimeout(r,2000));
 }
 sessionStorage.removeItem('activeJob');watchingId=null;$('cancel-job').hidden=true;
 await refreshRuns();await refreshJobs();$('refresh-history').click();
 const runId=job.result?.run_id||job.run_id;
 if(runId){try{await loadRun(runId);$('run-select').value=runId;}catch(e){if(e.httpStatus!==404)throw e;}}
 if(job.kind==='send'){const view=window.OutreachSendFeedback.describe(job);notice(view.title+' — '+view.message,['error','warning'].includes(view.tone));}
 else if(job.status==='completed')notice('Task completed');
 else notice(job.error||'task stopped; completed results were preserved',true);
 return job;
}
$('config-form').onsubmit=e=>{e.preventDefault();action(e.submitter,async()=>{const data={};for(const id of['sender','easykol_email','easykol_key','gmail_app_password','tracking_base_url','openai_key','openai_model','ai_gateway_url','ai_gateway_token'])data[id]=$(id).value;const r=await api('/api/config',data);$('easykol_key').value='';$('gmail_app_password').value='';$('openai_key').value='';$('ai_gateway_token').value='';notice(r.message);await refreshStatus();});};
$('quota').onclick=e=>action(e.target,async()=>{const r=await api('/api/quota',{});$('quota-result').hidden=false;$('quota-result').textContent=`Remaining: ${r.remaining}  Total: ${r.total}  Used today: ${r.dailyUsed}`;notice('EasyKOL connection verified');});
function validateSearch(){
 const form=$('search-form'),summary=$('search-validation');summary.hidden=true;
 form.querySelectorAll('.field-error').forEach(e=>e.remove());form.querySelectorAll('[aria-invalid]').forEach(e=>{e.removeAttribute('aria-invalid');e.removeAttribute('aria-describedby');});
 const errors=[];
 function invalid(id,message){const field=$(id);field.setAttribute('aria-invalid','true');const hint=element('span',message,'field-error');hint.id=id+'-error';field.setAttribute('aria-describedby',hint.id);field.after(hint);errors.push(field);}
 const queries=$('queries').value.split('\n').map(x=>x.trim()).filter(Boolean);
 if(!queries.length)invalid('queries','Describe at least one creator search.');
 else if(queries.length>20||queries.some(q=>q.length>500))invalid('queries','Use up to 20 queries, with at most 500 characters per query.');
 if(!/^[A-Za-z]{2}(\s*,\s*[A-Za-z]{2})*$/.test($('regions').value.trim()))invalid('regions','Enter two-letter country codes, such as US or US,GB.');
 for(const [id,min,max]of [['min-followers',0,Infinity],['avg-min',0,Infinity],['limit',1,50],['budget',1,Infinity],['max-followers',0,Infinity]]){
  const field=$(id);if(id==='max-followers'&&!field.value.trim())continue;
  const n=Number(field.value);if(!field.value.trim()||!Number.isSafeInteger(n)||n<min||n>max)invalid(id,`Enter a whole number ${max===Infinity?'of at least '+min:'from '+min+' to '+max}.`);
 }
 if(!errors.some(f=>['min-followers','max-followers'].includes(f.id))&&$('max-followers').value&&Number($('max-followers').value)<Number($('min-followers').value))invalid('max-followers','Maximum followers must be at least the minimum followers.');
 if(!errors.some(f=>['limit','budget','queries'].includes(f.id))&&queries.length*Number($('limit').value)>Number($('budget').value))invalid('budget',`Search credit budget must be at least ${queries.length*Number($('limit').value)} for these queries and results.`);
 if(errors.length){summary.textContent='Complete the required fields and fix the highlighted values before starting a search.';summary.hidden=false;errors[0].focus({preventScroll:true});errors[0].scrollIntoView({block:'center',behavior:'smooth'});return null;}
 return {queries,limit:Number($('limit').value),budget:Number($('budget').value),regions:$('regions').value.trim(),languages:$('languages').value,min_followers:Number($('min-followers').value),max_followers:$('max-followers').value,avg_min:Number($('avg-min').value),has_email:$('has-email').checked};
}
$('search-form').onsubmit=e=>{
 e.preventDefault();const data=validateSearch();if(!data)return;
 action(e.submitter,async()=>{
  const job=await submitJob('search',data);searchProgress(job);window.OutreachPages.go('contacts');
  try{await watchJob(job.id);}catch(error){$('contacts-search-panel').dataset.tone='error';$('contacts-search-title').textContent='Search status unavailable';$('contacts-search-detail').textContent=error.message+' Your request is saved. Check Recent tasks & recovery in Find Creators before starting another search.';$('contacts-cancel-job').hidden=true;}
 });
};
$('contacts-cancel-job').onclick=e=>action(e.target,async()=>{const id=sessionStorage.getItem('activeJob');if(!id)throw new Error('No search is currently running.');const result=await api('/api/cancel',{job_id:id});localFeedback(e.target,result.message,false);});
$('refresh-runs').onclick=e=>action(e.target,refreshRuns);
$('view-cards').onclick=()=>{contactView='cards';localStorage.setItem('outreachContactView',contactView);renderContacts();};
$('view-table').onclick=()=>{contactView='table';localStorage.setItem('outreachContactView',contactView);renderContacts();};
$('run-select').onchange=e=>{if(e.target.value)loadRun(e.target.value).catch(error=>{e.target.value=activeRun?.id||'';localFeedback(e.target,error.message);});else{loadGeneration++;activeRun=null;selected.clear();renderContacts();selectionCount();}};
$('manual-contact-form').onsubmit=e=>{e.preventDefault();action(e.submitter,async()=>{const status=$('manual-contact-status');status.textContent='Saving contact…';try{const previousRun=activeRun?.id,previousSelected=[...selected];const result=await api('/api/contact',{email:$('manual-contact-email').value,name:$('manual-contact-name').value,run_id:$('manual-contact-list').value});await refreshRuns();$('run-select').value=result.run.id;await loadRun(result.run.id);const valid=new Set(activeRun.contacts.map(r=>r.email));if(previousRun===result.run.id)for(const email of previousSelected)if(valid.has(email))selected.add(email);selected.add(result.email);$('contact-filter').value='';contactPage=Math.max(0,Math.floor(filteredContacts().findIndex(r=>r.email===result.email)/PAGE_SIZE));selectionCount();renderContacts();const message=(result.added?'Contact added':'This email is already in the list')+' and selected for outreach. No email was sent.';status.textContent=message;notice(message);$('manual-contact-email').value='';$('manual-contact-name').value='';$('manual-contact-email').focus();}catch(error){status.textContent=error.message;throw error;}});};
$('csv-file').onchange=e=>{const file=e.target.files[0];$('csv-file-name').textContent=file?file.name:'No file selected';action(e.target,async()=>{if(!file)return;if(file.size>2_000_000)throw new Error('CSV files must be 2 MB or smaller');let payload,path;if(file.name.toLowerCase().endsWith('.xlsx')){if(file.size>1_400_000)throw new Error('Excel files must be 1.4 MB or smaller; convert larger files to CSV');const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(const b of bytes)binary+=String.fromCharCode(b);payload={xlsx_base64:btoa(binary),title:file.name};path='/api/import-xlsx';}else{payload={csv_text:await file.text(),title:file.name};path='/api/import';}const run=await api(path,payload);await refreshRuns();$('run-select').value=run.id;await loadRun(run.id);notice(`Imported ${run.rows} records`);e.target.value='';$('csv-file-name').textContent='No file selected';});};
$('select-all').onclick=()=>{for(const r of filteredContacts())if(r.email)selected.add(r.email);renderContacts();selectionCount();};
$('contact-filter').oninput=$('only-email').onchange=()=>{contactPage=0;renderContacts();saveWorkspace();};
$('previous-page').onclick=()=>{contactPage--;renderContacts();};
$('next-page').onclick=()=>{contactPage++;renderContacts();};
$('clear-selection').onclick=()=>{selected.clear();renderContacts();selectionCount();};
$('export-csv').onclick=e=>action(e.target,async()=>{if(!activeRun)throw new Error('Open a contact list first');const r=await fetch('/api/csv/'+encodeURIComponent(activeRun.id),{headers:{'X-Outreach-Token':token}});if(!r.ok)throw new Error('Download failed');const u=URL.createObjectURL(await r.blob()),a=element('a');a.href=u;a.download=activeRun.id+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);});
$('draft-form').onsubmit=e=>{e.preventDefault();action(e.submitter,async()=>{if(!activeRun||!selected.size)throw new Error('Select recipients in Contacts first');const r=await api('/api/draft',{run_id:activeRun.id,selected_emails:[...selected],subject:$('subject').value,body:$('body').value});const c=await api('/api/campaign/'+r.campaign_id);renderCampaign(c,r.campaign_file);await refreshCampaigns();notice(`Draft saved with ${r.recipients} recipients; nothing sent`);});};
$('load-template').onclick=e=>action(e.target,async()=>{const id=$('template-select').value;if(!id)throw new Error('Select a template');const t=(await api('/api/templates')).templates.find(x=>x.id===id);if(!t)throw new Error('Template not found');$('subject').value=t.subject;$('body').value=t.body;invalidatePreview('Template loaded. Generate a new draft preview.');notice('Template loaded');});
$('save-template').onclick=e=>action(e.target,async()=>{const name=$('template-name').value.trim();if(!name)throw new Error('Enter a template name first');await api('/api/template',{name,subject:$('subject').value,body:$('body').value});await refreshTemplates();$('template-name').value='';notice('Template saved; nothing was sent');});
$('load-campaign').onclick=e=>action(e.target,async()=>{const id=$('campaign-select').value;if(!id)throw new Error('Select a campaign');renderCampaign(await api('/api/campaign/'+id),null);});
function batchSize(){const n=Number($('send-limit').value);if(!Number.isInteger(n)||n<1||n>500)throw new Error('Batch size must be an integer from 1 to 500');return n;}
$('browser-prompt').onclick=e=>action(e.target,async()=>{const text=`Use tiktok-outreach-personalized to send campaign ${campaign.id} through the signed-in Gmail account (${campaign.sender}), to the first ${batchSize()} recipients who have not been sent this campaign. Read the saved campaign and show a short preview first, then send with this authorization. Use browser-claim and browser-result to prevent duplicates.`;await navigator.clipboard.writeText(text);notice('Sending instructions copied. Codex can execute them; no email was sent.');});
$('send-smtp').onclick=e=>action(e.target,async()=>{
 const campaignId=campaign?.id;let attemptedSubmission=false,jobId=null;
 showSmtpFeedback({tone:'progress',busy:true,title:'Checking sending settings…',message:'No new email has been submitted yet.'},true);
 try{
  if(!campaignId)throw new Error('Generate and review an email preview first.');
  const settings=await api('/api/status');smtpConfigured=settings.gmail_configured;
  if(!smtpConfigured)throw new Error('SMTP is not configured. Add a Gmail app password in Account Setup, or use Copy Gmail send instruction with Codex.');
  if(!$('confirm-send').checked)throw new Error('Review the preview and recipients, then check the confirmation box before sending.');
  const count=batchSize();if(campaign?.id!==campaignId)throw new Error('The email preview changed. Review the current preview before sending.');
  attemptedSubmission=true;const job=await submitJob('send',{campaign_id:campaignId,execute:true,max_messages:count});jobId=job.id;
  const saved=smtpJobMap();saved[campaignId]=job.id;sessionStorage.setItem('smtpJobs',JSON.stringify(saved));
  $('confirm-send').checked=false;showSmtpJob(job,campaignId);await watchJob(job.id);
 }catch(error){
  if(campaign?.id===campaignId){const knownNotSent=!attemptedSubmission||(!jobId&&error.httpStatus&&error.httpStatus<500);showSmtpFeedback({tone:knownNotSent?'error':'warning',title:knownNotSent?'Not sent':jobId?'Sending status unavailable':'Submission status unconfirmed',message:knownNotSent?error.message:error.message+' Check Delivery log and Gmail Sent before retrying. Do not submit the batch again while its result is unknown.'},true);}
  notice(error.message,true);
 }
});
const STATUS_LABELS={accepted_by_gmail_api:'Sent — accepted by Gmail API',accepted_by_smtp:'Sent — accepted by Gmail',sent_browser:'Gmail reported success',sending:'Submitting / review required',sending_browser:'Browser submitting / review required',unknown:'Result uncertain',rejected:'Rejected by server',failed_before_submission:'Failed before submission'};
let historyOffset=0;
async function refreshMetrics(){const d=await api('/api/metrics');$('metric-sent').textContent=d.sent;$('metric-open').textContent=d.tracked?d.open_rate+'%':'Not enabled';$('metric-reply').textContent=d.reply_tracking_enabled?d.reply_rate+'%':'Not connected';$('metric-click').textContent=d.tracked?d.click_rate+'%':'Not enabled';}
async function refreshHistory(){
 const d=await api('/api/history?limit=100&offset='+historyOffset),root=$('history-result');root.replaceChildren();
 $('history-pages').hidden=!d.total;$('history-previous').disabled=historyOffset===0;$('history-next').disabled=historyOffset+d.deliveries.length>=d.total;
 $('history-page-info').textContent=`${historyOffset+1}–${historyOffset+d.deliveries.length} / of ${d.total} total`;
 if(!d.deliveries.length){root.textContent='No delivery records yet';return;}
 root.append(table(['Recipient','Status','Campaign','Time'],d.deliveries.map(r=>[r.email,STATUS_LABELS[r.status]||r.status,r.campaign.slice(0,12),new Date(r.updated*1000).toLocaleString()])));
}
$('refresh-history').onclick=e=>action(e.target,async()=>{historyOffset=0;await refreshHistory();await refreshMetrics();});
$('history-previous').onclick=e=>action(e.target,async()=>{historyOffset=Math.max(0,historyOffset-100);await refreshHistory();});
$('history-next').onclick=e=>action(e.target,async()=>{historyOffset+=100;await refreshHistory();});
$('suppress-form').onsubmit=e=>{e.preventDefault();action(e.submitter,async()=>{await api('/api/suppress',{email:$('suppress-email').value});notice('Added to the do not contact list. Future sends will skip this address.');$('suppress-email').value='';});};
async function restoretask(){
 const pending=JSON.parse(sessionStorage.getItem('pendingSubmission')||'null');
 if(pending){try{const job=await api('/api/job/'+encodeURIComponent(pending.id));sessionStorage.removeItem('pendingSubmission');return watchJob(job.id);}catch(e){if(e.httpStatus===404){sessionStorage.removeItem('pendingSubmission');notice('The previous request did not create a task. You can try again.');}else throw e;}}
 const id=sessionStorage.getItem('activeJob');if(id)return watchJob(id);
}
const FORM_FIELDS=['queries','regions','languages','min-followers','max-followers','avg-min','limit','budget','has-email','subject','body','send-limit','contact-filter','only-email','template-name','brand-name','brand-product','campaign-goal','brand-offer','personalization-language'];
function refreshEmailBrandSummary(){const name=$('brand-name').value.trim(),product=$('brand-product').value.trim();$('email-brand-summary').textContent=name||product?'Applied to this email: '+[name,product].filter(Boolean).join(' · ')+'. Edit a brief in Brand library and apply it to update this context.':'No brand brief applied to this email. Choose a saved brief above and click Apply to this email.';}
function saveWorkspace(){refreshEmailBrandSummary();const form={};for(const id of FORM_FIELDS){const el=$(id);form[id]=el.type==='checkbox'?el.checked:el.value;}sessionStorage.setItem('workspaceDraft',JSON.stringify({form,runId:activeRun?.id,selected:[...selected]}));}
async function restoreWorkspace(){
 let saved;try{saved=JSON.parse(sessionStorage.getItem('workspaceDraft')||'null');}catch{}
 if(saved){for(const[id,value]of Object.entries(saved.form||{})){if(!FORM_FIELDS.includes(id))continue;const el=$(id);if(el.type==='checkbox')el.checked=!!value;else el.value=String(value);}
  if(saved.runId){try{await loadRun(saved.runId);$('run-select').value=saved.runId;const valid=new Set(activeRun.contacts.map(r=>r.email));selected=new Set((saved.selected||[]).filter(e=>valid.has(e)));renderContacts();selectionCount();}catch(e){if(e.httpStatus!==404)throw e;}}
 }
 refreshEmailBrandSummary();
 const cid=sessionStorage.getItem('previewCampaign');if(cid){try{renderCampaign(await api('/api/campaign/'+cid),null);}catch(e){if(e.httpStatus===404)sessionStorage.removeItem('previewCampaign');else throw e;}}
}
for(const id of FORM_FIELDS)$(id).addEventListener('input',saveWorkspace);
function invalidatePreview(message){if(!campaign)return;campaign=null;sessionStorage.removeItem('previewCampaign');$('send-controls').hidden=true;$('campaign-preview').replaceChildren(element('p',message,'hint'));}
for(const id of ['subject','body'])$(id).addEventListener('input',()=>invalidatePreview('Content changed. Generate a new preview before sending.'));

function initializeInstruction(){
 const tabs=[...document.querySelectorAll('[data-instruction-tab]')];
 function selectTab(tab){
  for(const item of tabs){
   const active=item===tab;
   item.classList.toggle('active',active);
   item.setAttribute('aria-selected',String(active));item.tabIndex=active?0:-1;
   $(item.dataset.instructionTab).hidden=!active;
  }
 }
 for(const [index,tab] of tabs.entries()){
  tab.addEventListener('click',()=>selectTab(tab));
  tab.addEventListener('keydown',event=>{
   const targets={ArrowRight:(index+1)%tabs.length,ArrowLeft:(index+tabs.length-1)%tabs.length,Home:0,End:tabs.length-1};
   if(!Object.hasOwn(targets,event.key))return;
   event.preventDefault();const next=tabs[targets[event.key]];selectTab(next);next.focus();
  });
 }
}
initializeInstruction();
syncContactViewButtons();
Promise.all([refreshStatus(),refreshRuns(),refreshCampaigns(),refreshTemplates(),refreshHistory(),refreshMetrics()]).then(restoreWorkspace).then(restoretask).catch(e=>notice(e.message,true));

$('cancel-job').onclick=e=>action(e.target,async()=>{const id=sessionStorage.getItem('activeJob');if(!id)throw new Error('No task is currently running');const r=await api('/api/cancel',{job_id:id});notice(r.message);});
async function refreshJobs(){
 const d=await api('/api/jobs'),root=$('jobs-list');root.replaceChildren();
 if(!d.jobs.length){root.textContent='No background tasks';return;}
 root.append(table(['Type','Status','Time','Actions'],d.jobs.map(j=>{
  const actions=element('div'),view=element('button','View','secondary');
  view.onclick=()=>action(view,()=>watchJob(j.id));actions.append(view);
  if(j.provider_task_id&&j.source_run_id&&['failed','interrupted','cancelled'].includes(j.status)){
   const resume=element('button','Resume original task','secondary');
   resume.onclick=()=>action(resume,async()=>{const next=await submitJob('emails-resume',{source_job_id:j.id});notice('Resume the original task without submitting a new email lookup');await watchJob(next.id);});
   actions.append(resume);
  }
  return[({search:'Search',emails:'email enrichment','emails-resume':'email task resume',send:'Send'})[j.kind]||j.kind,JOB_LABELS[j.status]||j.status,new Date(j.created*1000).toLocaleString(),actions];
 })));
}
$('refresh-jobs').onclick=e=>action(e.target,refreshJobs);
refreshJobs().catch(e=>notice(e.message,true));
// V3 workspace navigation: keep panels mounted so drafts and selections survive page changes.
(() => {
 const pages = {
  discover:['Find Creators','Find the right creators for your next collaboration.'],
  contacts:['Contacts','Review your lists and choose who to contact.'],
  compose:['Outreach email','Shape your message, then review it before sending.'],
  history:['Delivery log','Keep track of deliveries and campaign activity.'],
  settings:['Account Setup','Connect the accounts you use for creator outreach.'],
  'user-instruction':['Instruction','']
 };
 const sidebar=document.getElementById('workspace-sidebar');
 const toggle=document.getElementById('sidebar-toggle');
 const links=[...sidebar.querySelectorAll('nav a')];
 const workflow=new Set(['discover','contacts','compose','history','settings']);
 let activePage=null;
 let collapsed=false;
 try {collapsed=localStorage.getItem('outreach-v3-sidebar-collapsed')==='true';} catch {}
 function setCollapsed(value){
  collapsed=value;document.body.classList.toggle('sidebar-collapsed',value);
  toggle.setAttribute('aria-expanded',String(!value));
  toggle.setAttribute('aria-label',value?'Expand sidebar':'Collapse sidebar');
  toggle.title=value?'Expand sidebar':'Collapse sidebar';
 }
 setCollapsed(collapsed);
 toggle.addEventListener('click',()=>{setCollapsed(!collapsed);try{localStorage.setItem('outreach-v3-sidebar-collapsed',String(collapsed));}catch{}});
 function showPage(){
  const hash=location.hash.slice(1);
  const page=hash==='ai-solution'?'user-instruction':Object.hasOwn(pages,hash)?hash:'discover';
  const continuous=workflow.has(page);
  for(const id of Object.keys(pages))document.getElementById(id).hidden=id!==page;
  for(const link of links){
   const selected=link.getAttribute('href')==='#'+page;
   link.classList.toggle('is-current',selected);
   if(selected)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
  }
  document.getElementById('workspace-page-title').textContent=continuous?'Creator outreach':pages[page][0];
  document.getElementById('workspace-page-description').textContent=continuous?'Find creators, manage contacts, prepare emails, and review activity in one workspace.':pages[page][1];
  document.title=pages[page][0]+' · Outreach V4';
  const order=Object.keys(pages),index=order.indexOf(page),previous=order[index-1],next=order[index+1];
  $('workflow-previous').disabled=!previous;$('workflow-next').disabled=!next;
  $('workflow-previous-label').textContent=previous?pages[previous][0]:'';
  $('workflow-next-label').textContent=next?pages[next][0]:'';
  $('workflow-page-position').textContent=`${index+1} / ${order.length}`;
  $('workflow-previous').onclick=()=>{if(previous)go(previous);};
  $('workflow-next').onclick=()=>{if(next)go(next);};
  if(activePage!==page){
   window.scrollTo({top:0,behavior:'instant'});
   const heading=$(page).querySelector('h2');if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true});}
   activePage=page;
  }
 }
 for(const link of links)link.addEventListener('click',()=>{
  if(link.hash===location.hash){activePage=null;showPage();}
 });
 function go(page){if(!Object.hasOwn(pages,page))return;if(location.hash==='#'+page)showPage();else location.hash=page;}
 window.OutreachPages={go};
 window.addEventListener('hashchange',showPage);
 showPage();
})();

let googleConnectionPending=false;
$('google-connect').onclick=()=>{const tab=window.open('about:blank','_blank');if(tab)tab.opener=null;action($('google-connect'),async()=>{try{const r=await api('/api/google/connect',{read:$('google-read').checked});if(tab){googleConnectionPending=true;tab.location=r.url;}else notice('Allow popups and click Connect Google again.');}catch(e){if(tab)tab.close();throw e;}});};
$('google-disconnect').onclick=()=>action($('google-disconnect'),async()=>{await api('/api/google/disconnect',{});await refreshStatus();notice('Google disconnected locally. Imported replies are preserved.');});
window.addEventListener('focus',()=>{if(googleConnectionPending){googleConnectionPending=false;refreshStatus().catch(()=>{});}});
