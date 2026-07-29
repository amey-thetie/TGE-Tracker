#!/usr/bin/env node
/**
 * app.js — runs the TGE Tracker locally.
 *
 * Usage:
 *   node app.js [port]        (defaults to 3000)
 *   npm start
 *
 * This is a plain static file server (Node built-ins only, no dependencies)
 * so you can open the widget at a real http:// URL instead of a file://
 * path. It does NOT add any backend or live data-fetching — the dataset
 * is still the point-in-time snapshot baked into tge_tracker_widget.html
 * at build time. To refresh the data itself, see README.md
 * "Refreshing the data" and the scripts/ pipeline.
 */
const http = require("http");
const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
const DEFAULT_FILE = "tge_tracker_widget.html";
const PORT = Number(process.argv[2]) || 3000;

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".py": "text/plain; charset=utf-8",
  ".md": "text/plain; charset=utf-8",
};

function resolveSafePath(root, urlPath) {
  const decoded = decodeURIComponent(urlPath.split("?")[0]);
  const resolved = path.normalize(path.join(root, decoded));
  if (resolved !== root && !resolved.startsWith(root + path.sep)) return null; // block path traversal
  return resolved;
}

const server = http.createServer((req, res) => {
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

server.listen(PORT, () => {
  console.log(`TGE Tracker running at http://localhost:${PORT}/`);
  console.log(`Serving ${ROOT}`);
  console.log("Press Ctrl+C to stop.");
});
