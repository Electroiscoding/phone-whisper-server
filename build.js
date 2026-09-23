const fs = require('fs');
const path = require('path');

const distDir = path.join(__dirname, 'dist');
if (fs.existsSync(distDir)) {
  fs.rmSync(distDir, { recursive: true, force: true });
}
fs.mkdirSync(distDir, { recursive: true });

// Copy all static files from root to dist
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

// Copy _worker.js to dist/
fs.copyFileSync(path.join(__dirname, '_worker.js'), path.join(distDir, '_worker.js'));

// Explicit _routes.json specifying exact paths that must trigger the Worker
const routesJson = {
  version: 1,
  include: [
    "/v1/*",
    "/s/*",
    "/auth/*",
    "/screen/*",
    "/inference*",
    "/telemetry*",
    "/tts*",
    "/speech*",
    "/health*",
    "/models*",
    "/backends*",
    "/register_tunnel*",
    "/probe_worker*"
  ],
  exclude: []
};
fs.writeFileSync(path.join(distDir, '_routes.json'), JSON.stringify(routesJson, null, 2));

console.log('Build completed successfully! dist/ populated with _worker.js, explicit _routes.json, and static assets.');
