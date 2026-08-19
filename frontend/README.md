# Nova frontend application

## Overview

This directory contains the React client for Nova's authenticated document
workspace. The application provides streaming chat, document upload and
indexing status, source citations, conversation search, responsive navigation,
theme preferences, voice input, and reduced-motion support.

## Local development

Install dependencies and start the Vite development server:

```bash
npm ci
npm run dev
```

The client expects the FastAPI service at `http://localhost:8000` by default.
Set `VITE_API_BASE_URL` when the backend uses a different origin.

## Verification

```bash
npm run check
npm run e2e
```

`npm run check` runs the configured lint, type-check, and production-build
validation. The Playwright suite verifies authentication, upload, streaming,
citations, session recovery, accessibility, and responsive layouts.

## Production routing

Production builds use the same-origin `/api` proxy defined by the Vercel
configuration. This routing preserves host-only authentication cookies and the
production Content Security Policy. Do not configure the browser client to call
the Render service directly in production.
