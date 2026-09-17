// The miss path with UPSTREAM_ENABLED "1" (set in vitest.config.js).
import { env, fetchMock, SELF } from 'cloudflare:test';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { BLACK, COLOR, clearBucket } from './png.js';

const get = (path) => SELF.fetch('https://images.misterzine.fyi' + path);
const hourKey = () => 'meta/upstream/' + new Date().toISOString().slice(0, 13).replace(/[-T]/g, '');

beforeEach(async () => {
  await clearBucket();
  // The Worker keeps the description map per runtime once loaded, so every
  // name the suite needs is in place before the first miss.
  await env.IMAGES.put('meta/desc.json', JSON.stringify({ twogame: 'Two: Game & Co', threegame: 'Three', blackgame: 'Black' }));
  fetchMock.activate();
  fetchMock.disableNetConnect();
});
afterEach(() => fetchMock.assertNoPendingInterceptors());

describe('misses with upstream on', () => {
  it('reports the toggle', async () => {
    expect((await (await get('/healthz')).json()).upstream).toBe(true);
  });

  it('stores an Arcade Database PNG with its dims', async () => {
    fetchMock.get('https://adb.arcadeitalia.net').intercept({ path: '/media/mame.current/ingames/newgame.png' }).reply(200, Buffer.from(COLOR));
    const r = await get('/snap/newgame.png');
    expect(r.status).toBe(200);
    expect(r.headers.get('X-Image-Source')).toBe('adb');
    expect(r.headers.get('X-Image-Width')).toBe('2');
    await r.arrayBuffer();
    const stored = await env.IMAGES.head('snap/newgame.png');
    expect(stored.customMetadata.src).toBe('adb');
    expect(await env.IMAGES.head('lock/snap/newgame')).toBeNull();
    expect(await (await env.IMAGES.get(hourKey())).text()).toBe('1');
  });

  it('falls through HTML, then libretro by description, else remembers the miss', async () => {
    fetchMock.get('https://adb.arcadeitalia.net').intercept({ path: '/media/mame.current/ingames/twogame.png' }).reply(200, '<html>nope</html>');
    fetchMock.get('https://raw.githubusercontent.com').intercept({ path: '/libretro-thumbnails/MAME/master/Named_Snaps/' + encodeURIComponent('Two_ Game _ Co') + '.png' }).reply(200, Buffer.from(COLOR));
    let r = await get('/snap/twogame.png');
    expect(r.status).toBe(200);
    expect(r.headers.get('X-Image-Source')).toBe('libretro');
    await r.arrayBuffer();

    fetchMock.get('https://adb.arcadeitalia.net').intercept({ path: '/media/mame.current/ingames/threegame.png' }).reply(404, '');
    fetchMock.get('https://raw.githubusercontent.com').intercept({ path: '/libretro-thumbnails/MAME/master/Named_Snaps/Three.png' }).reply(404, '');
    r = await get('/snap/threegame.png');
    expect(r.status).toBe(404);
    expect(r.headers.get('X-Image-Miss')).toBe('negative');
    const neg = await env.IMAGES.head('neg/snap/threegame');
    expect(neg.customMetadata.tries).toBe('1');
    expect(Date.parse(neg.customMetadata.until)).toBeGreaterThan(Date.now() + 29 * 86400e3);
    // Remembered: no further upstream call.
    expect((await get('/snap/threegame.png')).headers.get('X-Image-Miss')).toBe('negative');
  });

  it('treats an all-black capture as a miss', async () => {
    fetchMock.get('https://adb.arcadeitalia.net').intercept({ path: '/media/mame.current/ingames/blackgame.png' }).reply(200, Buffer.from(BLACK));
    fetchMock.get('https://raw.githubusercontent.com').intercept({ path: '/libretro-thumbnails/MAME/master/Named_Snaps/Black.png' }).reply(404, '');
    expect((await get('/snap/blackgame.png')).status).toBe(404);
    expect(await env.IMAGES.head('snap/blackgame.png')).toBeNull();
  });

  it('respects a lock and the hourly cap without calling upstream', async () => {
    await env.IMAGES.put('lock/snap/busy', '', { customMetadata: { exp: String(Date.now() + 30000) } });
    let r = await get('/snap/busy.png');
    expect(r.status).toBe(404);
    expect(r.headers.get('X-Image-Miss')).toBe('inflight');
    expect(r.headers.get('Cache-Control')).toBe('no-store');
    await env.IMAGES.put(hourKey(), '2'); // UPSTREAM_HOURLY_CAP is 2 in the test config
    r = await get('/snap/capped.png');
    expect(r.headers.get('X-Image-Miss')).toBe('capped');
    expect(await env.IMAGES.head('neg/snap/capped')).toBeNull();
  });
});
