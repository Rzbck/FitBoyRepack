function normalizeSourceText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

async function sha256(value) {
  if (!globalThis.crypto?.subtle) return '';
  const bytes = new TextEncoder().encode(value);
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
}

async function verifiedTranslation(source, candidate) {
  if (!candidate || typeof candidate !== 'object') return '';
  const text = String(candidate.text || '').trim();
  const expected = String(candidate.source_sha256 || '').toLowerCase();
  if (!text || !/^[0-9a-f]{64}$/.test(expected)) return '';

  const normalized = normalizeSourceText(source);
  if (!normalized) return '';
  const actual = await sha256(normalized);
  if (!actual || actual !== expected) return '';
  return text;
}

export async function localizeGameProse(game, translationsPayload, language) {
  if (language !== 'fr' || !translationsPayload?.games || !game?.id) return game;

  const publicEntry = translationsPayload.games[String(game.id)];
  if (!publicEntry || typeof publicEntry !== 'object') return game;

  const details = game.details && typeof game.details === 'object' ? game.details : {};
  const localizedDetails = { ...details };
  let translatedFields = 0;

  const description = String(details.description || '');
  const translatedDescription = await verifiedTranslation(description, publicEntry.description);
  if (translatedDescription) {
    localizedDetails.description = translatedDescription;
    translatedFields += 1;
  }

  if (Array.isArray(details.game_features) && publicEntry.game_features && typeof publicEntry.game_features === 'object') {
    const features = await Promise.all(details.game_features.map(async (source, index) => {
      const translated = await verifiedTranslation(source, publicEntry.game_features[String(index)]);
      if (translated) translatedFields += 1;
      return translated || source;
    }));
    localizedDetails.game_features = features;
  }

  if (!translatedFields) return game;
  return {
    ...game,
    details: localizedDetails,
    __localizedLanguage: 'fr',
    __translatedFields: translatedFields,
  };
}
