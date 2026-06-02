const API_BASE = 'http://localhost:8000';

async function refreshAccessToken(): Promise<string | null> {
  const refresh = localStorage.getItem('refreshToken');
  if (!refresh) return null;

  try {
    const res = await fetch(`${API_BASE}/api/auth/token/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    });

    if (!res.ok) return null;

    const data = await res.json();
    if (data.access) {
      localStorage.setItem('accessToken', data.access);
      return data.access;
    }
  } catch {
    // network error — fall through
  }

  return null;
}

/**
 * Drop-in replacement for fetch() that automatically:
 * 1. Attaches the stored Bearer token.
 * 2. Skips Content-Type when body is FormData (browser sets multipart boundary).
 * 3. On 401, attempts a silent token refresh and retries once.
 * 4. On second 401 (refresh also expired), redirects to /login.
 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  const token = localStorage.getItem('accessToken') ?? '';

  const makeHeaders = (t: string): HeadersInit => {
    const base: Record<string, string> = {
      ...(init.headers as Record<string, string> ?? {}),
      Authorization: `Bearer ${t}`,
    };
    // Don't set Content-Type for FormData — browser sets multipart/form-data with boundary
    if (!(init.body instanceof FormData)) {
      base['Content-Type'] = 'application/json';
    }
    return base;
  };

  let res = await fetch(url, { ...init, headers: makeHeaders(token) });

  if (res.status === 401) {
    const newToken = await refreshAccessToken();

    if (newToken) {
      res = await fetch(url, { ...init, headers: makeHeaders(newToken) });
    }

    if (res.status === 401) {
      // Both tokens expired — force re-login
      localStorage.removeItem('accessToken');
      localStorage.removeItem('refreshToken');
      window.location.href = '/login';
    }
  }

  return res;
}
