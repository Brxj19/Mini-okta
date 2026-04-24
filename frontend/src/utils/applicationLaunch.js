export function getApplicationLaunchUrl(app) {
  const firstRedirect = app?.redirect_uris?.[0];
  if (!firstRedirect) return null;

  try {
    const parsed = new URL(firstRedirect);
    const normalizedPath = parsed.pathname.replace(/\/+$/, '') || '/';

    if (app?.app_type === 'web' && normalizedPath === '/auth/callback') {
      return `${parsed.origin}/auth/login`;
    }

    return `${parsed.origin}/`;
  } catch {
    return null;
  }
}
