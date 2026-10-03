const STORAGE_KEY = 'fitboyrepack:language:v1';
const MODES = new Set(['auto', 'fr', 'en']);

const STRINGS = {
  fr: {
    'app.home': 'accueil',
    'app.searchSort': 'Recherche et tri du catalogue',
    'app.search': 'Rechercher',
    'app.searchPlaceholder': 'Titre, genre, année de sortie…',
    'app.sort': 'Tri',
    'sort.dateDesc': 'Ajouts récents',
    'sort.releaseDesc': 'Sorties récentes',
    'sort.releaseAsc': 'Sorties anciennes',
    'sort.relevance': 'Pertinence',
    'sort.dateAsc': 'Ajouts anciens',
    'sort.nameAsc': 'Nom A → Z',
    'sort.nameDesc': 'Nom Z → A',
    'app.filters': 'Filtres',
    'app.catalogLoading': 'Chargement…',
    'app.catalogHealth': 'État du catalogue',
    'app.games': 'jeux',
    'app.game': 'jeu',
    'app.favorites': 'Favoris',
    'app.filterCatalog': 'Filtres du catalogue',
    'app.closeFilters': 'Fermer les filtres',
    'app.filter': 'Filtrer',
    'app.clear': 'Effacer',
    'filter.releaseYear': 'Année de sortie',
    'filter.size': 'Taille',
    'filter.releasePeriod': 'Période de sortie',
    'filter.all': 'Toutes',
    'filter.thisWeek': 'Cette semaine',
    'filter.lastWeek': 'Semaine dernière',
    'filter.last7': '7 derniers jours',
    'filter.last30': '30 derniers jours',
    'filter.last90': '90 derniers jours',
    'filter.thisYear': 'Cette année',
    'filter.added': 'Ajoutés',
    'filter.days30': '30 j',
    'filter.description': 'Description',
    'filter.media': 'Médias',
    'library.title': 'Bibliothèque',
    'library.summary': 'Favoris · À jouer · Terminé',
    'library.favorite': 'Favoris',
    'library.backlog': 'À jouer',
    'library.completed': 'Terminé',
    'library.export': 'Exporter',
    'library.import': 'Importer',
    'genre.title': 'Genres',
    'genre.enriched': 'Filtres enrichis inclus',
    'genre.choose': 'Choisir les genres',
    'health.catalog': 'Catalogue',
    'health.dataState': 'État des données',
    'health.games': 'Jeux',
    'health.descriptions': 'Descriptions',
    'health.galleries': 'Galeries',
    'discover.title': 'Découvrir',
    'discover.summary': 'Nouveautés · Mises à jour · À jouer · Pour toi',
    'discover.new': 'Nouveautés',
    'discover.updated': 'Mis à jour',
    'discover.backlog': 'À jouer',
    'discover.forYou': 'Pour toi',
    'catalog.title': 'Catalogue',
    'empty.title': 'Aucun résultat',
    'empty.body': 'Essaie un autre titre ou retire un filtre.',
    'genre.dialogTitle': 'Genres et catégories',
    'genre.dialogHelp': 'Recherche dans les tags du catalogue et les genres enrichis',
    'app.close': 'Fermer',
    'genre.search': 'Rechercher un genre',
    'genre.searchPlaceholder': 'Chercher un genre…',
    'genre.clearAll': 'Tout effacer',
    'genre.currentResult': 'Résultat courant',
    'genre.list': 'Liste des genres',
    'card.addFavorite': 'Ajouter aux favoris',
    'card.removeFavorite': 'Retirer des favoris',
    'card.new': 'Nouveau',
    'footer.local': 'Catalogue statique · bibliothèque locale',
    'detail.published': 'Publié',
    'detail.releaseDate': 'Sortie du jeu',
    'detail.repackSize': 'Taille repack',
    'detail.loadingAria': 'Chargement de la fiche',
    'detail.loading': 'Chargement de la fiche détaillée…',
    'detail.enriching': 'Fiche détaillée en cours d’enrichissement.',
    'detail.favorite': 'Favori',
    'detail.backlog': 'À jouer',
    'detail.completed': 'Terminé',
    'detail.share': 'Partager',
    'detail.shareCopied': 'Lien copié ✓',
    'detail.copyPrompt': 'Copier ce lien :',
    'detail.source': 'Voir la page source ↗',
    'detail.developer': 'Développeur',
    'detail.publisher': 'Éditeur',
    'detail.platforms': 'Plateformes',
    'detail.verified': 'Données vérifiées',
    'detail.description': 'Description',
    'detail.gameFeatures': 'Fonctionnalités',
    'detail.repackFeatures': 'Fonctionnalités du repack',
    'detail.gallery': 'Galerie',
    'detail.imagesGifs': 'Images & GIFs',
    'detail.gameplay': 'Gameplay',
    'detail.noDetails': 'Aucun détail enrichi disponible pour cette fiche pour le moment.',
    'detail.missing': 'Fiche détaillée indisponible pour cette entrée.',
    'detail.error': 'La fiche détaillée est momentanément indisponible.',
    'detail.closeImage': 'Fermer l’image',
    'detail.prevImage': 'Image précédente',
    'detail.nextImage': 'Image suivante',
    'detail.gameMedia': 'Média du jeu',
    'detail.gameCapture': 'Capture du jeu',
    'filter.searchPrefix': 'Recherche : {value}',
    'filter.genreCount.one': '{count} genre',
    'filter.genreCount.other': '{count} genres',
    'filter.releasePrefix': 'Sortie {value}',
    'filter.sizePrefix': 'Taille {value}',
    'filter.addedRecently': 'Ajoutés récemment',
    'recommendation.profile': 'Profil local basé sur {count} choix, tags rares, fraîcheur et proximité des titres.',
    'library.invalidFile': 'Fichier de bibliothèque invalide.',
    'health.remaining': '{count} fiches restent à enrichir{sync}.',
    'health.sync': ' • synchro {value}',
    'catalog.updated': 'Mis à jour {value}',
    'catalog.unavailable': 'Catalogue indisponible',
    'catalog.loadFailed': 'Impossible de charger le catalogue',
    'action.favorite.add': 'Ajouter aux favoris',
    'action.favorite.remove': 'Retirer des favoris',
    'action.backlog.add': 'Ajouter à À jouer',
    'action.backlog.remove': 'Retirer de À jouer',
    'action.completed.add': 'Marquer comme terminé',
    'action.completed.remove': 'Retirer de Terminé',
    'action.share': 'Partager la fiche',
    'action.copied': 'Lien copié',
    'media.count.one': '{count} média',
    'media.count.other': '{count} médias',
    'language.label': 'Langue',
  },
  en: {
    'app.home': 'home',
    'app.searchSort': 'Catalog search and sorting',
    'app.search': 'Search',
    'app.searchPlaceholder': 'Title, genre, release year…',
    'app.sort': 'Sort',
    'sort.dateDesc': 'Recently added',
    'sort.releaseDesc': 'Recent releases',
    'sort.releaseAsc': 'Oldest releases',
    'sort.relevance': 'Relevance',
    'sort.dateAsc': 'Oldest additions',
    'sort.nameAsc': 'Name A → Z',
    'sort.nameDesc': 'Name Z → A',
    'app.filters': 'Filters',
    'app.catalogLoading': 'Loading…',
    'app.catalogHealth': 'Catalog status',
    'app.games': 'games',
    'app.game': 'game',
    'app.favorites': 'Favorites',
    'app.filterCatalog': 'Catalog filters',
    'app.closeFilters': 'Close filters',
    'app.filter': 'Filter',
    'app.clear': 'Clear',
    'filter.releaseYear': 'Release year',
    'filter.size': 'Size',
    'filter.releasePeriod': 'Release period',
    'filter.all': 'All',
    'filter.thisWeek': 'This week',
    'filter.lastWeek': 'Last week',
    'filter.last7': 'Last 7 days',
    'filter.last30': 'Last 30 days',
    'filter.last90': 'Last 90 days',
    'filter.thisYear': 'This year',
    'filter.added': 'Added',
    'filter.days30': '30 d',
    'filter.description': 'Description',
    'filter.media': 'Media',
    'library.title': 'Library',
    'library.summary': 'Favorites · Play later · Completed',
    'library.favorite': 'Favorites',
    'library.backlog': 'Play later',
    'library.completed': 'Completed',
    'library.export': 'Export',
    'library.import': 'Import',
    'genre.title': 'Genres',
    'genre.enriched': 'Includes enriched filters',
    'genre.choose': 'Choose genres',
    'health.catalog': 'Catalog',
    'health.dataState': 'Data status',
    'health.games': 'Games',
    'health.descriptions': 'Descriptions',
    'health.galleries': 'Galleries',
    'discover.title': 'Discover',
    'discover.summary': 'New · Updated · Play later · For you',
    'discover.new': 'New',
    'discover.updated': 'Updated',
    'discover.backlog': 'Play later',
    'discover.forYou': 'For you',
    'catalog.title': 'Catalog',
    'empty.title': 'No results',
    'empty.body': 'Try another title or remove a filter.',
    'genre.dialogTitle': 'Genres and categories',
    'genre.dialogHelp': 'Search catalog tags and enriched genres',
    'app.close': 'Close',
    'genre.search': 'Search a genre',
    'genre.searchPlaceholder': 'Search genres…',
    'genre.clearAll': 'Clear all',
    'genre.currentResult': 'Current result',
    'genre.list': 'Genre list',
    'card.addFavorite': 'Add to favorites',
    'card.removeFavorite': 'Remove from favorites',
    'card.new': 'New',
    'footer.local': 'Static catalog · local library',
    'detail.published': 'Published',
    'detail.releaseDate': 'Game release',
    'detail.repackSize': 'Repack size',
    'detail.loadingAria': 'Loading game details',
    'detail.loading': 'Loading game details…',
    'detail.enriching': 'Detailed game data is still being enriched.',
    'detail.favorite': 'Favorite',
    'detail.backlog': 'Play later',
    'detail.completed': 'Completed',
    'detail.share': 'Share',
    'detail.shareCopied': 'Link copied ✓',
    'detail.copyPrompt': 'Copy this link:',
    'detail.source': 'View source page ↗',
    'detail.developer': 'Developer',
    'detail.publisher': 'Publisher',
    'detail.platforms': 'Platforms',
    'detail.verified': 'Verified data',
    'detail.description': 'Description',
    'detail.gameFeatures': 'Game features',
    'detail.repackFeatures': 'Repack features',
    'detail.gallery': 'Gallery',
    'detail.imagesGifs': 'Images & GIFs',
    'detail.gameplay': 'Gameplay',
    'detail.noDetails': 'No enriched details are available for this game yet.',
    'detail.missing': 'Detailed game data is unavailable for this entry.',
    'detail.error': 'Detailed game data is temporarily unavailable.',
    'detail.closeImage': 'Close image',
    'detail.prevImage': 'Previous image',
    'detail.nextImage': 'Next image',
    'detail.gameMedia': 'Game media',
    'detail.gameCapture': 'Game screenshot',
    'filter.searchPrefix': 'Search: {value}',
    'filter.genreCount.one': '{count} genre',
    'filter.genreCount.other': '{count} genres',
    'filter.releasePrefix': 'Release {value}',
    'filter.sizePrefix': 'Size {value}',
    'filter.addedRecently': 'Recently added',
    'recommendation.profile': 'Local profile based on {count} choices, rare tags, freshness and title similarity.',
    'library.invalidFile': 'Invalid library file.',
    'health.remaining': '{count} entries still need enrichment{sync}.',
    'health.sync': ' • synced {value}',
    'catalog.updated': 'Updated {value}',
    'catalog.unavailable': 'Catalog unavailable',
    'catalog.loadFailed': 'Unable to load the catalog',
    'action.favorite.add': 'Add to favorites',
    'action.favorite.remove': 'Remove from favorites',
    'action.backlog.add': 'Add to Play later',
    'action.backlog.remove': 'Remove from Play later',
    'action.completed.add': 'Mark as completed',
    'action.completed.remove': 'Remove from Completed',
    'action.share': 'Share game',
    'action.copied': 'Link copied',
    'media.count.one': '{count} media item',
    'media.count.other': '{count} media items',
    'language.label': 'Language',
  },
};

let initialized = false;
let mode = 'auto';
let language = 'en';

function normalizeMode(value) {
  const candidate = String(value || '').toLowerCase();
  return MODES.has(candidate) ? candidate : 'auto';
}

function browserLanguage() {
  const values = [
    ...(Array.isArray(navigator.languages) ? navigator.languages : []),
    navigator.language,
  ].filter(Boolean);
  const first = values.map(value => String(value).toLowerCase()).find(value => value.startsWith('fr') || value.startsWith('en'));
  return first?.startsWith('fr') ? 'fr' : 'en';
}

function resolveLanguage(nextMode) {
  if (nextMode === 'fr' || nextMode === 'en') return nextMode;
  return browserLanguage();
}

function interpolate(template, vars) {
  return String(template).replace(/\{([a-zA-Z0-9_]+)\}/g, (_match, key) => (
    Object.prototype.hasOwnProperty.call(vars, key) ? String(vars[key]) : ''
  ));
}

export function t(key, vars = {}) {
  const table = STRINGS[language] || STRINGS.en;
  const fallback = STRINGS.en[key] || STRINGS.fr[key] || key;
  return interpolate(table[key] || fallback, vars);
}

export function currentLanguage() {
  return language;
}

export function languageMode() {
  return mode;
}

export function locale() {
  return language === 'fr' ? 'fr-FR' : 'en-US';
}

export function formatDateValue(value, options = { day:'2-digit', month:'short', year:'numeric' }) {
  const time = Date.parse(value || '');
  if (!Number.isFinite(time)) return '';
  return new Intl.DateTimeFormat(locale(), options).format(new Date(time));
}

export function formatNumber(value) {
  return Number(value || 0).toLocaleString(locale());
}

export function gameCountLabel(count) {
  return `${formatNumber(count)} ${count === 1 ? t('app.game') : t('app.games')}`;
}

export function mediaCountLabel(count) {
  const key = count === 1 ? 'media.count.one' : 'media.count.other';
  return t(key, { count: formatNumber(count) });
}

export function applyTranslations(root = document) {
  root.querySelectorAll?.('[data-i18n]').forEach(node => {
    const key = node.dataset.i18n;
    if (key) node.textContent = t(key);
  });
  root.querySelectorAll?.('[data-i18n-placeholder]').forEach(node => {
    const key = node.dataset.i18nPlaceholder;
    if (key) node.setAttribute('placeholder', t(key));
  });
  root.querySelectorAll?.('[data-i18n-aria-label]').forEach(node => {
    const key = node.dataset.i18nAriaLabel;
    if (key) node.setAttribute('aria-label', t(key));
  });
  root.querySelectorAll?.('[data-i18n-title]').forEach(node => {
    const key = node.dataset.i18nTitle;
    if (key) node.setAttribute('title', t(key));
  });
  root.querySelectorAll?.('[data-i18n-date]').forEach(node => {
    const value = node.dataset.i18nDate;
    if (value) node.textContent = formatDateValue(value);
  });
}

function refreshSwitcher() {
  const switcher = document.querySelector('#languageSwitcher');
  if (!switcher) return;
  switcher.setAttribute('aria-label', t('language.label'));
  switcher.querySelectorAll('[data-language-mode]').forEach(button => {
    const active = button.dataset.languageMode === mode;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
}

function commitState(nextMode, { persist = true, emit = true } = {}) {
  const previousLanguage = language;
  const previousMode = mode;
  mode = normalizeMode(nextMode);
  language = resolveLanguage(mode);

  if (persist) {
    try { localStorage.setItem(STORAGE_KEY, mode); } catch { /* storage unavailable */ }
  }

  document.documentElement.lang = language;
  document.documentElement.dataset.languageMode = mode;
  document.documentElement.dataset.language = language;
  applyTranslations(document);
  refreshSwitcher();
  document.documentElement.classList.remove('i18n-pending');

  if (emit && (previousLanguage !== language || previousMode !== mode)) {
    document.dispatchEvent(new CustomEvent('fitboy:language-change', {
      detail: { mode, language },
    }));
  }
}

export function setLanguageMode(nextMode) {
  commitState(nextMode, { persist:true, emit:true });
}

export function initI18n() {
  if (initialized) {
    applyTranslations(document);
    refreshSwitcher();
    document.documentElement.classList.remove('i18n-pending');
    return { mode, language };
  }
  initialized = true;

  let initialMode = document.documentElement.dataset.languageMode || 'auto';
  try {
    initialMode = localStorage.getItem(STORAGE_KEY) || initialMode;
  } catch { /* storage unavailable */ }

  commitState(initialMode, { persist:false, emit:false });

  document.querySelector('#languageSwitcher')?.addEventListener('click', event => {
    const button = event.target.closest('[data-language-mode]');
    if (!button) return;
    setLanguageMode(button.dataset.languageMode);
  });

  return { mode, language };
}
