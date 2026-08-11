import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.tsx';

type StoredTheme = 'light' | 'dark' | 'system';

function resolveInitialTheme(): 'light' | 'dark' {
  try {
    const persisted = JSON.parse(localStorage.getItem('rag-chat-storage') || '{}') as {
      version?: number;
      state?: { theme?: StoredTheme };
    };
    const preference = persisted.state?.theme;

    if (preference === 'light' || preference === 'dark') return preference;
    if (preference === 'system' && (persisted.version || 0) >= 2) {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
  } catch {
    // Invalid or unavailable storage falls back to Nova's dark default.
  }
  return 'dark';
}

document.documentElement.classList.remove('light', 'dark');
document.documentElement.classList.add(resolveInitialTheme());

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
