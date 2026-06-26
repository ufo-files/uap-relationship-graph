// @ts-check
const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests",
  testMatch: /.*\.spec\.js/,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:8765",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "python3 -m http.server 8765",
    url: "http://127.0.0.1:8765",
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
