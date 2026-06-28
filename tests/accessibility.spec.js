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

test("direct relationship graph renders one label per entity", async ({ page }) => {
  await page.goto("/");

  const search = page.getByRole("searchbox", { name: "Search entity or category" });
  await search.fill("CIA");
  await search.press("Enter");

  await expect(page.locator("#status")).toContainText("direct relationship graph");
  const duplicates = await page.locator(".html-graph-label[data-label-entity]").evaluateAll((labels) => {
    const seen = new Set();
    const repeated = new Set();
    for (const label of labels) {
      const id = label.getAttribute("data-label-entity");
      if (!id) continue;
      if (seen.has(id)) repeated.add(id);
      seen.add(id);
    }
    return Array.from(repeated);
  });
  expect(duplicates).toEqual([]);
});

test("direct relationship graph shows real outward connections", async ({ page }) => {
  await page.goto("/");

  const search = page.getByRole("searchbox", { name: "Search entity or category" });
  await search.fill("Central Intelligence Agency");
  await search.press("Enter");

  await expect(page.locator("#status")).toContainText("second-degree context nodes");
  const contextNodes = page.locator(".graph-node.context-node");
  await expect(contextNodes.first()).toBeAttached();

  const secondaryLabels = await page.locator(".html-graph-label[data-label-entity] .label-secondary").evaluateAll((labels) =>
    labels.map((label) => label.textContent || "")
  );
  expect(secondaryLabels.some((label) => label.includes("weight"))).toBe(true);
  expect(secondaryLabels.some((label) => label.includes("real connections") || label.startsWith("from "))).toBe(true);
});

test("category drill-in fits below the fixed header", async ({ page }) => {
  await page.goto("/");

  const category = page.locator(".html-graph-label[data-label-category]").first();
  await expect(category).toBeVisible({ timeout: 15000 });
  await category.click();
  await expect(page.locator("#status")).toContainText("select an entity");

  const overlap = await page.evaluate(() => {
    const topbar = document.querySelector(".topbar");
    const labels = Array.from(document.querySelectorAll(".html-graph-label"));
    const headerBottom = topbar ? topbar.getBoundingClientRect().bottom : 0;
    return labels
      .map((label) => label.getBoundingClientRect())
      .filter((rect) => rect.width > 0 && rect.height > 0)
      .some((rect) => rect.top < headerBottom + 4);
  });
  expect(overlap).toBe(false);
});

test("info card close button stays outside the scrollable body", async ({ page }) => {
  await page.goto("/");

  const search = page.getByRole("searchbox", { name: "Search entity or category" });
  await search.fill("CIA");
  await search.press("Enter");

  const details = page.locator("#node-card");
  const body = details.locator(".node-card-body");
  await expect(details).toBeVisible();
  await expect(body).toBeVisible();

  await body.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });

  const close = page.getByRole("button", { name: "Close info window" });
  await expect(close).toBeVisible();
  const closeOutsideBody = await close.evaluate((button) => {
    const buttonRect = button.getBoundingClientRect();
    const bodyRect = document.querySelector(".node-card-body").getBoundingClientRect();
    return buttonRect.bottom <= bodyRect.top;
  });
  expect(closeOutsideBody).toBe(true);

  await close.click();
  await expect(details).not.toBeVisible();
});

test("baked reclass decisions are removed from browser review state", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("uap-relationship-graph-reclass", JSON.stringify({
      reclassifications: { "people:star-trek": "tv_shows" },
      nameReclassifications: {},
      falsePositives: {},
      omissions: {},
      aliases: {},
      merges: {},
      nameMerges: {},
      notes: {},
    }));
  });

  await page.goto("/");

  await expect(page.locator("#review-status")).toHaveText("");
  await expect(page.getByRole("button", { name: "Download reclassified data" })).toBeHidden();
  const storedReview = await page.evaluate(() => localStorage.getItem("uap-relationship-graph-reclass"));
  expect(storedReview).toBeNull();
});

test("merge duplicate target is selected through search results", async ({ page }) => {
  await page.goto("/");

  const search = page.getByRole("searchbox", { name: "Search entity or category" });
  await search.fill("CIA");
  await search.press("Enter");

  const mergeSearch = page.getByRole("searchbox", { name: "Find entity to merge into" });
  await expect(mergeSearch).toBeVisible();
  await expect(page.getByRole("button", { name: "Merge" })).toBeDisabled();

  await mergeSearch.fill("Roswell");
  const roswell = page.locator("[data-merge-target='locations:roswell']");
  await expect(roswell).toBeVisible();
  await roswell.click();

  await expect(mergeSearch).toHaveValue("Roswell");
  await expect(roswell).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Merge" })).toBeEnabled();
});
