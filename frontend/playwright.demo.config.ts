import { defineConfig } from '@playwright/test';

import baseConfig from './playwright.config';

export default defineConfig({
  ...baseConfig,
  outputDir: 'demo-artifacts',
  reporter: [['list']],
  retries: 0,
  workers: 1,
  use: {
    ...baseConfig.use,
    trace: 'on',
    screenshot: 'on',
    video: { mode: 'on', size: { width: 1280, height: 720 } },
    launchOptions: { slowMo: 300 },
  },
});
