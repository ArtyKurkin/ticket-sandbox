/** Same-origin Django session requests; CSRF token comes from the rendered page. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const url = new URL(path, window.location.origin);
  if (url.origin !== window.location.origin) {
    throw new Error('API requests must use the Django origin');
  }
  const method = (init.method ?? 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    const token = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content;
    if (!token) throw new Error('Missing Django CSRF token');
    headers.set('X-CSRFToken', token);
  }
  return fetch(url, { ...init, method, headers, credentials: 'same-origin', mode: 'same-origin' });
}
