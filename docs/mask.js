// CRT slot mask for stills, after Timothy Lottes' RVM mode 2 (public domain).
// Draws the source image into a canvas at DEVICE resolution and applies the
// phosphor lattice there, so the mask is pixel-crisp at any display scale.
// Geometry (device px): 3px RGB stripe triads, 4px slots with 1 gap row,
// alternate triad columns staggered by 2. Energy-normalized in linear light
// so brightness survives (unlit subpixels get the gamma-squared color, lit
// ones are amplified).
(function () {
  'use strict';
  var DARK = 7 / 8;
  var LIM = 1 / (3 / 12 + (9 / 12) * DARK);
  var S2L = new Float32Array(256);
  for (var i = 0; i < 256; i++) {
    var c = i / 255;
    S2L[i] = c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  }
  var L2S = new Uint8Array(4096);
  for (var j = 0; j < 4096; j++) {
    var l = j / 4095;
    L2S[j] = Math.round((l < 0.0031308 ? l * 12.92 : 1.055 * Math.pow(l, 1 / 2.4) - 0.055) * 255);
  }

  // Render img into canvas (sized from its parent box * devicePixelRatio) and
  // mask it. opts.fit: 'cover' | 'fill'; opts.smooth: false = pixelated.
  // opts.blur: >1 softens along the scan direction (tent blur of roughly
  // that width in SOURCE pixels, pre-mask — worn-tube look). opts.rot:
  // tate — rotates the lattice AND the blur axis together (same tube).
  // Returns false if pixels are unreadable (CORS taint) — caller keeps the img.
  window.mzMask = function (img, canvas, opts) {
    opts = opts || {};
    var rot = !!opts.rot;
    // Render at full device density so every mask pixel lands exactly on a
    // device pixel (no canvas stretch, no rainbow). Apparent triad size on
    // phone-dense screens is handled by the integer lattice scale below.
    // (A capped-density stretch variant was tried 2026-07-11..14 and reverted:
    // pixel-perfect-but-coarser preferred over slightly-soft-but-finer.)
    var dpr = opts.dpr || window.devicePixelRatio || 1;
    var box = canvas.parentElement.getBoundingClientRect();
    var w = Math.max(1, Math.round(box.width * dpr));
    var h = Math.max(1, Math.round(box.height * dpr));
    canvas.width = w; canvas.height = h;
    var ctx = canvas.getContext('2d', { willReadFrequently: true });
    ctx.imageSmoothingEnabled = opts.smooth !== false;
    // Scan-direction blur at SOURCE resolution: two box passes (= tent
    // filter) built from alpha-accumulated sub-pixel-offset draws along the
    // raster axis. Full-res grid throughout — no decimation, so no aliasing
    // shimmer and no blocky re-upscale (a naive downscale/upscale draw
    // aliases hard past 2x). Softening is tied to the image's native pixels,
    // never the output size.
    var src = img;
    if (opts.blur > 1) {
      var bw = img.naturalWidth, bh = img.naturalHeight;
      var acc = document.createElement('canvas');
      acc.width = bw; acc.height = bh;
      acc.getContext('2d').drawImage(img, 0, 0);
      var span = opts.blur - 1;
      var taps = Math.max(2, Math.ceil(opts.blur));
      for (var pass = 0; pass < 2; pass++) {
        var nxt = document.createElement('canvas');
        nxt.width = bw; nxt.height = bh;
        var nctx = nxt.getContext('2d');
        for (var t = 0; t < taps; t++) {
          var o = span * (t / (taps - 1) - 0.5);
          nctx.globalAlpha = 1 / (t + 1);
          nctx.drawImage(acc, rot ? 0 : o, rot ? o : 0);
        }
        acc = nxt;
      }
      src = acc;
    }
    if (opts.fit === 'cover' || opts.fit === 'contain') {
      var s = (opts.fit === 'cover' ? Math.max : Math.min)(
        w / img.naturalWidth, h / img.naturalHeight);
      var dw = img.naturalWidth * s, dh = img.naturalHeight * s;
      ctx.drawImage(src, (w - dw) / 2, (h - dh) / 2, dw, dh);
    } else {
      ctx.drawImage(src, 0, 0, w, h);
    }
    var id;
    try { id = ctx.getImageData(0, 0, w, h); }
    catch (e) { return false; }
    var d = id.data;
    // Lattice scale: integer multiple of device px (fractional would band).
    // 1x reads right on desktops up through 2x displays; only genuinely
    // phone-dense screens (dpr >= 2.5) double it, and 2 is the ceiling.
    var m = opts.scale || Math.min(2, Math.max(1, Math.round(dpr / 1.5)));
    for (var y = 0; y < h; y++) {
      var row = y * w * 4;
      var yy = (y / m) | 0;
      for (var x = 0; x < w; x++) {
        var p = row + x * 4;
        var xx = (x / m) | 0;
        // a = stripe/stagger axis (across scanlines), b = slot axis. Tate
        // rotation swaps them — the mask is printed on the tube, so it turns
        // with the monitor. 90 vs 270 is moot: only the axis matters.
        var a = rot ? yy : xx;
        var b = rot ? xx : yy;
        var pb = (a % 6) >= 3 ? b + 2 : b;
        var open = (pb % 4) >= 1;
        var st = a % 3;
        for (var ch = 0; ch < 3; ch++) {
          var c0 = S2L[d[p + ch]];
          var amp = 1 / (LIM * 3 / 12 + LIM * (9 / 12) * c0);
          var l = (open && ch === st ? c0 : c0 * c0 * DARK) * amp;
          d[p + ch] = L2S[Math.max(0, Math.min(4095, (l * 4095) | 0))];
        }
      }
    }
    ctx.putImageData(id, 0, 0);
    return true;
  };
})();
