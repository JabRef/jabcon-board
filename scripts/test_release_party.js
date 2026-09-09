// Self-check for how long a release is celebrated: node scripts/test_release_party.js
const src = require('fs').readFileSync(__dirname + '/../site/app.js', 'utf8');
const head = src.slice(src.indexOf('const PARTY_MS ='), src.indexOf('\nlet partyTimer'));
const partyStage = new Function(head + '; return partyStage;')();

console.assert(partyStage(0) === 'confetti', 'the release itself opens with confetti');
console.assert(partyStage(59000) === 'confetti', 'the confetti keeps coming for the first minute');
console.assert(partyStage(61000) === 'tail', 'after the minute the dwarfs dance on');
console.assert(partyStage(2.5 * 3600000) === 'tail', 'the dance carries the celebration for hours');
console.assert(partyStage(4 * 3600000) === '', 'the party is over the same evening');
console.assert(partyStage(Infinity) === '', 'a release from before JabCon gets no party at all');
