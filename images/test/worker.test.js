import { env, fetchMock, SELF } from 'cloudflare:test';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { libretroName, pngIsBlank } from '../src/index.js';
import { BLACK, COLOR, clearBucket, seed } from './png.js';

const get = (path, init) => SELF.fetch('https://images.misterzine.fyi' + path, init);

beforeEach(async () => {
  await clearBucket();
  fetchMock.activate();
  fetchMock.disableNetConnect();
});
afterEach(() => fetchMock.assertNoPendingInterceptors());

describe('validation and info', () => {
  it('rejects names that are not setnames, cacheably', async () => {
    for (const p of ['/snap/DKONG.png', '/snap/..%2Fx.png', '/snap/' + 'a'.repeat(33) + '.png', '/snap/dkong.jpg', '/snap/dk ong.png']) {
      const r = await get(p);
      expect(r.status, p).toBe(404);
      if (r.headers.get('X-Image-Miss')) expect(r.headers.get('Cache-Control')).toContain('max-age=86400');
    }
    expect((await get('/snap/dkong.png', { method: 'POST' })).status).toBe(405);
    expect((await get('/')).status).toBe(200);
    const h = await (await get('/healthz')).json();
    expect(h.ok).toBe(true);
    expect(h.upstream).toBe(false);
  });
});

describe('hits', () => {
  it('serves a seeded picture with dims, ETag, 304 and HEAD', async () => {
    await seed('snap/dkong.png', COLOR);
    const r = await get('/snap/dkong.png');
    expect(r.status).toBe(200);
    expect(r.headers.get('Content-Type')).toBe('image/png');
    expect(r.headers.get('X-Image-Width')).toBe('2');
    expect(r.headers.get('X-Image-Height')).toBe('1');
    expect(r.headers.get('X-Image-Source')).toBe('psnaps287');
    expect(r.headers.get('Cache-Control')).toContain('immutable');
    const etag = r.headers.get('ETag');
    expect(etag).toBeTruthy();
    expect(new Uint8Array(await r.arrayBuffer())).toEqual(COLOR);
    const again = await get('/snap/dkong.png', { headers: { 'If-None-Match': etag } });
    expect(again.status).toBe(304);
    const head = await get('/snap/dkong.png', { method: 'HEAD' });
    expect(head.status).toBe(200);
    expect(head.headers.get('X-Image-Width')).toBe('2');
    expect((await head.arrayBuffer()).byteLength).toBe(0);
  });

  it('falls back to the parent and keeps a copy', async () => {
    await seed('snap/dkong.png', COLOR);
    await env.IMAGES.put('meta/parent.json', JSON.stringify({ dkongj: 'dkong' }));
    const r = await get('/snap/dkongj.png');
    expect(r.status).toBe(200);
    expect(r.headers.get('X-Image-Source')).toBe('parent:dkong');
    await r.arrayBuffer();
    const copy = await env.IMAGES.head('snap/dkongj.png');
    expect(copy).not.toBeNull();
    expect(copy.customMetadata.src).toBe('parent:dkong');
    expect(copy.customMetadata.w).toBe('2');
  });
});

describe('misses with upstream off', () => {
  it('answers 404 and writes nothing', async () => {
    const r = await get('/snap/nothing.png');
    expect(r.status).toBe(404);
    expect(r.headers.get('X-Image-Miss')).toBe('negative');
    expect(r.headers.get('Cache-Control')).toContain('max-age=86400');
    expect((await env.IMAGES.list()).objects.length).toBe(0);
  });

  it('honours an unexpired negative marker and ignores an expired one', async () => {
    await env.IMAGES.put('neg/snap/gone', '', { customMetadata: { until: new Date(Date.now() + 86400e3).toISOString(), tries: '1' } });
    expect((await get('/snap/gone.png')).headers.get('X-Image-Miss')).toBe('negative');
    // expired marker + parent available: the parent wins
    await env.IMAGES.put('neg/snap/dkongj', '', { customMetadata: { until: new Date(Date.now() - 1000).toISOString(), tries: '1' } });
    await seed('snap/dkong.png', COLOR);
    await env.IMAGES.put('meta/parent.json', JSON.stringify({ dkongj: 'dkong' }));
    const r = await get('/snap/dkongj.png');
    expect(r.status).toBe(200);
    await r.arrayBuffer();
  });
});

describe('helpers', () => {
  it('names libretro files and detects blank frames', async () => {
    expect(libretroName('Q*bert / Q-bert: The Game?')).toBe('Q_bert _ Q-bert_ The Game_');
    expect(await pngIsBlank(BLACK)).toBe(true);
    expect(await pngIsBlank(COLOR)).toBe(false);
    expect(await pngIsBlank(new Uint8Array([1, 2, 3]))).toBe(false);
  });
});
