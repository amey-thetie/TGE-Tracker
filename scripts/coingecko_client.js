// scripts/coingecko_client.js
// Public CoinGecko API only (no key required, rate-limited). Only ever
// accepts an EXACT normalized name/symbol match - no fuzzy "first result"
// guessing, since a company name is a much weaker search key than a real
// coin_uid and false positives would misclassify a company as POST_TGE.

const CG_BASE = "https://api.coingecko.com/api/v3";

function normalize(s) {
  return (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

async function findExactCoinGeckoId(name) {
  const res = await fetch(`${CG_BASE}/search?query=${encodeURIComponent(name)}`);
  if (!res.ok) return null;
  const data = await res.json();
  const target = normalize(name);
  const match = (data.coins || []).find(
    (c) => normalize(c.name) === target || normalize(c.symbol) === target
  );
  return match ? match.id : null;
}

async function fetchMarkets(ids) {
  if (!ids.length) return [];
  const res = await fetch(`${CG_BASE}/coins/markets?vs_currency=usd&ids=${ids.join(",")}`);
  if (!res.ok) return [];
  return res.json();
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// names: array of candidate names (e.g. company names) to check.
// Returns a map keyed by the ORIGINAL name -> {symbol, price_usd, market_cap_usd, volume_24h_usd}
// for names that matched exactly; unmatched names are simply absent.
async function verifyByExactName(names) {
  const idByName = {};
  for (const name of names) {
    try {
      const id = await findExactCoinGeckoId(name);
      if (id) idByName[name] = id;
    } catch {
      // ignore individual lookup failures, treat as unmatched
    }
    await sleep(1200); // be gentle with the free public rate limit
  }

  const uniqueIds = [...new Set(Object.values(idByName))];
  const markets = await fetchMarkets(uniqueIds);
  const marketsById = Object.fromEntries(markets.map((m) => [m.id, m]));

  const verified = {};
  for (const [name, id] of Object.entries(idByName)) {
    const m = marketsById[id];
    if (m) {
      verified[name] = {
        symbol: m.symbol,
        price_usd: m.current_price,
        market_cap_usd: m.market_cap,
        volume_24h_usd: m.total_volume,
      };
    }
  }
  return verified;
}

module.exports = { verifyByExactName, normalize };
