/* FitBoyRepack: low-frequency favicon animation for Chromium/Brave.
   Static FB remains the fallback when JS is unavailable or motion is reduced. */
(() => {
  'use strict';
  const icon = document.querySelector('link[rel="icon"]');
  if (!icon) return;

  const frames = [
    ['./favicon.svg?v=3', 6200],           // White FB on dark: primary identity
    ['./favicon-pulse.svg?v=3', 300],     // Short violet transition
    ['./favicon-gamepad.svg?v=3', 2200],  // Minimal gaming controller
    ['./favicon-pulse.svg?v=3', 300],
  ].map(([path, duration]) => ({
    url: new URL(path, document.baseURI).href,
    duration,
  }));

  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  let frameIndex = 0;
  let timerId = null;

  // Cache each tiny static SVG once so the first switch does not flash.
  for (const frame of frames.slice(1, 3)) {
    const image = new Image();
    image.src = frame.url;
  }

  function stop() {
    if (timerId !== null) {
      clearTimeout(timerId);
      timerId = null;
    }
  }

  function showNextFrame() {
    const frame = frames[frameIndex];
    if (!icon.isConnected) return;
    if (icon.href !== frame.url) icon.href = frame.url;
    timerId = window.setTimeout(() => {
      frameIndex = (frameIndex + 1) % frames.length;
      showNextFrame();
    }, frame.duration);
  }

  function restart() {
    stop();
    frameIndex = 0;
    icon.href = frames[0].url;
    if (!reducedMotion?.matches) showNextFrame();
  }

  reducedMotion?.addEventListener?.('change', restart);
  window.addEventListener('pagehide', stop);
  window.addEventListener('pageshow', restart);
  restart();
})();
