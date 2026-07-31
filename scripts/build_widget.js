const fs = require('fs');
const path = require('path');

const MARKER = /\/\*__DATA__\*\/.*?\/\*__END_DATA__\*\//s;

// Injects data/tge_dataset_full.json into widget_template.html and returns
// the resulting HTML string. Exported so app.js can call this directly
// after a live refresh, instead of shelling out to `node scripts/build_widget.js`.
function buildWidgetHtml(root, datasetJsonString) {
  const template = fs.readFileSync(path.join(root, 'widget_template.html'), 'utf8');
  const dataset = datasetJsonString || fs.readFileSync(path.join(root, 'data', 'tge_dataset_full.json'), 'utf8');
  if (!MARKER.test(template)) {
    throw new Error('placeholder not found in widget_template.html');
  }
  return template.replace(MARKER, dataset);
}

function main() {
  const root = path.join(__dirname, '..');
  const html = buildWidgetHtml(root);
  const outPath = path.join(root, 'tge_tracker_widget.html');
  fs.writeFileSync(outPath, html);
  console.log('wrote', outPath, '(' + Buffer.byteLength(html) + ' bytes)');
}

module.exports = { buildWidgetHtml };

if (require.main === module) main();
