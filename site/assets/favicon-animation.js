/* FitBoyRepack — true geometric FB ⇄ controller morph.
 * Each letter component moves into a controller control; the housing itself
 * interpolates from a rounded capsule into ergonomic grips. No cross-fade
 * or abrupt SVG swapping. Animates only when visible and motion is allowed.
 */
(() => {
  'use strict';
  const icon = document.querySelector('link[rel="icon"]');
  if (!icon) return;

  const fallback = new URL('./favicon.svg?v=5', document.baseURI).href;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 192;
  const ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx || typeof ctx.roundRect !== 'function') return;

  const WHITE = '#f7f8fc';
  const VIOLET = '#7c6cff';
  const DARK = '#101726';
  const motion = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  const HOLD_FB = 1650;
  const HOLD_PAD = 1550;
  const TRANSITION_MS = 1450;
  const FRAME_MS = 1000 / 60;
  let timer = null;
  let raf = null;
  let cycle = 0;
  let lastCommitted = -1;

  const clamp = x => Math.max(0, Math.min(1, x));
  const mix = (a, b, t) => a + (b - a) * t;
  const ease = x => { const t = clamp(x); return t * t * (3 - 2 * t); };
  const range = (a, b, x) => ease((x - a) / (b - a));

  function stroke(ax, ay, bx, by, width, color, opacity = 1) {
    if (width < 0.1 || opacity <= 0) return;
    ctx.save();
    ctx.globalAlpha = opacity;
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.lineTo(bx, by);
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineCap = 'round';
    ctx.stroke();
    ctx.restore();
  }

  function ellipse(x, y, rx, ry, color, opacity = 1) {
    if (rx <= 0 || ry <= 0 || opacity <= 0) return;
    ctx.save();
    ctx.globalAlpha = opacity;
    ctx.beginPath();
    ctx.ellipse(x, y, rx, ry, 0, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.restore();
  }

  function housing(t) {
    // Same cubic topology for both silhouettes: actual shape interpolation.
    // Rounded capsule -> arched shoulders and sweeping gamepad grips.
    const p = (a, b) => mix(a, b, t);
    ctx.beginPath();
    ctx.moveTo(p(20, 19), p(14, 12));
    ctx.bezierCurveTo(p(13, 12), p(14, 12), p(12, 10), p(18, 17),
                      p(12, 12), p(25, 24));
    ctx.lineTo(p(10, 4), p(40, 39));
    ctx.bezierCurveTo(p(9, 2), p(48, 47), p(13, 7), p(52, 54),
                      p(20, 15), p(50, 50));
    ctx.lineTo(p(24, 23), p(47, 45));
    ctx.bezierCurveTo(p(29, 29), p(45, 43), p(35, 35), p(45, 43),
                      p(40, 41), p(47, 45));
    ctx.lineTo(p(44, 49), p(50, 50));
    ctx.bezierCurveTo(p(51, 57), p(52, 54), p(55, 62), p(48, 47),
                      p(54, 60), p(40, 39));
    ctx.lineTo(p(52, 56), p(25, 24));
    ctx.bezierCurveTo(p(52, 54), p(18, 17), p(50, 52), p(14, 12),
                      p(44, 45), p(14, 12));
    ctx.closePath();
  }

  function paint(progress) {
    const t = clamp(progress);
    ctx.setTransform(3, 0, 0, 3, 0, 0);
    ctx.clearRect(0, 0, 64, 64);

    ctx.beginPath();
    ctx.roundRect(2, 2, 60, 60, 13);
    ctx.fillStyle = DARK;
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#34405e';
    ctx.stroke();

    const shell = range(0.09, 0.72, t);
    if (shell > 0) {
      ctx.save();
      housing(range(0.10, 0.95, t));
      const fill = ctx.createLinearGradient(18, 12, 46, 53);
      fill.addColorStop(0, '#40318b');
      fill.addColorStop(0.55, '#261f59');
      fill.addColorStop(1, '#4830ad');
      ctx.globalAlpha = shell;
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.lineWidth = mix(1.5, 3.4, shell);
      ctx.strokeStyle = WHITE;
      ctx.lineJoin = 'round';
      ctx.stroke();
      ctx.restore();
    }

    // F: one vertical and one horizontal bar become the controller's D-pad.
    const f = range(0.04, 0.98, t);
    const fw = mix(7, 5.4, f);
    stroke(mix(17.5, 19, f), mix(17.5, 25, f),
           mix(17.5, 19, f), mix(46.5, 37, f), fw, WHITE);
    stroke(mix(17.5, 13.5, f), mix(17.5, 31, f),
           mix(29, 24.5, f), mix(17.5, 31, f), fw, WHITE);
    const extra = 1 - range(0.24, 0.64, t);
    stroke(mix(17.5, 17, f), mix(31, 31, f),
           mix(28, 26, f), mix(31, 31, f), 6.5, WHITE, extra);

    // B: its vertical stem folds into the controller's center button.
    const b = range(0.06, 0.97, t);
    const stem = 1 - range(0.12, 0.72, t);
    stroke(mix(36.2, 31, b), mix(17.5, 20, b),
           mix(36.2, 34, b), mix(46.5, 20, b),
           mix(7, 2.6, b), VIOLET, stem);

    // The two original B bowls shrink and travel into the face buttons.
    const spots = [
      { from: [43.5, 23.5], to: [43.6, 26.5], color: WHITE },
      { from: [43.5, 39.4], to: [50, 35.2], color: '#c9c0ff' }
    ];
    for (const [index, spot] of spots.entries()) {
      const x = mix(spot.from[0], spot.to[0], b);
      const y = mix(spot.from[1], spot.to[1], b);
      const rx = mix(8.6, 3.55, b);
      const ry = mix(9.4, 3.55, b);
      // At the start they are the two solid purple lobes of the letter B;
      // by the end they become crisp, high-contrast face buttons.
      ellipse(x, y, rx, ry, VIOLET);
      const highlight = range(0.58, 0.97, t);
      ellipse(x, y, rx * 0.78, ry * 0.78, spot.color, highlight);
      const hole = 1 - range(0.1, 0.66, t);
      ellipse(mix(43.8, x, b), mix(spot.from[1], y, b),
              mix(2.8, 0, b), mix(3.2, 0, b), DARK, hole);
      if (index === 0 && t > 0.86) {
        ellipse(x, y, 1.1, 1.1, VIOLET, range(0.86, 1, t));
      }
    }

    // Tiny shoulder highlight, invisible until the controller is formed.
    const highlight = range(0.73, 1, t);
    stroke(29, 18.8, 35, 18.8, 2.15, '#c4b8ff', highlight);

    const serial = Math.round(t * 10000);
    if (serial === lastCommitted) return;
    lastCommitted = serial;
    icon.href = canvas.toDataURL('image/png');
  }

  function clear() {
    cycle++;
    if (timer !== null) clearTimeout(timer);
    if (raf !== null) cancelAnimationFrame(raf);
    timer = raf = null;
  }

  function enabled() {
    return !document.hidden && !motion?.matches;
  }

  function hold(pose, current) {
    if (current !== cycle || !enabled()) return;
    if (pose === 0) icon.href = fallback;
    timer = setTimeout(() => transition(pose, 1 - pose, current),
      pose === 0 ? HOLD_FB : HOLD_PAD);
  }

  function transition(from, to, current) {
    if (current !== cycle || !enabled()) return;
    let start = null;
    let lastFrame = -Infinity;

    function tick(now) {
      if (current !== cycle || !enabled()) return;
      if (start === null) start = now;
      const progress = clamp((now - start) / TRANSITION_MS);
      if (now - lastFrame >= FRAME_MS || progress === 1) {
        paint(mix(from, to, ease(progress)));
        lastFrame = now;
      }
      if (progress < 1) raf = requestAnimationFrame(tick);
      else { raf = null; hold(to, current); }
    }

    raf = requestAnimationFrame(tick);
  }

  function restart() {
    clear();
    lastCommitted = -1;
    icon.href = fallback;
    if (enabled()) hold(0, cycle);
  }

  motion?.addEventListener?.('change', restart);
  document.addEventListener('visibilitychange', restart);
  window.addEventListener('pagehide', clear);
  window.addEventListener('pageshow', restart);
  restart();
})();
