function initCatalogFocus() {
  const discovery = document.querySelector('#discoveryShell');
  const search = document.querySelector('#searchInput');
  const sidebarSections = [...document.querySelectorAll('.filter-sidebar details.sidebar-collapsible')];
  const dialog = document.querySelector('#gameDialog');
  const dialogContent = document.querySelector('#dialogContent');

  if (!document.querySelector('link[data-game-sheet-v4]')) {
    const sheet = document.createElement('link');
    sheet.rel = 'stylesheet';
    sheet.href = './assets/game-sheet-v4.css';
    sheet.dataset.gameSheetV4 = 'true';
    document.head.append(sheet);
  }

  if (discovery && search) {
    search.addEventListener('input', () => {
      if (search.value.trim()) discovery.open = false;
    });
  }

  for (const section of sidebarSections) {
    section.addEventListener('toggle', () => {
      if (!section.open) return;
      for (const other of sidebarSections) {
        if (other !== section) other.open = false;
      }
    });
  }

  const actionIcons = {
    favorite: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 0 0 0-7.8Z"/></svg>',
    backlog: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h14v16l-7-4-7 4V4Z"/></svg>',
    completed: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m8 12 2.6 2.6L16.5 9"/></svg>',
    share: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="m8.2 10.8 7.5-4.4M8.2 13.2l7.5 4.4"/></svg>',
  };

  function actionType(button) {
    if (button.dataset.actionType) return button.dataset.actionType;
    const label = button.textContent.trim().toLocaleLowerCase('fr');
    if (label.includes('favori')) return 'favorite';
    if (label.includes('jouer')) return 'backlog';
    if (label.includes('termin')) return 'completed';
    if (label.includes('partager') || label.includes('copi')) return 'share';
    return '';
  }

  function decorateDialogAction(button) {
    const type = actionType(button);
    if (!type || !actionIcons[type]) return;
    const raw = button.textContent.trim();
    const copied = type === 'share' && /copi/i.test(raw);
    const active = button.getAttribute('aria-pressed') === 'true' || button.classList.contains('active');
    const labels = {
      favorite: active ? 'Retirer des favoris' : 'Ajouter aux favoris',
      backlog: active ? 'Retirer de À jouer' : 'Ajouter à À jouer',
      completed: active ? 'Retirer de Terminé' : 'Marquer comme terminé',
      share: copied ? 'Lien copié' : 'Partager la fiche',
    };
    const label = labels[type];
    button.dataset.actionType = type;
    button.dataset.copied = copied ? 'true' : 'false';
    button.title = label;
    button.setAttribute('aria-label', label);
    if (button.querySelector('svg') && button.querySelector('.sr-only')?.textContent === label) return;
    button.innerHTML = `${actionIcons[type]}<span class="sr-only">${label}</span>`;
  }

  function placeAfter(anchor, node) {
    if (!anchor || !node) return;
    if (anchor.nextElementSibling !== node) anchor.after(node);
  }

  function compactDialogMedia() {
    if (!dialogContent) return;
    const layout = dialogContent.querySelector('.dialog-layout');
    const cover = layout?.querySelector('.dialog-cover');
    const coverDetails = cover?.querySelector('.cover-details');
    const actions = dialogContent.querySelector('.dialog-actions');
    const sourceLink = dialogContent.querySelector('.source-link');
    const preview = dialogContent.querySelector('.gameplay-preview');
    const previewButton = preview?.querySelector('.gameplay-preview-button');
    const gallery = dialogContent.querySelector('.dialog-media');
    const grid = gallery?.querySelector('.media-grid');

    if (cover && actions) {
      actions.querySelectorAll('.dialog-action').forEach(decorateDialogAction);
      if (coverDetails) placeAfter(coverDetails, actions);
      else if (actions.parentElement !== cover) cover.append(actions);
    }

    if (cover && sourceLink) {
      if (actions?.parentElement === cover) placeAfter(actions, sourceLink);
      else if (coverDetails) placeAfter(coverDetails, sourceLink);
      else if (sourceLink.parentElement !== cover) cover.append(sourceLink);
    }

    if (grid && previewButton) {
      previewButton.classList.add('media-item', 'media-item-featured');
      previewButton.dataset.mediaKind = 'gif';
      if (grid.firstElementChild !== previewButton) grid.prepend(previewButton);
      if (preview?.isConnected) preview.remove();
    }

    const galleryTitle = gallery?.querySelector('.dialog-subheading h3');
    if (galleryTitle && galleryTitle.textContent !== 'Galerie') galleryTitle.textContent = 'Galerie';
    const count = gallery?.querySelector('.dialog-subheading span');
    const mediaCount = grid?.querySelectorAll('.media-item').length || 0;
    if (count && mediaCount) count.textContent = `${mediaCount} média${mediaCount > 1 ? 's' : ''}`;
  }

  if (dialogContent) {
    const observer = new MutationObserver(compactDialogMedia);
    observer.observe(dialogContent, { childList:true, subtree:true });
    document.addEventListener('fitboy:game-open', () => requestAnimationFrame(compactDialogMedia));
  }

  if (dialog) {
    dialog.addEventListener('click', event => {
      if (event.target?.classList?.contains('media-lightbox-stage')) {
        dialog.querySelector('.media-lightbox-close')?.click();
      }
    });
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initCatalogFocus, { once:true });
} else {
  initCatalogFocus();
}
