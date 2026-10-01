function initCatalogFocus() {
  const discovery = document.querySelector('#discoveryShell');
  const search = document.querySelector('#searchInput');
  const sidebarSections = [...document.querySelectorAll('.filter-sidebar details.sidebar-collapsible')];
  const dialogContent = document.querySelector('#dialogContent');

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

  function compactDialogMedia() {
    if (!dialogContent) return;
    const layout = dialogContent.querySelector('.dialog-layout');
    const cover = layout?.querySelector('.dialog-cover');
    const preview = dialogContent.querySelector('.gameplay-preview');
    if (cover && preview && preview.parentElement !== cover) {
      cover.append(preview);
    }

    const previewTitle = preview?.querySelector('.dialog-subheading h3');
    if (previewTitle && previewTitle.textContent !== 'Gameplay') {
      previewTitle.textContent = 'Gameplay';
    }

    const galleryTitle = dialogContent.querySelector('.dialog-media .dialog-subheading h3');
    if (galleryTitle && galleryTitle.textContent !== 'Galerie') {
      galleryTitle.textContent = 'Galerie';
    }
  }

  if (dialogContent) {
    const observer = new MutationObserver(compactDialogMedia);
    observer.observe(dialogContent, { childList:true, subtree:true });
    document.addEventListener('fitboy:game-open', () => requestAnimationFrame(compactDialogMedia));
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initCatalogFocus, { once:true });
} else {
  initCatalogFocus();
}
