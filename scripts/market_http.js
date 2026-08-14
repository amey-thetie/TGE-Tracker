// scripts/market_http.js
// Shared fetch helper for the market-data clients (CoinGecko, CoinMarketCap).
// Both APIs answer an over-quota caller with 429 rather than an error body,
// and both are used from a user-facing Refresh button, so a single blind
// failure would silently show up as "coin not found" — i.e. a company
// misclassified as TGE_ANNOUNCED when it is actually trading. Retrying on
// 429/5xx keeps a transient throttle from becoming wrong data.

const DEFAULT_RETRIES = 2;

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// Returns parsed JSON, or throws. `label` is only used to make errors readable.
async function fetchJson(url, { headers, label = "API", retries = DEFAULT_RETRIES } = {}) {
  let lastErr;
  for (let attempt = 0; attempt <= retries; attempt++) {
    let res;
    try {
      res = await fetch(url, { headers });
    } catch (err) {
      // Network-level failure (DNS, socket) — worth one more try.
      lastErr = err;
      if (attempt < retries) {
        await sleep(1000 * (attempt + 1));
        continue;
      }
      throw new Error(`${label} request failed: ${err.message}`);
    }

    if (res.ok) return res.json();

    const retryable = res.status === 429 || res.status >= 500;
    const body = await res.text().catch(() => "");
    lastErr = new Error(`${label} error ${res.status}: ${body.slice(0, 300)}`);
    if (!retryable || attempt === retries) throw lastErr;

    // Honor Retry-After when the server sends it, otherwise back off linearly.
    const retryAfter = Number(res.headers.get("retry-after"));
    await sleep(Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter * 1000 : 2000 * (attempt + 1));
  }
  throw lastErr;
}

function normalize(s) {
  return (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

module.exports = { fetchJson, sleep, normalize };
