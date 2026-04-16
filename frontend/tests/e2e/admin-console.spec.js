import { expect, test } from '@playwright/test';

import { buildJwt, mockAuthenticatedShell, seedAuthenticatedSession } from './helpers';

test.describe('SigAuth admin console', () => {
  test('signs in and lands on the dashboard', async ({ page }) => {
    const idToken = buildJwt();

    await mockAuthenticatedShell(page);
    await page.route('**/api/v1/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id_token: idToken }),
      });
    });

    await page.goto('/login');
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();

    await page.getByLabel('Email').fill('admin@internal.com');
    await page.getByLabel('Password').fill('changeme_admin_secret!');
    await page.getByRole('button', { name: 'Sign in' }).click();

    await page.waitForURL('**/dashboard');
    await expect(page.getByText('Welcome back, Admin')).toBeVisible();
    await expect(page.getByText('SigVerse Academy')).toBeVisible();
  });

  test('saves profile and account preferences from settings', async ({ page }) => {
    const idToken = buildJwt();
    await seedAuthenticatedSession(page, { token: idToken });
    await mockAuthenticatedShell(page);

    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();

    await page.getByPlaceholder('First name').fill('Platform');
    await page.getByPlaceholder('Last name').fill('Admin');
    await page.getByRole('button', { name: 'Save profile' }).click();
    await expect(page.getByText('Profile updated.')).toBeVisible();

    await page.getByText('Weekly summary emails').locator('..').getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Save preferences' }).click();
    await expect(page.getByText('Preferences saved.')).toBeVisible();
  });

  test('searches as the user types and clears back to dashboard', async ({ page }) => {
    const idToken = buildJwt();
    await seedAuthenticatedSession(page, { token: idToken });
    await mockAuthenticatedShell(page, {
      usersResponse: {
        data: [
          {
            id: 'user-1',
            email: 'alice@internal.com',
            first_name: 'Alice',
            last_name: 'Analyst',
            profile_image_url: '',
          },
        ],
        pagination: { total: 1 },
      },
      appsResponse: {
        data: [{ id: 'app-1', name: 'SigVerse', app_type: 'spa', client_id: 'sigverse-client-id' }],
        pagination: { total: 1 },
      },
      groupsResponse: {
        data: [{ id: 'group-1', name: 'analytics-team', description: 'Analytics team' }],
      },
      auditResponse: {
        data: [{ id: 200, event_type: 'user.login.success', created_at: new Date().toISOString() }],
      },
    });

    await page.goto('/dashboard');
    const search = page.getByPlaceholder('Search users, apps, groups, events').first();
    await search.fill('alice');

    await page.waitForURL('**/search?q=alice');
    await expect(page.getByRole('heading', { name: 'Results for "alice"' })).toBeVisible();
    await expect(page.getByText('alice@example.com')).toBeVisible();

    await page.getByRole('button', { name: 'Clear search' }).first().click();
    await page.waitForURL('**/dashboard');
    await expect(page.getByRole('heading', { name: 'Welcome back, Admin' })).toBeVisible();
  });
});
