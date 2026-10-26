/** Keep local frontend/API cookie hosts aligned; production always uses its proxy. */
export function resolveAPIBaseURL(production: boolean, configured: string | undefined, hostname: string): string {
  if (production) return '/api';
  return (configured?.trim() || `http://${hostname || 'localhost'}:8000`).replace(/\/+$/, '');
}
