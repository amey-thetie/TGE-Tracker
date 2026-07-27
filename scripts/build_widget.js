const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const template = fs.readFileSync(path.join(root, 'widget_template.html'), 'utf8');
const dataset = fs.readFileSync(path.join(root, 'data', 'tge_dataset_full.json'), 'utf8');

const marker = /\/\*__DATA__\*\/.*?\/\*__END_DATA__\*\//s;
if (!marker.test(template)) {
  console.error('placeholder not found in template');
  process.exit(1);
}

const out = template.replace(marker, dataset);
const outPath = path.join(root, 'tge_tracker_widget.html');
fs.writeFileSync(outPath, out);
console.log('wrote', outPath, '(' + fs.statSync(outPath).size + ' bytes)');
