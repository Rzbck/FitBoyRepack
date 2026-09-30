(() => {
  const BLOCKED_HOSTS = new Set(['torrent-stats.info']);
  const BAD_HINTS = ['logo', 'avatar', 'counter', 'rating', 'button', 'icon', 'badge', 'banner', 'donat'];

  function shouldRemove(link) {
    try {
      const url = new URL(link.href, window.location.href);
      const text = `${url.hostname} ${url.pathname}`.toLowerCase();
      if (BLOCKED_HOSTS.has(url.hostname.toLowerCase())) return true;
      return BAD_HINTS.some(hint => text.includes(hint));
    } catch {
      return true;
    }
  }

  function sanitize(root = document) {
    root.querySelectorAll?.('.media-item').forEach(link => {
      if (shouldRemove(link)) link.remove();
    });

    root.querySelectorAll?.('.dialog-media').forEach(section => {
      const items = section.querySelectorAll('.media-item');
      const count = section.querySelector('.dialog-subheading span');
      if (!items.length) {
        section.remove();
      } else if (count) {
        count.textContent = `${items.length} média${items.length > 1 ? 's' : ''}`;
      }
    });
  }

  const observer = new MutationObserver(records => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node.nodeType === Node.ELEMENT_NODE) sanitize(node);
      }
    }
  });

  const target = document.getElementById('dialogContent') || document.body;
  observer.observe(target, { childList: true, subtree: true });
  sanitize(document);
})();
