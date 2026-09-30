const DATA_URL = './data/games.json';
const PAGE_SIZE = 60;
const FAVORITES_KEY = 'fitboyrepacks:favorites:v1';

const els = {
  grid: document.querySelector('#gameGrid'),
  template: document.querySelector('#cardTemplate'),
  search: document.querySelector('#searchInput'),
  genre: document.querySelector('#genreFilter'),
  sort: document.querySelector('#sortControl'),
  count: document.querySelector('#visibleCount'),
  status: document.querySelector('#catalogStatus'),
  loadMore: document.querySelector('#loadMore'),
  empty: document.querySelector('#emptyState'),
  favoritesToggle: document.querySelector('#favoritesToggle'),
  activeState: document.querySelector('#activeState'),
  dialog: document.querySelector('#gameDialog'),
  dialogContent: document.querySelector('#dialogContent'),
};

const state = {
  games: [],
  filtered: [],
  visible: PAGE_SIZE,
  favoritesOnly: false,
  favorites: readFavorites(),
};

function readFavorites() {
  try {
    return new Set(JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]'));
  } catch {
    return new Set();
  }
}

function saveFavorites() {
  localStorage.setItem(FAVORITES_KEY, JSON.stringify([...state.favorites]));
}

function normalized(value = '') {
  return String(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

function gameDate(game) {
  const time = Date.parse(game.post_date || '');
  return Number.isFinite(time) ? time : 0;
}

function formatDate(value) {
  const time = Date.parse(value || '');
  if (!Number.isFinite(time)) return 'Date inconnue';
  return new Intl.DateTimeFormat('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' }).format(time);
}

function isNew(game) {
  const time = gameDate(game);
  if (!time) return false;
  return Date.now() - time < 14 * 24 * 60 * 60 * 1000;
}

function getGenres(game) {
  const genres = game.genres ?? game.genre ?? [];
  if (Array.isArray(genres)) return genres.filter(Boolean).map(String);
  return String(genres || '').split(',').map((genre) => genre.trim()).filter(Boolean);
}

function buildGenreOptions() {
  const genres = [...new Set(state.games.flatMap(getGenres))]
    .sort((a, b) => a.localeCompare(b, 'fr', { sensitivity: 'base' }));

  const fragment = document.createDocumentFragment();
  for (const genre of genres) {
    const option = document.createElement('option');
    option.value = genre;
    option.textContent = genre;
    fragment.append(option);
  }
  els.genre.append(fragment);
}

function applyFilters() {
  const query = normalized(els.search.value);
  const genre = normalized(els.genre.value);
  const sort = els.sort.value;

  state.filtered = state.games.filter((game) => {
    if (state.favoritesOnly && !state.favorites.has(game.id)) return false;
    const genres = getGenres(game);
    if (genre && !genres.some((item) => normalized(item) === genre)) return false;
    if (!query) return true;
    const haystack = normalized([game.title, game.repack_size, ...genres].join(' '));
    return haystack.includes(query);
  });

  state.filtered.sort((a, b) => {
    if (sort === 'date_asc') return gameDate(a) - gameDate(b);
    if (sort === 'name_asc') return a.title.localeCompare(b.title, 'fr', { sensitivity: 'base' });
    if (sort === 'name_desc') return b.title.localeCompare(a.title, 'fr', { sensitivity: 'base' });
    return gameDate(b) - gameDate(a);
  });

  state.visible = PAGE_SIZE;
  render();
}

function createPill(text) {
  const pill = document.createElement('span');
  pill.className = 'genre-pill';
  pill.textContent = text;
  return pill;
}

function renderCard(game) {
  const card = els.template.content.firstElementChild.cloneNode(true);
  const image = card.querySelector('.cover');
  const open = card.querySelector('.card-open');
  const favorite = card.querySelector('.favorite-btn');

  card.dataset.gameId = game.id;
  card.querySelector('.card-title').textContent = game.title || 'Sans titre';
  card.querySelector('.card-date').textContent = formatDate(game.post_date);
  card.querySelector('.card-size').textContent = game.repack_size && game.repack_size !== 'N/A' ? game.repack_size : '';

  if (game.image_url) {
    image.src = game.image_url;
    image.alt = `Illustration de ${game.title}`;
    image.addEventListener('error', () => {
      image.removeAttribute('src');
      image.style.display = 'none';
    }, { once: true });
  } else {
    image.style.display = 'none';
  }

  const badge = card.querySelector('.new-badge');
  badge.hidden = !isNew(game);

  const row = card.querySelector('.genre-row');
  for (const genre of getGenres(game).slice(0, 3)) row.append(createPill(genre));

  const active = state.favorites.has(game.id);
  favorite.classList.toggle('active', active);
  favorite.textContent = active ? '♥' : '♡';
  favorite.setAttribute('aria-label', active ? 'Retirer des favoris' : 'Ajouter aux favoris');

  favorite.addEventListener('click', (event) => {
    event.stopPropagation();
    toggleFavorite(game.id);
  });
  open.addEventListener('click', () => openDialog(game));
  return card;
}

function toggleFavorite(id) {
  if (state.favorites.has(id)) state.favorites.delete(id);
  else state.favorites.add(id);
  saveFavorites();

  if (state.favoritesOnly) applyFilters();
  else render();
}

function render() {
  const shown = state.filtered.slice(0, state.visible);
  const fragment = document.createDocumentFragment();
  for (const game of shown) fragment.append(renderCard(game));

  els.grid.replaceChildren(fragment);
  els.count.textContent = state.filtered.length.toLocaleString('fr-FR');
  els.empty.hidden = state.filtered.length !== 0;
  els.loadMore.hidden = state.visible >= state.filtered.length;

  const active = [];
  if (els.search.value.trim()) active.push(`recherche « ${els.search.value.trim()} »`);
  if (els.genre.value) active.push(els.genre.value);
  if (state.favoritesOnly) active.push('favoris');
  els.activeState.hidden = active.length === 0;
  els.activeState.textContent = active.length ? `Filtres actifs : ${active.join(' • ')}` : '';

  els.favoritesToggle.classList.toggle('active', state.favoritesOnly);
  els.favoritesToggle.setAttribute('aria-pressed', String(state.favoritesOnly));
  els.favoritesToggle.textContent = state.favoritesOnly ? '♥ Favoris' : '♡ Favoris';
}

function openDialog(game) {
  const genres = getGenres(game);
  const layout = document.createElement('div');
  layout.className = 'dialog-layout';

  const cover = document.createElement('div');
  cover.className = 'dialog-cover';
  if (game.image_url) {
    const img = document.createElement('img');
    img.src = game.image_url;
    img.alt = '';
    img.referrerPolicy = 'no-referrer';
    img.addEventListener('error', () => img.remove(), { once: true });
    cover.append(img);
  }

  const info = document.createElement('div');
  info.className = 'dialog-info';
  const title = document.createElement('h2');
  title.textContent = game.title || 'Sans titre';
  info.append(title);

  const meta = document.createElement('div');
  meta.className = 'dialog-meta';
  const date = document.createElement('span');
  date.textContent = formatDate(game.post_date);
  meta.append(date);
  if (game.repack_size && game.repack_size !== 'N/A') {
    const size = document.createElement('span');
    size.textContent = `Taille : ${game.repack_size}`;
    meta.append(size);
  }
  info.append(meta);

  if (genres.length) {
    const genreBox = document.createElement('div');
    genreBox.className = 'dialog-genres';
    genres.forEach((genre) => genreBox.append(createPill(genre)));
    info.append(genreBox);
  }

  const note = document.createElement('p');
  note.className = 'dialog-note';
  note.textContent = 'FitBoyRepacks affiche uniquement les métadonnées du catalogue. Aucun fichier, magnet ou miroir de téléchargement n’est indexé dans cette application.';
  info.append(note);

  layout.append(cover, info);
  els.dialogContent.replaceChildren(layout);
  els.dialog.showModal();
}

async function loadCatalog() {
  try {
    const response = await fetch(DATA_URL, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.games = Array.isArray(payload) ? payload : (payload.games || []);

    state.games = state.games
      .filter((game) => game && game.id && game.title)
      .map((game) => ({ ...game, id: String(game.id) }));

    const generated = Array.isArray(payload) ? null : payload.generated_at;
    els.status.textContent = generated
      ? `Mis à jour ${new Intl.DateTimeFormat('fr-FR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(generated))}`
      : `${state.games.length.toLocaleString('fr-FR')} jeux`;

    buildGenreOptions();
    applyFilters();
  } catch (error) {
    console.error(error);
    els.status.textContent = 'Catalogue indisponible';
    els.empty.hidden = false;
    els.empty.querySelector('strong').textContent = 'Impossible de charger le catalogue';
    els.empty.querySelector('span').textContent = 'Vérifie data/games.json ou relance la GitHub Action.';
  }
}

let searchTimer;
els.search.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(applyFilters, 100);
});
els.genre.addEventListener('change', applyFilters);
els.sort.addEventListener('change', applyFilters);
els.loadMore.addEventListener('click', () => {
  state.visible += PAGE_SIZE;
  render();
});
els.favoritesToggle.addEventListener('click', () => {
  state.favoritesOnly = !state.favoritesOnly;
  applyFilters();
});

els.dialog.addEventListener('click', (event) => {
  if (event.target === els.dialog || event.target.closest('[data-close-dialog]')) els.dialog.close();
});
document.addEventListener('keydown', (event) => {
  if (event.key === '/' && document.activeElement?.tagName !== 'INPUT') {
    event.preventDefault();
    els.search.focus();
  }
});

loadCatalog();
