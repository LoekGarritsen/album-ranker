import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright configuration for Album Ranker E2E tests.
 *
 * Run against docker-compose services:
 *   docker-compose -f docker-compose.e2e.yml up -d
 *   cd e2e && npm test
 */
export default defineConfig({
  testDir: './tests',
  fullyParallel: false, // Run tests sequentially for real-time sync tests
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Single worker for predictable session state
  reporter: [['html', { open: 'never' }], ['list']],

  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8401',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Wait for services to be ready before running tests
  webServer: process.env.SKIP_WEBSERVER ? undefined : {
    command: 'cd .. && docker-compose -f docker-compose.e2e.yml up',
    url: 'http://localhost:8401',
    reuseExistingServer: !process.env.CI,
    timeout: 120000, // 2 minutes for containers to start
  },
})
