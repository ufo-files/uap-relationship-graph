const { test, expect } = require("@playwright/test");

test("graph is operable with keyboard and exposes accessible controls", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Transcript Relationship Graph" })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: "Search entity or category" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download data" })).toBeVisible();
  await expect(page.locator("#status")).toHaveAttribute("role", "status");
  await expect(page.locator("#review-status")).toHaveAttribute("aria-live", "polite");

  const graphButtons = page.locator(".html-graph-label[role='button']");
  await expect(graphButtons.first()).toBeVisible({ timeout: 15000 });
  await expect(graphButtons.first()).toHaveAttribute("tabindex", "0");

  await page.keyboard.press("Tab");
  await expect(graphButtons.first()).toBeFocused();

  await page.keyboard.press("Enter");
  await expect(page.locator("#status")).toContainText("select an entity");

  const entityButton = page.locator(".html-graph-label[data-label-entity]").first();
  await expect(entityButton).toBeVisible();
  await entityButton.focus();
  await expect(entityButton).toBeFocused();

  await page.keyboard.press(" ");
  const details = page.locator("#node-card");
  await expect(details).toBeVisible();
  await expect(details).toBeFocused();
  await expect(details.locator("#card-title")).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(details).not.toBeVisible();
  await expect(page.locator(".html-graph-label[aria-current='true']").first()).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(page.locator("#status")).toContainText("select an entity");

  await page.keyboard.press("Escape");
  await expect(page.locator("#status")).toContainText("select a group");
});

test("search submits without mouse and moves focus to a result", async ({ page }) => {
  await page.goto("/");

  const search = page.getByRole("searchbox", { name: "Search entity or category" });
  await search.fill("CIA");
  await search.press("Enter");

  await expect(page.locator("#status")).toContainText("direct relationship graph");
  await expect(page.locator(".html-graph-label[aria-current='true']")).toBeFocused();
});
