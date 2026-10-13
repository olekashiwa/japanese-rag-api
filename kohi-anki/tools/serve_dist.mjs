/** Простой статический сервер для проверки собранного приложения.
 *  Запуск: node tools/serve_dist.mjs [порт] */

import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, normalize, resolve } from 'node:path';

const rootDir = resolve(process.cwd(), 'dist');
const port = Number(process.argv[2] ?? 4173);

const types = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
};

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? '/', `http://127.0.0.1:${port}`);
    let filePath = join(rootDir, normalize(decodeURIComponent(url.pathname)));
    const info = await stat(filePath).catch(() => null);
    if (!info || info.isDirectory()) filePath = join(rootDir, 'index.html');
    const body = await readFile(filePath);
    response.writeHead(200, { 'content-type': types[extname(filePath)] ?? 'application/octet-stream' });
    response.end(body);
  } catch (error) {
    response.writeHead(500, { 'content-type': 'text/plain; charset=utf-8' });
    response.end(`Ошибка сервера: ${String(error)}`);
  }
});

server.listen(port, '127.0.0.1', () => {
  console.log(`dist обслуживается на http://127.0.0.1:${port}/ (корень: ${rootDir})`);
});
