import path from 'node:path';

import { expect, test, type Page, type Route } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const API_PATTERN = /https?:\/\/(?:localhost|127\.0\.0\.1):(?:8000|8001)\/.*/;
const CORS_HEADERS = {
  'access-control-allow-origin': 'http://127.0.0.1:4173',
  'access-control-allow-credentials': 'true',
  'access-control-allow-headers': '*',
  'access-control-allow-methods': '*',
};

async function fulfillJson(route: Route, data: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    headers: CORS_HEADERS,
    body: JSON.stringify(data),
  });
}

async function mockPortfolioApi(
  page: Page,
  options: { disconnectFirstStream?: boolean; activeSession?: boolean } = {},
) {
  let documents: Array<Record<string, unknown>> = [];
  let streamAttempts = 0;
  let refreshAttempts = 0;

  await page.route(API_PATTERN, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const endpoint = url.pathname;

    if (method === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: CORS_HEADERS });
      return;
    }

    if (method === 'POST' && endpoint === '/auth/login') {
      await fulfillJson(route, {
        access_token: 'portfolio-e2e-access-token-that-is-memory-only',
        user_id: '6ab4ef03-50ba-4782-95db-ecc55d64c53d',
        username: 'portfolio.user',
      });
      return;
    }
    if (method === 'POST' && endpoint === '/auth/refresh') {
      refreshAttempts += 1;
      if (options.activeSession) {
        await fulfillJson(route, {
          access_token: 'restored-e2e-access-token-that-is-memory-only',
          user_id: '6ab4ef03-50ba-4782-95db-ecc55d64c53d',
          username: 'portfolio.user',
        });
      } else {
        await fulfillJson(route, { detail: 'No active session' }, 401);
      }
      return;
    }
    if (method === 'POST' && endpoint === '/auth/logout') {
      await route.fulfill({ status: 204, headers: CORS_HEADERS });
      return;
    }
    if (method === 'GET' && endpoint === '/auth/me') {
      await fulfillJson(route, { user_id: '6ab4ef03-50ba-4782-95db-ecc55d64c53d' });
      return;
    }
    if (method === 'GET' && endpoint === '/health/ready') {
      await fulfillJson(route, {
        status: 'ready',
        ready: true,
        provider_status: 'reachable',
        model: 'llama-3.1-8b-instant',
        model_available: true,
        message: 'AI provider is ready.',
      });
      return;
    }
    if (method === 'GET' && endpoint === '/documents') {
      await fulfillJson(route, documents);
      return;
    }
    if (method === 'POST' && endpoint === '/documents/upload') {
      documents = [{
        id: 'portfolio.txt',
        name: 'portfolio.txt',
        size: 168,
        indexed: true,
        chunks: 1,
      }];
      await fulfillJson(route, {
        status: 'success',
        id: 'portfolio.txt',
        filename: 'portfolio.txt',
        indexed: true,
        chunks: 1,
      });
      return;
    }
    if (method === 'GET' && endpoint === '/conversation') {
      await fulfillJson(route, []);
      return;
    }
    if (method === 'POST' && endpoint === '/conversation/new') {
      const body = request.postDataJSON();
      await fulfillJson(route, {
        id: body.id,
        title: body.title,
        messages: body.messages,
        pinned: body.pinned,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      });
      return;
    }
    if (method === 'POST' && endpoint === '/chat/stream') {
      streamAttempts += 1;
      if (options.disconnectFirstStream && streamAttempts === 1) {
        await route.abort('connectionfailed');
        return;
      }
      const events = [
        { token: 'Nova combines BM25 lexical retrieval with FAISS vectors. ' },
        { token: 'Reciprocal rank fusion merges both rankings. ' },
        { token: '(Source: portfolio.txt)' },
      ];
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: { ...CORS_HEADERS, 'cache-control': 'no-cache' },
        body: `${events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')}data: [DONE]\n\n`,
      });
      return;
    }

    await fulfillJson(route, { detail: `Unmocked E2E endpoint: ${method} ${endpoint}` }, 404);
  });

  return {
    refreshAttempts: () => refreshAttempts,
  };
}

test('defaults to dark and restores an explicit light preference', async ({ page }) => {
  await mockPortfolioApi(page);
  await page.goto('/');
  await expect(page.locator('html')).toHaveClass(/dark/);

  await page.evaluate(() => {
    localStorage.setItem('rag-chat-storage', JSON.stringify({
      state: { theme: 'light' },
      version: 2,
    }));
  });
  await page.reload();

  await expect(page.locator('html')).toHaveClass(/light/);
});

test('logs in, uploads a document, chats, and receives a citation', async ({ page }) => {
  const consoleErrors: string[] = [];
  const unexpectedHttpErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error' && !message.text().startsWith('Failed to load resource:')) {
      consoleErrors.push(message.text());
    }
  });
  page.on('response', (response) => {
    const pathname = new URL(response.url()).pathname;
    if (response.status() >= 400 && pathname !== '/auth/refresh') {
      unexpectedHttpErrors.push(`${response.status()} ${pathname}`);
    }
  });
  await mockPortfolioApi(page);

  await page.goto('/');
  await page.getByPlaceholder('Enter username').fill('portfolio.user');
  await page.getByPlaceholder('Enter password').fill('strong-password');
  await page.getByRole('button', { name: 'Sign In' }).click();

  await expect(page.getByRole('heading', { name: 'Welcome to Nova' })).toBeVisible({ timeout: 15_000 });
  const persistedAfterLogin = await page.evaluate(() => localStorage.getItem('rag-chat-storage'));
  expect(persistedAfterLogin).not.toContain('portfolio-e2e-access-token');
  expect(persistedAfterLogin).not.toContain('"token"');
  const chooserPromise = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: /Upload a document/ }).click();
  const chooser = await chooserPromise;
  await chooser.setFiles(path.join(process.cwd(), 'e2e', 'fixtures', 'portfolio.txt'));

  const messageInput = page.getByLabel('Message input');
  await expect(messageInput).toBeVisible();
  await messageInput.fill('How does Nova combine lexical and semantic retrieval?');
  await page.getByRole('button', { name: 'Send message' }).click();

  await expect(page.getByText(/Reciprocal rank fusion merges both rankings/)).toBeVisible();
  await expect(page.getByText(/Source: portfolio\.txt/)).toBeVisible();
  expect(consoleErrors).toEqual([]);
  expect(unexpectedHttpErrors).toEqual([]);
});

test('restores a cookie session while removing legacy localStorage credentials', async ({ page }) => {
  const apiMock = await mockPortfolioApi(page, { activeSession: true });
  await page.addInitScript(() => {
    localStorage.setItem('rag-chat-storage', JSON.stringify({
      state: {
        token: 'legacy-local-storage-token',
        userId: 'legacy-user',
        username: 'legacy-name',
        conversations: [{ id: 'legacy-conversation', title: 'Stale', messages: [] }],
        currentConversationId: 'legacy-conversation',
        theme: 'dark',
      },
      version: 2,
    }));
  });

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Welcome to Nova' })).toBeVisible({ timeout: 15_000 });
  expect(apiMock.refreshAttempts()).toBe(1);

  const persisted = await page.evaluate(() => localStorage.getItem('rag-chat-storage'));
  expect(persisted).not.toContain('legacy-local-storage-token');
  expect(persisted).not.toContain('legacy-user');
  expect(persisted).not.toContain('legacy-conversation');
});

test('login screen has no serious accessibility violations', async ({ page }) => {
  await mockPortfolioApi(page);
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  const serious = results.violations.filter((violation) =>
    violation.impact === 'serious' || violation.impact === 'critical'
  );
  expect(serious).toEqual([]);
});

test('login visual regression', async ({ page }) => {
  await mockPortfolioApi(page);
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  await expect(page).toHaveScreenshot('login-dark.png', {
    fullPage: true,
    animations: 'disabled',
    maxDiffPixelRatio: 0.01,
    timeout: 15_000,
  });
});

test('reconnects when SSE disconnects before the first token', async ({ page }) => {
  await mockPortfolioApi(page, { disconnectFirstStream: true });
  await page.goto('/');
  await page.getByPlaceholder('Enter username').fill('portfolio.user');
  await page.getByPlaceholder('Enter password').fill('strong-password');
  await page.getByRole('button', { name: 'Sign In' }).click();

  const chooserPromise = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: /Upload a document/ }).click();
  const chooser = await chooserPromise;
  await chooser.setFiles(path.join(process.cwd(), 'e2e', 'fixtures', 'portfolio.txt'));

  const messageInput = page.getByLabel('Message input');
  await messageInput.fill('How is retrieval combined?');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByText(/Source: portfolio\.txt/)).toBeVisible();
});
