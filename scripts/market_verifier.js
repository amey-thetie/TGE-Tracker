// scripts/market_verifier.js
// Single entry point the refresh path uses to answer "does this company's
// token actually trade anywhere?".
//
// CoinGecko runs first — it needs no key, and the whole existing dataset was
// built against it, so keeping it primary means a refresh does not start
// producing prices from a different source than the snapshot it merges into.
// CoinMarketCap is consulted only for the names CoinGecko could not match,
// and only when a key is configured. That ordering makes CMC purely additive:
// with no CMC key the behavior is identical to before this module existed.
//
// Returns { verified, warnings, counts }:
//   verified — name -> { symbol, price_usd, market_cap_usd, volume_24h_usd, source }
//   warnings — human-readable strings for failures that were survivable
//              (a dead CMC key must not take down the whole Refresh, but it
//              must not be silent either — silence here looks exactly like
//              "no coin found", which is a data-quality lie).

const coingecko = require("./coingecko_client");
const coinmarketcap = require("./coinmarketcap_client");

async function verifyMarkets(names, { coingeckoKey, coingeckoPlan, coinmarketcapKey, symbolHints } = {}) {
  const verified = {};
  const warnings = [];
  const counts = { coingecko: 0, coinmarketcap: 0, unmatched: 0 };

  if (!names.length) return { verified, warnings, counts };

  try {
    const cg = await coingecko.verifyByExactName(names, { apiKey: coingeckoKey, plan: coingeckoPlan, symbolHints });
    for (const [name, market] of Object.entries(cg)) {
      verified[name] = { ...market, source: "coingecko" };
      counts.coingecko++;
    }
  } catch (err) {
    warnings.push(`CoinGecko lookup failed: ${err.message || err}`);
  }

  const unmatched = names.filter((n) => !verified[n]);
  if (unmatched.length && coinmarketcapKey) {
    try {
      const cmc = await coinmarketcap.verifyByExactName(unmatched, { apiKey: coinmarketcapKey });
      for (const [name, market] of Object.entries(cmc)) {
        verified[name] = { ...market, source: "coinmarketcap" };
        counts.coinmarketcap++;
      }
    } catch (err) {
      warnings.push(`CoinMarketCap lookup failed: ${err.message || err}`);
    }
  }

  counts.unmatched = names.filter((n) => !verified[n]).length;
  return { verified, warnings, counts };
}

module.exports = { verifyMarkets };
