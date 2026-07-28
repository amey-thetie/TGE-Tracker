// Backfills accurate round_date/round_type/funding_amount/source_url onto the full
// dataset using a fresh, UNFILTERED fetch of the most recent ~700 rounds. The original
// build_dataset.js only recorded round info for rows that matched the coin/token-sale
// filter, so most companies had no round_date at all even if they raised recently -
// this made the "latest fundraise brief companies" default view badly incomplete
// (see: only 10/49 July 2026 companies were showing up). This script does NOT change
// any existing TGE status/token classification - it only fixes the round display fields,
// and adds any companies that were missing entirely from the original roster/join.
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const rawDir = path.join(root, 'data', 'raw');

const full = JSON.parse(fs.readFileSync(path.join(root, 'data', 'tge_dataset_full.json'), 'utf8'));
const recent = JSON.parse(fs.readFileSync(path.join(rawDir, 'recent_rounds_unfiltered.json'), 'utf8')).companies;
const verifiedByCoinUid = JSON.parse(fs.readFileSync(path.join(rawDir, 'verifiedByCoinUid.json'), 'utf8'));

const byUid = new Map(full.companies.map(c => [c.u, c]));
let updated = 0, added = 0, skippedOlder = 0;

for (const r of recent) {
  const existing = byUid.get(r.company_uid);
  if (existing) {
    if (!existing.rd || r.round_date > existing.rd) {
      existing.rt = r.round_type;
      existing.rd = r.round_date;
      existing.ra = r.funding_amount || 0;
      existing.su = r.source_url || '';
      updated++;
    } else {
      skippedOlder++;
    }
  } else {
    // Company wasn't in the original roster/join at all - add it fresh using the
    // same classification rule set as build_dataset.js.
    let status, confidence, coin_symbol, price_usd, market_cap_usd, volume_24h_usd;
    if (r.coin_uid) {
      const v = verifiedByCoinUid[r.coin_uid];
      if (v) {
        const activelyTrading = (v.volume_24h_usd || 0) >= 1000;
        status = activelyTrading ? 'POST_TGE' : 'TOKEN_LIVE_NOT_TRADING';
        confidence = activelyTrading ? 0.85 : 0.6;
        coin_symbol = v.symbol.toUpperCase();
        price_usd = Math.round(v.price_usd * 100) / 100;
        market_cap_usd = Math.round(v.market_cap_usd || 0);
        volume_24h_usd = Math.round(v.volume_24h_usd || 0);
      } else {
        status = 'TGE_ANNOUNCED';
        confidence = 0.4;
      }
    } else {
      const rtUpper = (r.round_type || '').toUpperCase();
      const isTokenRound = /TOKEN|ICO|IEO|IDO/.test(rtUpper);
      status = isTokenRound ? 'TGE_ANNOUNCED' : 'UNKNOWN';
      confidence = isTokenRound ? 0.35 : 0.1;
    }

    const c = {
      u: r.company_uid,
      n: r.company_name,
      c: r.category || [],
      s: status,
      f: confidence,
      rt: r.round_type,
      rd: r.round_date,
      ra: r.funding_amount || 0,
      su: r.source_url || '',
    };
    if (r.coin_uid) {
      c.tn = r.coin_name;
      if (coin_symbol) c.ts = coin_symbol;
      if (price_usd !== undefined) c.mp = price_usd;
      if (market_cap_usd !== undefined) c.mc = market_cap_usd;
      if (volume_24h_usd !== undefined) c.mv = volume_24h_usd;
    }
    full.companies.push(c);
    byUid.set(c.u, c);
    added++;
  }
}

full.companies.sort((a, b) => a.n.localeCompare(b.n));

const statusCounts = {};
for (const c of full.companies) statusCounts[c.s] = (statusCounts[c.s] || 0) + 1;
full.stats = { total: full.companies.length, ...statusCounts };
full.generated_at = '2026-07-28T08:00:00Z';

console.log({ updated, added, skippedOlder, newTotal: full.companies.length, stats: full.stats });

const outPath = path.join(root, 'data', 'tge_dataset_full.json');
fs.writeFileSync(outPath, JSON.stringify(full));
console.log('wrote', outPath, '(' + fs.statSync(outPath).size + ' bytes)');
