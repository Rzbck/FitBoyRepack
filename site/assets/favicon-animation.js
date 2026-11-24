/* FitBoyRepack — centered FB ⇄ gamepad favicon.
 * Cached vector-canvas morphing (30 fps during transitions, no work during holds).
 * Falls back to favicon.svg for reduced motion, background tabs, or no canvas.
 */
(() => {
  'use strict';
  const icon = document.querySelector('link[rel="icon"]');
  if (!icon) return;

  const fallback = new URL('./favicon.svg?v=5', document.baseURI).href;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 128;
  const ctx = canvas.getContext('2d', { alpha: true, willReadFrequently: false });
  if (!ctx || typeof Path2D === 'undefined') return;

  const ACCENT = '#7c6cff';
  const WHITE = '#f7f8fc';
  const B_DARK = '#272445';
  const f = new Path2D('M14 18H30V25H21V31H29V38H21V46H14Z');
  const b = new Path2D('M33 18H43C49 18 52 21 52 25C52 28 50 31 47 32C51 33 53 36 53 39C53 44 49 46 43 46H33V18ZM40 24V29H43C45 29 46 28 46 26.5C46 25 45 24 43 24H40ZM40 35V40H43C45 40 46.5 39 46.5 37.5C46.5 36 45 35 43 35H40Z');
  const pad = new Path2D('M18 18C12 18 10 24 8 31L6 39C5 44 9 46 13 44L22 38H42L51 44C55 46 59 44 58 39L56 31C54 24 52 18 46 18H18Z');

  const motion = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  const FB_HOLD = 2600;
  const GAMEPAD_HOLD = 2400;
  const TRANSITION = 1400;
  const FRAME_INTERVAL = 1000 / 30;
  const FRAME_COUNT = Math.round(TRANSITION / FRAME_INTERVAL);
  const frames = new Map();
  let shownFrame = -1;
  let timer = 0;
  let animation = 0;
  let generation = 0;

  const clamp = (v) => Math.max(0, Math.min(1, v));
  const smooth = (a, b, v) => {
    const x = clamp((v - a) / (b - a));
    return x * x * (3 - 2 * x);
  };

  function circle(x, y, radius, color) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, 2 * Math.PI);
    ctx.fill();
  }

  function encodeFrame(mix) {
    ctx.setTransform(2, 0, 0, 2, 0, 0);
    ctx.clearRect(0, 0, 64, 64);

    // Invariant, centered backdrop: no jumping around the 16px tab slot.
    ctx.beginPath();
    ctx.roundRect(0.5, 0.5, 63, 63, 12.5);
    ctx.fillStyle = '#101726';
    ctx.fill();
    ctx.lineWidth = 1;
    ctx.strokeStyle = '#34405e';
    ctx.stroke();

    // Violet edge gently lights up *during* the transformation only.
    const bridge = Math.pow(Math.sin(Math.PI * mix), 2);
    if (bridge > 0.01) {
      ctx.save();
      ctx.globalAlpha = bridge * 0.5;
      ctx.beginPath();
      ctx.roundRect(1.8, 1.8, 60.4, 60.4, 11.5);
      ctx.strokeStyle = ACCENT;
      ctx.lineWidth = 2.2;
      ctx.stroke();
      ctx.restore();
    }

    // The F contracts toward the D-pad while the B becomes the action buttons.
    const logoOpacity = 1 - smooth(0.08, 0.8, mix);
    if (logoOpacity > 0) {
      ctx.save();
      ctx.globalAlpha = logoOpacity;
      ctx.translate(32, 32);
      const shrink = 1 - 0.22 * smooth(0.1, 0.88, mix);
      ctx.scale(1.2 * shrink, 1.27 * shrink);
      ctx.translate(-33, -32);
      ctx.fillStyle = WHITE;
      ctx.fill(f);
      ctx.fillStyle = ACCENT;
      ctx.fill(b, 'evenodd');
      ctx.restore();
    }

    const reveal = smooth(0.16, 0.94, mix);
    if (reveal > 0) {
      ctx.save();
      ctx.translate(32, 32);
      const spring = 0.035 * Math.sin(Math.PI * reveal);
      const scale = 0.76 + 0.24 * reveal + spring;
      ctx.scale(1.06 * scale, 1.2 * scale);
      ctx.rotate((1 - reveal) * -0.09);
      ctx.translate(-32, -32);

      // Draw the outline smoothly rather than swapping to a second image.
      ctx.globalAlpha = reveal;
      ctx.fillStyle = B_DARK;
      ctx.fill(pad);
      ctx.save();
      ctx.strokeStyle = WHITE;
      ctx.lineWidth = 3.4;
      ctx.lineJoin = 'round';
      ctx.stroke(pad);
      ctx.restore();

      const buttons = smooth(0.37, 0.9, mix);
      ctx.globalAlpha = reveal * buttons;
      ctx.strokeStyle = WHITE;
      ctx.lineWidth = 4.5;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(20, 25);
      ctx.lineTo(20, 36);
      ctx.moveTo(14.5, 30.5);
      ctx.lineTo(25.5, 30.5);
      ctx.stroke();
      circle(42.5, 26.5, 3.3, ACCENT);
      circle(49, 33.3, 3.3, '#bfb6ff');
      ctx.lineWidth = 2.1;
      ctx.strokeStyle = '#a399ff';
      ctx.beginPath();
      ctx.moveTo(29, 22.5);
      ctx.lineTo(35, 22.5);
      ctx.stroke();
      ctx.restore();
    }

    // PNG data URIs force Chromium/Brave to repaint favicons per frame.
    return canvas.toDataURL('image/png');
  }

  function paintFrame(index) {
    if(index===shownFrame)return;
    let src=frames.get(index);
    if(!src){
      src=encodeFrame(smooth(0,1,index/FRAME_COUNT));
      frames.set(index,src);
    }
    icon.href=src;
    shownFrame=index;
  }

  function stop() {
    generation++;
    if (timer) clearTimeout(timer);
    if (animation) cancelAnimationFrame(animation);
    timer = animation = 0;
  }

  function canAnimate() {
    return !document.hidden && !motion?.matches;
  }

  function hold(pose, cycle) {
    if (cycle !== generation || !canAnimate()) return;
    if (pose === 0) {icon.href = fallback;shownFrame=-1;}
    timer = setTimeout(() => transition(pose, 1 - pose, cycle),
      pose === 0 ? FB_HOLD : GAMEPAD_HOLD);
  }

  function transition(from, to, cycle) {
    if (cycle !== generation || !canAnimate()) return;
    let startedAt = null;
    let lastPaint = -Infinity;
    function frame(now) {
      if (cycle !== generation || !canAnimate()) return;
      if (startedAt === null) startedAt = now;
      const progress = clamp((now - startedAt) / TRANSITION);
      const index = Math.round((from + (to - from) * progress) * FRAME_COUNT);
      if (now - lastPaint >= FRAME_INTERVAL || progress >= 1) {
        paintFrame(index);
        lastPaint = now;
      }
      if (progress < 1) animation = requestAnimationFrame(frame);
      else {
        animation = 0;
        hold(to, cycle);
      }
    }
    animation = requestAnimationFrame(frame);
  }

  function restart() {
    stop();
    icon.href = fallback;
    shownFrame=-1;
    if (canAnimate()) hold(0, generation);
  }

  motion?.addEventListener?.('change', restart);
  document.addEventListener('visibilitychange', restart);
  window.addEventListener('pagehide', stop);
  window.addEventListener('pageshow', restart);
  restart();
})();
