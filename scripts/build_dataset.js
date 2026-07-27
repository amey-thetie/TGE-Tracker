const fs = require('fs');
const path = require('path');

const dir = path.join(__dirname, '..', 'data', 'raw');
const roster = JSON.parse(fs.readFileSync(path.join(dir, 'roster.json'), 'utf8'));
const joinByCompany = JSON.parse(fs.readFileSync(path.join(dir, 'joinByCompany.json'), 'utf8'));
const verifiedByCoinUid = JSON.parse(fs.readFileSync(path.join(dir, 'verifiedByCoinUid.json'), 'utf8'));
const unmatchedCoins = JSON.parse(fs.readFileSync(path.join(dir, 'unmatchedCoins.json'), 'utf8'));

console.log('roster:', roster.length, 'joinByCompany:', Object.keys(joinByCompany).length, 'verifiedByCoinUid:', Object.keys(verifiedByCoinUid).length, 'unmatchedCoins:', unmatchedCoins.length);

// Build a name-lookup for roster so join-only companies (not in roster) can still be included
const rosterByUid = new Map(roster.map(c => [c.company_uid, c.company_name]));

const allUids = new Set([...roster.map(c => c.company_uid), ...Object.keys(joinByCompany)]);
console.log('union of roster + join company_uids:', allUids.size);

function fmtUSD(n) {
  if (n === null || n === undefined) return null;
  return n;
}

const companies = [];

// Slim schema: only raw distinguishing fields. The widget renders reasoning/evidence
// text client-side from these fields via a template, since that text is otherwise
// ~95% identical boilerplate repeated across thousands of rows (4MB -> unusable).
const r2 = (n) => (n === null || n === undefined) ? null : Math.round(n * 100) / 100;

for (const uid of allUids) {
  const name = rosterByUid.get(uid) || (joinByCompany[uid] && joinByCompany[uid].company_name) || uid;
  const j = joinByCompany[uid];
  const category = (j && j.category) || [];

  let status, confidence;
  let coin_name = null, coin_symbol = null, price_usd = null, market_cap_usd = null, volume_24h_usd = null;

  if (j && j.coin_uid) {
    const v = verifiedByCoinUid[j.coin_uid];
    coin_name = j.coin_name;
    if (v) {
      coin_symbol = v.symbol.toUpperCase();
      price_usd = r2(v.price_usd);
      market_cap_usd = Math.round(v.market_cap_usd || 0);
      volume_24h_usd = Math.round(v.volume_24h_usd || 0);
      const activelyTrading = (v.volume_24h_usd || 0) >= 1000;
      status = activelyTrading ? 'POST_TGE' : 'TOKEN_LIVE_NOT_TRADING';
      confidence = activelyTrading ? 0.85 : 0.6;
    } else {
      status = 'TGE_ANNOUNCED';
      confidence = 0.4;
    }
  } else if (j && !j.coin_uid) {
    status = 'TGE_ANNOUNCED';
    confidence = 0.35;
  } else {
    status = 'UNKNOWN';
    confidence = 0.1;
  }

  const c = {
    u: uid,
    n: name,
    c: category,
    s: status,
    f: confidence,
  };
  if (j) {
    c.rt = j.round_type;
    c.rd = j.round_date;
    c.ra = j.funding_amount || 0;
    c.su = j.source_url || '';
  }
  if (coin_name) {
    c.tn = coin_name;
    if (coin_symbol) c.ts = coin_symbol;
    if (price_usd !== null) c.mp = price_usd;
    if (market_cap_usd !== null) c.mc = market_cap_usd;
    if (volume_24h_usd !== null) c.mv = volume_24h_usd;
  }
  companies.push(c);
}

companies.sort((a, b) => a.n.localeCompare(b.n));

const statusCounts = {};
for (const c of companies) statusCounts[c.s] = (statusCounts[c.s] || 0) + 1;
console.log('status counts:', JSON.stringify(statusCounts, null, 2));
console.log('total companies in final dataset:', companies.length);

const outObj = {
  generated_at: '2026-07-27T12:00:00Z',
  source: 'TIE Terminal (Fundraise Brief) + CoinGecko live cross-check',
  stats: { total: companies.length, ...statusCounts },
  companies,
};
const outPath = path.join(dir, '..', 'tge_dataset_full.json');
fs.writeFileSync(outPath, JSON.stringify(outObj));
console.log('wrote', outPath, '(' + fs.statSync(outPath).size + ' bytes)');
