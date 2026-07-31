// scripts/classify.js
// Shared classification rules (the mechanized subset of Instructions.py's
// CryptoLaunchVerifier methodology) so the live refresh endpoint in app.js
// and any future batch scripts stay consistent with one source of truth.

const TOKEN_ROUND_RE = /TOKEN|ICO|IEO|IDO/;

function isTokenSaleRound(roundType) {
  return !!roundType && TOKEN_ROUND_RE.test(String(roundType).toUpperCase());
}

// coinMarket: { symbol, price_usd, market_cap_usd, volume_24h_usd } | null
// Returns the {s, f, ...} fields to merge into a company entry.
function classifyCompany({ postTge, coinName, coinMarket, roundType }) {
  if (postTge) {
    return { s: "POST_TGE", f: 0.75, pv: "curated" };
  }
  if (coinMarket) {
    const activelyTrading = (coinMarket.volume_24h_usd || 0) >= 1000;
    return {
      s: activelyTrading ? "POST_TGE" : "TOKEN_LIVE_NOT_TRADING",
      f: activelyTrading ? 0.85 : 0.6,
      tn: coinName,
      ts: coinMarket.symbol.toUpperCase(),
      mp: Math.round(coinMarket.price_usd * 100) / 100,
      mc: Math.round(coinMarket.market_cap_usd || 0),
      mv: Math.round(coinMarket.volume_24h_usd || 0),
    };
  }
  if (coinName) {
    return { s: "TGE_ANNOUNCED", f: 0.4, tn: coinName };
  }
  if (isTokenSaleRound(roundType)) {
    return { s: "TGE_ANNOUNCED", f: 0.35 };
  }
  return { s: "UNKNOWN", f: 0.1 };
}

module.exports = { classifyCompany, isTokenSaleRound, TOKEN_ROUND_RE };
