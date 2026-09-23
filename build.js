const fs = require('fs');
const path = require('path');

const distDir = path.join(__dirname, 'dist');
if (fs.existsSync(distDir)) {
  fs.rmSync(distDir, { recursive: true, force: true });
}
fs.mkdirSync(distDir, { recursive: true });

// Copy all static files (*.html, *.js, *.json, etc.) from root to dist
const files = fs.readdirSync(__dirname);
for (const file of files) {
  if (file === 'dist' || file === 'node_modules' || file.startsWith('.')) continue;
  const src = path.join(__dirname, file);
  const dest = path.join(distDir, file);
  const stat = fs.statSync(src);
  if (stat.isFile()) {
    fs.copyFileSync(src, dest);
  }
}

// Ensure _worker.js is in dist/
fs.copyFileSync(path.join(__dirname, '_worker.js'), path.join(distDir, '_worker.js'));

// Explicit _routes.json so Pages routes all paths to _worker.js
const routesJson = {
  version: 1,
  include: ["/*"],
  exclude: []
};
fs.writeFileSync(path.join(distDir, '_routes.json'), JSON.stringify(routesJson, null, 2));

console.log('Build completed successfully! dist/ created with _worker.js and static assets.');
