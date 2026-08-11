import path from 'node:path';

import { expect, test, type Page, type Route } from '@playwright/test';

const API_PATTERN = /https?:\/\/(?:localhost|127\.0\.0\.1):(?:8000|8001)\/.*/;
const CORS_HEADERS = {
  'access-control-allow-origin': '*',
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

async function mockPortfolioApi(page: Page) {
  let documents: Array<Record<string, unknown>> = [];

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
        token: 'portfolio-e2e-token',
        user_id: '6ab4ef03-50ba-4782-95db-ecc55d64c53d',
        username: 'portfolio.user',
      });
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
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  await mockPortfolioApi(page);

  await page.goto('/');
  await page.getByPlaceholder('Enter username').fill('portfolio.user');
  await page.getByPlaceholder('Enter password').fill('strong-password');
  await page.getByRole('button', { name: 'Sign In' }).click();

  await expect(page.getByRole('heading', { name: 'Welcome to Nova' })).toBeVisible();
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
});
