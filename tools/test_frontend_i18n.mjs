import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { localizeGameProse } from '../site/assets/translations.js';

if (!globalThis.crypto) globalThis.crypto = webcrypto;

async function sha256(value) {
  const normalized = String(value || '').replace(/\s+/g, ' ').trim();
  const bytes = new TextEncoder().encode(normalized);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
}

const sourceDescription = 'A compact English description with   normalized whitespace.';
const sourceFeatures = [
  'First English feature.',
  'Second English feature.',
];

const payload = {
  translation_version: 1,
  language: 'fr',
  games: {
    demo: {
      description: {
        source_sha256: await sha256(sourceDescription),
        text: 'Une description française compacte.',
      },
      game_features: {
        '0': {
          source_sha256: await sha256(sourceFeatures[0]),
          text: 'Première fonctionnalité française.',
        },
        '1': {
          source_sha256: '0'.repeat(64),
          text: 'Cette traduction périmée ne doit jamais apparaître.',
        },
      },
    },
  },
};

const game = {
  id: 'demo',
  details: {
    description: sourceDescription,
    game_features: sourceFeatures,
    repack_features: ['Original repack text remains untouched.'],
  },
};

const fr = await localizeGameProse(game, payload, 'fr');
assert.equal(fr.details.description, 'Une description française compacte.');
assert.equal(fr.details.game_features[0], 'Première fonctionnalité française.');
assert.equal(fr.details.game_features[1], sourceFeatures[1], 'stale feature must fall back to English source');
assert.deepEqual(fr.details.repack_features, game.details.repack_features, 'repack prose must not be translated');
assert.equal(fr.__translatedFields, 2);

const en = await localizeGameProse(game, payload, 'en');
assert.equal(en, game, 'English mode must use the immutable source payload');

const stalePayload = structuredClone(payload);
stalePayload.games.demo.description.source_sha256 = 'f'.repeat(64);
const stale = await localizeGameProse(game, stalePayload, 'fr');
assert.equal(stale.details.description, sourceDescription, 'stale description must fail closed to English');

console.log('frontend translation hash/fallback contract OK');
