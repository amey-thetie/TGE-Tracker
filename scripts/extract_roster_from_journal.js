const fs = require('fs');

const journalPath = process.argv[2];
const outPath = process.argv[3];

const lines = fs.readFileSync(journalPath, 'utf8').split('\n').filter(Boolean);
console.log('journal lines:', lines.length);

let allCompanies = [];
let batchCount = 0;

for (const line of lines) {
  let entry;
  try { entry = JSON.parse(line); } catch (e) { console.log('skip unparsable line'); continue; }
  console.log('line type:', entry.type, 'label:', entry.label || entry.agent || '');
  if (entry.type === 'result' && entry.result && Array.isArray(entry.result.companies)) {
    allCompanies.push(...entry.result.companies);
    batchCount++;
    console.log(`  -> batch ${batchCount}: +${entry.result.companies.length} (running total ${allCompanies.length}), last_next_marker=${entry.result.last_next_marker ? 'present' : 'EMPTY'}`);
  }
}

// dedupe by company_uid just in case
const byUid = new Map();
for (const c of allCompanies) byUid.set(c.company_uid, c.company_name);
const deduped = Array.from(byUid.entries()).map(([company_uid, company_name]) => ({ company_uid, company_name }));

console.log('total collected:', allCompanies.length, 'deduped:', deduped.length);
fs.writeFileSync(outPath, JSON.stringify(deduped));
console.log('wrote', outPath);
