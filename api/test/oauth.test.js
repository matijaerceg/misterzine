import {env} from 'cloudflare:test';
import {beforeAll,beforeEach,afterEach,it,expect,vi} from 'vitest';
import schema from '../schema.sql?raw';
import worker from '../src/index.js';
const e={...env,GOOGLE_CLIENT_ID:'test-google',GOOGLE_CLIENT_SECRET:'test-secret',GITHUB_CLIENT_ID:'test-github',GITHUB_CLIENT_SECRET:'test-secret'};
const call=(path,headers={})=>worker.fetch(new Request('https://api.misterzine.fyi'+path,{headers}),e);
beforeAll(async()=>env.DB.batch(schema.replace(/--.*$/gm,'').split(';').map(s=>s.trim()).filter(Boolean).map(s=>env.DB.prepare(s))));
beforeEach(async()=>{await env.DB.prepare('DELETE FROM users').run();});
afterEach(()=>vi.unstubAllGlobals());
async function login(provider,claims={}) {
 const start=await call('/auth/'+provider+'?r=%2Freleases%2F%3Fcollection%3Dbrowse');
 expect(start.status).toBe(302);const target=new URL(start.headers.get('Location'));
 expect(start.headers.get('Set-Cookie')).toContain('HttpOnly; Secure; SameSite=Lax');
 if(provider==='google')expect(target.searchParams.get('code_challenge_method')).toBe('S256');
 vi.stubGlobal('fetch',async url=>{
  if(String(url)==='https://oauth2.googleapis.com/token')return Response.json({id_token:'header.'+btoa(JSON.stringify({iss:'https://accounts.google.com',aud:'test-google',exp:Math.floor(Date.now()/1000)+3600,sub:'verified-account',email:'matija.erceg@gmail.com',email_verified:true,...claims}))+'.signature'});
  if(String(url)==='https://github.com/login/oauth/access_token')return Response.json({access_token:'provider-test-token'});
  if(String(url)==='https://api.github.com/user')return Response.json({id:123,email:'matija.erceg@gmail.com'});
  throw new Error('Unexpected provider request');
 });
 const response=await call('/auth/'+provider+'/callback?code=test-code&state='+target.searchParams.get('state'),{Cookie:start.headers.get('Set-Cookie').split(';')[0]});
 const params=new URLSearchParams(new URL(response.headers.get('Location')).hash.slice(1));
 const token=params.get('t');return {params,me:token ? await (await call('/me',{Authorization:'Bearer '+token})).json() : null};
}
it('grants admin only after verified Google OAuth and clears permission when verification disappears',async()=>{
 const first=await login('google');expect(first.me).toMatchObject({provider:'google',list_admin:true});expect(first.params.get('r')).toBe('/releases/?collection=browse');
 const second=await login('google',{email_verified:false});expect(second.me.list_admin).toBe(false);expect(await env.DB.prepare('SELECT email FROM users').first('email')).toBeNull();
});
it('never grants admin from a GitHub profile email',async()=>{expect((await login('github')).me).toMatchObject({provider:'github',list_admin:false});});
it('rejects expired or wrong-audience Google tokens and callbacks without matching state',async()=>{
 expect((await login('google',{exp:1})).params.get('error')).toBe('idtoken');
 expect((await login('google',{aud:'another-app'})).params.get('error')).toBe('idtoken');
 const bad=await call('/auth/google/callback?code=bad&state=bad');expect(bad.headers.get('Location')).toContain('error=state');
 expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM users').first('n')).toBe(0);
});
