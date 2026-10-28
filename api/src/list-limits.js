// Durable account-based counters work across Worker instances. No IP is stored.
export async function limitListWrites(env, userId, creating, now = Date.now()) {
  const minute = Math.floor(now / 60000), hour = Math.floor(now / 3600000);
  const row = await env.DB.prepare(`
    INSERT INTO list_write_limits(user_id, minute, writes, hour, creates) VALUES (?1, ?2, 1, ?3, ?4)
    ON CONFLICT(user_id) DO UPDATE SET
      minute=excluded.minute, writes=CASE WHEN minute=?2 THEN writes+1 ELSE 1 END,
      hour=excluded.hour, creates=CASE WHEN hour=?3 THEN creates+?4 ELSE ?4 END
    WHERE (minute<>?2 OR writes<120) AND (?4=0 OR hour<>?3 OR creates<20)
    RETURNING user_id
  `).bind(userId, minute, hour, creating ? 1 : 0).first();
  if (row) return null;
  const current = await env.DB.prepare('SELECT hour,creates FROM list_write_limits WHERE user_id=?').bind(userId).first();
  const period = creating && current?.hour === hour && current.creates >= 20 ? 3600 : 60;
  const seconds = Math.max(1, period - Math.floor(now / 1000) % period);
  return new Response(JSON.stringify({error:'rate_limited', retry_after:seconds}), {status:429, headers:{
    'Content-Type':'application/json; charset=utf-8', 'Cache-Control':'no-store', 'Retry-After':String(seconds)
  }});
}
