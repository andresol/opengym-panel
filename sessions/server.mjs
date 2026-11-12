import http from 'node:http';
import fs from 'node:fs';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { SessionService, OpenGymApi } from './service.mjs';
import { PanelError, VERSION } from './model.mjs';

const same = (a, b) => {
  const first = Buffer.from(a || ''), second = Buffer.from(b || '');
  return first.length === second.length && first.length > 0 && crypto.timingSafeEqual(first, second);
};

async function readCommand(request) {
  if (String(request.headers['content-type'] || '').split(';')[0].trim() !== 'application/json') throw new PanelError('invalid_action');
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 2048) throw new PanelError('invalid_action', 413);
    chunks.push(chunk);
  }
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8')); }
  catch { throw new PanelError('invalid_action'); }
}

export function makeSessionServer({ service, readToken, writeToken }) {
  if (typeof readToken !== 'string' || typeof writeToken !== 'string' || readToken.length < 32 || writeToken.length < 32 || readToken === writeToken) {
    throw new Error('Separate private read/write credentials are required');
  }
  const server = http.createServer(async (request, response) => {
    const json = (status, value) => {
      const body = JSON.stringify(value);
      if (Buffer.byteLength(body) > 64000) {
        response.writeHead(503, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
        response.end('{"error":"workout_too_large"}');
        return;
      }
      response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff', 'Content-Length': Buffer.byteLength(body) });
      response.end(body);
    };
    try {
      const url = new URL(request.url, 'http://panel.local');
      if (request.method === 'GET' && url.pathname === '/health' && !url.search) {
        return json(200, { ok: true, version: VERSION });
      }
      const authorization = request.headers.authorization;
      if (request.method === 'GET') {
        if (!same(authorization, `Bearer ${readToken}`) && !same(authorization, `Bearer ${writeToken}`)) {
          throw new PanelError('unauthorized', 401);
        }
        if (url.pathname === '/api/profiles' && !url.search) return json(200, service.list());
        const match = url.pathname.match(/^\/api\/profiles\/([a-z][a-z0-9-]{0,30})\/plan$/);
        if (!match) throw new PanelError('not_found', 404);
        if ([...url.searchParams.keys()].some(key => !['day', 'routine'].includes(key)) ||
            url.searchParams.getAll('day').length > 1 || url.searchParams.getAll('routine').length > 1) {
          throw new PanelError('invalid_day');
        }
        const day = url.searchParams.get('day');
        const routine = url.searchParams.get('routine');
        if (day !== null && !/^[0-6]$/.test(day)) throw new PanelError('invalid_day');
        if (routine !== null && !/^[a-f0-9]{24}$/.test(routine)) throw new PanelError('invalid_routine');
        return json(200, service.view(match[1], day === null ? null : Number(day), routine));
      }
      // The former read-only key can never grant workout-write authority.
      if (!same(authorization, `Bearer ${writeToken}`)) throw new PanelError('unauthorized', 401);
      const match = url.pathname.match(/^\/api\/profiles\/([a-z][a-z0-9-]{0,30})\/action$/);
      if (request.method !== 'POST' || !match || url.search) throw new PanelError('not_found', 404);
      const command = await readCommand(request);
      return json(200, await service.enqueue(match[1], command));
    } catch (error) {
      if (error instanceof PanelError) return json(error.status, { error: error.code });
      return json(503, { error: 'service_unavailable' });
    }
  });
  server.requestTimeout = 12000;
  server.headersTimeout = 5000;
  server.keepAliveTimeout = 1000;
  server.maxConnections = 12;
  return server;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const config = JSON.parse(fs.readFileSync(process.env.SESSION_CONFIG, 'utf8'));
  const service = new SessionService({ profiles: config.profiles,
    dataDir: process.env.DATA_DIR, storeDir: process.env.SESSION_DIR,
    api: new OpenGymApi(process.env.PANEL_API_ORIGIN ?? config.apiOrigin) });
  setInterval(() => service.retrySaving().catch(() => {}), 15000).unref();
  makeSessionServer({ service, readToken: config.readToken, writeToken: config.writeToken })
    .listen(Number(process.env.PORT || 8894), '0.0.0.0');
}
