import assert from 'node:assert/strict';
import { gameReleaseYear } from '../site/assets/game-identity.js';
for (const [value, expected] of [['1989-01-01','1989'],['1999','1999'],['2000-01-01','2000'],['2026-03-04','2026'],[null,''],['',''],['unknown',''],['20260','']]) assert.equal(gameReleaseYear(value),expected);
console.log('release years OK');

const {formatDateValue}=await import('../site/assets/core/i18n.js');
assert.equal(formatDateValue('1995'),'1995');
assert.match(formatDateValue('2019-02'),/2019/);
assert.doesNotMatch(formatDateValue('2019-02'),/\b01\b/);
assert.match(formatDateValue('2016-05-09'),/\b09?\b/);
