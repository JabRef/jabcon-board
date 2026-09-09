// Self-check for the signed net size of a component: node scripts/test_component_net.js
const src = require('fs').readFileSync(__dirname + '/../site/app.js', 'utf8');
const net = new Function('fmt', src.slice(src.indexOf('const net ='), src.indexOf('\n', src.indexOf('const net ='))) + 'return net;')(String);

console.assert(net(3 - 5) === '<span class="net del">−2</span>', '3 added, 5 removed reads as -2');
console.assert(net(5 - 3) === '<span class="net add">+2</span>', 'growth is signed and green');
console.assert(net(0) === '<span class="net add">+0</span>', 'no change still shows a number');
console.assert(net(undefined) === '', 'data without the field renders nothing');
