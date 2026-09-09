// Self-check for the trend window: node scripts/test_trend_samples.js
// app.js is a plain browser script, so the two sampling functions are lifted out of it and evaluated here.
const src = require('fs').readFileSync(__dirname + '/../site/app.js', 'utf8');
const block = src.slice(src.indexOf('const TREND_H'), src.indexOf('function renderColumn'));
const h = (t, v) => ({ t: new Date(Date.now() - t * 60000).toISOString(), ...(v === undefined ? {} : { open_prs: v }) });
const run = (history) => new Function('data', 'esc', 'fmt', block + 'return trend("open_prs", true, true, true);')(
  { history }, String, String);

// a run that could not read the count leaves it out; the arrow skips that sample instead of reading 83 - 0
console.assert(run([h(180, 60), h(70), h(0, 83)]).includes('23'), 'a sample without the count must not set the base');
console.assert(run([h(180, 69), h(70, 69), h(0, 83)]).includes('14'), 'the newest sample in the window is the base');
console.assert(run([h(180, 69), h(0, 69)]).includes('▬'), 'an unmoved number gets the flat bar');
console.assert(run([h(0, 83)]) === '', 'a single sample is no tendency');
console.assert(run([h(70), h(0, 83)]) === '', 'no usable base, no arrow');
console.log('ok');
