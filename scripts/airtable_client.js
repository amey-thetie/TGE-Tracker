// scripts/airtable_client.js
// Thin wrapper over Airtable's REST API (not the MCP tool - this runs in a
// plain Node server that only has whatever token the user supplies via
// .env). Requires Node 18+ for global fetch.

const BASE_URL = "https://api.airtable.com/v0";

async function airtableFetch(token, baseId, tableId, params) {
  const url = new URL(`${BASE_URL}/${baseId}/${encodeURIComponent(tableId)}`);
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null) url.searchParams.set(k, v);
  }
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Airtable API error ${res.status}: ${body.slice(0, 300)}`);
  }
  return res.json();
}

// Fetches funded_companies records newer than sinceIso (created_timestamp),
// sorted newest-first, capped at maxRecords as a safety bound.
async function fetchRecentFundedCompanies(token, { baseId, tableId, sinceIso, maxRecords = 300 }) {
  const records = [];
  let offset;
  const filterByFormula = sinceIso
    ? `IS_AFTER({created_timestamp}, DATETIME_PARSE("${sinceIso}"))`
    : undefined;
  do {
    const params = {
      pageSize: 100,
      "sort[0][field]": "created_timestamp",
      "sort[0][direction]": "desc",
    };
    if (filterByFormula) params.filterByFormula = filterByFormula;
    if (offset) params.offset = offset;
    const page = await airtableFetch(token, baseId, tableId, params);
    records.push(...page.records);
    offset = page.offset;
  } while (offset && records.length < maxRecords);
  return records;
}

module.exports = { airtableFetch, fetchRecentFundedCompanies };
