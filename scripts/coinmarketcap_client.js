// scripts/coinmarketcap_client.js
// CoinMarketCap Pro API wrapper, used as a second opinion for companies
// CoinGecko could not match. Requires a key (CMC has no anonymous tier):
// https://pro-api.coinmarketcap.com with an X-CMC_PRO_API_KEY header.
//
// Unlike the CoinGecko client this does NOT hit a search endpoint per name.
// CMC has no name-search, so we pull the id map once per process, index it
// by normalized name and symbol, and match locally. That means N candidate
// names cost a fixed handful of calls instead of N, which matters because
// the free CMC tier bills per credit and caps at 30 calls/minute.
//
// Matching is exact and UNAMBIGUOUS-only: if a query still resolves to two
// different listings, it is left unmatched rather than guessed. A wrong
// match here promotes a company to POST_TGE with a real price attached,
// which is a worse outcome than leaving it TGE_ANNOUNCED.
//
// Matching runs in tiers, strictest first, because punctuation-stripping
// alone is too blunt on CMC's catalog: it lists "Bitcoin" AND "Bitcoin.ℏ",
// which both reduce to "bitcoin". Refusing that pair as ambiguous would
// throw away the real coin. 136 of ~7,900 listed names collide this way, so
// this is the common case, not an edge case. Trying literal (case-folded)
// equality before the stripped form resolves it without ever ranking or
// guessing between two equally-good candidates.

const { fetchJson, sleep, normalize } = require("./market_http");

const CMC_BASE = "https://pro-api.coinmarketcap.com";
const MAP_PAGE_SIZE = 5000; // API maximum
const MAX_MAP_PAGES = 6; // safety bound; ~30k active listings is well past the real count
const QUOTE_BATCH = 100; // API maximum ids per quotes/latest call

// Case-folded, whitespace-trimmed, but punctuation PRESERVED — the strict
// tier. normalize() (punctuation stripped) is the loose tier.
function exact(s) {
  return (s || "").trim().toLowerCase();
}

function headersFor(apiKey) {
  return { "X-CMC_PRO_API_KEY": apiKey, Accept: "application/json" };
}

// CMC can return HTTP 200 with an error in the envelope, so check both.
function unwrap(payload) {
  const status = payload && payload.status;
  if (status && status.error_code) {
    throw new Error(`CoinMarketCap error ${status.error_code}: ${status.error_message || "unknown"}`);
  }
  return payload ? payload.data : null;
}

// The id map is stable across a refresh and expensive-ish to pull, so cache
// it for the lifetime of the process (the server is a local dev process;
// restarting it picks up newly listed coins).
let mapCache = null;

async function fetchIdMap(apiKey) {
  if (mapCache) return mapCache;
  const listings = [];
  for (let page = 0; page < MAX_MAP_PAGES; page++) {
    const url = `${CMC_BASE}/v1/cryptocurrency/map?listing_status=active&start=${page * MAP_PAGE_SIZE + 1}&limit=${MAP_PAGE_SIZE}`;
    const data = unwrap(await fetchJson(url, { headers: headersFor(apiKey), label: "CoinMarketCap" }));
    if (!Array.isArray(data) || data.length === 0) break;
    listings.push(...data);
    if (data.length < MAP_PAGE_SIZE) break;
    await sleep(250);
  }

  // key -> array of ids. Arrays (not single ids) so collisions stay visible
  // to the matcher instead of silently becoming last-write-wins.
  const indexes = {
    exactName: new Map(),
    normName: new Map(),
    exactSymbol: new Map(),
    normSymbol: new Map(),
  };
  const push = (index, key, id) => {
    if (!key) return;
    const existing = index.get(key);
    if (existing) existing.push(id);
    else index.set(key, [id]);
  };
  for (const c of listings) {
    push(indexes.exactName, exact(c.name), c.id);
    push(indexes.normName, normalize(c.name), c.id);
    push(indexes.exactSymbol, exact(c.symbol), c.id);
    push(indexes.normSymbol, normalize(c.symbol), c.id);
  }

  mapCache = { ...indexes, count: listings.length };
  return mapCache;
}

async function fetchQuotes(apiKey, ids) {
  const quotes = {};
  for (let i = 0; i < ids.length; i += QUOTE_BATCH) {
    const chunk = ids.slice(i, i + QUOTE_BATCH);
    const url = `${CMC_BASE}/v2/cryptocurrency/quotes/latest?id=${chunk.join(",")}&convert=USD`;
    const data = unwrap(await fetchJson(url, { headers: headersFor(apiKey), label: "CoinMarketCap" }));
    for (const [id, entry] of Object.entries(data || {})) {
      // v2 returns an object per id when queried by id, but an array per key
      // when queried by symbol; tolerate either shape.
      const coin = Array.isArray(entry) ? entry[0] : entry;
      if (coin) quotes[id] = coin;
    }
    if (i + QUOTE_BATCH < ids.length) await sleep(250);
  }
  return quotes;
}

// Resolves one query string to a single CMC id, or null.
//
// Name beats symbol: a company called "Ondo Finance" matching a coin named
// "Ondo Finance" is far stronger evidence than a three-letter ticker
// happening to collide. Within each field, literal equality beats the
// punctuation-stripped form. A tier that produces exactly one id wins; a
// tier that produces several is a genuine ambiguity and stops the search
// for that field rather than falling through to a weaker signal, since a
// name we cannot pin down is not evidence we should trade down to a ticker.
function resolveId(idx, query) {
  const fields = [
    [idx.exactName, idx.normName],
    [idx.exactSymbol, idx.normSymbol],
  ];
  const strictKey = exact(query);
  const looseKey = normalize(query);
  for (const [strictIndex, looseIndex] of fields) {
    const hits = (strictKey && strictIndex.get(strictKey)) || (looseKey && looseIndex.get(looseKey));
    if (!hits) continue; // nothing for this field, try the next one
    const unique = [...new Set(hits)];
    return unique.length === 1 ? unique[0] : null; // ambiguous -> give up entirely
  }
  return null;
}

// names: array of candidate names to check.
// opts: { apiKey } — required.
// Returns a map keyed by the ORIGINAL name -> {symbol, price_usd,
// market_cap_usd, volume_24h_usd}. Unmatched and ambiguous names are absent.
async function verifyByExactName(names, { apiKey } = {}) {
  if (!apiKey) throw new Error("CoinMarketCap requires an API key (COINMARKETCAP_API_KEY).");
  if (!names.length) return {};

  const idx = await fetchIdMap(apiKey);

  const idByName = {};
  for (const name of names) {
    const id = resolveId(idx, name);
    if (id != null) idByName[name] = id;
  }

  const uniqueIds = [...new Set(Object.values(idByName))];
  if (!uniqueIds.length) return {};
  const quotes = await fetchQuotes(apiKey, uniqueIds);

  const verified = {};
  for (const [name, id] of Object.entries(idByName)) {
    const coin = quotes[String(id)];
    const usd = coin && coin.quote && coin.quote.USD;
    if (!usd || usd.price == null) continue; // listed but no live quote — treat as unverified
    verified[name] = {
      symbol: coin.symbol,
      price_usd: usd.price,
      market_cap_usd: usd.market_cap,
      volume_24h_usd: usd.volume_24h,
    };
  }
  return verified;
}

// Exposed for tests / scripts that want a clean pull in one process.
function clearMapCache() {
  mapCache = null;
}

module.exports = { verifyByExactName, clearMapCache };
