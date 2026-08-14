#!/usr/bin/env node
/**
 * app.js — runs the TGE Tracker locally, with a live refresh endpoint.
 *
 * Usage:
 *   node app.js [port]        (defaults to 3000)
 *   npm start
 *
 * Serves the widget as a static file (Node built-ins only) AND exposes
 * POST /api/refresh, which the widget's Refresh button calls to:
 *   1. Fetch companies added to Airtable's Fundraise Brief since the
 *      current snapshot's generated_at timestamp (incremental, not a full
 *      historical re-pull).
 *   2. For any flagged as a token issuer, try to verify a live, actively
 *      traded coin on CoinGecko's public API (exact name/symbol match
 *      only — no fuzzy guessing).
 *   3. Classify each new company with the same rules as the batch
 *      pipeline (scripts/classify.js), merge into data/tge_dataset_full.json,
 *      and rebuild tge_tracker_widget.html on disk.
 *   4. Return the updated dataset so the page can re-render without a
 *      full reload.
 *
 * Requires an Airtable Personal Access Token in a local .env file
 * (AIRTABLE_TOKEN=...) — copy .env.example to get started. Without it,
 * /api/refresh returns a clear error and the static widget still works.
 *
 * Binds to 127.0.0.1 only (not your network) since this now holds a
 * credential and can write to disk.
 */
const http = require("http");
const fs = require("fs");
const path = require("path");

const { fetchRecentFundedCompanies } = require("./scripts/airtable_client");
const { verifyByExactName } = require("./scripts/coingecko_client");
const { classifyCompany } = require("./scripts/classify");
const { buildWidgetHtml } = require("./scripts/build_widget");

// This is meant to be a resilient long-running local dev server — one bad
// request should never take the whole thing down. Log and keep serving
// rather than let Node's default "crash on unhandled rejection" behavior
// kill the process out from under whoever's using it.
process.on("unhandledRejection", (err) => {
  console.error("Unhandled promise rejection (server staying up):", err);
});
process.on("uncaughtException", (err) => {
  console.error("Uncaught exception (server staying up):", err);
});

const ROOT = __dirname;
const DEFAULT_FILE = "tge_tracker_widget.html";
// Priority: explicit CLI arg (manual `node app.js 8080`) > PORT env var
// (set by tooling that auto-assigns a free port) > default 3000.
const PORT = Number(process.argv[2]) || Number(process.env.PORT) || 3000;
const HOST = "127.0.0.1";

const AIRTABLE_BASE_ID = "apppBDKslp00CJu9n"; // "Fundraise Data"
const AIRTABLE_TABLE_ID = "tblVMMb8i1Yn9SKs1"; // funded_companies

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".py": "text/plain; charset=utf-8",
  ".md": "text/plain; charset=utf-8",
};

function loadEnvFile() {
  const envPath = path.join(ROOT, ".env");
  const env = {};
  if (!fs.existsSync(envPath)) return env;
  for (const rawLine of fs.readFileSync(envPath, "utf8").split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const idx = line.indexOf("=");
    if (idx === -1) continue;
    const key = line.slice(0, idx).trim();
    let val = line.slice(idx + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    env[key] = val;
  }
  return env;
}
const ENV = { ...loadEnvFile(), ...process.env };

function resolveSafePath(root, urlPath) {
  const decoded = decodeURIComponent(urlPath.split("?")[0]);
  const resolved = path.normalize(path.join(root, decoded));
  if (resolved !== root && !resolved.startsWith(root + path.sep)) return null; // block path traversal
  return resolved;
}

function sendJson(res, status, body) {
  const text = JSON.stringify(body);
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Content-Length": Buffer.byteLength(text) });
  res.end(text);
}

function firstLookupValue(field) {
  return Array.isArray(field) ? field[0] : field || null;
}

async function handleRefresh(req, res) {
  const token = ENV.AIRTABLE_TOKEN;
  if (!token) {
    sendJson(res, 400, {
      error: "AIRTABLE_TOKEN is not set. Copy .env.example to .env and add your Airtable Personal Access Token, then restart the server.",
    });
    return;
  }

  const datasetPath = path.join(ROOT, "data", "tge_dataset_full.json");
  let dataset;
  try {
    dataset = JSON.parse(fs.readFileSync(datasetPath, "utf8"));
  } catch (err) {
    sendJson(res, 500, { error: `Could not read ${datasetPath}: ${err.message}` });
    return;
  }

  try {
    // Use a DEDICATED sync cursor, not generated_at. generated_at means "when
    // was this snapshot last built" and gets bumped by any rebuild or
    // reclassification pass; reusing it as the ingest cursor means such a pass
    // silently advances it past Airtable records that were never ingested, and
    // the next refresh then reports "0 new" while skipping them for good.
    // Falls back to generated_at only on first run, before the field exists.
    const sinceIso = dataset.last_airtable_sync || dataset.generated_at;
    const records = await fetchRecentFundedCompanies(token, {
      baseId: AIRTABLE_BASE_ID,
      tableId: AIRTABLE_TABLE_ID,
      sinceIso,
    });

    const byUid = new Map(dataset.companies.map((c) => [c.u, c]));
    const candidates = [];
    for (const r of records) {
      const f = r.fields || {};
      const name = f.funded_company;
      if (!name) continue;
      const uid = f.company_uid || `airtable_${r.id}`;
      if (byUid.has(uid)) continue; // already tracked, skip (backfill is a separate concern)
      candidates.push({
        uid,
        name,
        roundDate: firstLookupValue(f.METRIC_last_round_date),
        tokenIssuer: f.token_issuer === "TRUE",
      });
    }

    const namesToVerify = candidates.filter((c) => c.tokenIssuer).map((c) => c.name);
    const verified = namesToVerify.length ? await verifyByExactName(namesToVerify) : {};

    let added = 0;
    for (const cand of candidates) {
      const coinMarket = verified[cand.name] || null;
      const classification = classifyCompany({
        postTge: false, // Airtable's curated "Post TGE Token" checkbox lives on FundingRounds, not funded_companies; not available in this incremental pull
        coinName: coinMarket ? cand.name : null,
        coinMarket,
        roundType: null,
      });
      const entry = { u: cand.uid, n: cand.name, c: [], ...classification };
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

    dataset.companies.sort((a, b) => a.n.localeCompare(b.n));
    const statusCounts = {};
    for (const c of dataset.companies) statusCounts[c.s] = (statusCounts[c.s] || 0) + 1;
    dataset.stats = { total: dataset.companies.length, ...statusCounts };
    dataset.generated_at = new Date().toISOString();
    // Only advance the sync cursor after Airtable actually returned - if the
    // fetch had failed we'd have thrown before reaching here, so the cursor
    // never skips a window we didn't successfully read.
    dataset.last_airtable_sync = dataset.generated_at;

    const datasetJson = JSON.stringify(dataset);
    fs.writeFileSync(datasetPath, datasetJson);
    fs.writeFileSync(path.join(ROOT, DEFAULT_FILE), buildWidgetHtml(ROOT, datasetJson));

    sendJson(res, 200, {
      added,
      checked: records.length,
      total: dataset.companies.length,
      generated_at: dataset.generated_at,
      dataset,
    });
  } catch (err) {
    sendJson(res, 502, { error: String(err.message || err) });
  }
}

const server = http.createServer((req, res) => {
  if (req.url === "/api/refresh" && req.method === "POST") {
    handleRefresh(req, res).catch((err) => {
      console.error("Unhandled error in /api/refresh:", err);
      if (!res.headersSent) sendJson(res, 500, { error: `Internal error: ${err.message || err}` });
      else if (!res.writableEnded) res.end();
    });
    return;
  }

  const urlPath = req.url === "/" ? `/${DEFAULT_FILE}` : req.url;
  const filePath = resolveSafePath(ROOT, urlPath);

  if (!filePath) {
    res.writeHead(403, { "Content-Type": "text/plain" });
    res.end("Forbidden");
    return;
  }

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end(`Not found: ${urlPath}`);
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, { "Content-Type": MIME_TYPES[ext] || "application/octet-stream" });
    res.end(data);
  });
});

server.on("error", (err) => {
  if (err.code === "EADDRINUSE") {
    console.error(`Port ${PORT} is already in use. Try a different one: node app.js ${PORT + 1}`);
    process.exit(1);
  }
  throw err;
});

server.listen(PORT, HOST, () => {
  console.log(`TGE Tracker running at http://localhost:${PORT}/`);
  console.log(`Serving ${ROOT}`);
  console.log(ENV.AIRTABLE_TOKEN ? "Live refresh: enabled (AIRTABLE_TOKEN found)" : "Live refresh: disabled — see .env.example");
  console.log("Press Ctrl+C to stop.");
});
