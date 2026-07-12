import { defineConfig, devices } from '@playwright/test'

// Functional / e2e suite (Step 1) + live deployment verification (Step 7) run
// against the REAL deployed frontend. Generous timeouts absorb the Render free-tier
// cold start (~62 s) so a slow-but-working answer is not misread as a failure.
export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/results/artifacts',
  timeout: 180_000,
  expect: { timeout: 140_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: 'e2e/results/html', open: 'never' }]],
  use: {
    baseURL: process.env.FRONTEND_URL || 'https://srh-frontend.vercel.app',
    headless: true,
    screenshot: 'on',
    trace: 'retain-on-failure',
    video: 'off',
    actionTimeout: 30_000,
    navigationTimeout: 60_000,
  },
  projects: [
    { name: 'desktop-chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-android', use: { ...devices['Pixel 5'] } },
  ],
})
