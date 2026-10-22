import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {randomBytes} from 'node:crypto';
import worker,{targetURL} from './worker.mjs';

const id=()=>randomBytes(32).toString('base64url');
function setup(){
 const sql=new DatabaseSync(':memory:');sql.exec(readFileSync(new URL('./schema.sql',import.meta.url),'utf8'));
 const token=id(),pending=[];
 const db={prepare(query){let values=[];return {bind(...v){values=v;return this;},async first(){return sql.prepare(query).get(...values)||null;},async all(){return {results:sql.prepare(query).all(...values)};},async run(){return sql.prepare(query).run(...values);}};},async batch(queries){sql.exec('BEGIN');try{for(const q of queries)await q.run();sql.exec('COMMIT');}catch(e){sql.exec('ROLLBACK');throw e;}}};
 const env={TRACKING_DB:db,TRACKING_ADMIN_TOKEN:token};
 return {sql,env,async call(path,{data,auth=true,method}={}){const headers={};if(auth)headers.Authorization='Bearer '+token;if(data)headers['Content-Type']='application/json';const r=await worker.fetch(new Request('https://receiver.test-account.workers.dev'+path,{method:method||(data?'POST':'GET'),headers,body:data?JSON.stringify(data):undefined}),env,{waitUntil(p){pending.push(p);}});await Promise.all(pending.splice(0));return r;}};
}
test('management API denies missing auth and arbitrary uploads',async()=>{const s=setup();assert.equal((await s.call('/v1/events',{data:{ids:[id()]},auth:false})).status,401);assert.equal((await s.call('/v1/register',{data:{id:id(),links:[],email:'private@example.com'}})).status,400);assert.equal((await s.call('/v1/register',{data:{id:id(),links:[],path:'/Users/private'}})).status,400);s.sql.close();});
test('public events deduplicate, IDs stay opaque, redirect cannot be replaced',async()=>{const s=setup(),mid=id(),lid=id();assert.equal((await s.call('/v1/register',{data:{id:mid,links:[{id:lid,target:'https://example.com/product'}]}})).status,200);await s.call('/o/'+mid+'.gif',{auth:false});await s.call('/o/'+mid+'.gif',{auth:false});const click=await s.call('/c/'+lid,{auth:false});assert.equal(click.status,302);assert.equal(click.headers.get('Location'),'https://example.com/product');assert.equal((await s.call('/c/'+lid+'?url=https://evil.example',{auth:false})).status,404);assert.equal((await s.call('/v1/register',{data:{id:mid,links:[{id:lid,target:'https://evil.example'}]}})).status,409);const events=(await (await s.call('/v1/events',{data:{ids:[mid]}})).json()).events;assert.equal(events.length,2);assert.deepEqual(new Set(events.map(e=>e.event)),new Set(['open','click']));assert.deepEqual(Object.keys(events[0]).sort(),['event','id','occurred']);s.sql.close();});
test('unregistered pixels do not create data and no arbitrary files are served',async()=>{const s=setup();assert.equal((await s.call('/o/'+id()+'.gif',{auth:false})).headers.get('Content-Type'),'image/gif');assert.equal(s.sql.prepare('SELECT COUNT(*) AS n FROM events').get().n,0);for(const path of ['/api/status','/config.json','/Users/private.txt','/v1/events'])assert.notEqual((await s.call(path,{auth:false})).status,200);s.sql.close();});
test('only external HTTPS destinations are accepted',()=>{for(const value of ['http://example.com','file:///Users/private','https://127.0.0.1','https://[::1]','https://localhost','https://x.internal','https://u:p@example.com','https://example.com:1234'])assert.throws(()=>targetURL(value));assert.equal(targetURL('https://example.com/a?x=1'),'https://example.com/a?x=1');});
test('statistics failure does not break a known redirect',async()=>{const s=setup(),mid=id(),lid=id();await s.call('/v1/register',{data:{id:mid,links:[{id:lid,target:'https://example.com/'}]}});s.sql.exec('DROP TABLE events');const r=await s.call('/c/'+lid,{auth:false});assert.equal(r.status,302);assert.equal(r.headers.get('Location'),'https://example.com/');s.sql.close();});
