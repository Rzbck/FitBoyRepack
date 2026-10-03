function cleanScalar(value) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text || /^Q\d+$/i.test(text)) return '';
  return text;
}

export function normalizeIdentity(value = '') {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('fr')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function titleParts(title = '') {
  const source = cleanScalar(title);
  const parts = source.split(/\s+[–—]\s+/, 2);
  return {
    name: parts[0]?.trim() || source,
    version: parts[1]?.trim() || '',
  };
}

function verifiedMetadata(game) {
  const value = game?.verified_metadata;
  return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
}

export function canonicalTitle(game) {
  return cleanScalar(
    game?.canonical_title
    || verifiedMetadata(game)?.canonical_title
  );
}

export function displayTitle(game) {
  const canonical = canonicalTitle(game);
  if (canonical) return canonical;
  return titleParts(game?.title).name || cleanScalar(game?.title);
}

export function editionTitle(game) {
  const source = cleanScalar(game?.title);
  const canonical = canonicalTitle(game);

  if (!source) return '';
  if (!canonical) return titleParts(source).version;
  if (source.localeCompare(canonical, undefined, { sensitivity:'accent' }) === 0) return '';

  const sourceLower = source.toLocaleLowerCase('fr');
  const canonicalLower = canonical.toLocaleLowerCase('fr');

  if (sourceLower.startsWith(canonicalLower)) {
    return source.slice(canonical.length).replace(/^[\s:–—-]+/, '').trim();
  }

  return source;
}

export function cleanGenreLabel(value) {
  const raw = cleanScalar(value);
  if (!raw) return '';

  const cleaned = raw
    .replace(/\s+video game$/i, '')
    .replace(/\s+computer game$/i, '')
    .replace(/\s+game$/i, '')
    .trim();

  if (!cleaned) return '';

  const aliases = new Map([
    ['grand strategy wargame', 'Grand Strategy'],
    ['role-playing', 'RPG'],
    ['role-playing video', 'RPG'],
    ['real-time strategy', 'Real-Time Strategy'],
    ['turn-based strategy', 'Turn-Based Strategy'],
    ['first-person shooter', 'First-Person Shooter'],
    ['third-person shooter', 'Third-Person Shooter'],
  ]);

  const alias = aliases.get(cleaned.toLocaleLowerCase('fr'));
  if (alias) return alias;

  return cleaned.replace(
    /(^|[-\s])\p{L}/gu,
    match => match.toLocaleUpperCase('fr')
  );
}

function rawGenres(game) {
  const value = game?.genres ?? game?.genre ?? [];
  return (Array.isArray(value) ? value : String(value || '').split(','))
    .map(item => String(item || '').trim())
    .filter(Boolean);
}

export function effectiveGenreLabels(game) {
  const metadata = verifiedMetadata(game);
  const source = [
    ...(Array.isArray(metadata?.genres) ? metadata.genres : []),
    ...(Array.isArray(game?.metadata_genres) ? game.metadata_genres : []),
    ...rawGenres(game),
  ];

  const out = [];
  const seen = new Set();

  for (const value of source) {
    const label = cleanGenreLabel(value);
    const key = normalizeIdentity(label);
    if (!label || !key || seen.has(key)) continue;
    seen.add(key);
    out.push(label);
  }

  return out;
}
