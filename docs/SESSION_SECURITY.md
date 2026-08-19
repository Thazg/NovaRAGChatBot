# Session security architecture

## Session lifecycle

1. Register/login returns a 10-minute access token in the JSON response and sets a 30-day refresh token as a cookie.
2. The frontend keeps the access token only in module/Zustand memory. The persisted store contains preferences only.
3. After a reload, `POST /api/auth/refresh` uses the HttpOnly cookie to restore the session.
4. Refresh tokens are single-use. The backend stores only a SHA-256 token hash, revokes the old record atomically, and rotates the browser cookie.
5. Concurrent frontend refreshes share one promise so React StrictMode, parallel 401 responses, and multiple components cannot replay the same refresh token.
6. Logout revokes the current refresh record and expires the cookie.

Production cookie attributes are:

```text
__Host-nova_refresh=...; Path=/; Max-Age=2592000; Secure; HttpOnly; SameSite=Strict
```

The `__Host-` prefix requires `Secure`, `Path=/`, and no `Domain` attribute. Cookie-backed POST endpoints also reject an untrusted or missing `Origin` in production.

## Same-origin proxy requirement

The browser calls `https://novachatbot.vercel.app/api/*`. Vercel rewrites requests to Render server-side, so cookies stay host-only for the public frontend and the app avoids cross-site cookie behavior. The production frontend must keep:

```env
VITE_API_BASE_URL=/api
```

Do not replace it with the public Render URL.

## Production configuration

```env
ENVIRONMENT=production
JWT_SECRET=<unique random value, at least 32 bytes>
ACCESS_TOKEN_TTL_SECONDS=600
REFRESH_TOKEN_TTL_SECONDS=2592000
COOKIE_SECURE=true
CORS_ORIGINS=https://novachatbot.vercel.app
```

`render.yaml` declares these settings, but secret values marked `sync: false` still need to be entered in Render. Production startup fails closed if `JWT_SECRET` is missing, default, or shorter than 32 bytes.

Generate a secret locally without placing it in Git:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Verification procedure

- DevTools → Application → Local Storage: `rag-chat-storage` must not contain `token`, `userId`, conversations, or the access-token value.
- DevTools → Application → Cookies: production refresh cookie is named `__Host-nova_refresh` and has Secure, HttpOnly, SameSite Strict, and Path `/`.
- Login response and refresh response include `Cache-Control: no-store` and never include a refresh token in JSON.
- Reloading the page restores a valid session through `/api/auth/refresh`.
- Replaying an already-consumed refresh token returns 401 and does not delete a newer rotated cookie.
- Logout removes the cookie; the old refresh token cannot be reused.
- Requests to cookie endpoints from an untrusted Origin return 403.

Automated evidence lives in `backend/tests/test_auth.py`, `backend/tests/test_api.py`, and `frontend/e2e/portfolio-flow.spec.ts`.

## Residual risk

These controls do not eliminate cross-site scripting risk. The Vercel Content
Security Policy and memory-only access token reduce exposure, while dependency
review, output sanitization, and continuing security testing remain required.
Upload and SSRF controls are documented separately in
[`UPLOAD_SECURITY.md`](./UPLOAD_SECURITY.md).
