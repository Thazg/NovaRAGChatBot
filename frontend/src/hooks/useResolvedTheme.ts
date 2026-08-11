import { useEffect, useState } from 'react';

export type ThemePreference = 'light' | 'dark' | 'system';

export function useResolvedTheme(theme: ThemePreference): 'light' | 'dark' {
  const query = '(prefers-color-scheme: dark)';
  const [systemTheme, setSystemTheme] = useState<'light' | 'dark'>(() =>
    window.matchMedia(query).matches ? 'dark' : 'light'
  );

  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setSystemTheme(media.matches ? 'dark' : 'light');
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  return theme === 'system' ? systemTheme : theme;
}
