/** Download cloudflared (remote-play tunnel) into desktop/vendor/ if absent.
 *
 * Runs before electron-builder (local desktop:package and CI both call it);
 * the binary is bundled via extraResources. Pinned by "latest" deliberately —
 * quick tunnels are an evergreen client feature, and the exe only updates
 * when a fresh machine (or CI runner) builds.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const https = require('https');

const URL_ = 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe';
const DEST_DIR = path.join(__dirname, '..', 'vendor');
const DEST = path.join(DEST_DIR, 'cloudflared.exe');
const MIN_BYTES = 10 * 1024 * 1024; // sanity: a real build is ~50MB

function download(url, dest, redirects = 0) {
  return new Promise((resolve, reject) => {
    if (redirects > 8) return reject(new Error('too many redirects'));
    https.get(url, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        return resolve(download(res.headers.location, dest, redirects + 1));
      }
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error(`HTTP ${res.statusCode} for ${url}`));
      }
      const tmp = dest + '.tmp';
      const out = fs.createWriteStream(tmp);
      res.pipe(out);
      out.on('finish', () => out.close(() => {
        fs.renameSync(tmp, dest);
        resolve();
      }));
      out.on('error', reject);
    }).on('error', reject);
  });
}

async function main() {
  if (fs.existsSync(DEST) && fs.statSync(DEST).size >= MIN_BYTES) {
    console.log(`cloudflared already present (${(fs.statSync(DEST).size / 1e6).toFixed(1)} MB)`);
    return;
  }
  fs.mkdirSync(DEST_DIR, { recursive: true });
  console.log('downloading cloudflared…');
  await download(URL_, DEST);
  const size = fs.statSync(DEST).size;
  if (size < MIN_BYTES) throw new Error(`downloaded cloudflared looks wrong (${size} bytes)`);
  console.log(`cloudflared ready (${(size / 1e6).toFixed(1)} MB)`);
}

main().catch((err) => {
  console.error('fetch-cloudflared failed:', err.message);
  process.exit(1);
});
