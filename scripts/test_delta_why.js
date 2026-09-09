// Self-check for the hand-over lines in a delta tooltip: node scripts/test_delta_why.js
const src = require('fs').readFileSync(__dirname + '/../site/app.js', 'utf8');
const block = src.slice(src.indexOf('const TREND_H'), src.indexOf('function renderColumn'));
const s = (t, parts) => ({ t: new Date(Date.now() - t * 60000).toISOString(), parts });
const why = (history, login) => new Function('data', 'esc', 'fmt', block + `return deltaWhy(${JSON.stringify(login)});`)(
  { history }, String, String);
const p = (b) => ({ m: 0, r: 0, o: 0, a: 0, k: 0, x: 0, b });

const moved = [s(180, { poor: p(['⚡ Component collector']), maran: p([]) }),
               s(0, { poor: p([]), maran: p(['⚡ Component collector']) })];
console.assert(why(moved, 'poor').includes('lost ⚡ Component collector (−100) to maran'), 'the loser learns who took it');
console.assert(why(moved, 'maran').includes('earned ⚡ Component collector (+100) from poor'), 'the winner learns whom it came from');

// nobody else holds it now: the sticker was simply given up, no name to add
const dropped = [s(180, { poor: p(['⚡ x']) }), s(0, { poor: p([]) })];
console.assert(why(dropped, 'poor')[0] === 'lost ⚡ x (−100)', 'no other side, no suffix');

// a sticker held by two people all along is no hand-over for the third who just earned it
const shared = [s(180, { a: p(['🏅 y']), c: p([]) }), s(0, { a: p(['🏅 y']), c: p(['🏅 y']) })];
console.assert(why(shared, 'c')[0] === 'earned 🏅 y (+100)', 'a standing holder is not the source');
console.log('ok');
