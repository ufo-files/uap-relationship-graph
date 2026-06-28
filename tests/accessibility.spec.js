const { test, expect } = require("@playwright/test");

test("graph is operable with keyboard and exposes accessible controls", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "UFO Files Relationship Graph" })).toBeVisible();
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

  const selectedLabel = page.locator(".html-graph-label[aria-current='true']");
  await expect(selectedLabel).toBeFocused();
  await expect(page.locator("#status")).not.toContainText("Loading graph");
});

test("direct relationship graph renders one label per entity", async ({ page }) => {
  await page.goto("/");

  const search = page.getByRole("searchbox", { name: "Search entity or category" });
  await search.fill("CIA");
  await search.press("Enter");

  await expect(page.locator(".html-graph-label[aria-current='true']")).toBeFocused();
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

test("direct relationship graph keeps outward context subtle", async ({ page }) => {
  await page.goto("/");

  const search = page.getByRole("searchbox", { name: "Search entity or category" });
  await search.fill("Central Intelligence Agency");
  await search.press("Enter");

  await expect(page.locator(".html-graph-label[aria-current='true']")).toBeFocused();
  const contextNodes = page.locator(".graph-node.context-node");
  await expect(contextNodes.first()).toBeAttached();
  await expect(contextNodes.first().locator("circle")).toHaveAttribute("opacity", ".38");

  const secondaryLabels = await page.locator(".html-graph-label[data-label-entity] .label-secondary").evaluateAll((labels) =>
    labels.map((label) => label.textContent || "")
  );
  expect(secondaryLabels.some((label) => label.includes("weight"))).toBe(false);
  expect(secondaryLabels.some((label) => label.includes("real connections") || label.startsWith("from "))).toBe(false);
});

test("hovering an entity highlights its visible connections", async ({ page }) => {
  await page.goto("/");

  const search = page.getByRole("searchbox", { name: "Search entity or category" });
  await search.fill("Central Intelligence Agency");
  await search.press("Enter");

  const selectedLabel = page.locator(".html-graph-label[aria-current='true']");
  await expect(selectedLabel).toBeFocused();
  await selectedLabel.hover();

  await expect.poll(async () => page.locator(".graph-edge.connection-highlight").count()).toBeGreaterThan(0);
  await expect.poll(async () => page.locator(".graph-node.connection-highlight").count()).toBeGreaterThan(1);
  await expect.poll(async () => page.locator(".html-graph-label.connection-highlight").count()).toBeGreaterThan(1);
  await expect.poll(async () => page.locator(".graph-node.connection-dim").count()).toBeGreaterThan(0);
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

test("mobile category drill-in starts focused on the selected group", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  const category = page.locator(".html-graph-label[data-label-category='people']");
  await expect(category).toBeVisible({ timeout: 15000 });
  await category.evaluate((element) => element.click());

  const viewAll = page.locator(".html-graph-label[data-label-category-list='people']");
  await expect(viewAll).toBeVisible();
  await expect(page.locator("#status")).toContainText("People");

  const metrics = await page.evaluate(() => {
    const topbar = document.querySelector(".topbar");
    const selected = document.querySelector(".html-graph-label[data-label-category-list='people']");
    const entityLabels = Array.from(document.querySelectorAll(".html-graph-label[data-label-entity]"));
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const topbarBottom = topbar ? topbar.getBoundingClientRect().bottom : 0;
    const selectedRect = selected ? selected.getBoundingClientRect() : null;
    const visibleEntityLabels = entityLabels.filter((label) => {
      const rect = label.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 && rect.bottom > topbarBottom && rect.top < viewportHeight && rect.right > 0 && rect.left < viewportWidth;
    }).length;
    return {
      viewportWidth,
      topbarBottom,
      selectedLeft: selectedRect ? selectedRect.left : -1,
      selectedRight: selectedRect ? selectedRect.right : -1,
      selectedTop: selectedRect ? selectedRect.top : -1,
      selectedBottom: selectedRect ? selectedRect.bottom : -1,
      visibleEntityLabels,
    };
  });
  expect(metrics.selectedLeft).toBeGreaterThanOrEqual(8);
  expect(metrics.selectedRight).toBeLessThanOrEqual(metrics.viewportWidth - 8);
  expect(metrics.selectedTop).toBeGreaterThan(metrics.topbarBottom);
  expect(metrics.visibleEntityLabels).toBeGreaterThan(8);
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
    return buttonRect.left >= bodyRect.right || buttonRect.bottom <= bodyRect.top;
  });
  expect(closeOutsideBody).toBe(true);

  await close.click();
  await expect(details).not.toBeVisible();
});

test("entity graph fit reserves the open sidebar", async ({ page }) => {
  await page.goto("/");

  const search = page.getByRole("searchbox", { name: "Search entity or category" });
  await search.fill("CIA");
  await search.press("Enter");

  const details = page.locator("#node-card");
  const selectedLabel = page.locator(".html-graph-label[aria-current='true']");
  await expect(details).toBeVisible();
  await expect(selectedLabel).toBeFocused();

  const spacing = await page.evaluate(() => {
    const svg = document.querySelector("#graph");
    const viewBox = (svg.getAttribute("viewBox") || "").split(/\s+/).map(Number);
    const sidebar = document.querySelector("#node-card");
    const label = document.querySelector(".html-graph-label[aria-current='true']");
    const sidebarRect = sidebar.getBoundingClientRect();
    const labelRect = label.getBoundingClientRect();
    return {
      sidebarRight: sidebarRect.right,
      labelLeft: labelRect.left,
      viewBoxWidth: viewBox[2],
    };
  });
  expect(spacing.labelLeft).toBeGreaterThan(spacing.sidebarRight + 16);
  expect(spacing.viewBoxWidth).toBeLessThan(5200);
});

test("manual relationships are visible in direct entity views", async ({ page }) => {
  await page.goto("/");

  const search = page.getByRole("searchbox", { name: "Search entity or category" });
  await search.fill("Skinwalker Ranch");
  await search.press("Enter");

  await expect(page.locator(".html-graph-label[aria-current='true']")).toBeFocused();
  await expect(page.locator(".html-graph-label[data-label-entity='locations:uinta-basin']")).toBeVisible();
  await expect(page.locator(".relationship-target[data-card-entity='locations:uinta-basin']")).toBeVisible();
});

test("baked reclass decisions are removed from browser review state", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("relationship-graph-reclass", JSON.stringify({
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
  const storedReview = await page.evaluate(() => localStorage.getItem("relationship-graph-reclass"));
  expect(storedReview).toBeNull();
});

test("merge duplicate target is selected through search results", async ({ page }) => {
  await page.goto("/");

  const search = page.getByRole("searchbox", { name: "Search entity or category" });
  await search.fill("CIA");
  await search.press("Enter");

  const mergeSearch = page.getByRole("searchbox", { name: "Find entity to merge into" });
  await expect(mergeSearch).toBeVisible();
  const mergeButton = page.getByRole("button", { name: "Merge", exact: true });
  await expect(mergeButton).toBeDisabled();

  await mergeSearch.fill("Roswell");
  const roswell = page.locator("[data-merge-target='locations:roswell']");
  await expect(roswell).toBeVisible();
  await roswell.click();

  await expect(mergeSearch).toHaveValue("Roswell");
  await expect(roswell).toHaveAttribute("aria-pressed", "true");
  await expect(mergeButton).toBeEnabled();
});

test("manual connections can be removed from connection rows", async ({ page }) => {
  await page.goto("/");

  const search = page.getByRole("searchbox", { name: "Search entity or category" });
  await search.fill("Harvard Medical School");
  await search.press("Enter");

  const remove = page.getByRole("button", { name: /Remove manual connection to Harvard University/i });
  await expect(remove).toBeVisible();
  await remove.click();

  await expect(remove).not.toBeVisible();
  const storedReview = await page.evaluate(() => JSON.parse(localStorage.getItem("relationship-graph-reclass") || "{}"));
  expect(Object.keys(storedReview.removedManualRelationships || {})).toContain("universities:harvard-medical-school--universities:harvard-university");
  expect(storedReview.manualRelationships || {}).not.toHaveProperty("universities:harvard-medical-school--universities:harvard-university");
});

test("false positive action requires confirmation", async ({ page }) => {
  await page.goto("/");

  const search = page.getByRole("searchbox", { name: "Search entity or category" });
  await search.fill("Hal Puthoff");
  await search.press("Enter");

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("false positive");
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "Mark false positive" }).click();

  await expect(page.locator("#node-card")).toBeVisible();
  const storedReview = await page.evaluate(() => JSON.parse(localStorage.getItem("relationship-graph-reclass") || "{}"));
  expect(JSON.stringify(storedReview.falsePositives || {})).not.toMatch(/puthoff|putoff/i);
});

test("false positives can be reviewed and restored", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("relationship-graph-reclass", JSON.stringify({
      reclassifications: {},
      nameReclassifications: {},
      falsePositives: {
        "government_agencies:central-intelligence-agency": {
          name: "Central Intelligence Agency",
          category: "government_agencies",
          categoryLabel: "Government agencies",
        },
      },
      removedFalsePositives: {},
      omissions: {},
      aliases: {},
      merges: {},
      nameMerges: {},
      removedMerges: {},
      removedNameMerges: {},
      removedManualRelationships: {},
      manualRelationships: {},
      notes: {},
    }));
  });
  await page.goto("/");

  await page.getByRole("button", { name: "Review false positives" }).click();
  const restore = page.getByRole("button", { name: /Central Intelligence Agency/i });
  await expect(restore).toBeVisible();
  await restore.click();

  await expect(page.locator("#node-card")).toBeVisible();
  const storedReview = await page.evaluate(() => JSON.parse(localStorage.getItem("relationship-graph-reclass") || "{}"));
  expect(storedReview.falsePositives || {}).not.toHaveProperty("government_agencies:central-intelligence-agency");
});
