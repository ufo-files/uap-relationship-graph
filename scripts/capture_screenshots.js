const { chromium } = require("@playwright/test");
const { spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const OUTPUT_DIR = path.join(ROOT, "screenshots");
const VIEWPORT = { width: 1440, height: 1000 };

function findOpenPort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
    server.on("error", reject);
  });
}

function startServer(port) {
  const server = spawn("python3", ["-m", "http.server", String(port), "--bind", "127.0.0.1"], {
    cwd: ROOT,
    stdio: ["ignore", "pipe", "pipe"],
  });
  server.stdout.on("data", (chunk) => process.stdout.write(`[server] ${chunk}`));
  server.stderr.on("data", (chunk) => process.stderr.write(`[server] ${chunk}`));
  return server;
}

async function waitForServer(port) {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    try {
      await new Promise((resolve, reject) => {
        const socket = net.connect(port, "127.0.0.1", () => {
          socket.end();
          resolve();
        });
        socket.on("error", reject);
      });
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 150));
    }
  }
  throw new Error("Timed out waiting for screenshot server");
}

async function openApp(page, baseUrl) {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.waitForSelector(".html-graph-label", { timeout: 30000 });
  await page.waitForTimeout(500);
}

async function capture(page, name) {
  await page.screenshot({
    path: path.join(OUTPUT_DIR, `${name}.png`),
    fullPage: false,
  });
}

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const port = await findOpenPort();
  const server = startServer(port);
  const baseUrl = `http://127.0.0.1:${port}/`;

  try {
    await waitForServer(port);
    const browser = await chromium.launch();
    const page = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 1 });

    await openApp(page, baseUrl);
    await capture(page, "relationship-graph-main");

    await page.getByText("People", { exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#status")?.textContent?.includes("People"));
    await page.waitForTimeout(700);
    await capture(page, "relationship-graph-people");

    await openApp(page, baseUrl);
    await page.getByText("Events & Claims", { exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#status")?.textContent?.includes("Events timeline"));
    await page.waitForTimeout(700);
    await capture(page, "relationship-graph-events-timeline");

    await browser.close();
  } finally {
    server.kill("SIGTERM");
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
