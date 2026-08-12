# Nova AI frontend

The React client for Nova's private document workspace. It includes authenticated chat, streaming responses, document upload and indexing, global search, responsive navigation, light/dark themes, voice input, and motion-aware animation.

## Local development

```bash
npm install
npm run dev
```

For local development, set `VITE_API_BASE_URL` to the FastAPI backend URL when it is not available at `http://localhost:8000`. Production builds intentionally use the same-origin `/api` proxy so host-only authentication cookies and the production Content Security Policy remain valid. Run `npm run build` for a production bundle and `npm run lint` for static checks.
