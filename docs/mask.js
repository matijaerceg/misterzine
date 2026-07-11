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
  // Returns false if pixels are unreadable (CORS taint) — caller keeps the img.
  window.mzMask = function (img, canvas, opts) {
    opts = opts || {};
    var dpr = window.devicePixelRatio || 1;
    var box = canvas.parentElement.getBoundingClientRect();
    var w = Math.max(1, Math.round(box.width * dpr));
    var h = Math.max(1, Math.round(box.height * dpr));
    canvas.width = w; canvas.height = h;
    var ctx = canvas.getContext('2d', { willReadFrequently: true });
    ctx.imageSmoothingEnabled = opts.smooth !== false;
    if (opts.fit === 'cover' || opts.fit === 'contain') {
      var s = (opts.fit === 'cover' ? Math.max : Math.min)(
        w / img.naturalWidth, h / img.naturalHeight);
      var dw = img.naturalWidth * s, dh = img.naturalHeight * s;
      ctx.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh);
    } else {
      ctx.drawImage(img, 0, 0, w, h);
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
        var py = (xx % 6) >= 3 ? yy + 2 : yy;
        var open = (py % 4) >= 1;
        var st = xx % 3;
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
