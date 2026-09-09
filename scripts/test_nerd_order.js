// Self-check for the nerd corner's page variety: node scripts/test_nerd_order.js
// app.js is a plain browser script, so the ordering block is lifted out of it by its markers and evaluated here.
const src = require('fs').readFileSync(__dirname + '/../site/app.js', 'utf8');
const block = src.slice(src.indexOf('const NERD_PAGE'), src.indexOf('function renderNerd'));
const { nerdOrder, nerdKind } = new Function(block + 'return { nerdOrder, nerdKind };')();

const items = [
  { author: 'a', text: 'deleted One' }, { author: 'a', text: 'deleted Two' }, { author: 'a', text: 'deleted Three' },
  { author: 'a', text: 'virtual threads' }, { author: 'b', title: 'Longest identifier', text: 'x' },
  { author: 'a', title: 'Longest method', text: 'y' }, { author: 'c', title: 'Shortest method', text: 'z' },
];
const page = nerdOrder(items).slice(0, 4);
const uniq = (xs) => new Set(xs).size === xs.length;
console.assert(uniq(page.map(nerdKind)), 'kinds repeat on a page: ' + JSON.stringify(page));
// three authors cannot fill four slots, but the repeat must be spread out, never side by side
console.assert(page.every((r, i) => i === 0 || r.author !== page[i - 1].author), 'same author twice in a row: ' + JSON.stringify(page));
console.assert(page.filter((r) => r.author === 'a').length <= 2, 'one author owns the page: ' + JSON.stringify(page));
console.assert(nerdOrder(items).length === items.length, 'items lost');
console.log('ok', page.map((r) => `${r.author}:${nerdKind(r)}`).join(' | '));
