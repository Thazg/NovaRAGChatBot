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
  options: { disconnectFirstStream?: boolean; activeSession?: boolean; unavailableSession?: boolean } = {},
) {
  let documents: Array<Record<string, unknown>> = [];
  let streamAttempts = 0;
  let refreshAttempts = 0;
  let lastChatRequest: Record<string, unknown> | null = null;
  let preferences = {
    display_name: 'Portfolio User',
    theme: 'dark',
    language: 'auto',
    character_style: 'warm',
    nickname: '',
    custom_instructions: '',
  };

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
      if (options.unavailableSession) {
        await route.abort('connectionfailed');
        return;
      }
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
    if (method === 'GET' && endpoint === '/auth/preferences') {
      await fulfillJson(route, preferences);
      return;
    }
    if ((method === 'PUT' || method === 'PATCH') && endpoint === '/auth/preferences') {
      preferences = { ...preferences, ...request.postDataJSON() };
      await fulfillJson(route, preferences);
      return;
    }
    if (method === 'GET' && endpoint === '/health/ready') {
      await fulfillJson(route, {
        status: 'ready',
        ready: true,
        provider_status: 'reachable',
        model: 'openai/gpt-oss-20b',
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
      lastChatRequest = request.postDataJSON();
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
    lastChatRequest: () => lastChatRequest,
    preferences: () => preferences,
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

  await expect(page.getByRole('heading', { name: 'Add your first document' })).toBeVisible({ timeout: 15_000 });
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
  await expect(page.getByRole('heading', { name: 'Add your first document' })).toBeVisible({ timeout: 15_000 });
  expect(apiMock.refreshAttempts()).toBe(1);

  const persisted = await page.evaluate(() => localStorage.getItem('rag-chat-storage'));
  expect(persisted).not.toContain('legacy-local-storage-token');
  expect(persisted).not.toContain('legacy-user');
  expect(persisted).not.toContain('legacy-conversation');
});

test('offers session recovery when the API is temporarily unavailable', async ({ page }) => {
  await mockPortfolioApi(page, { unavailableSession: true });
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Your session is still recoverable' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry session' })).toBeVisible();
  await page.getByRole('button', { name: 'Go to sign in' }).click();
  await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
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

test('reconnects mid-stream without duplicating rendered tokens', async ({ page }) => {
  await mockPortfolioApi(page);
  await page.goto('/');
  await page.getByPlaceholder('Enter username').fill('portfolio.user');
  await page.getByPlaceholder('Enter password').fill('strong-password');
  await page.getByRole('button', { name: 'Sign In' }).click();

  const chooserPromise = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: /Upload a document/ }).click();
  const chooser = await chooserPromise;
  await chooser.setFiles(path.join(process.cwd(), 'e2e', 'fixtures', 'portfolio.txt'));

  await page.evaluate(() => {
    const nativeFetch = window.fetch.bind(window);
    let streamCalls = 0;
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (!url.endsWith('/chat/stream')) return nativeFetch(input, init);
      streamCalls += 1;
      const first = 'Nova combines BM25 lexical retrieval with FAISS vectors. ';
      if (streamCalls === 1) {
        const body = new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify({ token: first })}\n\n`));
            setTimeout(() => controller.error(new Error('simulated mid-stream disconnect')), 30);
          },
        });
        return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
      }
      const events = [
        { token: first },
        { token: 'Reciprocal rank fusion merges both rankings. ' },
        { token: '(Source: portfolio.txt)' },
      ];
      return new Response(
        `${events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')}data: [DONE]\n\n`,
        { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
      );
    };
  });

  const messageInput = page.getByLabel('Message input');
  await messageInput.fill('How is retrieval combined?');
  await page.getByRole('button', { name: 'Send message' }).click();

  const answer = page.getByText(/Nova combines BM25 lexical retrieval/).last();
  await expect(answer).toContainText('Reciprocal rank fusion merges both rankings.');
  await expect(answer).toContainText('(Source: portfolio.txt)');
  await expect(answer).not.toContainText('vectors. Nova combines');
});

test('scopes chat requests to a selected document and keeps settings usable', async ({ page }) => {
  const apiMock = await mockPortfolioApi(page);
  await page.goto('/');
  await page.getByPlaceholder('Enter username').fill('portfolio.user');
  await page.getByPlaceholder('Enter password').fill('strong-password');
  await page.getByRole('button', { name: 'Sign In' }).click();

  await expect(page.getByRole('heading', { name: 'Add your first document' })).toBeVisible({ timeout: 15_000 });
  const chooserPromise = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Upload a document' }).click();
  const chooser = await chooserPromise;
  await chooser.setFiles(path.join(process.cwd(), 'e2e', 'fixtures', 'portfolio.txt'));

  await page.getByRole('button', { name: 'Docs' }).click();
  await page.getByRole('button', { name: 'Ask questions about portfolio.txt' }).click();
  await expect(page.getByText('Document scope')).toBeVisible();
  await expect(page.getByPlaceholder('Ask about portfolio.txt...')).toBeVisible();

  const messageInput = page.getByLabel('Message input');
  await messageInput.fill('Summarize this document.');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByText(/Reciprocal rank fusion merges both rankings/)).toBeVisible();
  expect(apiMock.lastChatRequest()).toMatchObject({ document_name: 'portfolio.txt' });

  await page.getByRole('button', { name: 'Open settings' }).click();
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
  await page.getByRole('button', { name: 'Light', exact: true }).click();
  await expect(page.locator('html')).toHaveClass(/light/);
  await expect(page.getByText('Preferences save automatically')).toBeVisible();
  await expect.poll(() => apiMock.preferences().theme).toBe('light');
});

test('keeps the mobile workspace and settings navigation usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockPortfolioApi(page);
  await page.goto('/');
  await page.getByPlaceholder('Enter username').fill('portfolio.user');
  await page.getByPlaceholder('Enter password').fill('strong-password');
  await page.getByRole('button', { name: 'Sign In' }).click();

  await expect(page.getByRole('heading', { name: 'Add your first document' })).toBeVisible({ timeout: 15_000 });
  const chooserPromise = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Upload a document' }).click();
  const chooser = await chooserPromise;
  await chooser.setFiles(path.join(process.cwd(), 'e2e', 'fixtures', 'portfolio.txt'));

  await expect(page.getByRole('button', { name: 'New' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Docs' })).toBeVisible();
  await page.getByRole('button', { name: 'Open settings' }).click();
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
  await expect(page.getByRole('button', { name: /General/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /Profile/ })).toBeVisible();
  await page.getByRole('button', { name: /Profile/ }).click();
  await expect(page.getByRole('heading', { name: 'Your Nova profile' })).toBeVisible();

  const hasHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(hasHorizontalOverflow).toBe(false);
});
