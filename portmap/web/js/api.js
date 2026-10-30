// Talks to server.py. The whole network document is loaded and saved at once;
// `revision` lets the server refuse a save based on stale data (HTTP 409).

export class ConflictError extends Error {}

export async function loadNetwork() {
  const res = await fetch('api/network', { cache: 'no-store' });
  if (!res.ok) throw new Error(`load failed: HTTP ${res.status}`);
  return { doc: await res.json(), source: res.headers.get('X-Portmap-Source') ?? 'data' };
}

export async function saveNetwork(doc) {
  const res = await fetch('api/network', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(doc),
  });
  const body = await res.json().catch(() => ({}));
  if (res.status === 409) throw new ConflictError(body.error ?? 'conflict');
  if (!res.ok) throw new Error(body.error ?? `save failed: HTTP ${res.status}`);
  return body;
}
