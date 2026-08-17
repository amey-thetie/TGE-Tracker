// scripts/sweep.js
// The two things that can change the snapshot, in one place so the manual
// Refresh button and the background scheduler can never drift apart:
//
//   ingestNewCompanies  — pulls Airtable rows added since the sync cursor.
//                         This is what /api/refresh has always done.
//   reverifyRecent      — re-checks companies already in the dataset whose
//                         status could still move, which nothing did before.
//
// reverifyRecent closes the gap that made the tracker look stale: a company
// ingested at TGE_ANNOUNCED stayed there forever, even after its token went
// live, because the refresh path skips uids it already has.

const fs = require("fs");
const path = require("path");

const { fetchRecentFundedCompanies } = require("./airtable_client");
const { verifyMarkets } = require("./market_verifier");
const { classifyCompany } = require("./classify");
const { buildWidgetHtml } = require("./build_widget");

const AIRTABLE_BASE_ID = "apppBDKslp00CJu9n"; // "Fundraise Data"
const AIRTABLE_TABLE_ID = "tblVMMb8i1Yn9SKs1"; // funded_companies

// Statuses a sweep is allowed to move. Anything already confirmed trading, or
// confirmed by a human, is left alone — see the note on demotion below.
const MOVABLE = new Set(["TGE_ANNOUNCED", "TOKEN_LIVE_NOT_TRADING"]);

const ACTIVE_VOLUME_THRESHOLD = 1000; // same bar the rest of the pipeline uses

// A company-name match is only trustworthy when something independently says
// this company actually ran a token event. Without that, a generic name
// collides with an unrelated coin and the sweep writes a wrong row — this is
// how "OKX" matched a dormant token literally named OKX, and how "Axis"
// matched MAXIS in the earlier bulk pass.
//
// The corroboration used here is the same one that pass validated against:
// an explicitly token-sale-typed round. In that pass 180 of 183 matches were
// corroborated this way, and reverting the 3 that weren't removed the only
// bad match. An asserted token name (c.tn) needs none of this — it is the
// link the pipeline already established, and stays fully automatic.
const TOKEN_ROUND_RE = /TOKEN|ICO|IEO|IDO/;
const MIN_INFERRED_NAME_LENGTH = 3;

// A promotion via company name writes c.tn = <company name>. Without this set,
// the NEXT sweep would see c.tn populated, treat the row as an asserted link,
// skip the corroboration guard entirely and score it 0.85 — laundering an
// inferred match into a confident one over successive runs. The pv tag is the
// durable record of how the link was actually established, so trust that.
const INFERRED_PROVENANCE = new Set(["name-match", "cmc-name-match"]);

function isInferredLink(c) {
  return !c.tn || INFERRED_PROVENANCE.has(c.pv);
}

function canPromoteByCompanyName(c) {
  const name = String(c.n || "").replace(/[^a-z0-9]/gi, "");
  if (name.length < MIN_INFERRED_NAME_LENGTH) return false;
  return TOKEN_ROUND_RE.test(String(c.rt || "").toUpperCase());
}

// Confidence for a promotion whose company->token link is INFERRED from a
// name match rather than asserted by a coin_uid. Deliberately below the 0.85
// the coin_uid path earns; mirrors scripts/verify_announced_by_name.py.
const INFERRED_TRADING_CONFIDENCE = 0.7;

function firstLookupValue(field) {
  return Array.isArray(field) ? field[0] : field || null;
}

function datasetPath(root) {
  return path.join(root, "data", "tge_dataset_full.json");
}

function readDataset(root) {
  return JSON.parse(fs.readFileSync(datasetPath(root), "utf8"));
}

// Recomputes derived fields and writes both artifacts the batch pipeline
// produces, so a swept widget is byte-comparable to a rebuilt one.
function finalizeDataset(root, dataset) {
  dataset.companies.sort((a, b) => a.n.localeCompare(b.n));
  const statusCounts = {};
  for (const c of dataset.companies) statusCounts[c.s] = (statusCounts[c.s] || 0) + 1;
  dataset.stats = { total: dataset.companies.length, ...statusCounts };
  dataset.generated_at = new Date().toISOString();

  const datasetJson = JSON.stringify(dataset);
  fs.writeFileSync(datasetPath(root), datasetJson);
  fs.writeFileSync(path.join(root, "tge_tracker_widget.html"), buildWidgetHtml(root, datasetJson));
  return dataset.generated_at;
}

// --- ingest -------------------------------------------------------------

async function ingestNewCompanies(dataset, { token, marketKeys }) {
  // Use a DEDICATED sync cursor, not generated_at. generated_at means "when
  // was this snapshot last built" and now gets bumped by every sweep too;
  // reusing it as the ingest cursor would skip Airtable records permanently.
  const sinceIso = dataset.last_airtable_sync || dataset.generated_at;
  const records = await fetchRecentFundedCompanies(token, {
    baseId: AIRTABLE_BASE_ID,
    tableId: AIRTABLE_TABLE_ID,
    sinceIso,
  });

  const byUid = new Map(dataset.companies.map((c) => [c.u, c]));
  const candidates = [];
  let promotedFromSynthetic = 0;
  for (const r of records) {
    const f = r.fields || {};
    const name = f.funded_company;
    if (!name) continue;

    // A company first seen before TIE Terminal assigned it a company_uid was
    // stored under a synthetic airtable_<recordId> key. Once the real uid
    // exists, keying only on that uid would add a SECOND entry for the same
    // Airtable record — a silent duplicate (this actually happened to
    // Attestable and TradeZero). Drop the synthetic twin first: the same
    // Airtable record ID means the same company, not a name collision.
    if (f.company_uid) {
      const syntheticKey = `airtable_${r.id}`;
      const twin = byUid.get(syntheticKey);
      if (twin) {
        const idx = dataset.companies.indexOf(twin);
        if (idx !== -1) dataset.companies.splice(idx, 1);
        byUid.delete(syntheticKey);
        promotedFromSynthetic++;
      }
    }

    const uid = f.company_uid || `airtable_${r.id}`;
    if (byUid.has(uid)) continue; // already tracked — reverifyRecent handles those
    candidates.push({
      uid,
      name,
      roundDate: firstLookupValue(f.METRIC_last_round_date),
      tokenIssuer: f.token_issuer === "TRUE",
    });
  }

  const namesToVerify = candidates.filter((c) => c.tokenIssuer).map((c) => c.name);
  const { verified, warnings } = await verifyMarkets(namesToVerify, marketKeys);

  let added = 0;
  for (const cand of candidates) {
    const coinMarket = verified[cand.name] || null;
    const classification = classifyCompany({
      postTge: false, // the curated flag lives on FundingRounds, not funded_companies
      coinName: coinMarket ? cand.name : null,
      coinMarket,
      roundType: null,
    });
    const entry = { u: cand.uid, n: cand.name, c: [], ...classification };
    if (coinMarket && coinMarket.source === "coinmarketcap") entry.pv = "cmc-name-match";
    if (!coinMarket && cand.tokenIssuer) {
      entry.s = "TGE_ANNOUNCED";
      entry.f = 0.3;
    }
    if (cand.roundDate) {
      entry.rt = "UNSPECIFIED";
      entry.rd = cand.roundDate;
      entry.ra = 0;
      entry.su = "";
    }
    dataset.companies.push(entry);
    byUid.set(cand.uid, entry);
    added++;
  }

  // Only advance the cursor after Airtable actually returned — a throw above
  // leaves it untouched, so the next run re-reads the same window.
  dataset.last_airtable_sync = new Date().toISOString();

  return { added, promotedFromSynthetic, checked: records.length, warnings };
}

// --- re-verification ----------------------------------------------------

function monthsAgoIso(months) {
  const d = new Date();
  d.setMonth(d.getMonth() - months);
  return d.toISOString().slice(0, 10);
}

// Companies whose status can still move AND whose round is recent enough to
// be worth spending rate limit on. A row with no round date is skipped: we
// cannot tell how old it is, and guessing would burn the budget on the tail.
function selectRecentCandidates(dataset, monthsBack) {
  const cutoff = monthsAgoIso(monthsBack);
  return dataset.companies.filter((c) => {
    if (!MOVABLE.has(c.s) || !c.rd || c.rd < cutoff) return false;
    // Rows with an asserted token name always qualify. Rows without one can
    // only be resolved by company name, so skip them unless that match would
    // be corroborated — this both prevents the wrong-row case and avoids
    // spending rate limit on a lookup whose result we would refuse anyway.
    return isInferredLink(c) ? canPromoteByCompanyName(c) : true;
  });
}

async function reverifyRecent(dataset, { marketKeys, monthsBack = 12 }) {
  const candidates = selectRecentCandidates(dataset, monthsBack);
  if (!candidates.length) {
    return { candidates: 0, promoted: 0, updated: 0, stillUnverified: 0, changes: [], warnings: [] };
  }

  // Query by the token name when we already have one — that is the link the
  // original pipeline asserted, and a far stronger key than a company name.
  // Fall back to the company name, which is an INFERRED link and scored lower.
  const queryFor = (c) => c.tn || c.n;
  const queries = [...new Set(candidates.map(queryFor))];

  const { verified, warnings } = await verifyMarkets(queries, marketKeys);

  let promoted = 0;
  let updated = 0;
  const changes = [];

  for (const c of candidates) {
    const market = verified[queryFor(c)];
    if (!market) continue;

    const trading = (market.volume_24h_usd || 0) >= ACTIVE_VOLUME_THRESHOLD;
    const nextStatus = trading ? "POST_TGE" : "TOKEN_LIVE_NOT_TRADING";

    // Never demote. The link used here can be a name match, which is weaker
    // evidence than whatever produced the existing row; weaker evidence must
    // not overwrite a stronger prior. Volume dipping below the bar is also
    // routine noise, not a retraction of the launch.
    if (c.s === "POST_TGE" && nextStatus !== "POST_TGE") continue;

    const inferred = isInferredLink(c); // company-name link, incl. one a prior sweep wrote
    // Belt-and-braces: selectRecentCandidates already filters these out, but
    // keep the invariant at the point of write so no future caller can
    // promote on an uncorroborated name match by accident.
    if (inferred && !canPromoteByCompanyName(c)) continue;
    const before = c.s;

    if (before !== nextStatus) {
      c.s = nextStatus;
      c.f = trading ? (inferred ? INFERRED_TRADING_CONFIDENCE : 0.85) : 0.6;
      if (inferred) c.pv = market.source === "coinmarketcap" ? "cmc-name-match" : "name-match";
      if (!c.tn) c.tn = queryFor(c);
      promoted++;
      changes.push({ u: c.u, n: c.n, from: before, to: nextStatus, source: market.source });
    } else {
      updated++; // same status, refreshed market figures
    }

    c.ts = String(market.symbol || "").toUpperCase();
    c.mp = Math.round((market.price_usd || 0) * 100) / 100;
    c.mc = Math.round(market.market_cap_usd || 0);
    c.mv = Math.round(market.volume_24h_usd || 0);
  }

  return {
    candidates: candidates.length,
    promoted,
    updated,
    stillUnverified: candidates.length - promoted - updated,
    changes,
    warnings,
  };
}

// --- the whole pass -----------------------------------------------------

// One complete sweep: ingest, then re-verify, then write. Returns a summary
// suitable for logging or returning over HTTP.
async function runSweep(root, { env, monthsBack = 12, log = () => {} } = {}) {
  const marketKeys = {
    coingeckoKey: env.COINGECKO_API_KEY,
    coingeckoPlan: env.COINGECKO_API_PLAN,
    coinmarketcapKey: env.COINMARKETCAP_API_KEY,
  };

  const dataset = readDataset(root);
  const warnings = [];

  let ingest = { added: 0, checked: 0 };
  if (env.AIRTABLE_TOKEN) {
    ingest = await ingestNewCompanies(dataset, { token: env.AIRTABLE_TOKEN, marketKeys });
    warnings.push(...(ingest.warnings || []));
    log(`ingest: ${ingest.added} added from ${ingest.checked} Airtable record(s)`);
  } else {
    warnings.push("AIRTABLE_TOKEN is not set — sweep re-verified existing rows only, no new companies ingested.");
  }

  const reverify = await reverifyRecent(dataset, { marketKeys, monthsBack });
  warnings.push(...(reverify.warnings || []));
  log(
    `re-verify: ${reverify.candidates} candidate(s) from the last ${monthsBack} months, ` +
    `${reverify.promoted} status change(s), ${reverify.updated} figure refresh(es)`
  );
  for (const ch of reverify.changes) {
    log(`  ${ch.n}: ${ch.from} -> ${ch.to} (via ${ch.source})`);
  }

  dataset.last_sweep = new Date().toISOString();
  dataset.last_sweep_stats = {
    added: ingest.added,
    candidates: reverify.candidates,
    promoted: reverify.promoted,
    updated: reverify.updated,
  };

  const generatedAt = finalizeDataset(root, dataset);

  return {
    added: ingest.added,
    checked: ingest.checked,
    candidates: reverify.candidates,
    promoted: reverify.promoted,
    updated: reverify.updated,
    changes: reverify.changes,
    total: dataset.companies.length,
    generated_at: generatedAt,
    warnings,
  };
}

module.exports = {
  ingestNewCompanies,
  reverifyRecent,
  selectRecentCandidates,
  finalizeDataset,
  readDataset,
  datasetPath,
  runSweep,
  MOVABLE,
  INFERRED_TRADING_CONFIDENCE,
};
