const fs = require('fs');

const inPath = process.argv[2];
const outDir = process.argv[3];

const raw = fs.readFileSync(inPath, 'utf8');
const outer = JSON.parse(raw);
const data = outer.result;
console.log('logs:', JSON.stringify(outer.logs));
console.log('totalTokens:', outer.totalTokens, 'totalToolCalls:', outer.totalToolCalls);

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(outDir + '/roster.json', JSON.stringify(data.roster));
fs.writeFileSync(outDir + '/joinByCompany.json', JSON.stringify(data.joinByCompany));
fs.writeFileSync(outDir + '/verifiedByCoinUid.json', JSON.stringify(data.verifiedByCoinUid));
fs.writeFileSync(outDir + '/unmatchedCoins.json', JSON.stringify(data.unmatchedCoins));
fs.writeFileSync(outDir + '/stats.json', JSON.stringify(data.stats, null, 2));

console.log('stats:', JSON.stringify(data.stats));
console.log('roster length:', data.roster.length);
console.log('joinByCompany keys:', Object.keys(data.joinByCompany).length);
console.log('verifiedByCoinUid keys:', Object.keys(data.verifiedByCoinUid).length);
console.log('unmatchedCoins length:', data.unmatchedCoins.length);

// sample a few join entries
const joinSample = Object.entries(data.joinByCompany).slice(0, 5);
console.log('join sample:', JSON.stringify(joinSample, null, 2));
const verifySample = Object.entries(data.verifiedByCoinUid).slice(0, 5);
console.log('verify sample:', JSON.stringify(verifySample, null, 2));
