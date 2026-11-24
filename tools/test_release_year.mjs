import assert from 'node:assert/strict';
import { gameReleaseYear } from '../site/assets/game-identity.js';
for (const [value, expected] of [['1989-01-01','1989'],['1999','1999'],['2000-01-01','2000'],['2026-03-04','2026'],[null,''],['',''],['unknown',''],['20260','']]) assert.equal(gameReleaseYear(value),expected);
console.log('release years OK');
