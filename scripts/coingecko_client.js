// scripts/coingecko_client.js
// CoinGecko API wrapper. Works with no key at all (public rate-limited
// endpoint, the original behavior) and with either paid tier if one is
// supplied: a Demo key on the public host, or a Pro key on pro-api. Only
// ever accepts an EXACT normalized name/symbol match - no fuzzy "first
// result" guessing, since a company name is a much weaker search key than a
// real coin_uid and false positives would misclassify a company as POST_TGE.

const { fetchJson, sleep, normalize } = require("./market_http");

const PUBLIC_BASE = "https://api.coingecko.com/api/v3";
const PRO_BASE = "https://pro-api.coingecko.com/api/v3";

// Per-lookup delay by tier. The search endpoint is called once per candidate
// name, so this is what paces a Refresh.
//   none — no published limit; ~5-15 req/min in practice, 1.2s is the value
//          this project has always used.
//   demo — documented at 30 req/min, so anything under 2s will start 429ing.
//   pro  — 500+ req/min; a small delay is just politeness.
const DELAY_MS = { none: 1200, demo: 2100, pro: 120 };

// Resolves which host/header/pacing to use from the supplied credentials.
// plan is "demo" or "pro"; anything else with a key present is treated as
// demo, which is the tier a free CoinGecko account hands out.
function resolveTier(apiKey, plan) {
  if (!apiKey) return { base: PUBLIC_BASE, headers: {}, delayMs: DELAY_MS.none, tier: "none" };
  if (String(plan).toLowerCase() === "pro") {
    return { base: PRO_BASE, headers: { "x-cg-pro-api-key": apiKey }, delayMs: DELAY_MS.pro, tier: "pro" };
  }
  return { base: PUBLIC_BASE, headers: { "x-cg-demo-api-key": apiKey }, delayMs: DELAY_MS.demo, tier: "demo" };
}

// Resolves a query to at most ONE CoinGecko id, refusing anything ambiguous.
//
// Two rules matter here, and dropping either produces wrong rows:
//
//  1. Name before symbol. A coin NAME equal to the query is a much stronger
//     signal than a 3-4 letter SYMBOL that happens to collide with it. These
//     were previously checked in a single pass, so a symbol collision could
//     win over a real name match purely on result ordering.
//
//  2. Refuse ties. This used to take .find() — the FIRST match — so a query
//     resolving to several distinct coins silently picked one by result
//     order. CoinGecko lists two separate coins named "Solomon" (SOLO and
//     SOL777), and the sweep promoted a company on a coin flip between them.
//     The CoinMarketCap client already abandons a tier that resolves to more
//     than one listing; this now matches, so the two sources agree.
async function findExactCoinGeckoId(name, tier) {
  const data = await fetchJson(`${tier.base}/search?query=${encodeURIComponent(name)}`, {
    headers: tier.headers,
    label: "CoinGecko",
  });
  const target = normalize(name);
  const coins = data.coins || [];

  for (const key of ["name", "symbol"]) {
    const ids = [...new Set(
      coins.filter((c) => normalize(c[key]) === target).map((c) => c.id)
    )];
    if (ids.length === 1) return ids[0];
    if (ids.length > 1) return null; // ambiguous — refuse rather than guess
  }
  return null;
}

async function fetchMarkets(ids, tier) {
  if (!ids.length) return [];
  // /coins/markets caps a request at 250 ids; chunk so a large refresh does
  // not silently lose the tail of the list.
  const out = [];
  for (let i = 0; i < ids.length; i += 250) {
    const chunk = ids.slice(i, i + 250);
    const page = await fetchJson(
      `${tier.base}/coins/markets?vs_currency=usd&per_page=250&ids=${chunk.join(",")}`,
      { headers: tier.headers, label: "CoinGecko" }
    );
    out.push(...page);
    if (i + 250 < ids.length) await sleep(tier.delayMs);
  }
  return out;
}

// names: array of candidate names (e.g. company names) to check.
// opts: { apiKey, plan } — both optional; omitting apiKey uses the public API.
// Returns a map keyed by the ORIGINAL name -> {symbol, price_usd, market_cap_usd, volume_24h_usd}
// for names that matched exactly; unmatched names are simply absent.
async function verifyByExactName(names, { apiKey, plan } = {}) {
  const tier = resolveTier(apiKey, plan);
  const idByName = {};
  for (const name of names) {
    try {
      const id = await findExactCoinGeckoId(name, tier);
      if (id) idByName[name] = id;
    } catch {
      // ignore individual lookup failures, treat as unmatched
    }
    await sleep(tier.delayMs);
  }

  const uniqueIds = [...new Set(Object.values(idByName))];
  let markets = [];
  try {
    markets = await fetchMarkets(uniqueIds, tier);
  } catch {
    // A markets failure means we know the coin exists but have no price;
    // leaving it unmatched is the safe direction (TGE_ANNOUNCED, not POST_TGE).
    markets = [];
  }
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

module.exports = { verifyByExactName, normalize, resolveTier };
