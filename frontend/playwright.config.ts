import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright Configuration for Widget Visual Tests
 *
 * See https://playwright.dev/docs/test-configuration
 */
/**
 * Target URL. Defaults to the local dev server (:3200), which Playwright boots
 * via `webServer` below. Set AUDIT_BASE_URL to point the design audit at an
 * already-running server or a deployed preview (then Playwright won't try to
 * boot its own — useful in CI and when :3200 is taken by `docker compose`).
 */
const BASE_URL = process.env.AUDIT_BASE_URL || 'http://localhost:3200';

export default defineConfig({
  testDir: './tests',

  /* Run tests in files in parallel */
  fullyParallel: true,

  /* Fail the build on CI if you accidentally left test.only in the source code */
  forbidOnly: !!process.env.CI,

  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,

  /* Opt out of parallel tests on CI */
  workers: process.env.CI ? 1 : undefined,

  /* Reporter to use */
  reporter: 'html',

  /* Shared settings for all the projects below */
  use: {
    /* Base URL to use in actions like `await page.goto('/')` */
    baseURL: BASE_URL,

    /* Collect trace when retrying the failed test */
    trace: 'on-first-retry',

    /* Screenshot on failure */
    screenshot: 'only-on-failure',
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },

    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },

    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },

    /* Test against mobile viewports */
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },
  ],

  /* Boot the local dev server before the tests — unless AUDIT_BASE_URL points
   * at an already-running server / deployed preview. */
  webServer: process.env.AUDIT_BASE_URL
    ? undefined
    : {
        command: 'npm run dev',
        url: 'http://localhost:3200',
        reuseExistingServer: !process.env.CI,
        timeout: 120 * 1000,
      },
});
