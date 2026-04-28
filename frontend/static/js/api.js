export async function api(method, url, body = undefined, opts = {}) {
  const redirectOn401 = opts.redirectOn401 !== false;
  const fetchOpts = { method, credentials: 'include', headers: {} };
  if (body !== undefined && body !== null) {
    if (body instanceof FormData) {
      fetchOpts.body = body;
    } else {
      fetchOpts.headers['Content-Type'] = 'application/json';
      fetchOpts.body = JSON.stringify(body);
    }
  }
  const res = await fetch(url, fetchOpts);
  if (res.status === 401) {
    if (redirectOn401) {
      window.location.href = '/';
    }
    throw new Error('unauth');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const d = err.detail;
    let msg;
    if (typeof d === 'string') msg = d;
    else if (Array.isArray(d)) msg = d.map((e) => e.msg || JSON.stringify(e)).join(', ');
    else msg = `HTTP ${res.status}`;
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}
