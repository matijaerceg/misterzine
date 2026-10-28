import {env} from 'cloudflare:test';
import {beforeAll,beforeEach,it,expect} from 'vitest';
import schema from '../schema.sql?raw';
import {limitListWrites} from '../src/list-limits.js';
beforeAll(async()=>env.DB.batch(schema.replace(/--.*$/gm,'').split(';').map(s=>s.trim()).filter(Boolean).map(s=>env.DB.prepare(s))));
beforeEach(async()=>{await env.DB.prepare('DELETE FROM users').run();await env.DB.prepare("INSERT INTO users(id,provider,provider_user_id) VALUES(1,'github','limits'),(2,'github','other')").run();});
it('atomically limits creation bursts, isolates accounts, allows edits/deletes, and resets the hour',async()=>{
  const now=360000000;
  const results=await Promise.all(Array.from({length:25},()=>limitListWrites(env,1,true,now)));
  expect(results.filter(r=>r===null)).toHaveLength(20);
  const limited=results.find(Boolean);expect(limited.status).toBe(429);expect(limited.headers.get('Retry-After')).toBe('3600');
  expect(await limitListWrites(env,2,true,now)).toBeNull();
  expect(await limitListWrites(env,1,false,now)).toBeNull();
  expect(await limitListWrites(env,1,true,now+3600000)).toBeNull();
});
it('bounds all writes per minute without keeping raw addresses; counters disappear with the account',async()=>{
  const now=360000000;
  await env.DB.prepare('INSERT INTO list_write_limits VALUES(1,6000,119,100,0)').run();
  expect(await limitListWrites(env,1,false,now)).toBeNull();
  const r=await limitListWrites(env,1,false,now);expect(r.status).toBe(429);expect(r.headers.get('Retry-After')).toBe('60');
  expect(await limitListWrites(env,1,false,now+60000)).toBeNull();
  await env.DB.prepare('DELETE FROM users WHERE id=1').run();expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM list_write_limits').first('n')).toBe(0);
});
