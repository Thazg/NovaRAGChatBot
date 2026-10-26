import path from 'node:path';
import { readFile } from 'node:fs/promises';

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
  let signedIn = Boolean(options.activeSession);
  let savedConversation: Record<string, unknown> | null = null;
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
      signedIn = true;
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
      if (signedIn) {
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
      await fulfillJson(route, savedConversation ? [savedConversation] : []);
      return;
    }
    if (method === 'POST' && endpoint === '/conversation/new') {
      const body = request.postDataJSON();
      savedConversation = {
        id: body.id,
        title: body.title,
        messages: body.messages,
        pinned: body.pinned,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      };
      await fulfillJson(route, savedConversation);
      return;
    }
    if (method === 'POST' && endpoint === '/chat/stream') {
      lastChatRequest = request.postDataJSON();
      streamAttempts += 1;
      if (options.disconnectFirstStream && streamAttempts === 1) {
        await route.abort('connectionfailed');
        return;
      }
      const evidence = [{ id: 'E1', document_id: 'portfolio.txt', file_name: 'portfolio.txt', page: null, line_start: 1, line_end: 2, chunk_index: 1,
        content: 'Nova combines BM25 lexical retrieval with FAISS vectors. Reciprocal rank fusion merges both rankings.' }];
      const events = [
        { evidence },
        { token: 'Nova combines BM25 lexical retrieval with FAISS vectors. ' },
        { token: 'Reciprocal rank fusion merges both rankings. ' },
        { token: '[E1]' },
      ];
      savedConversation = {
        ...(savedConversation || {}), id: lastChatRequest.session_id, title: 'Evidence question',
        createdAt: Date.now(), updatedAt: Date.now(),
        messages: [{ id: 'user-1', role: 'user', content: lastChatRequest.question, createdAt: Date.now() },
          { id: 'answer-1', role: 'assistant', content: 'Nova combines BM25 lexical retrieval with FAISS vectors. Reciprocal rank fusion merges both rankings. [E1]',
            createdAt: Date.now(), retrievedDocs: evidence }],
      };
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
    streamAttempts: () => streamAttempts,
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
  await expect(page.getByText(/Source: portfolio\.txt/)).toBeVisible();
  await expect(page.getByRole('link', { name: /portfolio\.txt/ })).toHaveCount(0);
  await page.reload();
  await expect(page.getByLabel('Message input')).toBeVisible({ timeout: 15_000 });
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
  await expect(page.getByText('DOCUMENT WORKFLOW', { exact: true })).toBeVisible();
  await expect(page.getByText('ACCOUNT ACCESS', { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot('login-dark.png', {
    fullPage: true,
    animations: 'disabled',
    maxDiffPixelRatio: 0.01,
    timeout: 15_000,
  });
});

test('requires explicit regeneration when a POST fails before the first token', async ({ page }) => {
  const apiMock = await mockPortfolioApi(page, { disconnectFirstStream: true });
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
  await expect(page.getByText('Response interrupted. This answer may be incomplete.')).toBeVisible();
  expect(apiMock.streamAttempts()).toBe(1);
  await page.getByRole('button', { name: 'Regenerate answer', exact: true }).click();
  await expect(page.getByText(/Source: portfolio\.txt/)).toBeVisible();
  expect(apiMock.streamAttempts()).toBe(2);
  expect(apiMock.lastChatRequest()).toMatchObject({ regenerate: true });
});

test('keeps a broken stream incomplete until the user regenerates', async ({ page }) => {
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

  await expect(page.getByText('Response interrupted. This answer may be incomplete.')).toBeVisible();
  await expect(page.getByText(/Reciprocal rank fusion merges both rankings/)).toHaveCount(0);
  await page.getByRole('button', { name: 'Regenerate answer', exact: true }).click();
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
  await expect(page.getByText('Private workspace')).toHaveCount(0);

  await page.getByRole('button', { name: 'Open settings' }).click();
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
  const settingsSidebarBox = await page.locator('.nova-settings-sidebar').boundingBox();
  const activeNavBox = await page.getByRole('button', { name: /General/ }).boundingBox();
  expect(settingsSidebarBox).not.toBeNull();
  expect(activeNavBox).not.toBeNull();
  expect(activeNavBox!.x + activeNavBox!.width).toBeLessThanOrEqual(settingsSidebarBox!.x + settingsSidebarBox!.width + 1);
  await page.getByRole('button', { name: 'Light', exact: true }).click();
  await expect(page.locator('html')).toHaveClass(/light/);
  await expect(page.getByText('Preferences save automatically')).toBeVisible();
  await expect.poll(() => apiMock.preferences().theme).toBe('light');
  await page.getByRole('button', { name: /About Nova/ }).click();
  await expect(page.getByRole('heading', { name: 'Nova RAG Workspace', exact: true })).toBeVisible();
  await expect(page.getByText(/powered by Groq/i)).toHaveCount(0);
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

test('shows plain page and line sources on mobile without document links', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
      writeText: async (text: string) => { sessionStorage.setItem('test-clipboard', text); },
    } });
    Object.defineProperty(navigator, 'share', { configurable: true, value:
      async (data: ShareData) => { sessionStorage.setItem('test-shared', data.text || ''); },
    });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await mockPortfolioApi(page, { activeSession: true });
  const evidence = [{ id: 'E1', document_id: 'stored-paper.pdf', file_name: 'paper.pdf', page: 2, line_start: 6, line_end: 9, chunk_index: 1,
    content: 'Beta evidence on the second page.' }];
  await page.route('**/chat/stream', async route => {
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body:
      `data: ${JSON.stringify({ evidence })}\n\ndata: ${JSON.stringify({ token: 'Beta evidence is on page two [E1].' })}\n\ndata: [DONE]\n\n` });
  });
  await page.goto('/');
  const chooserPromise = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Upload a document' }).click();
  await (await chooserPromise).setFiles(path.join(process.cwd(), 'e2e/fixtures/portfolio.txt'));
  await page.getByLabel('Message input').fill('Where is beta evidence?');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByText('Beta evidence is on page two (Source: paper.pdf, Page 2, Lines 6–9).')).toBeVisible();
  await expect(page.getByRole('link', { name: /paper\.pdf/ })).toHaveCount(0);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const expected = 'Beta evidence is on page two (Source: paper.pdf, Page 2, Lines 6–9).';
  await page.getByRole('button', { name: 'Copy', exact: true }).click();
  expect(await page.evaluate(() => sessionStorage.getItem('test-clipboard'))).toBe(expected);
  await page.getByRole('button', { name: 'Share', exact: true }).click();
  expect(await page.evaluate(() => sessionStorage.getItem('test-shared'))).toBe(expected);
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations.filter(item => item.impact === 'serious' || item.impact === 'critical')).toEqual([]);
  await page.screenshot({ path: 'test-results/page-line-source-mobile.png', animations: 'disabled' });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole('button', { name: /^Actions for / }).click();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('menuitem', { name: 'Export', exact: true }).click();
  const download = await downloadPromise;
  const exported = await readFile((await download.path())!, 'utf-8');
  expect(exported).toContain(`ASSISTANT: ${expected}`);
  expect(exported).not.toContain('[E1]');
});


async function openLifecycleWorkspace(page: Page) {
  await mockPortfolioApi(page, { activeSession: true });
  await page.goto('/');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Upload a document', exact: true }).click();
  await (await chooser).setFiles(path.join(process.cwd(), 'e2e/fixtures/portfolio.txt'));
  await expect(page.getByLabel('Message input')).toBeVisible();
}

test('renders chat without avatars using left-aligned text and dash lists', async ({ page }) => {
  await openLifecycleWorkspace(page);
  await page.route('**/chat/stream', async (route) => {
    const answer = 'Here are the findings:\n\n- First finding\n- Second finding\n\n1. First step\n2. Second step';
    await route.fulfill({
      contentType: 'text/event-stream', headers: CORS_HEADERS,
      body: `data: ${JSON.stringify({ token: answer })}\n\ndata: [DONE]\n\n`,
    });
  });
  await page.getByLabel('Message input').fill('List the findings');
  await page.getByRole('button', { name: 'Send message' }).click();
  const assistant = page.locator('[data-message-role="assistant"]');
  const user = page.locator('[data-message-role="user"]');
  await expect(assistant.getByText('First finding', { exact: true })).toBeVisible();
  await expect(assistant.locator('p').first()).toHaveCSS('text-align', 'left');
  await expect(assistant.locator('ul')).toHaveCSS('list-style-type', '"-  "');
  await expect(assistant.locator('ol')).toHaveCSS('list-style-type', 'decimal');
  await expect(assistant.locator('.lucide-sparkles')).toHaveCount(0);
  await expect(user.locator('.lucide-user, img')).toHaveCount(0);
  await page.screenshot({ path: 'test-results/chat-layout-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(assistant.getByText('Second finding', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/chat-layout-mobile.png', fullPage: true });
});

test('hides source locations until streaming completes while preserving answer tokens', async ({ page }) => {
  await openLifecycleWorkspace(page);
  await page.evaluate(() => {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (!url.endsWith('/chat/stream')) return nativeFetch(input, init);
      return new Response(new ReadableStream<Uint8Array>({ start(controller) {
        const enqueue = (event: unknown) => controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`));
        enqueue({ evidence: [{ id: 'E1', document_id: 'portfolio.txt', file_name: 'portfolio.txt', page: 2,
          line_start: 6, line_end: 9, chunk_index: 1, content: 'Supporting passage.' }] });
        window.addEventListener('test:answer-token', () => enqueue({ token: 'Supported answer [E' }), { once: true });
        window.addEventListener('test:citation-token', () => enqueue({ token: '1].' }), { once: true });
        window.addEventListener('test:complete-answer', () => {
          controller.enqueue(new TextEncoder().encode('data: [DONE]\n\n'));
          controller.close();
        }, { once: true });
      } }), { headers: { 'Content-Type': 'text/event-stream' } });
    };
  });
  await page.getByLabel('Message input').fill('Explain this document.');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByText('Nova is thinking...', { exact: true })).toBeVisible();
  await expect(page.getByText(/Source:/)).toHaveCount(0);
  await page.evaluate(() => window.dispatchEvent(new Event('test:answer-token')));
  await expect(page.getByText('Supported answer', { exact: true })).toBeVisible();
  await expect(page.getByText('Supported answer', { exact: true })).toHaveCSS('text-align', 'left');
  await expect(page.getByText(/Source:|\[E/)).toHaveCount(0);
  await page.evaluate(() => window.dispatchEvent(new Event('test:citation-token')));
  await expect(page.getByText('Supported answer .', { exact: true })).toBeVisible();
  await expect(page.getByText(/Source:|\[E/)).toHaveCount(0);
  await page.evaluate(() => window.dispatchEvent(new Event('test:complete-answer')));
  await expect(page.getByText('Supported answer (Source: portfolio.txt, Page 2, Lines 6–9).', { exact: true })).toBeVisible();
  await expect(page.getByText('Nova is thinking...', { exact: true })).toHaveCount(0);
});

test('a late canceled stream cannot finish or append to its replacement', async ({ page }) => {
  await openLifecycleWorkspace(page);
  await page.evaluate(() => {
    const nativeFetch = window.fetch.bind(window);
    let calls = 0;
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (!url.endsWith('/chat/stream')) return nativeFetch(input, init);
      const call = ++calls;
      const body = new ReadableStream<Uint8Array>({ start(controller) {
        controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify({ token: call === 1 ? 'First partial answer.' : 'Replacement partial answer.' })}\n\n`));
        if (call === 1) {
          // A transport can settle after AbortController.abort() returns.
          window.addEventListener('test:finish-first', () => {
            controller.enqueue(new TextEncoder().encode('data: {"token":" Stale output."}\n\n'));
            queueMicrotask(() => controller.error(new DOMException('Delayed abort', 'AbortError')));
          }, { once: true });
        } else {
          init?.signal?.addEventListener('abort', () => {
            sessionStorage.setItem('replacement-aborted', 'true');
            controller.error(new DOMException('Canceled', 'AbortError'));
          }, { once: true });
        }
      } });
      return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } });
    };
  });
  await page.getByLabel('Message input').fill('Explain the first experiment.');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByText('First partial answer.')).toBeVisible();
  await page.getByRole('button', { name: 'Stop generation' }).click();
  await expect(page.getByText('Response interrupted. This answer may be incomplete.')).toBeVisible();
  await page.getByLabel('Message input').fill('Explain the replacement experiment.');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByText('Replacement partial answer.')).toBeVisible();
  await page.evaluate(async () => {
    window.dispatchEvent(new Event('test:finish-first'));
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  });
  await expect(page.getByText(/Stale output/)).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Stop generation' })).toBeVisible();
  await page.getByRole('button', { name: 'Stop generation' }).click();
  expect(await page.evaluate(() => sessionStorage.getItem('replacement-aborted'))).toBe('true');
  await expect(page.getByText('Response interrupted. This answer may be incomplete.')).toHaveCount(2);
});

test('changing conversations cancels generation without making the new chat busy', async ({ page }) => {
  await openLifecycleWorkspace(page);
  await page.evaluate(() => {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (!url.endsWith('/chat/stream')) return nativeFetch(input, init);
      return new Response(new ReadableStream<Uint8Array>({ start(controller) {
        controller.enqueue(new TextEncoder().encode('data: {"token":"Pending old conversation."}\n\n'));
        init?.signal?.addEventListener('abort', () => {
          sessionStorage.setItem('conversation-request-aborted', 'true');
          controller.error(new DOMException('Conversation changed', 'AbortError'));
        }, { once: true });
      } }), { headers: { 'Content-Type': 'text/event-stream' } });
    };
  });
  await page.getByLabel('Message input').fill('Explain this document.');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByText('Pending old conversation.')).toBeVisible();
  await page.keyboard.press('Control+n');
  await expect(page.getByLabel('Message input')).toBeEnabled();
  expect(await page.evaluate(() => sessionStorage.getItem('conversation-request-aborted'))).toBe('true');
  await expect(page.getByText('Pending old conversation.')).toHaveCount(0);
});

test('a delayed refresh cannot restore credentials after logout', async ({ page }) => {
  await openLifecycleWorkspace(page);
  const outcome = await page.evaluate(async () => {
    const { auth, api } = await import('/src/services/api.ts');
    const nativeFetch = window.fetch.bind(window);
    let release: () => void = () => {};
    let authorization: string | null = 'not-checked';
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith('/auth/refresh')) return new Promise<Response>(resolve => {
        // Deliberately ignore abort to exercise stale-response protection too.
        release = () => resolve(new Response(JSON.stringify({
          access_token: 'late-refresh-token-that-must-not-be-restored',
          user_id: '6ab4ef03-50ba-4782-95db-ecc55d64c53d', username: 'old.user',
        }), { headers: { 'Content-Type': 'application/json' } }));
      });
      if (url.endsWith('/documents')) {
        authorization = new Headers(init?.headers).get('Authorization');
        return new Response('[]', { headers: { 'Content-Type': 'application/json' } });
      }
      return nativeFetch(input, init);
    };
    const pending = auth.refresh().then(() => 'restored', () => 'rejected');
    await auth.logout();
    release();
    const refresh = await pending;
    await api.getDocuments();
    window.fetch = nativeFetch;
    return { refresh, authorization };
  });
  expect(outcome).toEqual({ refresh: 'rejected', authorization: null });
});

for (const terminal of ['finished', 'failed'] as const) {
  test(`web search waits for indexing and handles a ${terminal} job honestly`, async ({ page }) => {
    await openLifecycleWorkspace(page);
    let settled = false;
    await page.route('**/documents/search-download', route => fulfillJson(route, {
      status: 'success', downloaded: [{ id: 'paper.pdf', file_name: 'paper.pdf', new: true }],
      message: 'Downloaded one PDF.', job_id: 'index-job-123',
    }));
    await page.route('**/documents/jobs/index-job-123', route => fulfillJson(route, {
      id: 'index-job-123', status: settled ? terminal : 'started', progress: settled ? 100 : 40,
      result: settled && terminal === 'finished' ? { indexed: true, chunks: 4 } : null,
      error: settled && terminal === 'failed' ? 'Document parsing failed; try another PDF.' : null,
    }));
    await page.getByLabel('Message input').fill('search for denoising experiments');
    await page.getByRole('button', { name: 'Send message' }).click();
    await expect(page.getByText(/They are not ready for questions yet/)).toBeVisible();
    await expect(page.getByText(/Indexing completed\. You can now ask/)).toHaveCount(0);
    await expect(page.getByLabel('Message input')).toBeDisabled();
    settled = true;
    if (terminal === 'finished') {
      await expect(page.getByText(/Indexing completed\. You can now ask/)).toBeVisible();
    } else {
      await expect(page.getByText('Document parsing failed; try another PDF.')).toBeVisible();
      await expect(page.getByText('Response interrupted. This answer may be incomplete.')).toBeVisible();
      await expect(page.getByText(/Indexing completed\. You can now ask/)).toHaveCount(0);
    }
    await expect(page.getByLabel('Message input')).toBeEnabled();
  });
}

test('downloads original documents with authentication and allows retry after failure', async ({ page }) => {
  await openLifecycleWorkspace(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route(/\/documents$/, route => fulfillJson(route, [{
    id: 'storage-only.pdf', name: 'Báo cáo.pdf', size: 24, indexed: false, chunks: 0,
  }]));
  let unavailable = false;
  let downloads = 0;
  page.on('download', () => { downloads += 1; });
  const original = '%PDF-1.4\nOriginal bytes\n';
  await page.route('**/documents/storage-only.pdf/download', async route => {
    expect(route.request().headers().authorization).toMatch(/^Bearer /);
    expect(new URL(route.request().url()).search).toBe('');
    if (unavailable) return fulfillJson(route, { detail: 'Document storage is temporarily unavailable' }, 503);
    await route.fulfill({ status: 200, headers: CORS_HEADERS, contentType: 'application/octet-stream', body: original });
  });
  await page.getByRole('button', { name: 'Docs', exact: true }).click();
  const button = page.getByRole('button', { name: 'Download Báo cáo.pdf', exact: true });
  await expect(button).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Ask questions about Báo cáo.pdf' })).toBeDisabled();
  const downloaded = page.waitForEvent('download');
  await button.click();
  const download = await downloaded;
  expect(download.suggestedFilename()).toBe('Báo cáo.pdf');
  expect(await readFile((await download.path())!, 'utf-8')).toBe(original);
  unavailable = true;
  await button.click();
  await expect(page.getByText('Document storage is temporarily unavailable', { exact: true })).toBeVisible();
  await expect(button).toBeEnabled();
  expect(downloads).toBe(1);
  const box = await button.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
});

test('document listing failures are recoverable and unindexed files are not called processing', async ({ page }) => {
  await openLifecycleWorkspace(page);
  let unavailable = true;
  await page.route(/\/documents$/, route => unavailable
    ? fulfillJson(route, { detail: 'Durable storage is temporarily unavailable.' }, 503)
    : fulfillJson(route, [{ id: 'unindexed.txt', name: 'unindexed.txt', size: 42, indexed: false, chunks: 0 }]));
  await page.getByRole('button', { name: 'Docs', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Durable storage is temporarily unavailable.');
  await expect(page.getByText('No documents', { exact: true })).toHaveCount(0);
  unavailable = false;
  await page.getByRole('button', { name: 'Retry loading documents' }).click();
  await expect(page.getByText('Not indexed — re-index to retry')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Ask questions about unindexed.txt' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Refresh documents' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Re-index all documents' })).toBeVisible();
});


test('legacy browser preferences cannot leak document scope or instructions into a different account', async ({ page }) => {
  await mockPortfolioApi(page, { activeSession: true });
  await page.addInitScript(() => localStorage.setItem('rag-chat-storage', JSON.stringify({
    version: 4,
    state: { theme: 'light', sidebarOpen: true, customInstructions: 'PRIVATE PREVIOUS ACCOUNT INSTRUCTIONS',
      nickname: 'Private nickname', displayName: 'Private profile', avatar: 'data:image/private',
      selectedDocument: { id: 'private-document-id.txt', name: 'private-document-title.txt' } },
  })));
  await page.route('**/auth/preferences', route => fulfillJson(route, { detail: 'Preferences unavailable' }, 503));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Add your first document' })).toBeVisible({ timeout: 15_000 });
  const result = await page.evaluate(async () => {
    const { useChatStore } = await import('/src/store/useChatStore.ts');
    return { scope: useChatStore.getState().selectedDocument,
      instructions: useChatStore.getState().customInstructions,
      persisted: localStorage.getItem('rag-chat-storage') };
  });
  expect(result.scope).toBeNull();
  expect(result.instructions).toBe('');
  expect(result.persisted).not.toContain('PRIVATE');
  expect(result.persisted).not.toContain('private-document');
  expect(result.persisted).not.toContain('Private profile');
  expect(result.persisted).not.toContain('data:image/private');
  await expect(page.locator('html')).toHaveClass(/light/);
});

test('failed account deletion preserves settings and session so the user can retry', async ({ page }) => {
  await openLifecycleWorkspace(page);
  let attempts = 0;
  let logoutCalls = 0;
  await page.route('**/auth/account', route => ++attempts === 1
    ? fulfillJson(route, { detail: 'Account deletion is pending. Retry deleting the account.' }, 503)
    : fulfillJson(route, { status: 'success', message: 'Account deleted' }));
  await page.route('**/auth/logout', async route => {
    logoutCalls += 1;
    await route.fulfill({ status: 204, headers: CORS_HEADERS });
  });
  await page.getByRole('button', { name: 'Open settings' }).click();
  await page.getByRole('button', { name: /Privacy & data/ }).click();
  await page.getByRole('button', { name: 'Delete account', exact: true }).click();
  await page.getByPlaceholder('portfolio.user').fill('portfolio.user');
  await page.getByRole('button', { name: 'Delete permanently', exact: true }).click();
  await expect(page.getByText('Account deletion is pending. Retry deleting the account.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Delete permanently', exact: true })).toBeEnabled();
  expect(logoutCalls).toBe(0);
  await page.getByRole('button', { name: 'Delete permanently', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sign In', exact: true })).toBeVisible();
  expect(logoutCalls).toBe(1);
});

test('Enter used to confirm IME composition does not submit the chat', async ({ page }) => {
  await openLifecycleWorkspace(page);
  await page.getByLabel('Message input').fill('Tóm tắt tài liệu');
  await page.getByLabel('Message input').dispatchEvent('keydown', { key: 'Enter', isComposing: true });
  await expect(page.getByLabel('Message input')).toHaveValue('Tóm tắt tài liệu');
  await expect(page.getByText(/Reciprocal rank fusion merges/)).toHaveCount(0);
  await page.getByLabel('Message input').press('Enter');
  await expect(page.getByText(/Reciprocal rank fusion merges/)).toBeVisible();
});

test('conversation changes preserve server-confirmed state after failures and can be retried', async ({ page }) => {
  await openLifecycleWorkspace(page);
  await page.getByLabel('Message input').fill('Explain the retrieval experiment.');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByText(/Reciprocal rank fusion merges/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Stop generation' })).toHaveCount(0);
  const original = await page.evaluate(async () => {
    const { useChatStore } = await import('/src/store/useChatStore.ts');
    return useChatStore.getState().conversations[0];
  });
  let fail = true;
  await page.route(`**/conversation/${original.id}`, async route => {
    if (fail) return fulfillJson(route, { detail: 'Conversation storage is unavailable.' }, 503);
    if (route.request().method() === 'DELETE') return fulfillJson(route, { status: 'success' });
    return fulfillJson(route, { ...original, ...route.request().postDataJSON() });
  });
  await page.getByRole('button', { name: `Actions for ${original.title}`, exact: true }).click();
  await page.getByRole('menuitem', { name: 'Rename', exact: true }).click();
  const rename = page.getByRole('dialog', { name: 'Rename Conversation' });
  await rename.getByRole('textbox', { name: 'Conversation title' }).fill('Saved conversation title');
  await rename.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('Conversation storage is unavailable.', { exact: true })).toBeVisible();
  const unsavedTitle = await page.evaluate(async () => {
    const { useChatStore } = await import('/src/store/useChatStore.ts');
    return useChatStore.getState().conversations[0].title;
  });
  expect(unsavedTitle).toBe(original.title);
  await expect(rename).toBeVisible();
  fail = false;
  await rename.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(rename).toBeHidden();
  const actions = page.getByRole('button', { name: 'Actions for Saved conversation title', exact: true });
  await expect(actions).toBeVisible();
  fail = true;
  await actions.click();
  await page.getByRole('menuitem', { name: 'Delete', exact: true }).click();
  const deletion = page.getByRole('dialog', { name: 'Delete Conversation', exact: true });
  await deletion.getByRole('button', { name: 'Delete', exact: true }).click();
  await expect(deletion).toBeVisible();
  await expect(page.getByText('Conversation deleted', { exact: true })).toHaveCount(0);
  const count = await page.evaluate(async () => {
    const { useChatStore } = await import('/src/store/useChatStore.ts');
    return useChatStore.getState().conversations.length;
  });
  expect(count).toBe(1);
  fail = false;
  await deletion.getByRole('button', { name: 'Delete', exact: true }).click();
  await expect(deletion).toBeHidden();
  await expect(page.getByText('Conversation deleted', { exact: true })).toBeVisible();
  await expect(actions).toHaveCount(0);
});

test('failed pin and duplicate requests do not invent saved conversations', async ({ page }) => {
  await openLifecycleWorkspace(page);
  await page.getByLabel('Message input').fill('Explain this document.');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByText(/Reciprocal rank fusion merges/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Stop generation' })).toHaveCount(0);
  await page.route('**/conversation/*', route => fulfillJson(route, { detail: 'Could not save conversation.' }, 503));
  const result = await page.evaluate(async () => {
    const { useChatStore } = await import('/src/store/useChatStore.ts');
    const state = useChatStore.getState();
    const id = state.conversations[0].id;
    const failures: string[] = [];
    for (const action of [state.pinConversation, state.duplicateConversation]) {
      try { await action(id); } catch (error) { failures.push(error instanceof Error ? error.message : 'failed'); }
    }
    return { failures, count: useChatStore.getState().conversations.length, pinned: Boolean(useChatStore.getState().conversations[0].pinned) };
  });
  expect(result.failures).toEqual(['Could not save conversation.', 'Could not save conversation.']);
  expect(result.count).toBe(1);
  expect(result.pinned).toBe(false);
});
