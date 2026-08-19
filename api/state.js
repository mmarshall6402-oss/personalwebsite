const U = process.env.KV_REST_API_URL;
const T = process.env.KV_REST_API_TOKEN;

async function redis(cmd) {
  const r = await fetch(U, {
    method: 'POST',
    headers: { Authorization: `Bearer ${T}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(cmd)
  });
  if (!r.ok) throw new Error('store ' + r.status);
  return (await r.json()).result;
}

const clean = k => String(k || '').replace(/[^a-z0-9-]/gi, '').slice(0, 40);

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (!U || !T) return res.status(503).json({ error: 'no_store' });

  const body = req.method === 'GET' ? {} : (typeof req.body === 'string' ? JSON.parse(req.body) : req.body || {});
  const key = clean(req.query.key || body.key);
  if (key.length < 5) return res.status(400).json({ error: 'bad_key' });
  const rk = 'board:' + key;

  try {
    if (req.method === 'GET') {
      const raw = await redis(['GET', rk]);
      return res.status(200).json(raw ? JSON.parse(raw) : { rev: 0, data: null });
    }

    if (req.method === 'PUT' || req.method === 'POST') {
      const raw = await redis(['GET', rk]);
      const cur = raw ? JSON.parse(raw) : { rev: 0, data: null };

      // Optimistic concurrency. A stale writer gets the current doc back
      // and merges client-side rather than clobbering the other device.
      if (Number(body.baseRev) !== Number(cur.rev)) return res.status(409).json(cur);

      const next = { rev: cur.rev + 1, at: Date.now(), data: body.data };
      await redis(['SET', rk, JSON.stringify(next)]);
      return res.status(200).json({ rev: next.rev, at: next.at });
    }

    res.setHeader('Allow', 'GET, PUT');
    return res.status(405).end();
  } catch (e) {
    return res.status(500).json({ error: String(e.message || e) });
  }
}
