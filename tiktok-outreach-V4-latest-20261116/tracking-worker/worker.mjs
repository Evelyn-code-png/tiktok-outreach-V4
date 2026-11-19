// Independent event receiver. No local connector, filesystem, mail access or outbound fetch.
const ID = /^[A-Za-z0-9_-]{43}$/;
const HEADERS = {'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'};
const PIXEL = Uint8Array.from(atob('R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=='), c=>c.charCodeAt(0));
const json = (data,status=200)=>new Response(JSON.stringify(data),{status,headers:{...HEADERS,'Content-Type':'application/json'}});

async function authorized(request,env) {
  if (!ID.test(env.TRACKING_ADMIN_TOKEN||'')) return false;
  const provided=request.headers.get('Authorization')||'';
  const encoder=new TextEncoder();
  const [a,b]=await Promise.all([provided,'Bearer '+env.TRACKING_ADMIN_TOKEN].map(s=>crypto.subtle.digest('SHA-256',encoder.encode(s))));
  const aa=new Uint8Array(a),bb=new Uint8Array(b);
  let diff=0;for(let i=0;i<aa.length;i++)diff|=aa[i]^bb[i];return diff===0;
}

export function targetURL(value) {
  if(typeof value!=='string'||value.length>2048||/[\r\n\x00]/.test(value))throw new Error('Invalid destination');
  const u=new URL(value),h=u.hostname.toLowerCase();
  if(u.protocol!=='https:'||u.username||u.password||u.port||!h.includes('.')||h.includes(':')||
    /^[\d.]+$/.test(h)||['localhost','.localhost','.local','.internal','.test','.invalid'].some(s=>h===s||h.endsWith(s)))throw new Error('Public HTTPS destination required');
  return u.href;
}

async function body(request) {
  if(!request.headers.get('Content-Type')?.startsWith('application/json'))throw new Error('JSON required');
  const reader=request.body?.getReader();if(!reader)throw new Error('Body required');
  let size=0,text='';const decoder=new TextDecoder();
  try {for(;;){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>32768)throw new Error('Request too large');text+=decoder.decode(value,{stream:true});}}
  finally{await reader.cancel().catch(()=>{});}
  const data=JSON.parse(text+decoder.decode());if(!data||Array.isArray(data)||typeof data!=='object')throw new Error('Object required');return data;
}

async function record(env,id,event) {
  // Only the first event of each type is stored. IPs, headers and user agents are never stored.
  await env.TRACKING_DB.prepare('INSERT OR IGNORE INTO events(message_id,event,occurred) VALUES(?,?,?)').bind(id,event,Math.floor(Date.now()/1000)).run();
}

export default {
  async fetch(request,env,ctx) {
    const u=new URL(request.url),path=u.pathname;
    if(u.search)return json({error:'Not found'},404);
    try {
      const open=path.match(/^\/o\/([A-Za-z0-9_-]{43})\.gif$/);
      if(request.method==='GET'&&open) {
        try{const row=await env.TRACKING_DB.prepare('SELECT id FROM messages WHERE id=?').bind(open[1]).first();if(row)ctx.waitUntil(record(env,row.id,'open').catch(()=>{}));}catch{}
        return new Response(PIXEL,{headers:{...HEADERS,'Content-Type':'image/gif'}});
      }
      const click=path.match(/^\/c\/([A-Za-z0-9_-]{43})$/);
      if(request.method==='GET'&&click) {
        const row=await env.TRACKING_DB.prepare('SELECT message_id,target FROM links WHERE id=?').bind(click[1]).first();
        if(!row)return json({error:'Link unavailable'},404);
        const target=targetURL(row.target);
        // A statistics write failure must not prevent a valid link from redirecting.
        ctx.waitUntil(record(env,row.message_id,'click').catch(()=>{}));
        return new Response(null,{status:302,headers:{...HEADERS,Location:target}});
      }
      if(!path.startsWith('/v1/'))return json({service:'Outreach event receiver'},path==='/'?200:404);
      if(!await authorized(request,env))return json({error:'Unauthorized'},401);
      if(path==='/v1/health'&&request.method==='GET') {
        await env.TRACKING_DB.prepare('SELECT id FROM messages LIMIT 1').all();
        return json({service:'outreach-tracking',version:1});
      }
      if(request.method!=='POST')return json({error:'Not found'},404);
      const data=await body(request);
      if(path==='/v1/register') {
        if(Object.keys(data).some(k=>!['id','links'].includes(k))||!ID.test(data.id)||!Array.isArray(data.links)||data.links.length>50)throw new Error('Invalid registration');
        const links=data.links.map(l=>{
          if(!l||Object.keys(l).some(k=>!['id','target'].includes(k))||!ID.test(l.id))throw new Error('Invalid link');
          return {id:l.id,target:targetURL(l.target)};
        });
        if(new Set(links.map(l=>l.id)).size!==links.length)throw new Error('Duplicate link');
        // A caller with the management secret cannot change an already issued destination.
        for(const l of links){const old=await env.TRACKING_DB.prepare('SELECT message_id,target FROM links WHERE id=?').bind(l.id).first();if(old&&(old.message_id!==data.id||old.target!==l.target))return json({error:'Existing link differs'},409);}
        await env.TRACKING_DB.batch([
          env.TRACKING_DB.prepare('INSERT OR IGNORE INTO messages(id,created) VALUES(?,?)').bind(data.id,Math.floor(Date.now()/1000)),
          ...links.map(l=>env.TRACKING_DB.prepare('INSERT OR IGNORE INTO links(id,message_id,target) VALUES(?,?,?)').bind(l.id,data.id,l.target))
        ]);
        return json({id:data.id});
      }
      if(path==='/v1/events') {
        if(Object.keys(data).some(k=>k!=='ids')||!Array.isArray(data.ids)||data.ids.length<1||data.ids.length>100||!data.ids.every(id=>ID.test(id)))throw new Error('Invalid selection');
        const marks=data.ids.map(()=>'?').join(',');
        const result=await env.TRACKING_DB.prepare(`SELECT message_id AS id,event,occurred FROM events WHERE message_id IN (${marks})`).bind(...data.ids).all();
        return json({events:result.results});
      }
      return json({error:'Not found'},404);
    } catch(error) {
      // No request URLs, bodies, credentials or exception details are written to logs.
      return json({error:'Request could not be completed'},400);
    }
  }
};
