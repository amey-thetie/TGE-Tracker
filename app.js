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
 *      traded coin — CoinGecko first, then CoinMarketCap for whatever
 *      CoinGecko could not match (exact name/symbol match only on both —
 *      no fuzzy guessing).
 *   3. Classify each new company with the same rules as the batch
 *      pipeline (scripts/classify.js), merge into data/tge_dataset_full.json,
 *      and rebuild tge_tracker_widget.html on disk.
 *   4. Return the updated dataset so the page can re-render without a
 *      full reload.
 *
 * Requires an Airtable Personal Access Token in a local .env file
 * (AIRTABLE_TOKEN=...) — copy .env.example to get started. Without it,
 * /api/refresh returns a clear error and the static widget still works.
 * The market-data keys are both optional: COINGECKO_API_KEY only raises
 * rate limits (the public API needs no key), and COINMARKETCAP_API_KEY
 * only adds the fallback lookup. Neither is needed to run.
 *
 * Binds to 127.0.0.1 only (not your network) since this now holds a
 * credential and can write to disk.
 */
const http = require("http");
const fs = require("fs");
const path = require("path");

const {
  ingestNewCompanies,
  finalizeDataset,
  readDataset,
  datasetPath,
  runSweep,
} = require("./scripts/sweep");

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

// Background sweep settings, read after ENV so .env can set them.
// SWEEP_INTERVAL_MINUTES=0 disables the scheduler; the manual Refresh button
// keeps working either way.
const SWEEP_INTERVAL_MINUTES = numberOr(ENV.SWEEP_INTERVAL_MINUTES, 60);
const SWEEP_MAX_AGE_MONTHS = numberOr(ENV.SWEEP_MAX_AGE_MONTHS, 12);
const SWEEP_ON_START = String(ENV.SWEEP_ON_START || "").toLowerCase() === "true";

function numberOr(raw, fallback) {
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}

// Both the scheduler and /api/refresh rewrite the same two files, and a sweep
// can run for minutes. Serialize them so a Refresh clicked mid-sweep can't
// interleave two read-modify-write cycles and lose one of them.
let writeLock = null;
function withWriteLock(label, fn) {
  if (writeLock) return Promise.reject(new Error(`Busy: ${writeLock} is already running. Try again in a moment.`));
  writeLock = label;
  return Promise.resolve()
    .then(fn)
    .finally(() => { writeLock = null; });
}

// Cheap snapshot metadata for the widget's poll, re-read only when the file
// actually changes on disk rather than parsing ~600KB every poll.
let snapshotCache = { mtimeMs: -1, generated_at: null, total: 0 };
function snapshotMeta() {
  const p = datasetPath(ROOT);
  const st = fs.statSync(p);
  if (st.mtimeMs !== snapshotCache.mtimeMs) {
    const d = JSON.parse(fs.readFileSync(p, "utf8"));
    snapshotCache = { mtimeMs: st.mtimeMs, generated_at: d.generated_at, total: d.companies.length };
  }
  return snapshotCache;
}

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

async function handleRefresh(req, res) {
  const token = ENV.AIRTABLE_TOKEN;
  if (!token) {
    sendJson(res, 400, {
      error: "AIRTABLE_TOKEN is not set. Copy .env.example to .env and add your Airtable Personal Access Token, then restart the server.",
    });
    return;
  }

  let dataset;
  try {
    dataset = readDataset(ROOT);
  } catch (err) {
    sendJson(res, 500, { error: `Could not read the dataset: ${err.message}` });
    return;
  }

  try {
    const result = await withWriteLock("a manual refresh", async () => {
      const ingest = await ingestNewCompanies(dataset, { token, marketKeys: marketKeys() });
      const generatedAt = finalizeDataset(ROOT, dataset);
      return { ...ingest, generated_at: generatedAt };
    });

    for (const w of result.warnings || []) console.warn(`Refresh warning: ${w}`);

    sendJson(res, 200, {
      added: result.added,
      checked: result.checked,
      total: dataset.companies.length,
      generated_at: result.generated_at,
      warnings: result.warnings || [],
      dataset,
    });
  } catch (err) {
    const msg = String(err.message || err);
    // A sweep holding the write lock is a conflict, not an upstream failure —
    // the widget shows this text verbatim, so it should say "try again", not
    // imply Airtable or CoinGecko broke.
    sendJson(res, msg.startsWith("Busy:") ? 409 : 502, { error: msg });
  }
}

function marketKeys() {
  return {
    coingeckoKey: ENV.COINGECKO_API_KEY,
    coingeckoPlan: ENV.COINGECKO_API_PLAN,
    coinmarketcapKey: ENV.COINMARKETCAP_API_KEY,
  };
}

// --- background sweep ---------------------------------------------------

let sweepTimer = null;

async function runScheduledSweep(trigger) {
  try {
    const result = await withWriteLock("a scheduled sweep", () =>
      runSweep(ROOT, {
        env: ENV,
        monthsBack: SWEEP_MAX_AGE_MONTHS,
        log: (line) => console.log(`  ${line}`),
      })
    );
    const changed = result.added || result.promoted || result.updated;
    console.log(
      `Sweep (${trigger}) done: +${result.added} new, ${result.promoted} status change(s), ` +
      `${result.updated} figure refresh(es)${changed ? "" : " — nothing changed"}`
    );
    for (const w of result.warnings || []) console.warn(`  Sweep warning: ${w}`);
    return result;
  } catch (err) {
    // A sweep failure must never take the server down or stop the schedule.
    console.error(`Sweep (${trigger}) failed: ${err.message || err}`);
    return null;
  }
}

function startScheduler() {
  if (!SWEEP_INTERVAL_MINUTES) {
    console.log("Auto-sweep: disabled (set SWEEP_INTERVAL_MINUTES to enable)");
    return;
  }
  const ms = SWEEP_INTERVAL_MINUTES * 60 * 1000;
  sweepTimer = setInterval(() => { runScheduledSweep("scheduled"); }, ms);
  console.log(
    `Auto-sweep: every ${SWEEP_INTERVAL_MINUTES} min, re-checking rounds from the last ` +
    `${SWEEP_MAX_AGE_MONTHS} months`
  );
  if (SWEEP_ON_START) {
    console.log("Auto-sweep: running one now (SWEEP_ON_START=true)");
    runScheduledSweep("startup");
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

  // Cheap poll target: just the snapshot's identity, so an open tab can tell
  // whether anything changed without pulling the whole dataset every minute.
  if (req.url === "/api/snapshot" && req.method === "GET") {
    try {
      const meta = snapshotMeta();
      sendJson(res, 200, { generated_at: meta.generated_at, total: meta.total, busy: writeLock });
    } catch (err) {
      sendJson(res, 500, { error: String(err.message || err) });
    }
    return;
  }

  // Full dataset, fetched only after /api/snapshot says the timestamp moved.
  if (req.url === "/api/dataset" && req.method === "GET") {
    try {
      const body = fs.readFileSync(datasetPath(ROOT));
      res.writeHead(200, { "Content-Type": "application/json; charset=utf-8", "Content-Length": body.length });
      res.end(body);
    } catch (err) {
      sendJson(res, 500, { error: String(err.message || err) });
    }
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
  const cgPlan = String(ENV.COINGECKO_API_PLAN || "demo").toLowerCase() === "pro" ? "pro" : "demo";
  console.log(
    ENV.COINGECKO_API_KEY
      ? `CoinGecko: keyed (${cgPlan} tier)`
      : "CoinGecko: public API, no key (slower, rate-limited)"
  );
  console.log(
    ENV.COINMARKETCAP_API_KEY
      ? "CoinMarketCap: enabled (fallback for coins CoinGecko can't match)"
      : "CoinMarketCap: disabled — set COINMARKETCAP_API_KEY to enable the fallback"
  );
  startScheduler();
  console.log("Press Ctrl+C to stop.");
});

// Stop the timer on shutdown so a sweep in flight doesn't hold the process open.
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => {
    if (sweepTimer) clearInterval(sweepTimer);
    server.close(() => process.exit(0));
    // Don't wait forever on keep-alive sockets.
    setTimeout(() => process.exit(0), 2000).unref();
  });
}
