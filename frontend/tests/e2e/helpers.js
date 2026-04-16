export function buildJwt(payloadOverrides = {}) {
  const header = { alg: 'none', typ: 'JWT' };
  const payload = {
    iss: 'http://localhost:8000',
    sub: 'user-1',
    aud: 'admin-console',
    exp: Math.floor(Date.now() / 1000) + 60 * 60,
    iat: Math.floor(Date.now() / 1000),
    jti: 'token-jti',
    email: 'admin@example.com',
    email_verified: true,
    name: 'Admin User',
    given_name: 'Admin',
    family_name: 'User',
    org_id: 'org-123',
    is_super_admin: false,
    roles: ['org:admin'],
    permissions: ['app:read', 'user:read', 'group:read', 'role:read', 'audit:read', 'org:read'],
    groups: ['admins'],
    group_ids: ['group-1'],
    app_groups: [],
    app_group_ids: [],
    app_roles: ['app:admin'],
    ...payloadOverrides,
  };

  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  return `${encode(header)}.${encode(payload)}.sig`;
}

export async function seedAuthenticatedSession(page, { token, orgId = 'org-123', rememberBrowser = true } = {}) {
  await page.addInitScript(
    ({ seededToken, seededOrgId, seededRememberBrowser }) => {
      window.localStorage.setItem('idp_token', seededToken);
      window.localStorage.setItem('active_org_id', seededOrgId);
      window.localStorage.setItem('idp_remember_browser', String(Boolean(seededRememberBrowser)));
    },
    { seededToken: token, seededOrgId: orgId, seededRememberBrowser: rememberBrowser },
  );
}

export async function mockAuthenticatedShell(page, overrides = {}) {
  const profile = {
    id: 'user-1',
    email: 'admin@example.com',
    first_name: 'Admin',
    last_name: 'User',
    profile_image_url: '',
    ...overrides.profile,
  };
  const organization = {
    id: 'org-123',
    name: 'sigverse-academy',
    display_name: 'SigVerse Academy',
    slug: 'sigverse-academy',
    status: 'active',
    access_tier: 'verified_enterprise',
    verification_status: 'approved',
    ...overrides.organization,
  };
  const notifications = overrides.notifications ?? [];
  const sessions = overrides.sessions ?? [
    {
      jti: 'session-1',
      client_id: 'admin-console',
      user_agent: 'Playwright',
      ip_address: '127.0.0.1',
      issued_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
      current: true,
    },
  ];
  const usersResponse = overrides.usersResponse ?? { data: [], pagination: { total: 3 } };
  const appsResponse = overrides.appsResponse ?? { data: [], pagination: { total: 2 } };
  const groupsResponse = overrides.groupsResponse ?? { data: [] };
  const auditResponse = overrides.auditResponse ?? {
    data: [
      {
        id: 101,
        event_type: 'user.login.success',
        created_at: new Date().toISOString(),
      },
    ],
  };

  await page.route('**/api/v1/me/profile', async (route) => {
    if (route.request().method() === 'PATCH') {
      const body = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...profile,
          first_name: body.first_name,
          last_name: body.last_name,
          profile_image_url: body.profile_image_url,
        }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(profile) });
  });

  await page.route('**/api/v1/notifications?limit=20', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: notifications, unread_count: notifications.filter((item) => !item.read).length }),
    });
  });

  await page.route('**/api/v1/organizations/*/plan-status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        org_id: organization.id,
        org_name: organization.display_name,
        org_slug: organization.slug,
        access_tier: organization.access_tier,
        verification_status: organization.verification_status,
        current_plan_code: 'admin_provisioned',
        current_plan: { code: 'admin_provisioned', name: 'Admin Provisioned' },
      }),
    });
  });

  await page.route('**/api/v1/me/organization', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(organization) });
  });

  await page.route('**/api/v1/me/preferences', async (route) => {
    if (route.request().method() === 'PUT') {
      const body = route.request().postDataJSON();
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ security_alerts: true, weekly_summary_emails: false }),
    });
  });

  await page.route('**/api/v1/me/mfa', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ enabled: true, org_enforced: false, recovery_codes_remaining: 6 }),
    });
  });

  await page.route('**/api/v1/me/sessions', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: sessions }) });
  });

  await page.route('**/api/v1/me/sessions/*', async (route) => {
    await route.fulfill({ status: 204, body: '' });
  });

  await page.route('**/api/v1/organizations/*/users?*', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(usersResponse) });
  });

  await page.route('**/api/v1/organizations/*/applications?*', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(appsResponse) });
  });

  await page.route('**/api/v1/organizations/*/groups?*', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(groupsResponse) });
  });

  await page.route('**/api/v1/organizations/*/audit-log?*', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(auditResponse) });
  });

  await page.route('**/api/v1/logout', async (route) => {
    await route.fulfill({ status: 204, body: '' });
  });
}
