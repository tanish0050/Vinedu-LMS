import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { join, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { handleApi } from './auth.js';

const root = join(fileURLToPath(new URL('.', import.meta.url)), 'public');
const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml' };
const server = http.createServer(async (req, res) => {
  const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  if (pathname.startsWith('/api/')) { try { await handleApi(req, res); } catch (error) { console.error(error); if (!res.headersSent) { res.writeHead(error.status || 500, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }); res.end(JSON.stringify({ error: error.status ? error.message : 'Something went wrong. Please try again.' })); } } return; }
  const requested = pathname === '/' ? '/index.html' : pathname;
  if (!['/index.html', '/app.js', '/styles.css'].includes(requested)) { res.writeHead(404); res.end('Not found'); return; }
  try {
    const body = await readFile(join(root, requested));
    res.writeHead(200, { 'Content-Type': types[extname(requested)] || 'application/octet-stream', 'Cache-Control': 'no-cache', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'strict-origin-when-cross-origin', 'X-Frame-Options': 'DENY', 'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'" });
    res.end(body);
  } catch {
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }); res.end('Not found');
  }
});
server.listen(process.env.PORT || 3000, '0.0.0.0', () => console.log(`Vinedu LMS ready on port ${process.env.PORT || 3000}`));
