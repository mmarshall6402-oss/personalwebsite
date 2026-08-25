const BASE = (process.env.CANVAS_BASE_URL || '').trim();   // e.g. https://yourschool.instructure.com
const TOKEN = (process.env.CANVAS_TOKEN || '').trim();      // Canvas → Account → Settings → New Access Token

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (!BASE || !TOKEN) return res.status(503).json({ error: 'not_configured' });

  const today = new Date().toISOString().slice(0, 10);
  const url = `${BASE.replace(/\/$/, '')}/api/v1/planner/items?start_date=${today}&per_page=50`;

  try {
    const r = await fetch(url, { headers: { Authorization: `Bearer ${TOKEN}` } });
    if (!r.ok) return res.status(502).json({ error: 'canvas_' + r.status });

    const items = await r.json();
    const assignments = items
      .filter(i => i.plannable_type === 'assignment' && i.plannable?.due_at)
      .map(i => ({
        id: i.plannable_id,
        title: i.plannable.title,
        course: i.context_name || '',
        due_at: i.plannable.due_at,
        points: i.plannable.points_possible ?? null,
        url: i.html_url
      }))
      .sort((a, b) => a.due_at < b.due_at ? -1 : 1);

    return res.status(200).json({ assignments });
  } catch (e) {
    return res.status(500).json({ error: String(e.message || e) });
  }
}
