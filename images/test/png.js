// Tiny valid PNGs for the tests: 2x1, RGB. BLACK has all-zero pixels.
import { env } from 'cloudflare:test';

export function png(pixels) {
  const sig = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  const chunk = (type, data) => {
    const len = [data.length >>> 24, (data.length >>> 16) & 255, (data.length >>> 8) & 255, data.length & 255];
    const body = [...type].map(c => c.charCodeAt(0)).concat([...data]);
    return len.concat(body, crc32(body));
  };
  const ihdr = [0, 0, 0, 2, 0, 0, 0, 1, 8, 2, 0, 0, 0];
  const raw = [0, ...pixels]; // one scanline: filter byte + 2 RGB pixels
  return new Uint8Array([...sig, ...chunk('IHDR', ihdr), ...chunk('IDAT', deflateStore(raw)), ...chunk('IEND', [])]);
}
// zlib stream with one stored (uncompressed) block
function deflateStore(bytes) {
  const n = bytes.length;
  const out = [0x78, 0x01, 0x01, n & 255, n >> 8, (~n) & 255, ((~n) >> 8) & 255, ...bytes];
  let a = 1, b = 0;
  for (const x of bytes) { a = (a + x) % 65521; b = (b + a) % 65521; }
  return out.concat([(b >> 8) & 255, b & 255, (a >> 8) & 255, a & 255]);
}
function crc32(bytes) {
  let c, crc = 0xffffffff;
  for (const x of bytes) {
    c = (crc ^ x) & 255;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    crc = (crc >>> 8) ^ c;
  }
  crc = (crc ^ 0xffffffff) >>> 0;
  return [crc >>> 24, (crc >>> 16) & 255, (crc >>> 8) & 255, crc & 255];
}
export const BLACK = png([0, 0, 0, 0, 0, 0]);
export const COLOR = png([255, 0, 0, 0, 255, 0]);

export async function clearBucket() {
  const list = await env.IMAGES.list();
  for (const o of list.objects) await env.IMAGES.delete(o.key);
}
export async function seed(key, bytes, meta) {
  await env.IMAGES.put(key, bytes, { httpMetadata: { contentType: 'image/png' }, customMetadata: meta || { w: '2', h: '1', src: 'psnaps287' } });
}
