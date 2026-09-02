import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const packageJsonPath = path.resolve(__dirname, '../package.json');

const target = process.argv[2]; // 'extension' or 'npm'

if (!target || (target !== 'extension' && target !== 'npm')) {
  console.error("Usage: node prepare-package.js [extension|npm]");
  process.exit(1);
}

try {
  const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
  
  if (target === 'extension') {
    packageJson.name = 'swades-agent';
    packageJson.publisher = 'xerv';
    delete packageJson.files; // vsce requires either .vscodeignore or files, not both
  } else if (target === 'npm') {
    packageJson.name = '@xerv/swades-agent';
    packageJson.files = [
      "src/",
      "dist/",
      "README.md",
      "walkthrough.md",
      "LICENSE",
      ".env.example"
    ];
  }
  
  fs.writeFileSync(packageJsonPath, JSON.stringify(packageJson, null, 2), 'utf8');
  console.log(`[prepare-package] Prepared package.json for ${target} (name: "${packageJson.name}")`);
} catch (err) {
  console.error(`[prepare-package] Error: ${err.message}`);
  process.exit(1);
}
