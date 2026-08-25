const BASE = (process.env.CANVAS_BASE_URL || '').trim();   // e.g. https://yourschool.instructure.com
const TOKEN = (process.env.CANVAS_TOKEN || '').trim();      // Canvas → Account → Settings → New Access Token

function nextLink(linkHeader) {
  if (!linkHeader) return null;
  const part = linkHeader.split(',').find(p => /rel="next"/.test(p));
  return part ? part.split(';')[0].trim().replace(/^<|>$/g, '') : null;
}

async function canvasGetAll(url) {
  const out = [];
  let next = url;
  while (next) {
    const r = await fetch(next, { headers: { Authorization: `Bearer ${TOKEN}` } });
    if (!r.ok) throw new Error('canvas_' + r.status);
    out.push(...(await r.json()));
    next = nextLink(r.headers.get('link'));
  }
  return out;
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (!BASE || !TOKEN) return res.status(503).json({ error: 'not_configured' });

  const root = BASE.replace(/\/$/, '');

  try {
    // planner/items only covers a ~2 week window; pull every active course's
    // own assignment list instead so nothing past that window is missed.
    const courses = await canvasGetAll(`${root}/api/v1/courses?enrollment_state=active&per_page=100`);

    const perCourse = await Promise.all(courses.map(async c => {
      try {
        const items = await canvasGetAll(`${root}/api/v1/courses/${c.id}/assignments?per_page=100&order_by=due_at`);
        return items.map(a => ({ ...a, courseName: c.name }));
      } catch {
        return []; // course assignments hidden/unpublished for this user — skip it
      }
    }));

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const assignments = perCourse.flat()
      .filter(a => a.due_at && new Date(a.due_at) >= today)
      .map(a => ({
        id: a.id,
        title: a.name,
        course: a.courseName,
        due_at: a.due_at,
        points: a.points_possible ?? null,
        url: a.html_url
      }))
      .sort((a, b) => a.due_at < b.due_at ? -1 : 1);

    return res.status(200).json({ assignments });
  } catch (e) {
    return res.status(500).json({ error: String(e.message || e) });
  }
}
