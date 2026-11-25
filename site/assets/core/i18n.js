import { STORAGE_KEYS, readText, writeText } from './storage.js';
const STORAGE_KEY = STORAGE_KEYS.language;
const MODES = new Set(['auto', 'fr', 'en']);

const STRINGS = {
  fr: {
    'app.home': 'FitBoyRepack — accueil',
    'app.metaDescription': 'FitBoyRepack — catalogue léger, filtrable et actualisé automatiquement.',
    'app.searchSort': 'Recherche et tri du catalogue',
    'app.search': 'Rechercher',
    'app.searchPlaceholder': 'Titre, genre, développeur, éditeur…',
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
    'filter.sizeLt1': '< 1 Go',
    'filter.size1to10': '1–10 Go',
    'filter.size10to50': '10–50 Go',
    'filter.size50plus': '50+ Go',
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
    'library.summary': 'Favoris · À jouer · Terminé · Wishlist',
    'library.favorite': 'Favoris',
    'library.backlog': 'À jouer',
    'library.completed': 'Terminé',
    'library.export': 'Exporter',
    'library.import': 'Importer',
    'wishlist.title': 'Wishlist',
    'wishlist.eyebrow': 'MA BIBLIOTHÈQUE',
    'wishlist.intro': 'Les jeux que tu attends. Leur disponibilité est vérifiée dans notre catalogue.',
    'wishlist.placeholder': 'Nom du jeu attendu…',
    'wishlist.inputLabel': 'Nom du jeu attendu',
    'wishlist.add': '+ Ajouter',
    'wishlist.addThis': '☆ Ajouter ce jeu à ma wishlist',
    'wishlist.local': 'Sur cet appareil',
    'wishlist.footer': 'Vérification au chargement du catalogue · Sans notifications',
    'wishlist.checking': 'Vérification du catalogue…',
    'wishlist.available': 'Disponible',
    'wishlist.pending': 'En attente',
    'wishlist.summary': '{pending} en attente · {available} disponible(s)',
    'wishlist.matchedTo': 'Trouvé sous le nom : {title}',
    'wishlist.view': 'Voir la fiche',
    'wishlist.openNamed': 'Ouvrir la fiche de {title}',
    'wishlist.remove': 'Supprimer de la wishlist',
    'wishlist.removeNamed': 'Supprimer {title} de la wishlist',
    'wishlist.invalid': 'Entre un titre de jeu valide.',
    'wishlist.duplicate': 'Ce jeu figure déjà dans ta wishlist.',
    'wishlist.maxItems': 'La wishlist est limitée à 1 000 jeux.',
    'wishlist.added': 'Jeu ajouté à la wishlist.',
    'wishlist.storageError': 'Enregistrement local indisponible.',
    'wishlist.empty': 'Aucun jeu suivi pour l’instant. Ajoute un titre ci-dessus.',
    'wishlist.list': 'Jeux attendus',
    'genre.title': 'Genres',
    'genre.enriched': 'Filtres enrichis inclus',
    'genre.choose': 'Choisir les genres',
    'health.catalog': 'Catalogue',
    'health.dataState': 'État des données',
    'health.games': 'Jeux',
    'health.descriptions': 'Descriptions',
    'health.galleries': 'Galeries',
    'library.suggestions': 'Tu pourrais aimer',
    'library.myFavorites': 'Mes favoris',
    'library.recommendationHint': 'D’après tes jeux enregistrés',
    'library.emptyFavoritesTitle': 'Aucun favori',
    'library.emptyFavoritesBody': 'Ajoute des jeux avec le cœur pour les retrouver ici.',
    'sort.steamBest': 'Steam · Mieux notés',
    'sort.steamPopular': 'Steam · Plus populaires',
    'sort.steamHidden': 'Steam · Pépites méconnues',
    'rating.card': 'Steam {percent}% · {reviews} avis',
    'rating.votes': '{count} avis',
    'rating.positivePercent': '{percent}% positifs',
    'rating.negativePercent': '{percent}% négatifs',
    'rating.barLabel': '{positive}% positifs, {negative}% négatifs',
    'rating.coverage': 'Avis Steam disponibles : {rated} / {total} jeux',
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
    'genre.matchingResults.one': '{count} genre trouvé · {games}',
    'genre.matchingResults.other': '{count} genres trouvés · {games}',
    'genre.list': 'Liste des genres',
    'card.addFavorite': 'Ajouter aux favoris',
    'card.removeFavorite': 'Retirer des favoris',
    'card.new': 'Nouveau',
    'card.releaseUnknown': 'Sortie inconnue',
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
    'detail.officialSteam': 'Description officielle sur Steam ↗',
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
    'detail.mediaFallback': 'Image de secours · résolution réduite',
    'detail.mediaUnavailable': 'Image indisponible chez l’hébergeur',
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
    'catalog.updatedCompact': 'MàJ {value}',
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
    'app.home': 'FitBoyRepack — home',
    'app.metaDescription': 'FitBoyRepack — a lightweight, filterable catalog updated automatically.',
    'app.searchSort': 'Catalog search and sorting',
    'app.search': 'Search',
    'app.searchPlaceholder': 'Title, genre, developer, publisher…',
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
    'filter.sizeLt1': '< 1 GB',
    'filter.size1to10': '1–10 GB',
    'filter.size10to50': '10–50 GB',
    'filter.size50plus': '50+ GB',
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
    'library.summary': 'Favorites · Play later · Completed · Wishlist',
    'library.favorite': 'Favorites',
    'library.backlog': 'Play later',
    'library.completed': 'Completed',
    'library.export': 'Export',
    'library.import': 'Import',
    'wishlist.title': 'Wishlist',
    'wishlist.eyebrow': 'MY LIBRARY',
    'wishlist.intro': 'Track games you are waiting for. Availability is checked against this catalog.',
    'wishlist.placeholder': 'Game title you are waiting for…',
    'wishlist.inputLabel': 'Expected game title',
    'wishlist.add': '+ Add',
    'wishlist.addThis': '☆ Add this game to wishlist',
    'wishlist.local': 'Saved on this device',
    'wishlist.footer': 'Checked whenever the catalog loads · No notifications',
    'wishlist.checking': 'Checking the catalog…',
    'wishlist.available': 'Available',
    'wishlist.pending': 'Waiting',
    'wishlist.summary': '{pending} waiting · {available} available',
    'wishlist.matchedTo': 'Listed as: {title}',
    'wishlist.view': 'Open game',
    'wishlist.openNamed': 'Open {title}',
    'wishlist.remove': 'Remove from wishlist',
    'wishlist.removeNamed': 'Remove {title} from wishlist',
    'wishlist.invalid': 'Enter a valid game title.',
    'wishlist.duplicate': 'This game is already on your wishlist.',
    'wishlist.maxItems': 'The wishlist supports up to 1,000 games.',
    'wishlist.added': 'Game added to wishlist.',
    'wishlist.storageError': 'Local saving is unavailable.',
    'wishlist.empty': 'No games tracked yet. Add a title above.',
    'wishlist.list': 'Wanted games',
    'genre.title': 'Genres',
    'genre.enriched': 'Includes enriched filters',
    'genre.choose': 'Choose genres',
    'health.catalog': 'Catalog',
    'health.dataState': 'Data status',
    'health.games': 'Games',
    'health.descriptions': 'Descriptions',
    'health.galleries': 'Galleries',
    'library.suggestions': 'You might like',
    'library.myFavorites': 'My favorites',
    'library.recommendationHint': 'Based on your saved games',
    'library.emptyFavoritesTitle': 'No favorites yet',
    'library.emptyFavoritesBody': 'Use the heart icon to save games here.',
    'sort.steamBest': 'Steam · Best reviewed',
    'sort.steamPopular': 'Steam · Most popular',
    'sort.steamHidden': 'Steam · Hidden gems',
    'rating.card': 'Steam {percent}% · {reviews} reviews',
    'rating.votes': '{count} reviews',
    'rating.positivePercent': '{percent}% positive',
    'rating.negativePercent': '{percent}% negative',
    'rating.barLabel': '{positive}% positive, {negative}% negative',
    'rating.coverage': 'Steam reviews available: {rated} / {total} games',
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
    'genre.matchingResults.one': '{count} genre found · {games}',
    'genre.matchingResults.other': '{count} genres found · {games}',
    'genre.list': 'Genre list',
    'card.addFavorite': 'Add to favorites',
    'card.removeFavorite': 'Remove from favorites',
    'card.new': 'New',
    'card.releaseUnknown': 'Release unknown',
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
    'detail.officialSteam': 'Official description on Steam ↗',
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
    'detail.mediaFallback': 'Fallback image · reduced resolution',
    'detail.mediaUnavailable': 'Image unavailable from host',
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
    'catalog.updatedCompact': 'Upd. {value}',
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
  const raw=String(value||'');
  if (/^\d{4}$/.test(raw)) return raw;
  if (/^\d{4}-\d{2}$/.test(raw)) {
    const time=Date.parse(raw+'-01T00:00:00Z');
    return Number.isFinite(time) ? new Intl.DateTimeFormat(locale(),{month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(time)) : '';
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    const time=Date.parse(raw+'T00:00:00Z');
    return Number.isFinite(time) ? new Intl.DateTimeFormat(locale(),{...options,timeZone:'UTC'}).format(new Date(time)) : '';
  }
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
  root.querySelectorAll?.('[data-i18n-content]').forEach(node => {
    const key = node.dataset.i18nContent;
    if (key) node.setAttribute('content', t(key));
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
    writeText(STORAGE_KEY,mode);
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
    initialMode = readText(STORAGE_KEY,initialMode);
  } catch { /* storage unavailable */ }

  commitState(initialMode, { persist:false, emit:false });

  window.addEventListener('storage',event=>{
    if(event.key===STORAGE_KEY||event.key===null)commitState(readText(STORAGE_KEY,'auto'),{persist:false,emit:true});
  });
  document.querySelector('#languageSwitcher')?.addEventListener('click', event => {
    const button = event.target.closest('[data-language-mode]');
    if (!button) return;
    setLanguageMode(button.dataset.languageMode);
  });

  return { mode, language };
}
