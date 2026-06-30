const RAW = window.TRANSCRIPT_INTELLIGENCE_DATA;
const REVIEW_KEY = "relationship-graph-reclass";
const PREVIOUS_REVIEW_KEY = "uap-relationship-graph-reclass";
const LEGACY_REVIEW_KEY = "transcript-intelligence-v2-review";
const BUILT_REVIEW = normalizeReview(RAW.reclassDecisions || RAW.reclass_decisions || RAW.reviewDecisions || RAW.review_decisions || {});
const CURRENT_REVIEW_BASE = RAW.manifest && (RAW.manifest.pipeline_hash || RAW.manifest.registry_hash || RAW.manifest.generated_at) || "";
const THEME = {
  primary: "#111111",
  primarySoft: "#f6f5ef",
  entityFill: "#111111",
  entityAlt: "#f6f5ef",
  edge: "#111111",
  context: "#999999",
  activeHalo: "#ffffff",
  bgStroke: "#f6f5ef",
  edgeOpacity: { low: ".08", mid: ".16", high: ".34", relationship: ".36" },
};
const svg = document.getElementById("graph");
const graphLabelsEl = document.getElementById("graph-labels");
const statusEl = document.getElementById("status");
const cardEl = document.getElementById("node-card");
const hoverCardEl = document.getElementById("hover-card");
const cornerLabelEl = document.getElementById("corner-label");
const searchEl = document.getElementById("search");
const reviewStatusEl = document.getElementById("review-status");
const reviewFalsePositivesButton = document.getElementById("review-false-positives");
const appSwitcher = document.getElementById("app-switcher");
let mode = "categories";
let activeCategory = null;
let selectedEntityId = null;
let eventsClaimsView = "timeline";
let viewBox = { x: 120, y: 80, w: 1960, h: 1340 };
let dragStart = null;
let labelItems = [];
let hoverZoomTarget = null;
let hoverZoomDelta = 0;
let touchState = null;
const HOVER_ZOOM_ACTIVATE_DELTA = 900;
const ENTITY_ZOOM_OUT_STEP_UP_WIDTH = 5600;
const CATEGORY_ZOOM_OUT_STEP_UP_WIDTH = 7400;
const MIN_ZOOM_WIDTH = 240;
const MIN_ZOOM_HEIGHT = 165;
const MAX_ZOOM_WIDTH = 10800;
const MAX_ZOOM_HEIGHT = 10800;
const NEIGHBORHOOD_RELATIONSHIP_LIMIT = 48;
const CARD_RELATIONSHIP_LIMIT = 28;
const SECOND_DEGREE_CONTEXT_LIMIT = 12;
const SECOND_DEGREE_PER_NEIGHBOR_LIMIT = 2;
const SECOND_DEGREE_EDGE_LIMIT = 24;
const SECOND_DEGREE_LABEL_LIMIT = 0;
const TIMELINE_VERTICAL_SCALE = 0.9;

initializeReviewStorage();
let DATA = applyReviewDecisions(normalizeData(RAW));
const entitiesById = new Map();
const mentionsById = new Map(DATA.mentions.map((mention) => [mention.id, mention]));
const relationshipsById = new Map();
const relationshipsByEntity = new Map();
rebuildIndexes();

function currentTheme() {
  return THEME;
}

function normalizeData(raw) {
  const entities = raw.entities.map((entity) => ({
    ...entity,
    categoryLabel: entity.categoryLabel || entity.category_label || raw.categoryLabels[entity.category] || entity.category,
    topCategory: raw.categoryToTop[entity.category] || "needs_review",
    topCategoryLabel: raw.topCategoryLabels[raw.categoryToTop[entity.category] || "needs_review"] || "Needs Review",
    evidenceIds: entity.evidenceIds || entity.evidence_ids || [],
  }));
  const mentions = raw.mentions.map((mention) => ({
    ...mention,
    categoryLabel: mention.categoryLabel || mention.category_label || raw.categoryLabels[mention.category] || mention.category,
  }));
  const relationships = raw.relationships.map((relationship) => ({
    ...relationship,
    sourceName: relationship.sourceName || relationship.source_name,
    targetName: relationship.targetName || relationship.target_name,
    evidenceSegmentIds: relationship.evidenceSegmentIds || relationship.evidence_segment_ids || [],
    evidence: relationship.evidence || [],
  }));
  return { ...raw, entities, mentions, relationships };
}

function applyReviewDecisions(data) {
  const review = readReview();
  const falseIds = new Set(Object.keys(review.falsePositives || {}));
  data.entities = data.entities.filter((entity) => !falseIds.has(entity.id));
  for (const entity of data.entities) {
    const targetCategory = review.reclassifications && review.reclassifications[entity.id];
    if (targetCategory && data.categoryLabels[targetCategory]) {
      applyEntityCategory(entity, targetCategory, data);
    }
    const aliases = review.aliases || {};
    const alias = aliases[entity.id] || aliases[normalizeText(entity.name)];
    if (alias && alias.trim()) {
      applyEntityRename(entity, alias.trim(), data);
    }
  }
  const mergeRules = Object.values(review.merges || {}).concat(Object.values(review.nameMerges || {}));
  for (const merge of mergeRules) {
    if (!merge || !merge.targetName) continue;
    const source = data.entities.find((entity) => entity.id === merge.sourceId || normalizeText(entity.name) === normalizeText(merge.sourceName || ""));
    const target = data.entities.find((entity) => entity.id === merge.targetId) ||
      data.entities.find((entity) => normalizeText(entity.name) === normalizeText(merge.targetName) && entity.category === merge.targetCategory);
    if (source && target && source.id !== target.id) mergeEntityInto(source, target, data);
  }
  removeManualRelationships(data, review.removedManualRelationships || {});
  applyManualRelationships(data, review.manualRelationships || {});
  const visibleEntityIds = new Set(data.entities.map((entity) => entity.id));
  data.relationships = data.relationships.filter((relationship) => visibleEntityIds.has(relationship.source) && visibleEntityIds.has(relationship.target));
  return data;
}

function manualRelationshipKey(sourceId, targetId) {
  return [sourceId, targetId].sort().join("--");
}

function manualRelationshipDomId(key) {
  const slug = String(key || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return "manual-" + (slug || "item");
}

function entityByManualReference(item, side, data = DATA) {
  const id = item && item[side + "Id"];
  const entityById = id ? data.entities.find((entity) => entity.id === id) : null;
  if (entityById) return entityById;
  const category = item && item[side + "Category"];
  const review = readReview();
  const aliases = { ...(BUILT_REVIEW.aliases || {}), ...(review.aliases || {}) };
  const names = [item && item[side + "Name"]];
  if (id && aliases[id]) names.push(aliases[id]);
  const normalizedName = normalizeText(item && item[side + "Name"]);
  if (normalizedName && aliases[normalizedName]) names.push(aliases[normalizedName]);
  for (const nameValue of names) {
    const name = normalizeText(nameValue);
    if (!name) continue;
    const matches = data.entities.filter((entity) => normalizeText(entity.name) === name);
    if (category) {
      const categoryMatches = matches.filter((entity) => entity.category === category);
      if (categoryMatches.length === 1) return categoryMatches[0];
    }
    if (matches.length === 1) return matches[0];
  }
  return null;
}

function removeManualRelationships(data, removedManualRelationships) {
  const removed = new Set(Object.entries(removedManualRelationships || {}).map(([key, item]) => {
    if (item && typeof item === "object" && item.sourceId && item.targetId) {
      return manualRelationshipKey(item.sourceId, item.targetId);
    }
    return key;
  }));
  if (!removed.size) return;
  data.relationships = data.relationships.filter((relationship) => {
    if (relationship.type !== "manual") return true;
    return !removed.has(manualRelationshipKey(relationship.source, relationship.target)) && !removed.has(relationship.id.replace(/^manual-/, ""));
  });
}

function applyManualRelationships(data, manualRelationships) {
  const existingManualPairs = new Set(data.relationships
    .filter((relationship) => relationship.type === "manual")
    .map((relationship) => manualRelationshipKey(relationship.source, relationship.target)));
  for (const [id, item] of Object.entries(manualRelationships || {})) {
    if (!item || typeof item !== "object") continue;
    const source = entityByManualReference(item, "source", data);
    const target = entityByManualReference(item, "target", data);
    if (!source || !target || source.id === target.id) continue;
    const key = manualRelationshipKey(source.id, target.id);
    if (existingManualPairs.has(key)) continue;
    data.relationships.unshift({
      id: manualRelationshipDomId(key),
      source: source.id < target.id ? source.id : target.id,
      target: source.id < target.id ? target.id : source.id,
      sourceName: source.id < target.id ? source.name : target.name,
      targetName: source.id < target.id ? target.name : source.name,
      type: "manual",
      weight: 50,
      confidence: 1,
      evidenceSegmentIds: [],
      evidence: [],
    });
    existingManualPairs.add(key);
  }
}

function mergeEntityInto(source, target, data = DATA) {
  target.count = (target.count || 0) + (source.count || 0);
  target.evidenceIds = Array.from(new Set([...(target.evidenceIds || []), ...(source.evidenceIds || [])]));
  target.transcripts = Array.from(new Set([...(target.transcripts || []), ...(source.transcripts || [])])).sort();
  data.entities = data.entities.filter((entity) => entity.id !== source.id);
  const mergedRelationships = new Map();
  for (const relationship of data.relationships) {
    const next = { ...relationship };
    if (next.source === source.id) {
      next.source = target.id;
      next.sourceName = target.name;
    }
    if (next.target === source.id) {
      next.target = target.id;
      next.targetName = target.name;
    }
    if (next.source === next.target) continue;
    const key = [next.source, next.target].sort().join("::") + "::" + next.type;
    const existing = mergedRelationships.get(key);
    if (existing) {
      existing.weight += next.weight || 0;
      existing.evidenceSegmentIds = Array.from(new Set([...(existing.evidenceSegmentIds || []), ...(next.evidenceSegmentIds || [])]));
      existing.evidence = [...(existing.evidence || []), ...(next.evidence || [])].slice(0, 8);
    } else {
      mergedRelationships.set(key, next);
    }
  }
  data.relationships = Array.from(mergedRelationships.values());
}

function applyEntityCategory(entity, category, data = DATA) {
  entity.category = category;
  entity.categoryLabel = data.categoryLabels[category] || category;
  entity.topCategory = data.categoryToTop[category] || "needs_review";
  entity.topCategoryLabel = data.topCategoryLabels[entity.topCategory] || "Needs Review";
}

function applyEntityRename(entity, name, data = DATA) {
  const nextName = String(name || "").trim();
  if (!nextName) return;
  const previousName = entity.name;
  entity.name = nextName;
  entity.canonicalName = nextName;
  entity.significance = entity.significance ? entity.significance.replace(previousName, nextName) : entity.significance;
  for (const relationship of data.relationships) {
    if (relationship.source === entity.id) relationship.sourceName = nextName;
    if (relationship.target === entity.id) relationship.targetName = nextName;
  }
}

function rebuildIndexes() {
  entitiesById.clear();
  relationshipsById.clear();
  relationshipsByEntity.clear();
  for (const entity of DATA.entities) {
    entitiesById.set(entity.id, entity);
  }
  DATA.relationships = DATA.relationships.filter((relationship) => entitiesById.has(relationship.source) && entitiesById.has(relationship.target));
  for (const relationship of DATA.relationships) {
    relationshipsById.set(relationship.id, relationship);
    if (!relationshipsByEntity.has(relationship.source)) relationshipsByEntity.set(relationship.source, []);
    if (!relationshipsByEntity.has(relationship.target)) relationshipsByEntity.set(relationship.target, []);
    relationshipsByEntity.get(relationship.source).push(relationship);
    relationshipsByEntity.get(relationship.target).push(relationship);
  }
}

function setViewBox(x, y, w, h) {
  viewBox = { x, y, w, h };
  svg.setAttribute("viewBox", [x, y, w, h].join(" "));
  renderLabelLayer();
}

function graphHeaderInsetPx() {
  const topbar = document.querySelector(".topbar");
  if (!topbar) return 0;
  const rect = topbar.getBoundingClientRect();
  return Math.max(0, Math.ceil(rect.bottom + 52));
}

function graphSidebarInsetPx() {
  if (!cardEl.classList.contains("open") || isCompactViewport()) return 0;
  const rect = cardEl.getBoundingClientRect();
  return Math.max(0, Math.ceil(rect.right + 24));
}

function fitBoundsToViewport(minX, minY, maxX, maxY, options = {}) {
  const rect = svg.getBoundingClientRect();
  const rectWidth = Math.max(1, rect.width || svg.clientWidth || 1);
  const rectHeight = Math.max(1, rect.height || svg.clientHeight || 1);
  const topInset = options.reserveHeader === false ? 0 : graphHeaderInsetPx();
  const bottomInset = options.bottomInsetPx ?? 24;
  const leftInset = options.leftInsetPx ?? 0;
  const rightInset = options.rightInsetPx ?? 0;
  const padding = options.padding ?? 0;
  const availableW = Math.max(240, rectWidth - leftInset - rightInset);
  const availableH = Math.max(180, rectHeight - topInset - bottomInset);
  const paddedMinX = minX - padding;
  const paddedMinY = minY - padding;
  const paddedMaxX = maxX + padding;
  const paddedMaxY = maxY + padding;
  const contentW = Math.max(1, paddedMaxX - paddedMinX);
  const contentH = Math.max(1, paddedMaxY - paddedMinY);
  const ratio = rectWidth / rectHeight;
  let scale = Math.min(availableW / contentW, availableH / contentH);
  if (!Number.isFinite(scale) || scale <= 0) scale = 1;
  scale *= options.zoomFactor ?? 1;
  let width = clamp(rectWidth / scale, MIN_ZOOM_WIDTH, MAX_ZOOM_WIDTH);
  let height = width / ratio;
  if (height < MIN_ZOOM_HEIGHT) {
    height = MIN_ZOOM_HEIGHT;
    width = height * ratio;
  }
  if (height > MAX_ZOOM_HEIGHT) {
    height = MAX_ZOOM_HEIGHT;
    width = height * ratio;
  }
  const actualScale = rectWidth / width;
  const contentCx = (paddedMinX + paddedMaxX) / 2;
  const contentCy = (paddedMinY + paddedMaxY) / 2;
  const availableCenterX = leftInset + availableW / 2;
  const availableCenterY = topInset + availableH / 2;
  setViewBox(
    contentCx - availableCenterX / actualScale,
    contentCy - availableCenterY / actualScale,
    width,
    height
  );
}

function fitNodesToViewport(nodes, options = {}) {
  const items = nodes.filter(Boolean);
  if (!items.length) return;
  fitBoundsToViewport(
    Math.min(...items.map((node) => node.x - (node.r || 0))),
    Math.min(...items.map((node) => node.y - (node.r || 0))),
    Math.max(...items.map((node) => node.x + (node.r || 0))),
    Math.max(...items.map((node) => node.y + (node.r || 0))),
    options
  );
}

function isCompactViewport() {
  const rect = svg.getBoundingClientRect();
  return Math.min(rect.width || window.innerWidth, window.innerWidth) <= 820;
}

function fit() {
  setViewBox(0, -250, 2200, 2000);
}

function fitParentGraph() {
  setViewBox(-2100, -2500, 6400, 6600);
}

function fitEgoGraph(nodes, center) {
  const items = [center].concat(nodes);
  const maxRadius = Math.max(...items.map((node) => node.r));
  const longestLabel = Math.max(...items.map((node) => (node.raw?.name || node.label || "").length));
  const labelWidthPad = longestLabel * maxRadius * .42;
  const labelHeightPad = maxRadius * 4.8;
  const xPad = Math.max(maxRadius * 5.2, labelWidthPad);
  const topPad = Math.max(maxRadius * 2.8, labelHeightPad * .55);
  const bottomPad = Math.max(maxRadius * 4.2, labelHeightPad);
  const minX = Math.min(...items.map((node) => node.x - node.r)) - xPad;
  const maxX = Math.max(...items.map((node) => node.x + node.r)) + xPad;
  const minY = Math.min(...items.map((node) => node.y - node.r)) - topPad;
  const maxY = Math.max(...items.map((node) => node.y + node.r)) + bottomPad;
  fitBoundsToViewport(minX, minY, maxX, maxY, {
    reserveHeader: true,
    bottomInsetPx: 32,
    leftInsetPx: graphSidebarInsetPx(),
    zoomFactor: isCompactViewport() ? 1.08 : 1.18,
  });
}

function fitHomeCategoryGraph(nodes, center) {
  const items = [center].concat(nodes);
  const maxRadius = Math.max(...items.map((node) => node.r));
  const longestLabel = Math.max(...nodes.map((node) => (node.raw?.name || node.label || "").length));
  const labelWidthPad = longestLabel * maxRadius * .34;
  const xPad = Math.max(maxRadius * 4.2, labelWidthPad);
  const topPad = maxRadius * 2.2;
  const bottomPad = maxRadius * 3.2;
  const minX = Math.min(...items.map((node) => node.x - node.r)) - xPad;
  const maxX = Math.max(...items.map((node) => node.x + node.r)) + xPad;
  const minY = Math.min(...items.map((node) => node.y - node.r)) - topPad;
  const maxY = Math.max(...items.map((node) => node.y + node.r)) + bottomPad;
  fitBoundsToViewport(minX, minY, maxX, maxY, {
    reserveHeader: true,
    bottomInsetPx: 88,
    zoomFactor: isCompactViewport() ? 1.1 : 1.25,
  });
}

function fitSelectedEgoGraph(nodes, center) {
  const items = [center].concat(nodes).filter(Boolean);
  if (!items.length) return;
  const rect = svg.getBoundingClientRect();
  const rectWidth = Math.max(1, rect.width || svg.clientWidth || 1);
  const rectHeight = Math.max(1, rect.height || svg.clientHeight || 1);
  const topInset = Math.max(24, graphHeaderInsetPx() - 120);
  const bottomInset = 32;
  const leftInset = isCompactViewport() ? 0 : Math.min(graphSidebarInsetPx(), 340);
  const rightInset = 24;
  const availableW = Math.max(180, rectWidth - leftInset - rightInset);
  const availableH = Math.max(180, rectHeight - topInset - bottomInset);
  const minX = Math.min(...items.map((node) => node.x - node.r));
  const maxX = Math.max(...items.map((node) => node.x + node.r));
  const minY = Math.min(...items.map((node) => node.y - node.r));
  const maxY = Math.max(...items.map((node) => node.y + node.r));
  const contentW = Math.max(1, maxX - minX);
  const contentH = Math.max(1, maxY - minY);
  const heightScale = (availableH * .9) / contentH;
  const widthScale = (availableW * .94) / contentW;
  let scale = Math.min(heightScale, widthScale);
  if (!Number.isFinite(scale) || scale <= 0) scale = 1;
  scale *= isCompactViewport() ? .96 : 1;
  let width = clamp(rectWidth / scale, MIN_ZOOM_WIDTH, MAX_ZOOM_WIDTH);
  let height = width / (rectWidth / rectHeight);
  if (height < MIN_ZOOM_HEIGHT) {
    height = MIN_ZOOM_HEIGHT;
    width = height * (rectWidth / rectHeight);
  }
  if (height > MAX_ZOOM_HEIGHT) {
    height = MAX_ZOOM_HEIGHT;
    width = height * (rectWidth / rectHeight);
  }
  const actualScale = rectWidth / width;
  const contentCx = (minX + maxX) / 2;
  const contentCy = (minY + maxY) / 2;
  const availableCenterX = leftInset + availableW / 2;
  const availableCenterY = topInset + availableH / 2;
  setViewBox(
    contentCx - availableCenterX / actualScale,
    contentCy - availableCenterY / actualScale,
    width,
    height
  );
}

function fitCategoryDrillViewport(activeCategoryNode, nodes) {
  if (!isCompactViewport()) {
    const items = [activeCategoryNode].concat(nodes).filter(Boolean);
    const rect = svg.getBoundingClientRect();
    const rectWidth = Math.max(1, rect.width || svg.clientWidth || 1);
    const rectHeight = Math.max(1, rect.height || svg.clientHeight || 1);
    const topInset = Math.max(24, graphHeaderInsetPx() - 36);
    const bottomInset = 64;
    const availableH = Math.max(180, rectHeight - topInset - bottomInset);
    const minX = Math.min(...items.map((node) => node.x - (node.r || 0)));
    const maxX = Math.max(...items.map((node) => node.x + (node.r || 0)));
    const minY = Math.min(...items.map((node) => node.y - (node.r || 0)));
    const maxY = Math.max(...items.map((node) => node.y + (node.r || 0)));
    const contentW = Math.max(1, maxX - minX);
    const contentH = Math.max(1, maxY - minY);
    const heightScale = (availableH * .87) / contentH;
    const widthScale = (rectWidth * .84) / contentW;
    let scale = Math.min(heightScale, widthScale);
    if (!Number.isFinite(scale) || scale <= 0) scale = 1;
    let width = clamp(rectWidth / scale, MIN_ZOOM_WIDTH, MAX_ZOOM_WIDTH);
    let height = width / (rectWidth / rectHeight);
    if (height < MIN_ZOOM_HEIGHT) {
      height = MIN_ZOOM_HEIGHT;
      width = height * (rectWidth / rectHeight);
    }
    if (height > MAX_ZOOM_HEIGHT) {
      height = MAX_ZOOM_HEIGHT;
      width = height * (rectWidth / rectHeight);
    }
    const actualScale = rectWidth / width;
    const contentCx = (minX + maxX) / 2;
    const contentCy = (minY + maxY) / 2;
    const availableCenterY = topInset + availableH / 2;
    setViewBox(
      contentCx - rectWidth / actualScale / 2,
      contentCy - availableCenterY / actualScale,
      width,
      height
    );
    return;
  }
  const focusRadius = 760;
  fitBoundsToViewport(
    activeCategoryNode.x - focusRadius,
    activeCategoryNode.y - focusRadius,
    activeCategoryNode.x + focusRadius,
    activeCategoryNode.y + focusRadius,
    {
      padding: 80,
      reserveHeader: true,
      bottomInsetPx: 48,
      leftInsetPx: 12,
      rightInsetPx: 12,
    }
  );
}

function spreadContextNodes(nodes, center) {
  if (nodes.length < 2) return nodes;
  const sorted = nodes.slice().sort((a, b) => a.angle - b.angle);
  for (let pass = 0; pass < 5; pass++) {
    for (let index = 1; index < sorted.length; index++) {
      const previous = sorted[index - 1];
      const current = sorted[index];
      const radius = Math.max(1, (previous.contextRadius + current.contextRadius) / 2);
      const previousName = previous.raw?.name || previous.label || "";
      const currentName = current.raw?.name || current.label || "";
      const labelSpan = Math.max(previousName.length, currentName.length) * 18;
      const minGap = Math.max(.18, Math.min(.42, labelSpan / radius));
      const gap = current.angle - previous.angle;
      if (gap >= minGap) continue;
      const shift = (minGap - gap) / 2;
      previous.angle -= shift;
      current.angle += shift;
    }
  }
  for (const node of nodes) {
    node.x = center.x + Math.cos(node.angle) * node.contextRadius;
    node.y = center.y + Math.sin(node.angle) * node.contextRadius;
  }
  return nodes;
}

function setCornerLabel(title, detail) {
  if (!title) {
    cornerLabelEl.classList.remove("open");
    cornerLabelEl.innerHTML = "";
    return;
  }
  cornerLabelEl.innerHTML = '<strong>' + esc(title) + '</strong><span>' + esc(detail || "") + '</span>';
  cornerLabelEl.classList.add("open");
}

function setEventsClaimsCornerLabel(view, detail) {
  const selectedTimeline = view === "timeline" ? " selected" : "";
  const selectedGraph = view === "graph" ? " selected" : "";
  const title = view === "timeline" ? "Timeline" : "Graph";
  cornerLabelEl.innerHTML =
    '<strong><span class="corner-view-switcher"><span class="corner-view-switcher-text">' + esc(title) + '</span>' +
      '<select id="events-view-switcher" aria-label="Events & Claims view">' +
        '<option value="timeline"' + selectedTimeline + '>Timeline</option>' +
        '<option value="graph"' + selectedGraph + '>Graph</option>' +
      '</select></span></strong><span>' + esc(detail || "") + '</span>';
  cornerLabelEl.classList.add("open");
  const switcher = document.getElementById("events-view-switcher");
  if (switcher) {
    switcher.addEventListener("change", () => {
      eventsClaimsView = switcher.value === "graph" ? "graph" : "timeline";
      activeCategory = "events_claims";
      selectedEntityId = null;
      mode = "categories";
      hideHoverPreview();
      render();
      focusSelectedGraphLabel();
    });
  }
}

function setGraphLabels(items) {
  labelItems = items;
  renderLabelLayer();
}

function nodeLabel(id, kind, node, primary, secondary = "", radius = node.r) {
  return {
    id,
    kind,
    x: node.x,
    y: node.y + radius,
    primary,
    secondary,
  };
}

function graphViewportTransform() {
  const rect = svg.getBoundingClientRect();
  const svgRatio = rect.width / rect.height;
  const viewRatio = viewBox.w / viewBox.h;
  const scale = svgRatio > viewRatio ? rect.height / viewBox.h : rect.width / viewBox.w;
  const renderedW = viewBox.w * scale;
  const renderedH = viewBox.h * scale;
  return {
    rect,
    scale,
    offsetX: rect.left + (rect.width - renderedW) / 2,
    offsetY: rect.top + (rect.height - renderedH) / 2,
  };
}

function graphToScreen(x, y) {
  const transform = graphViewportTransform();
  return {
    x: transform.offsetX + (x - viewBox.x) * transform.scale,
    y: transform.offsetY + (y - viewBox.y) * transform.scale,
  };
}

function graphLabelTop(pointY) {
  const topbar = document.querySelector(".topbar");
  const headerBottom = topbar ? topbar.getBoundingClientRect().bottom : 0;
  return Math.max(pointY + 6, headerBottom + 8);
}

function estimateLabelWidth(item) {
  if (/\btimeline-date-label\b/.test(item.className || "")) return Math.min(170, Math.max(76, item.primary.length * 7.8));
  if (/\btimeline-connected-label\b/.test(item.className || "")) {
    return Math.min(160, Math.max(78, Math.max(item.primary.length * 7.4, (item.secondary || "").length * 6.5)));
  }
  return Math.min(190, Math.max(84, Math.max(item.primary.length * 8, (item.secondary || "").length * 6.8)));
}

function estimateLabelHeight(item, width) {
  const primaryChars = Math.max(8, Math.floor(width / 7.4));
  const secondaryChars = Math.max(8, Math.floor(width / 6.5));
  const primaryLines = Math.max(1, Math.ceil(item.primary.length / primaryChars));
  const secondaryLines = item.secondary ? Math.max(1, Math.ceil(item.secondary.length / secondaryChars)) : 0;
  return primaryLines * 13 + secondaryLines * 11 + (secondaryLines ? 5 : 0);
}

function rectsOverlap(a, b, gap = 6) {
  return a.left - gap < b.right &&
    a.right + gap > b.left &&
    a.top - gap < b.bottom &&
    a.bottom + gap > b.top;
}

function screenToGraph(x, y) {
  const transform = graphViewportTransform();
  return {
    x: viewBox.x + (x - transform.offsetX) / transform.scale,
    y: viewBox.y + (y - transform.offsetY) / transform.scale,
  };
}

function renderLabelLayer() {
  if (!graphLabelsEl || !labelItems.length) {
    if (graphLabelsEl) graphLabelsEl.innerHTML = "";
    return;
  }
  const positioned = labelItems.map((item) => {
    const point = graphToScreen(item.x, item.y);
    return { item, point, top: graphLabelTop(point.y) };
  });
  graphLabelsEl.innerHTML = positioned.map(({ item, point, top }) => {
    if (item.kind === "annotation") {
      return '<div class="html-graph-label' + (item.className ? ' ' + esc(item.className) : '') + '" aria-hidden="true" style="left:' + point.x.toFixed(1) + 'px;top:' + top.toFixed(1) + 'px">' +
        '<span class="label-primary">' + esc(item.primary) + '</span>' +
        (item.secondary ? '<span class="label-secondary">' + esc(item.secondary) + '</span>' : '') +
      '</div>';
    }
    const attr = item.kind === "category"
      ? ' data-label-category="' + esc(item.id) + '"'
      : item.kind === "category-list"
        ? ' data-label-category-list="' + esc(item.id) + '"'
        : ' data-label-entity="' + esc(item.id) + '"';
    const state = ((item.kind === "category" || item.kind === "category-list") && activeCategory === item.id) || (item.kind === "entity" && selectedEntityId === item.id)
      ? ' aria-current="true"'
      : "";
    const secondary = item.secondary ? ". " + item.secondary : "";
    const action = item.kind === "category"
      ? "Open category"
      : item.kind === "category-list"
        ? "Open full entity list"
        : "Open entity";
    return '<div class="html-graph-label' + (item.className ? ' ' + esc(item.className) : '') + '" role="button" tabindex="0" aria-label="' + esc(action + ": " + item.primary + secondary) + '"' + state + ' style="left:' + point.x.toFixed(1) + 'px;top:' + top.toFixed(1) + 'px"' + attr + '>' +
      '<span class="label-primary">' + esc(item.primary) + '</span>' +
      (item.secondary ? '<span class="label-secondary">' + esc(item.secondary) + '</span>' : '') +
    '</div>';
  }).join("");
}

function render() {
  if (mode === "neighborhood" && selectedEntityId && entitiesById.has(selectedEntityId)) {
    renderNeighborhood(entitiesById.get(selectedEntityId));
  } else if (mode === "category-list" && activeCategory) {
    renderCategoryGrid(activeCategory);
  } else if (activeCategory) {
    renderCategory(activeCategory);
  } else {
    renderCategories();
  }
}

function renderCategories() {
  const theme = currentTheme();
  const layout = buildCategoryLayout();
  const nodes = layout.nodes;
  const nodeById = layout.nodeById;
  const maxEdge = layout.maxEdge;
  const edges = layout.edges;
  const center = layout.center;
  const spokes = nodes.map((node) => ({ source: center.id, target: node.id, weight: node.count || 1 }));
  const spokeNodeById = new Map(nodeById);
  spokeNodeById.set(center.id, center);
  const maxSpoke = Math.max(1, ...spokes.map((edge) => edge.weight));
  svg.innerHTML =
    drawEdges(spokes, spokeNodeById, maxSpoke, "ego-spoke") +
    drawEdges(edges, nodeById, maxEdge, "ego-context") +
    '<g class="graph-node home-root" data-home-root="true" aria-hidden="true">' +
      '<circle cx="' + center.x + '" cy="' + center.y + '" r="' + center.r + '" fill="' + theme.activeHalo + '" stroke="' + theme.primary + '" stroke-width="1" opacity=".92"></circle>' +
    '</g>' +
    nodes.map((node) => {
    return '<g class="graph-node" data-category="' + esc(node.id) + '">' +
      '<circle cx="' + node.x + '" cy="' + node.y + '" r="' + node.r + '" fill="' + theme.primary + '" opacity=".9"></circle>' +
    '</g>';
  }).join("");
  setGraphLabels([nodeLabel(
    center.id,
    "annotation",
    center,
    "UFO Files",
    DATA.manifest.counts.entities.toLocaleString() + " entities",
    center.r
  )].concat(nodes.map((node) => nodeLabel(
    node.id,
    "category",
    node,
    truncate(node.label, 24),
    node.count + " entities · " + node.mentions + " mentions"
  ))));
  statusEl.textContent = nodes.length + " groups · " + DATA.manifest.counts.entities.toLocaleString() + " entities · select a group";
  cardEl.classList.remove("open");
  setCornerLabel(null);
  wireCategoryNodes();
  fitHomeCategoryGraph(nodes, center);
}

function buildCategoryLayout() {
  const categoryStats = new Map();
  for (const entity of DATA.entities) {
    const stat = categoryStats.get(entity.topCategory) || { id: entity.topCategory, label: entity.topCategoryLabel, count: 0, mentions: 0 };
    stat.count += 1;
    stat.mentions += entity.count || 0;
    categoryStats.set(entity.topCategory, stat);
  }
  const categories = Object.keys(DATA.topCategoryLabels)
    .map((id) => categoryStats.get(id) || { id, label: DATA.topCategoryLabels[id], count: 0, mentions: 0 })
    .filter((category) => category.count > 0);
  const categorySet = new Set(categories.map((category) => category.id));
  const edgeWeights = new Map();
  for (const relationship of DATA.relationships) {
    const source = entitiesById.get(relationship.source);
    const target = entitiesById.get(relationship.target);
    if (!source || !target || source.topCategory === target.topCategory) continue;
    if (!categorySet.has(source.topCategory) || !categorySet.has(target.topCategory)) continue;
    const key = [source.topCategory, target.topCategory].sort().join("::");
    edgeWeights.set(key, (edgeWeights.get(key) || 0) + relationship.weight);
  }
  const center = {
    id: "ufo-files-root",
    label: "UFO Files",
    x: 1100,
    y: 750,
    r: 72,
    count: DATA.manifest.counts.entities || 0,
    mentions: DATA.manifest.counts.mentions || 0,
    raw: { name: "UFO Files" },
  };
  const nodes = parentCategoryNodes(categories.sort((a, b) => b.count - a.count), center.x, center.y);
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const maxEdge = Math.max(1, ...edgeWeights.values());
  const edges = Array.from(edgeWeights.entries()).sort((a, b) => b[1] - a[1]).slice(0, 95).map(([key, weight]) => {
    const [source, target] = key.split("::");
    return { source, target, weight };
  });
  return { nodes, nodeById, maxEdge, edges, edgeWeights, center };
}

function renderCategory(categoryId) {
  if (categoryId === "events_claims" && eventsClaimsView === "timeline") {
    renderEventsTimeline(categoryId);
    return;
  }
  const theme = currentTheme();
  const label = DATA.topCategoryLabels[categoryId] || categoryId;
  const categoryLayout = buildCategoryLayout();
  const activeCategoryNode = categoryLayout.nodeById.get(categoryId) || { x: 1100, y: 750, r: 24 };
  const allPrimary = DATA.entities.filter((entity) => entity.topCategory === categoryId).sort((a, b) => entityGraphScore(b) - entityGraphScore(a));
  const primary = allPrimary.slice(0, 50);
  const primarySet = new Set(primary.map((entity) => entity.id));
  const rels = DATA.relationships.filter((relationship) => primarySet.has(relationship.source) && primarySet.has(relationship.target)).slice(0, 150);
  const nodes = radialNodes(primary, activeCategoryNode.x, activeCategoryNode.y, 460, 900, (entity) => entity.count || 1);
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const maxEdge = Math.max(1, ...rels.map((relationship) => relationship.weight));
  const sharedNeighborById = new Map();
  const sharedEdgeWeights = new Map();
  for (const node of nodes) {
    for (const relationship of relationshipsByEntity.get(node.id) || []) {
      const outsideId = relationship.source === node.id ? relationship.target : relationship.source;
      const outside = entitiesById.get(outsideId);
      if (!outside || outside.topCategory === categoryId || primarySet.has(outsideId)) continue;
      if (!sharedNeighborById.has(outsideId)) {
        sharedNeighborById.set(outsideId, { entity: outside, sources: new Set(), weight: 0 });
      }
      const shared = sharedNeighborById.get(outsideId);
      shared.sources.add(node.id);
      shared.weight += relationship.weight;
      const edgeKey = node.id + "::" + outsideId;
      sharedEdgeWeights.set(edgeKey, (sharedEdgeWeights.get(edgeKey) || 0) + relationship.weight);
    }
  }
  const sharedNeighbors = Array.from(sharedNeighborById.entries())
    .map(([id, item]) => ({ id, ...item, sourceCount: item.sources.size }))
    .filter((item) => item.sourceCount >= 2)
    .sort((a, b) => b.sourceCount - a.sourceCount || b.weight - a.weight || entityGraphScore(b.entity) - entityGraphScore(a.entity))
    .slice(0, 22);
  const sharedNeighborIds = new Set(sharedNeighbors.map((item) => item.id));
  const maxSharedWeight = Math.max(1, ...sharedNeighbors.map((item) => item.weight));
  const sharedNodes = sharedNeighbors.map((item, index) => {
    const sourceNodes = Array.from(item.sources).map((id) => nodeById.get(id)).filter(Boolean);
    const avgX = sourceNodes.reduce((total, node) => total + node.x, 0) / Math.max(1, sourceNodes.length);
    const avgY = sourceNodes.reduce((total, node) => total + node.y, 0) / Math.max(1, sourceNodes.length);
    const dx = avgX - activeCategoryNode.x;
    const dy = avgY - activeCategoryNode.y;
    const length = Math.max(1, Math.hypot(dx, dy));
    const angle = Math.atan2(dy, dx) + ((index % 5) - 2) * .08;
    const radius = 1260 + (index % 3) * 120;
    return {
      id: item.id,
      x: activeCategoryNode.x + Math.cos(angle) * radius,
      y: activeCategoryNode.y + Math.sin(angle) * radius,
      r: 9 + Math.sqrt(item.weight / maxSharedWeight) * 13,
      angle,
      contextRadius: radius,
      weight: item.weight,
      sourceCount: item.sourceCount,
      raw: item.entity,
    };
  });
  spreadContextNodes(sharedNodes, activeCategoryNode);
  const sharedNodeById = new Map(sharedNodes.map((node) => [node.id, node]));
  const sharedNodesSvg = sharedNodes.map((node) => {
    return '<g class="graph-node" data-entity="' + esc(node.id) + '">' +
      '<circle cx="' + node.x + '" cy="' + node.y + '" r="' + node.r + '" fill="' + theme.entityAlt + '" stroke="' + theme.primary + '" stroke-width="1" opacity=".76"></circle>' +
    '</g>';
  }).join("");
  const contextEdges = Array.from(sharedEdgeWeights.entries())
    .map(([key, weight]) => {
      const [childId, outsideId] = key.split("::");
      return { childId, outsideId, weight };
    })
    .filter((edge) => nodeById.has(edge.childId) && sharedNeighborIds.has(edge.outsideId) && sharedNodeById.has(edge.outsideId))
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 80);
  const maxContextEdge = Math.max(1, ...contextEdges.map((edge) => edge.weight));
  const contextEdgesSvg = contextEdges.map((edge) => {
    const child = nodeById.get(edge.childId);
    const outside = sharedNodeById.get(edge.outsideId);
    if (!child || !outside) return "";
    const width = (0.7 + (edge.weight / maxContextEdge) * 3.4).toFixed(1);
    return '<line x1="' + child.x + '" y1="' + child.y + '" x2="' + outside.x + '" y2="' + outside.y + '" stroke="' + theme.primary + '" stroke-width="' + width + '" opacity=".34"></line>';
  }).join("");
  svg.innerHTML =
    contextEdgesSvg +
    '<g class="graph-node" data-category-list="' + esc(categoryId) + '">' +
      '<circle cx="' + activeCategoryNode.x + '" cy="' + activeCategoryNode.y + '" r="' + activeCategoryNode.r + '" fill="' + theme.activeHalo + '" stroke="' + theme.primary + '" stroke-width="1"></circle>' +
    '</g>' +
    drawRelationshipEdges(rels, nodeById, maxEdge, "drill") +
    nodes.map((node) => {
      const entity = node.raw;
      const inCategory = entity.topCategory === categoryId;
      return '<g class="graph-node" data-entity="' + esc(entity.id) + '">' +
        '<circle cx="' + node.x + '" cy="' + node.y + '" r="' + node.r + '" fill="' + (inCategory ? theme.entityFill : theme.entityAlt) + '" stroke="' + (inCategory ? theme.bgStroke : theme.primary) + '" stroke-width="1"></circle>' +
      '</g>';
    }).join("") +
    sharedNodesSvg;
  const sharedLabelNodes = sharedNodes
    .slice()
    .sort((a, b) => b.sourceCount - a.sourceCount || b.weight - a.weight)
    .slice(0, 8);
  setGraphLabels([nodeLabel(
    categoryId,
    "category-list",
    activeCategoryNode,
    "View all " + truncate(label, 18),
    allPrimary.length.toLocaleString() + " entities",
    activeCategoryNode.r
  )].concat(nodes.map((node) => nodeLabel(
    node.raw.id,
    "entity",
    node,
    truncate(entityDisplayName(node.raw), 24)
  ))).concat(sharedLabelNodes.map((node) => nodeLabel(
    node.id,
    "entity",
    node,
    truncate(entityDisplayName(node.raw), 22),
    node.sourceCount + " connected nodes",
    node.r
  ))));
  statusEl.textContent = label + " · select an entity for its direct relationship graph";
  if (categoryId === "events_claims") {
    setEventsClaimsCornerLabel("graph", "Relationship graph · switch back to hard-date timeline");
  } else {
    setCornerLabel(null);
  }
  wireEntityNodes();
  wireCategoryNodes();
  wireCategoryListNodes();
  fitCategoryDrillViewport(activeCategoryNode, nodes);
}

function renderEventsTimeline(categoryId) {
  const theme = currentTheme();
  const label = DATA.topCategoryLabels[categoryId] || categoryId;
  const categoryLayout = buildCategoryLayout();
  const activeCategoryNode = categoryLayout.nodeById.get(categoryId) || { x: 1100, y: 750, r: 24 };
  const timeline = buildEventsTimeline();
  if (!timeline.length) {
    renderCategoryGrid(categoryId);
    return;
  }
  const baseY = 760;
  const startX = 420;
  const firstYear = timeline[0].date.getUTCFullYear();
  const lastYear = timeline[timeline.length - 1].date.getUTCFullYear();
  const timelineStartYear = Math.floor(firstYear / 10) * 10;
  const timelineEndYear = Math.ceil(lastYear / 10) * 10;
  const timelineStartDate = Date.UTC(timelineStartYear, 0, 1);
  const timelineEndDate = Date.UTC(timelineEndYear, 0, 1);
  const timelineDuration = Math.max(1, timelineEndDate - timelineStartDate);
  const width = Math.max(4800, (timelineEndYear - timelineStartYear) * 48);
  const endX = startX + width;
  const categoryControlNode = { ...activeCategoryNode, x: startX - 230, y: baseY - 430, r: Math.max(18, Math.min(24, activeCategoryNode.r)) };
  const maxWeight = Math.max(1, ...timeline.map((item) => item.weight));
  const nodes = [];
  const edges = [];
  const labels = [];
  const dateNodes = timeline.map((item, index) => {
    const x = startX + ((item.date.getTime() - timelineStartDate) / timelineDuration) * width;
    const dateOffset = timelineDateOffset(index);
    const y = baseY + dateOffset;
    const node = {
      id: item.dateEntity.id,
      x,
      y,
      r: 9 + Math.sqrt(item.weight / maxWeight) * 9,
      raw: item.dateEntity,
      item,
      labelOffset: 0,
    };
    nodes.push(node);
    return node;
  });
  const entityNodesById = new Map();
  const entityLinks = [];
  function addTimelineEntity(dateIndex, dateNode, entity, weight, kind, rank) {
    const existing = entityNodesById.get(entity.id) || {
      id: entity.id,
      entityId: entity.id,
      raw: entity,
      kind,
      weight: 0,
      dateRefs: [],
    };
    if (kind === "event") existing.kind = "event";
    existing.weight += weight;
    existing.dateRefs.push({ dateIndex, dateNode, weight, kind, rank });
    entityNodesById.set(entity.id, existing);
    entityLinks.push({ source: dateNode, target: existing, weight, isContext: kind !== "event" });
  }
  for (const [dateIndex, dateNode] of dateNodes.entries()) {
    const item = dateNode.item;
    const eventCount = Math.min(3, item.events.length);
    for (const [eventIndex, eventItem] of item.events.slice(0, eventCount).entries()) {
      addTimelineEntity(dateIndex, dateNode, eventItem.entity, eventItem.weight, "event", eventIndex);
    }
    const contextCount = Math.min(4, item.context.length);
    for (const [contextIndex, contextItem] of item.context.slice(0, contextCount).entries()) {
      addTimelineEntity(dateIndex, dateNode, contextItem.entity, contextItem.weight, "context", contextIndex);
    }
  }
  const entityNodes = Array.from(entityNodesById.values())
    .sort((a, b) => Math.min(...a.dateRefs.map((ref) => ref.dateIndex)) - Math.min(...b.dateRefs.map((ref) => ref.dateIndex)) || entityGraphScore(b.raw) - entityGraphScore(a.raw));
  const maxEntityWeight = Math.max(1, ...entityNodes.map((node) => node.weight));
  for (const [nodeIndex, node] of entityNodes.entries()) {
    const firstRef = node.dateRefs.slice().sort((a, b) => a.dateIndex - b.dateIndex || a.rank - b.rank)[0];
    const totalWeight = node.dateRefs.reduce((total, ref) => total + ref.weight, 0) || 1;
    const averageX = node.dateRefs.reduce((total, ref) => total + ref.dateNode.x * ref.weight, 0) / totalWeight;
    const side = firstRef.rank % 2 === 0 ? -1 : 1;
    const lane = Math.floor(firstRef.rank / 2);
    const band = node.kind === "event"
      ? [520, 780, 1080, 1340][(firstRef.dateIndex + firstRef.rank * 2 + nodeIndex) % 4]
      : [420, 650, 900, 1160][(firstRef.dateIndex * 2 + firstRef.rank + nodeIndex) % 4];
    node.x = averageX + ((nodeIndex % 9) - 4) * 46;
    node.y = baseY + side * (band + lane * 110) * TIMELINE_VERTICAL_SCALE;
    node.r = node.kind === "event"
      ? 8 + Math.sqrt(node.weight / maxEntityWeight) * 9
      : 4.8 + Math.sqrt(node.weight / maxEntityWeight) * 7;
    node.isContext = node.kind !== "event";
    nodes.push(node);
  }
  spreadTimelineEntityNodes(entityNodes, baseY);
  spreadTimelineLabelNodes(dateNodes, entityNodes, baseY, width);
  for (const node of dateNodes) {
    labels.push({
      id: node.item.dateEntity.id,
      kind: "entity",
      className: "timeline-date-label",
      x: node.x,
      y: node.y + node.r,
      primary: node.item.displayDate,
      secondary: node.item.events.length + " " + pluralize("link", node.item.events.length),
    });
  }
  const labeledContextIds = new Set(entityNodes
    .filter((node) => node.isContext)
    .sort((a, b) => b.weight - a.weight || b.dateRefs.length - a.dateRefs.length || entityGraphScore(b.raw) - entityGraphScore(a.raw))
    .slice(0, 8)
    .map((node) => node.entityId));
  for (const node of entityNodes) {
    if (node.isContext && node.dateRefs.length < 2 && !labeledContextIds.has(node.entityId)) continue;
    labels.push({
      id: node.entityId,
      kind: "entity",
      className: "timeline-connected-label",
      x: node.x,
      y: node.y + node.r,
      primary: truncate(entityDisplayName(node.raw), node.kind === "event" ? 24 : 22),
      secondary: node.dateRefs.length > 1
        ? node.dateRefs.length + " date links"
        : truncate(node.raw.categoryLabel || node.raw.topCategoryLabel || "Related", 24),
    });
  }
  const tickYears = [];
  for (let year = timelineStartYear; year <= timelineEndYear; year += 10) {
    const x = startX + ((Date.UTC(year, 0, 1) - timelineStartDate) / timelineDuration) * width;
    const isFirstYear = year === timelineStartYear;
    const isLastYear = year === timelineEndYear;
    labels.push({
      id: "year-" + year,
      kind: "annotation",
      className: "timeline-year-label",
      x: x + (isFirstYear ? 110 : isLastYear ? -110 : 0),
      y: baseY + 28,
      primary: String(year),
      secondary: "",
    });
    tickYears.push('<g class="timeline-date-marker" aria-hidden="true">' +
      '<line class="timeline-tick" x1="' + x.toFixed(1) + '" y1="' + (baseY - 28) + '" x2="' + x.toFixed(1) + '" y2="' + (baseY + 28) + '"></line>' +
    '</g>');
  }
  const tickYearSvg = tickYears.join("");
  svg.innerHTML =
    '<line class="timeline-axis" x1="' + startX + '" y1="' + baseY + '" x2="' + endX + '" y2="' + baseY + '"></line>' +
    tickYearSvg +
    dateNodes.map((node) => {
      return '<line class="timeline-date-stem" x1="' + node.x.toFixed(1) + '" y1="' + baseY + '" x2="' + node.x.toFixed(1) + '" y2="' + node.y.toFixed(1) + '"></line>';
    }).join("") +
    entityLinks.map((edge) => '<line class="timeline-link" x1="' + edge.source.x.toFixed(1) + '" y1="' + edge.source.y.toFixed(1) + '" x2="' + edge.target.x.toFixed(1) + '" y2="' + edge.target.y.toFixed(1) + '" opacity="' + (edge.isContext ? ".14" : ".26") + '"></line>').join("") +
    dateNodes.map((node) => {
      return '<g class="graph-node" data-entity="' + esc(node.raw.id) + '">' +
        '<circle class="timeline-date" cx="' + node.x.toFixed(1) + '" cy="' + node.y + '" r="' + node.r.toFixed(1) + '"></circle>' +
        '<title>' + esc(node.item.displayDate + " · exact parsed date · " + node.item.events.length + " linked " + pluralize("entity", node.item.events.length)) + '</title>' +
      '</g>';
    }).join("") +
    entityNodes.map((node) => {
      return '<g class="graph-node" data-entity="' + esc(node.entityId) + '">' +
        '<circle class="' + (node.isContext ? 'timeline-context' : 'timeline-event') + '" cx="' + node.x.toFixed(1) + '" cy="' + node.y.toFixed(1) + '" r="' + node.r.toFixed(1) + '"></circle>' +
        '<title>' + esc(entityDisplayName(node.raw) + " · " + node.dateRefs.length + " timeline " + pluralize("link", node.dateRefs.length)) + '</title>' +
      '</g>';
    }).join("");
  setGraphLabels(labels);
  statusEl.textContent = "Events timeline · " + timeline.length.toLocaleString() + " exact dated source links · fuzzy dates excluded";
  setEventsClaimsCornerLabel("timeline", "Exact parsed dates only · event, document, and source links included");
  cardEl.classList.remove("open");
  wireEntityNodes();
  const timelineMinY = Math.min(
    ...dateNodes.map((node) => node.y + Math.min(0, node.labelOffset) - node.r - 70),
    ...entityNodes.map((node) => node.y - node.r - 74)
  );
  const timelineMaxY = Math.max(
    ...dateNodes.map((node) => node.y + Math.max(0, node.labelOffset) + node.r + 84),
    ...entityNodes.map((node) => node.y + node.r + 92)
  );
  fitTimelineAxisToViewport(startX, endX, timelineMinY, timelineMaxY);
}

function fitTimelineAxisToViewport(startX, endX, minY, maxY) {
  const rect = svg.getBoundingClientRect();
  const rectWidth = Math.max(1, rect.width || svg.clientWidth || 1);
  const rectHeight = Math.max(1, rect.height || svg.clientHeight || 1);
  const topInset = Math.max(24, graphHeaderInsetPx() - 20);
  const bottomInset = 12;
  const availableH = Math.max(180, rectHeight - topInset - bottomInset);
  const width = Math.max(MIN_ZOOM_WIDTH, endX - startX);
  const height = Math.max(MIN_ZOOM_HEIGHT, width / (rectWidth / rectHeight));
  const actualScale = rectWidth / width;
  const focusY = (minY + maxY) / 2;
  setViewBox(
    startX,
    focusY - (topInset + availableH / 2) / actualScale,
    width,
    height
  );
}

function timelineDateOffset(index) {
  const lanes = [-260, 300, -520, 560, -760, 800, -960, 1000];
  return lanes[index % lanes.length] * TIMELINE_VERTICAL_SCALE;
}

function timelineDateLabelXOffset(index) {
  const offsets = [-54, 58, 0, -82, 86, -28, 34, 0];
  return offsets[index % offsets.length];
}

function spreadTimelineEntityNodes(nodes, baseY) {
  const lanes = [-1, 1];
  for (const side of lanes) {
    const sideNodes = nodes
      .filter((node) => side < 0 ? node.y < baseY : node.y >= baseY)
      .sort((a, b) => a.x - b.x || Math.abs(a.y - baseY) - Math.abs(b.y - baseY));
    for (let index = 0; index < sideNodes.length; index++) {
      const current = sideNodes[index];
      for (let previousIndex = 0; previousIndex < index; previousIndex++) {
        const previous = sideNodes[previousIndex];
        const horizontalGap = Math.abs(current.x - previous.x);
        const verticalGap = Math.abs(current.y - previous.y);
        if (horizontalGap < 168 && verticalGap < 82) {
          const direction = index % 2 === 0 ? 1 : -1;
          current.x += direction * (168 - horizontalGap + 34);
          if (Math.abs(current.x - previous.x) < 132) {
            current.y += side * (82 - verticalGap + 16);
          }
        }
      }
    }
  }
}

function timelineNodeLabelItem(node) {
  if (node.item) {
    return {
      className: "timeline-date-label",
      primary: node.item.displayDate,
      secondary: node.item.events.length + " " + pluralize("link", node.item.events.length),
    };
  }
  return {
    className: "timeline-connected-label",
    primary: truncate(entityDisplayName(node.raw), node.kind === "event" ? 24 : 22),
    secondary: node.dateRefs.length > 1
      ? node.dateRefs.length + " date links"
      : truncate(node.raw.categoryLabel || node.raw.topCategoryLabel || "Related", 24),
  };
}

function timelineNodeLabelPriority(node) {
  if (node.item) return 0;
  return node.kind === "event" ? 1 : 2;
}

function timelineNodeLabelRect(node, scale) {
  const item = timelineNodeLabelItem(node);
  const width = estimateLabelWidth(item) / scale;
  const height = estimateLabelHeight(item, estimateLabelWidth(item)) / scale;
  const top = node.y + node.r + 6 / scale;
  return {
    left: node.x - width / 2,
    right: node.x + width / 2,
    top,
    bottom: top + height,
  };
}

function spreadTimelineLabelNodes(dateNodes, entityNodes, baseY, timelineWidth) {
  const rect = svg.getBoundingClientRect();
  const scale = Math.max(0.05, (rect.width || svg.clientWidth || 1440) / Math.max(1, timelineWidth));
  const gap = 7 / scale;
  const step = (28 * TIMELINE_VERTICAL_SCALE) / scale;
  const allNodes = dateNodes.concat(entityNodes)
    .sort((a, b) => timelineNodeLabelPriority(a) - timelineNodeLabelPriority(b) || a.x - b.x || Math.abs(a.y - baseY) - Math.abs(b.y - baseY));
  const placed = [];
  for (const node of allNodes) {
    const side = node.y < baseY ? -1 : 1;
    for (let attempts = 0; attempts < 8; attempts++) {
      const currentRect = timelineNodeLabelRect(node, scale);
      const overlap = placed.find((entry) => rectsOverlap(currentRect, entry.rect, gap));
      if (!overlap) break;
      const overlapAmount = Math.min(currentRect.bottom, overlap.rect.bottom) - Math.max(currentRect.top, overlap.rect.top);
      node.y += side * (Math.max(step, overlapAmount + gap));
    }
    placed.push({ node, rect: timelineNodeLabelRect(node, scale) });
  }
}

function buildEventsTimeline() {
  const events = DATA.entities
    .map((entity) => ({ sourceEntity: entity, entity: timelineCanonicalEventEntity(entity) }))
    .filter((item) => item.entity);
  const eventMentionsBySegment = new Map();
  for (const eventItem of events) {
    for (const mentionId of eventItem.sourceEntity.evidenceIds || []) {
      const mention = mentionsById.get(mentionId);
      if (!mention || !mention.segment_id) continue;
      if (!eventMentionsBySegment.has(mention.segment_id)) eventMentionsBySegment.set(mention.segment_id, []);
      eventMentionsBySegment.get(mention.segment_id).push({ ...eventItem, mention });
    }
  }
  const entriesByKey = new Map();
  for (const dateEntity of DATA.entities.filter((entity) => entity.category === "dates_times")) {
    const parsed = parseExactDate(dateEntity.name);
    if (!parsed) continue;
    for (const mentionId of dateEntity.evidenceIds || []) {
      const mention = mentionsById.get(mentionId);
      if (!mention || !mention.segment_id) continue;
      const segmentEvents = eventMentionsBySegment.get(mention.segment_id) || [];
      const scoredEvents = segmentEvents
        .map((eventItem) => ({ eventItem, score: timelineEventDateMentionScore(dateEntity, mention, eventItem) }))
        .filter((item) => item.score > 0);
      const candidates = scoredEvents.length
        ? scoredEvents
        : segmentEvents
          .slice()
          .sort((a, b) => entityGraphScore(b.entity) - entityGraphScore(a.entity))
          .slice(0, 2)
          .map((eventItem) => ({ eventItem, score: 1 }));
      for (const item of dedupeTimelineEventCandidates(candidates).slice(0, scoredEvents.length ? 4 : 2)) {
        addTimelineSubject(entriesByKey, parsed, dateEntity, mention, item.eventItem.entity, item.score);
      }
      const dateSentence = timelineDateSentence(mention.excerpt || "", dateEntity.name);
      for (const subject of timelineExplicitSourceSubjects(dateSentence)) {
        addTimelineSubject(entriesByKey, parsed, dateEntity, mention, subject, timelineSourceSubjectScore(subject));
      }
    }
  }
  for (const relationship of DATA.relationships) {
    const source = entitiesById.get(relationship.source);
    const target = entitiesById.get(relationship.target);
    if (!source || !target) continue;
    const dateEntity = source.category === "dates_times" ? source : target.category === "dates_times" ? target : null;
    const rawEventEntity = source.category === "dates_times" ? target : source;
    const eventEntity = timelineCanonicalEventEntity(rawEventEntity);
    if (!dateEntity || !eventEntity) continue;
    const parsed = parseExactDate(dateEntity.name);
    if (!parsed) continue;
    const relationshipScore = timelineEventDateRelationshipScore(dateEntity, rawEventEntity, eventEntity, relationship);
    if (!relationshipScore) continue;
    addTimelineSubject(entriesByKey, parsed, dateEntity, null, eventEntity, relationshipScore);
  }
  addTimelineSourceDateEntries(entriesByKey);
  const entries = Array.from(entriesByKey.values())
    .map((entry) => ({
      ...entry,
      events: Array.from(entry.eventsById.values())
        .sort((a, b) => b.weight - a.weight || entityGraphScore(b.entity) - entityGraphScore(a.entity)),
      context: dateRelationshipContext(entry.dateEntity.id, entry.eventsById),
    }))
    .filter((entry) => entry.events.length)
    .sort((a, b) => a.date - b.date || b.weight - a.weight);
  return rationalizeTimelineEntries(entries);
}

function dedupeTimelineEventCandidates(candidates) {
  const byId = new Map();
  for (const item of candidates) {
    const id = item.eventItem.entity.id;
    const existing = byId.get(id);
    if (!existing || item.score > existing.score) byId.set(id, item);
  }
  return Array.from(byId.values()).sort((a, b) => b.score - a.score || entityGraphScore(b.eventItem.entity) - entityGraphScore(a.eventItem.entity));
}

function addTimelineSubject(entriesByKey, parsed, dateEntity, mention, subjectEntity, score) {
  if (!subjectEntity || !score) return;
  const key = parsed.iso + "::" + dateEntity.id;
  if (!entriesByKey.has(key)) {
    entriesByKey.set(key, {
      date: parsed.date,
      iso: parsed.iso,
      displayDate: dateEntity.name,
      dateEntity,
      weight: 0,
      eventsById: new Map(),
      transcripts: new Set(),
    });
  }
  const entry = entriesByKey.get(key);
  const eventEntry = entry.eventsById.get(subjectEntity.id) || { entity: subjectEntity, weight: 0 };
  eventEntry.weight += score;
  entry.eventsById.set(subjectEntity.id, eventEntry);
  entry.weight += score;
  if (mention && mention.transcript_title) entry.transcripts.add(mention.transcript_title);
}

function rationalizeTimelineEntries(entries) {
  const maxEntries = 64;
  if (entries.length <= maxEntries) return entries;
  const selected = new Map();
  const add = (entry) => selected.set(entry.iso + "::" + entry.dateEntity.id, entry);
  const byYear = new Map();
  for (const entry of entries) {
    const year = entry.date.getUTCFullYear();
    if (!byYear.has(year)) byYear.set(year, []);
    byYear.get(year).push(entry);
    if (entry.events.some((item) => item.entity.category === "events")) add(entry);
    if (entry.events.some((item) => item.entity.category === "document_names" && year >= 2010)) add(entry);
  }
  for (const [year, yearEntries] of byYear.entries()) {
    yearEntries
      .slice()
      .sort((a, b) => timelineEntryPriority(b) - timelineEntryPriority(a) || b.weight - a.weight || b.events.length - a.events.length)
      .slice(0, year >= 2010 ? 4 : 1)
      .forEach(add);
  }
  entries
    .slice()
    .sort((a, b) => timelineEntryPriority(b) - timelineEntryPriority(a) || b.weight - a.weight || b.events.length - a.events.length)
    .slice(0, 30)
    .forEach(add);
  add(entries[0]);
  add(entries[entries.length - 1]);
  let values = Array.from(selected.values());
  if (values.length > maxEntries) {
    values = values
      .sort((a, b) => {
        return timelineEntryPriority(b) - timelineEntryPriority(a) || b.weight - a.weight || b.events.length - a.events.length;
      })
      .slice(0, maxEntries);
  }
  return values.sort((a, b) => a.date - b.date || b.weight - a.weight);
}

function timelineEntryPriority(entry) {
  const year = entry.date.getUTCFullYear();
  const hasEvent = entry.events.some((item) => item.entity.category === "events");
  const hasDocument = entry.events.some((item) => item.entity.category === "document_names" || item.entity.category === "books" || item.entity.category === "white_papers" || item.entity.category === "leaks");
  const hasNews = entry.events.some((item) => item.entity.category === "newsrooms" || item.entity.category === "websites");
  const recent = year >= 2010 ? 4 : 0;
  return (hasEvent ? 9 : 0) + (hasDocument ? 5 : 0) + (hasNews ? 4 : 0) + recent + Math.min(6, Math.log2(Math.max(1, entry.weight)));
}

function timelineSourceSubjectScore(entity) {
  if (entity.category === "document_names" || entity.category === "books" || entity.category === "white_papers" || entity.category === "leaks") return 6;
  if (entity.category === "newsrooms" || entity.category === "websites") return 5;
  return 4;
}

function timelineExplicitSourceSubjects(sentence) {
  const subjects = [];
  if (!sentence) return subjects;
  const add = (id) => {
    const entity = entitiesById.get(id);
    if (entity && !subjects.some((item) => item.id === entity.id)) subjects.push(entity);
  };
  if (/\b(new york times|nyt)\b/i.test(sentence)) add("newsrooms:the-new-york-times");
  if (/\badvanced aerospace threat identification program\b|\baatip\b/i.test(sentence)) add("government_project_codenames:advanced-aerospace-threat-identification-program");
  return subjects;
}

function addTimelineSourceDateEntries(entriesByKey) {
  const dateEntityByIso = new Map();
  for (const entity of DATA.entities.filter((item) => item.category === "dates_times")) {
    const parsed = parseExactDate(entity.name);
    if (parsed && !dateEntityByIso.has(parsed.iso)) dateEntityByIso.set(parsed.iso, entity);
  }
  const documents = DATA.entities.filter((entity) => (
    entity.category === "document_names" ||
    entity.category === "books" ||
    entity.category === "white_papers" ||
    entity.category === "leaks"
  ));
  const titles = Array.from(new Set(DATA.mentions.map((mention) => mention.transcript_title).filter(Boolean)));
  for (const title of titles) {
    const documentEntity = timelineDocumentForTitle(title, documents);
    if (!documentEntity) continue;
    for (const parsed of extractTimelineTitleDates(title)) {
      const dateEntity = dateEntityByIso.get(parsed.iso);
      if (!dateEntity) continue;
      addTimelineSubject(entriesByKey, parsed, dateEntity, { transcript_title: title }, documentEntity, 10);
    }
  }
}

function timelineDocumentForTitle(title, documents) {
  const normalizedTitle = normalizeText(title);
  if (!normalizedTitle) return null;
  return documents
    .filter((documentEntity) => {
      const name = normalizeText(documentEntity.name);
      return name && (normalizedTitle === name || normalizedTitle.includes(name) || name.includes(normalizedTitle));
    })
    .sort((a, b) => b.name.length - a.name.length || entityGraphScore(b) - entityGraphScore(a))[0] || null;
}

function extractTimelineTitleDates(title) {
  const text = String(title || "").replace(/\s+/g, " ").trim();
  const parsed = [];
  const months = "(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)";
  const monthPattern = new RegExp("\\b" + months + "\\.?\\s+(\\d{1,2}),?\\s+(\\d{4})\\b", "ig");
  let match;
  while ((match = monthPattern.exec(text))) {
    const value = match[1] + " " + match[2] + ", " + match[3];
    const date = parseExactDate(value);
    if (date) parsed.push(date);
  }
  const numeric = text.match(/(?:^|\s)(\d{1,2})[\s/-](\d{1,2})[\s/-](\d{2,4})\s*$/);
  if (numeric) {
    let year = Number(numeric[3]);
    year = year < 100 ? (year >= 30 ? 1900 + year : 2000 + year) : year;
    const first = Number(numeric[1]);
    const second = Number(numeric[2]);
    const month = first > 12 && second <= 12 ? second - 1 : first - 1;
    const day = first > 12 && second <= 12 ? first : second;
    const date = normalizedUtcDate(year, month, day);
    if (date) parsed.push(date);
  }
  const byIso = new Map(parsed.map((item) => [item.iso, item]));
  return Array.from(byIso.values());
}

function timelineCanonicalEventEntity(entity) {
  if (!entity) return null;
  if (entity.category === "events") return entity;
  const aliases = {
    "great war": "events:world-war",
    "first world war": "events:world-war",
    "world war i": "events:world-war",
    "world war one": "events:world-war",
    "second world war": "events:second-world-war",
    "world war ii": "events:second-world-war",
    "world war two": "events:second-world-war",
  };
  const targetId = aliases[normalizeText(entity.name)];
  return targetId ? entitiesById.get(targetId) || null : null;
}

function timelineEventDateMentionScore(dateEntity, dateMention, eventItem) {
  const sentence = timelineDateSentence(dateMention.excerpt || "", dateEntity.name);
  if (!sentence) return 0;
  const names = timelineEventNames(eventItem.sourceEntity, eventItem.entity);
  const matchedInSentence = names.some((name) => normalizedTextIncludes(sentence, name));
  if (!matchedInSentence) return 0;
  const sameEntity = eventItem.sourceEntity && eventItem.sourceEntity.id === eventItem.entity.id;
  return sameEntity ? 5 : 7;
}

function timelineEventDateRelationshipScore(dateEntity, rawEventEntity, eventEntity, relationship) {
  if (relationship.type === "manual") return Math.max(5, Math.round((relationship.weight || 50) / 10));
  const names = timelineEventNames(rawEventEntity, eventEntity);
  for (const evidence of relationship.evidence || []) {
    const sentence = timelineDateSentence(evidence.excerpt || "", dateEntity.name);
    if (sentence && names.some((name) => normalizedTextIncludes(sentence, name))) {
      return Math.max(2, Math.round((relationship.weight || 1) / 8));
    }
  }
  return 0;
}

function timelineEventNames(sourceEntity, canonicalEntity) {
  return Array.from(new Set([sourceEntity && sourceEntity.name, canonicalEntity && canonicalEntity.name].filter(Boolean)));
}

function timelineDateSentence(text, dateName) {
  const excerpt = String(text || "");
  const normalizedExcerpt = normalizeText(excerpt);
  const normalizedDate = normalizeText(dateName);
  if (!normalizedExcerpt || !normalizedDate || !normalizedExcerpt.includes(normalizedDate)) return "";
  const lower = excerpt.toLowerCase();
  const literalDateIndex = lower.indexOf(String(dateName || "").toLowerCase());
  const normalizedDateIndex = normalizedExcerpt.indexOf(normalizedDate);
  const approximateIndex = literalDateIndex >= 0 ? literalDateIndex : Math.max(0, Math.round(normalizedDateIndex / Math.max(1, normalizedExcerpt.length) * excerpt.length));
  const before = Math.max(
    excerpt.lastIndexOf(".", approximateIndex),
    excerpt.lastIndexOf("?", approximateIndex),
    excerpt.lastIndexOf("!", approximateIndex),
    excerpt.lastIndexOf(";", approximateIndex)
  );
  const afterCandidates = [".", "?", "!", ";"]
    .map((mark) => excerpt.indexOf(mark, approximateIndex + String(dateName || "").length))
    .filter((index) => index >= 0);
  const after = afterCandidates.length ? Math.min(...afterCandidates) : Math.min(excerpt.length, approximateIndex + 220);
  return excerpt.slice(before + 1, after + 1);
}

function normalizedTextIncludes(text, phrase) {
  const haystack = normalizeText(text);
  const needle = normalizeText(phrase);
  return !!needle && haystack.includes(needle);
}

function dateRelationshipContext(dateEntityId, eventIds = new Map()) {
  return (relationshipsByEntity.get(dateEntityId) || [])
    .map((relationship) => {
      const otherId = relationship.source === dateEntityId ? relationship.target : relationship.source;
      const entity = entitiesById.get(otherId);
      if (!entity || eventIds.has(otherId)) return null;
      if (entity.category === "dates_times") return null;
      return {
        entity,
        relationship,
        weight: relationship.weight || 1,
        score: relationshipGraphScore(relationship) + Math.min(80, entityGraphScore(entity) * .012),
      };
    })
    .filter(Boolean)
    .sort((a, b) => b.score - a.score || b.weight - a.weight)
    .slice(0, 24);
}

function parseExactDate(value) {
  const text = String(value || "").trim().replace(/\s+/g, " ");
  if (!text || /^(on|in|from|when|about|circa|around|before|after|during)\b/i.test(text)) return null;
  if (!/\d/.test(text) || !/\b\d{4}\b|\b\d{1,2}\/\d{1,2}\/\d{2,4}\b/.test(text)) return null;
  if (/\b(early|mid|late|spring|summer|fall|winter|morning|afternoon|evening|night|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/i.test(text)) return null;
  const months = {
    jan: 0, january: 0,
    feb: 1, february: 1,
    mar: 2, march: 2,
    apr: 3, april: 3,
    may: 4,
    jun: 5, june: 5,
    jul: 6, july: 6,
    aug: 7, august: 7,
    sep: 8, sept: 8, september: 8,
    oct: 9, october: 9,
    nov: 10, november: 10,
    dec: 11, december: 11,
  };
  let match = text.match(/^([A-Za-z]+)\.?\s+(\d{1,2}),?\s*(\d{4})$/);
  if (match && Object.prototype.hasOwnProperty.call(months, match[1].toLowerCase())) {
    return normalizedUtcDate(Number(match[3]), months[match[1].toLowerCase()], Number(match[2]));
  }
  match = text.match(/^(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})$/);
  if (match && Object.prototype.hasOwnProperty.call(months, match[2].toLowerCase())) {
    return normalizedUtcDate(Number(match[3]), months[match[2].toLowerCase()], Number(match[1]));
  }
  match = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (match) return normalizedUtcDate(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  match = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})$/);
  if (match) {
    let year = Number(match[3]);
    year = year < 100 ? (year >= 30 ? 1900 + year : 2000 + year) : year;
    const first = Number(match[1]);
    const second = Number(match[2]);
    const month = first > 12 && second <= 12 ? second - 1 : first - 1;
    const day = first > 12 && second <= 12 ? first : second;
    return normalizedUtcDate(year, month, day);
  }
  return null;
}

function normalizedUtcDate(year, month, day) {
  if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) return null;
  if (year < 1800 || year > 2100) return null;
  const date = new Date(Date.UTC(year, month, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month || date.getUTCDate() !== day) return null;
  return { date, iso: date.toISOString().slice(0, 10) };
}

function renderCategoryGrid(categoryId) {
  const theme = currentTheme();
  const label = DATA.topCategoryLabels[categoryId] || categoryId;
  const entities = DATA.entities
    .filter((entity) => entity.topCategory === categoryId)
    .sort((a, b) => entityGraphScore(b) - entityGraphScore(a) || a.name.localeCompare(b.name));
  const scores = entities.map((entity) => Math.max(1, entityGraphScore(entity)));
  const minScore = Math.min(...scores);
  const maxScore = Math.max(1, ...scores);
  const logMin = Math.log(minScore);
  const logRange = Math.max(.001, Math.log(maxScore) - logMin);
  const maxRadius = 18;
  const minRadius = 3.5;
  const cell = maxRadius * 3.4;
  const headerHeight = cell * .9;
  const blockGap = cell * 1.4;
  const grouped = new Map();
  for (const entity of entities) {
    const group = grouped.get(entity.category) || {
      id: entity.category,
      label: entity.categoryLabel,
      entities: [],
      score: 0,
    };
    group.entities.push(entity);
    group.score += entityGraphScore(entity);
    grouped.set(entity.category, group);
  }
  const groups = Array.from(grouped.values())
    .sort((a, b) => b.entities.length - a.entities.length || b.score - a.score || a.label.localeCompare(b.label));
  const targetAtlasWidth = Math.max(cell * 18, Math.sqrt(Math.max(1, entities.length)) * cell * 1.45);
  let cursorX = 0;
  let cursorY = 0;
  let rowHeight = 0;
  const blocks = groups.map((group) => {
    const columns = Math.max(1, Math.ceil(Math.sqrt(group.entities.length * 1.25)));
    const rows = Math.max(1, Math.ceil(group.entities.length / columns));
    const width = columns * cell;
    const height = rows * cell + headerHeight;
    if (cursorX > 0 && cursorX + width > targetAtlasWidth) {
      cursorX = 0;
      cursorY += rowHeight + blockGap;
      rowHeight = 0;
    }
    const block = { ...group, x: cursorX, y: cursorY, width, height, columns, rows };
    cursorX += width + blockGap;
    rowHeight = Math.max(rowHeight, height);
    return block;
  });
  const atlasWidth = Math.max(...blocks.map((block) => block.x + block.width), cell);
  const atlasHeight = Math.max(...blocks.map((block) => block.y + block.height), cell);
  const offsetX = 1100 - atlasWidth / 2;
  const offsetY = 750 - atlasHeight / 2;
  const blockSvg = blocks.map((block) => {
    return '<rect x="' + (offsetX + block.x - cell * .28) + '" y="' + (offsetY + block.y - cell * .18) + '" width="' + (block.width + cell * .56) + '" height="' + (block.height + cell * .42) + '" fill="none" stroke="' + theme.context + '" stroke-width="1" opacity=".24"></rect>';
  }).join("");
  const groupLabels = blocks.map((block) => ({
    id: "group:" + block.id,
    kind: "annotation",
    x: offsetX + block.x,
    y: offsetY + block.y - cell * .34,
    primary: block.label,
    secondary: block.entities.length.toLocaleString() + " entities",
  }));
  const nodes = [];
  for (const block of blocks) {
    for (const [index, entity] of block.entities.entries()) {
      const column = index % block.columns;
      const row = Math.floor(index / block.columns);
      const value = Math.max(1, entityGraphScore(entity));
      const normalized = (Math.log(value) - logMin) / logRange;
      nodes.push({
        id: entity.id,
        x: offsetX + block.x + column * cell + cell / 2,
        y: offsetY + block.y + headerHeight + row * cell + cell / 2,
        r: minRadius + Math.pow(normalized, 1.05) * (maxRadius - minRadius),
        raw: entity,
        score: value,
        group: block,
      });
    }
  }
  svg.innerHTML = blockSvg + nodes.map((node) => {
    const opacity = node.r < 6 ? ".72" : ".9";
    const stroke = node.r < 6 ? theme.context : theme.primary;
    return '<g class="graph-node" data-entity="' + esc(node.id) + '">' +
      '<circle cx="' + node.x + '" cy="' + node.y + '" r="' + node.r + '" fill="' + theme.entityAlt + '" stroke="' + stroke + '" stroke-width="1" opacity="' + opacity + '"></circle>' +
      '<title>' + esc(node.raw.name + " · " + node.raw.categoryLabel + " · " + (node.raw.count || 0).toLocaleString() + " mentions") + '</title>' +
    '</g>';
  }).join("");
  const labeledByGroup = new Map();
  const labelNodes = nodes.filter((node) => {
    const count = labeledByGroup.get(node.group.id) || 0;
    if (count >= 10) return false;
    if (node.r < 8 && count >= 3) return false;
    labeledByGroup.set(node.group.id, count + 1);
    return true;
  }).slice(0, 180);
  setGraphLabels(groupLabels.concat(labelNodes.map((node) => nodeLabel(
    node.raw.id,
    "entity",
    node,
    truncate(entityDisplayName(node.raw), 22),
    (node.raw.count || 0).toLocaleString() + " mentions",
    node.r
  ))));
  statusEl.textContent = label + " atlas · " + entities.length.toLocaleString() + " entities grouped by category";
  setCornerLabel(label, entities.length.toLocaleString() + " entities · grouped atlas");
  cardEl.classList.remove("open");
  wireEntityNodes();
  const padding = cell * 2.2;
  const minX = offsetX - padding;
  const minY = offsetY - padding;
  const maxX = offsetX + atlasWidth + padding;
  const maxY = offsetY + atlasHeight + padding;
  fitBoundsToViewport(minX, minY, maxX, maxY, { reserveHeader: true, bottomInsetPx: 32 });
}

function entityGraphScore(entity) {
  const relationships = relationshipsByEntity.get(entity.id) || [];
  const evidence = (entity.evidenceIds || []).map((id) => mentionsById.get(id)).filter(Boolean);
  const transcriptCount = new Set(evidence.map((mention) => mention.transcript_title || mention.transcript_id || "")).size;
  const relationshipWeight = relationships.reduce((total, relationship) => total + (relationship.weight || 1), 0);
  return (entity.count || 0) * 4 + transcriptCount * 18 + relationships.length * 10 + relationshipWeight * 1.5;
}

function renderNeighborhood(entity) {
  const theme = currentTheme();
  const rels = (relationshipsByEntity.get(entity.id) || [])
    .slice()
    .sort((a, b) => relationshipGraphScore(b) - relationshipGraphScore(a))
    .slice(0, NEIGHBORHOOD_RELATIONSHIP_LIMIT);
  const relatedById = new Map();
  for (const relationship of rels) {
    const otherId = relationship.source === entity.id ? relationship.target : relationship.source;
    const relatedEntity = entitiesById.get(otherId);
    if (relatedEntity && !relatedById.has(relatedEntity.id)) {
      relatedById.set(relatedEntity.id, { entity: relatedEntity, relationship });
    }
  }
  const visibleNeighborIds = new Set(relatedById.keys());
  const neighborRelByPair = new Map();
  for (const neighborId of visibleNeighborIds) {
    for (const relationship of relationshipsByEntity.get(neighborId) || []) {
      if (!visibleNeighborIds.has(relationship.source) || !visibleNeighborIds.has(relationship.target)) continue;
      const a = relationship.source < relationship.target ? relationship.source : relationship.target;
      const b = relationship.source < relationship.target ? relationship.target : relationship.source;
      const key = a + "::" + b;
      const score = relationshipGraphScore(relationship);
      if (!neighborRelByPair.has(key)) {
        neighborRelByPair.set(key, {
          id: "neighbor:" + key,
          source: a,
          target: b,
          source_name: entitiesById.get(a)?.name || relationship.source_name,
          target_name: entitiesById.get(b)?.name || relationship.target_name,
          type: relationship.type,
          weight: relationship.weight || 1,
          confidence: relationship.confidence || 0,
          layoutScore: score,
        });
      } else {
        const existing = neighborRelByPair.get(key);
        existing.weight += relationship.weight || 1;
        existing.layoutScore += score;
        existing.confidence = Math.max(existing.confidence || 0, relationship.confidence || 0);
        if (existing.type !== relationship.type) existing.type = "related";
      }
    }
  }
  const neighborRels = Array.from(neighborRelByPair.values())
    .sort((a, b) => b.layoutScore - a.layoutScore)
    .slice(0, 18);
  const maxNeighborCount = Math.max(1, ...Array.from(relatedById.values()).map((item) => item.entity.count || 1));
  const neighborScoreByPair = new Map();
  for (const relationship of neighborRels) {
    neighborScoreByPair.set(relationship.source + "::" + relationship.target, relationship.layoutScore || relationship.weight || 1);
    neighborScoreByPair.set(relationship.target + "::" + relationship.source, relationship.layoutScore || relationship.weight || 1);
  }
  function pairScore(a, b) {
    return neighborScoreByPair.get(a + "::" + b) || 0;
  }
  function directScore(id) {
    const item = relatedById.get(id);
    return item ? relationshipGraphScore(item.relationship) : 0;
  }
  const adjacency = new Map(Array.from(visibleNeighborIds).map((id) => [id, []]));
  for (const relationship of neighborRels) {
    if (adjacency.has(relationship.source)) adjacency.get(relationship.source).push(relationship.target);
    if (adjacency.has(relationship.target)) adjacency.get(relationship.target).push(relationship.source);
  }
  const unseen = new Set(visibleNeighborIds);
  const components = [];
  while (unseen.size) {
    const seed = Array.from(unseen).sort((a, b) => directScore(b) - directScore(a))[0];
    const stack = [seed];
    const component = [];
    unseen.delete(seed);
    while (stack.length) {
      const id = stack.pop();
      component.push(id);
      for (const next of adjacency.get(id) || []) {
        if (!unseen.has(next)) continue;
        unseen.delete(next);
        stack.push(next);
      }
    }
    components.push(component);
  }
  const orderedIds = [];
  for (const component of components.sort((a, b) => Math.max(...b.map(directScore)) - Math.max(...a.map(directScore)))) {
    const remaining = new Set(component);
    let current = component.slice().sort((a, b) => directScore(b) - directScore(a))[0];
    while (current) {
      orderedIds.push(current);
      remaining.delete(current);
      const previous = current;
      current = Array.from(remaining)
        .sort((a, b) => pairScore(previous, b) - pairScore(previous, a) || directScore(b) - directScore(a))[0];
    }
  }
  const allDirectNeighborIds = new Set();
  for (const relationship of relationshipsByEntity.get(entity.id) || []) {
    const otherId = relationship.source === entity.id ? relationship.target : relationship.source;
    allDirectNeighborIds.add(otherId);
  }
  const secondDegreeById = new Map();
  const secondDegreeEdgeByPair = new Map();
  for (const neighborId of orderedIds) {
    const candidates = (relationshipsByEntity.get(neighborId) || [])
      .map((relationship) => {
        const otherId = relationship.source === neighborId ? relationship.target : relationship.source;
        return { relationship, otherId, score: relationshipGraphScore(relationship) };
      })
      .filter((item) => {
        const other = entitiesById.get(item.otherId);
        return other && item.otherId !== entity.id && !visibleNeighborIds.has(item.otherId) && !allDirectNeighborIds.has(item.otherId);
      })
      .sort((a, b) => b.score - a.score || entityGraphScore(entitiesById.get(b.otherId)) - entityGraphScore(entitiesById.get(a.otherId)))
      .slice(0, SECOND_DEGREE_PER_NEIGHBOR_LIMIT);
    for (const item of candidates) {
      const other = entitiesById.get(item.otherId);
      if (!secondDegreeById.has(item.otherId)) {
        secondDegreeById.set(item.otherId, { id: item.otherId, entity: other, sources: new Set(), weight: 0, score: 0 });
      }
      const context = secondDegreeById.get(item.otherId);
      context.sources.add(neighborId);
      context.weight += item.relationship.weight || 1;
      context.score += item.score + Math.min(90, entityGraphScore(other) * .025);
      const key = neighborId + "::" + item.otherId;
      if (!secondDegreeEdgeByPair.has(key)) {
        secondDegreeEdgeByPair.set(key, {
          id: "context:" + key,
          source: neighborId,
          target: item.otherId,
          type: item.relationship.type,
          weight: item.relationship.weight || 1,
          score: item.score,
        });
      } else {
        const existing = secondDegreeEdgeByPair.get(key);
        existing.weight += item.relationship.weight || 1;
        existing.score += item.score;
        if (existing.type !== item.relationship.type) existing.type = "related";
      }
    }
  }
  const secondDegree = Array.from(secondDegreeById.values())
    .map((item) => ({ ...item, sourceCount: item.sources.size }))
    .sort((a, b) => b.sourceCount - a.sourceCount || b.score - a.score || entityGraphScore(b.entity) - entityGraphScore(a.entity))
    .slice(0, SECOND_DEGREE_CONTEXT_LIMIT);
  const secondDegreeIds = new Set(secondDegree.map((item) => item.id));
  const nodes = orderedIds.map((id, index) => {
    const item = relatedById.get(id);
    const count = orderedIds.length;
    const angle = (Math.PI * 2 * index) / Math.max(1, count) - Math.PI / 2;
    const ring = count <= 18 ? 0 : index % 2;
    const radius = count <= 10 ? 690 : count <= 18 ? 740 : ring ? 840 : 610;
    const scale = Math.sqrt(Math.max(1, item.entity.count || 1) / maxNeighborCount);
    return {
      id: item.entity.id,
      label: item.entity.name,
      x: 1100 + Math.cos(angle) * radius,
      y: 750 + Math.sin(angle) * radius,
      r: 9 + scale * 22,
      raw: item.entity,
      relationship: item.relationship,
    };
  });
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const center = { id: entity.id, x: 1100, y: 750, r: 46, raw: entity };
  nodeById.set(entity.id, center);
  const secondDegreeGroups = new Map();
  for (const item of secondDegree) {
    const anchorId = Array.from(item.sources)
      .sort((a, b) => {
        const bEdge = secondDegreeEdgeByPair.get(b + "::" + item.id);
        const aEdge = secondDegreeEdgeByPair.get(a + "::" + item.id);
        return (bEdge?.score || 0) - (aEdge?.score || 0) || directScore(b) - directScore(a);
      })[0];
    item.anchorId = anchorId;
    if (!secondDegreeGroups.has(anchorId)) secondDegreeGroups.set(anchorId, []);
    secondDegreeGroups.get(anchorId).push(item);
  }
  const maxSecondDegreeScore = Math.max(1, ...secondDegree.map((item) => item.score || item.weight || 1));
  const secondDegreeNodes = secondDegree.map((item, index) => {
    const anchorNode = nodeById.get(item.anchorId);
    const sourceNodes = Array.from(item.sources).map((id) => nodeById.get(id)).filter(Boolean);
    const group = secondDegreeGroups.get(item.anchorId) || [item];
    const groupIndex = Math.max(0, group.findIndex((candidate) => candidate.id === item.id));
    const fan = Math.min(.88, Math.max(.24, (group.length - 1) * .24));
    const fanOffset = group.length <= 1 ? 0 : (groupIndex / (group.length - 1) - .5) * fan;
    const avgX = sourceNodes.reduce((total, node) => total + node.x, 0) / Math.max(1, sourceNodes.length);
    const avgY = sourceNodes.reduce((total, node) => total + node.y, 0) / Math.max(1, sourceNodes.length);
    const baseAngle = anchorNode
      ? Math.atan2(anchorNode.y - center.y, anchorNode.x - center.x)
      : sourceNodes.length
        ? Math.atan2(avgY - center.y, avgX - center.x)
        : (Math.PI * 2 * index) / Math.max(1, secondDegree.length) - Math.PI / 2;
    const angle = baseAngle + fanOffset;
    const radius = 1040 + (groupIndex % 3) * 82 + Math.floor(groupIndex / 3) * 40 + Math.min(56, item.sourceCount * 12);
    const scoreScale = Math.sqrt(Math.max(1, item.score || item.weight || 1) / maxSecondDegreeScore);
    return {
      id: item.id,
      label: item.entity.name,
      x: center.x + Math.cos(angle) * radius,
      y: center.y + Math.sin(angle) * radius,
      r: 3.5 + scoreScale * 5 + Math.min(2, item.sourceCount),
      raw: item.entity,
      anchorId: item.anchorId,
      anchorName: anchorNode?.raw?.name || "",
      sourceCount: item.sourceCount,
      score: item.score,
    };
  });
  for (const node of secondDegreeNodes) nodeById.set(node.id, node);
  const maxEdge = Math.max(1, ...rels.map((relationship) => relationship.weight));
  const maxNeighborEdge = Math.max(1, ...neighborRels.map((relationship) => relationship.weight || 1));
  const secondDegreeEdges = Array.from(secondDegreeEdgeByPair.values())
    .filter((relationship) => nodeById.has(relationship.source) && secondDegreeIds.has(relationship.target))
    .sort((a, b) => b.score - a.score || b.weight - a.weight)
    .slice(0, SECOND_DEGREE_EDGE_LIMIT);
  const maxSecondDegreeEdge = Math.max(1, ...secondDegreeEdges.map((relationship) => relationship.weight || 1));
  const secondDegreeEdgesSvg = secondDegreeEdges.map((relationship) => {
    const source = nodeById.get(relationship.source);
    const target = nodeById.get(relationship.target);
    if (!source || !target) return "";
    const width = (0.25 + ((relationship.weight || 1) / maxSecondDegreeEdge) * .9).toFixed(1);
    return '<line class="graph-edge" data-edge="' + esc(relationship.id) + '" x1="' + source.x + '" y1="' + source.y + '" x2="' + target.x + '" y2="' + target.y + '" stroke="' + theme.context + '" stroke-width="' + width + '" opacity=".12"><title>' + esc(connectionCategoryText(relationship)) + '</title></line>';
  }).join("");
  const neighborEdgesSvg = neighborRels.map((relationship) => {
    const source = nodeById.get(relationship.source);
    const target = nodeById.get(relationship.target);
    if (!source || !target) return "";
    const width = (0.45 + ((relationship.weight || 1) / maxNeighborEdge) * 2.1).toFixed(1);
    return '<line class="graph-edge" data-edge="' + esc(relationship.id) + '" x1="' + source.x + '" y1="' + source.y + '" x2="' + target.x + '" y2="' + target.y + '" stroke="' + theme.context + '" stroke-width="' + width + '" opacity=".26"><title>' + esc(connectionCategoryText(relationship)) + '</title></line>';
  }).join("");
  const secondDegreeNodesSvg = secondDegreeNodes.map((node) => {
    return '<g class="graph-node context-node" data-entity="' + esc(node.raw.id) + '">' +
      '<circle cx="' + node.x + '" cy="' + node.y + '" r="' + node.r + '" fill="' + theme.entityAlt + '" stroke="' + theme.context + '" stroke-width="1" opacity=".38"></circle>' +
      '<title>' + esc(node.raw.name + " · connected through " + node.sourceCount + " direct " + pluralize("neighbor", node.sourceCount)) + '</title>' +
    '</g>';
  }).join("");
  svg.innerHTML = secondDegreeEdgesSvg +
    neighborEdgesSvg +
    drawRelationshipEdges(rels, nodeById, maxEdge, "drill") +
    secondDegreeNodesSvg +
    '<g class="graph-node" data-entity="' + esc(entity.id) + '">' +
      '<circle cx="1100" cy="750" r="46" fill="' + theme.primary + '" stroke="' + theme.bgStroke + '" stroke-width="1"></circle>' +
    '</g>' +
    nodes.map((node) => {
      const relatedEntity = node.raw;
      return '<g class="graph-node" data-entity="' + esc(relatedEntity.id) + '">' +
        '<circle cx="' + node.x + '" cy="' + node.y + '" r="' + node.r + '" fill="' + theme.entityAlt + '" stroke="' + theme.primary + '" stroke-width="1"></circle>' +
      '</g>';
    }).join("");
  const secondDegreeLabelNodes = secondDegreeNodes
    .slice()
    .sort((a, b) => b.sourceCount - a.sourceCount || b.score - a.score || entityGraphScore(b.raw) - entityGraphScore(a.raw))
    .slice(0, SECOND_DEGREE_LABEL_LIMIT);
  setGraphLabels([nodeLabel(
    entity.id,
    "entity",
    center,
    truncate(entityDisplayName(entity), 34),
    entity.topCategoryLabel
  )].concat(nodes.map((node) => nodeLabel(
    node.raw.id,
    "entity",
    node,
    truncate(entityDisplayName(node.raw), 24),
    truncate(node.raw.topCategoryLabel || node.raw.categoryLabel, 28)
  ))).concat(secondDegreeLabelNodes.map((node) => nodeLabel(
    node.raw.id,
    "entity",
    node,
    truncate(entityDisplayName(node.raw), 22),
    node.sourceCount > 1
      ? node.sourceCount + " real connections"
      : "from " + truncate(node.anchorName || "direct node", 18),
    node.r
  ))));
  statusEl.textContent = entity.name + " · " + entity.topCategoryLabel;
  setCornerLabel(null);
  renderCard(entity, rels);
  wireEntityNodes();
  fitSelectedEgoGraph(nodes, center);
}

function relationshipGraphScore(relationship) {
  if (relationship.type === "manual") return 1000000 + (relationship.weight || 1);
  const typeBoost = relationship.type === "co_mentioned" ? 0 : 18;
  const source = entitiesById.get(relationship.source);
  const target = entitiesById.get(relationship.target);
  const crossCategoryBoost = source && target && source.topCategory !== target.topCategory ? 10 : 0;
  return (relationship.weight || 1) * 24 + typeBoost + crossCategoryBoost + Math.round((relationship.confidence || 0) * 10);
}

function pluralize(word, count) {
  return count === 1 ? word : word + "s";
}

function connectionCategoryText(relationship) {
  const source = entitiesById.get(relationship.source);
  const target = entitiesById.get(relationship.target);
  const sourceLabel = source?.topCategoryLabel || source?.categoryLabel || "Entity";
  const targetLabel = target?.topCategoryLabel || target?.categoryLabel || "Entity";
  return sourceLabel === targetLabel ? sourceLabel : sourceLabel + " ↔ " + targetLabel;
}

function radialNodes(items, cx, cy, innerRadius, outerRadius, sizeValue) {
  const values = items.map((item) => Math.max(1, sizeValue(item)));
  const minValue = Math.min(...values);
  const maxValue = Math.max(1, ...values);
  return items.map((item, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(1, items.length) - Math.PI / 2;
    const progress = items.length <= 1 ? 1 : index / (items.length - 1);
    const radius = innerRadius + Math.pow(progress, .62) * (outerRadius - innerRadius);
    const value = Math.max(1, sizeValue(item));
    const logMin = Math.log(minValue);
    const logRange = Math.log(maxValue) - logMin;
    const normalized = logRange < 0.001 ? 0.5 : (Math.log(value) - logMin) / logRange;
    const scale = Math.pow(normalized, 1.08);
    return {
      id: item.id,
      label: item.label || item.name,
      count: item.count || item.entities || 0,
      mentions: item.mentions || value,
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
      r: 8 + scale * 28,
      raw: item,
    };
  });
}

function parentCategoryNodes(categories, cx, cy) {
  const maxCount = Math.max(1, ...categories.map((category) => category.count || 1));
  const radiusFor = (category) => Math.max(18, Math.min(150, Math.sqrt((category.count || 1) / maxCount) * 150));
  const outerRadius = 1120;
  return categories.map((category, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(1, categories.length) - Math.PI / 2;
    return {
      id: category.id,
      label: category.label,
      count: category.count || 0,
      mentions: category.mentions || 0,
      x: cx + Math.cos(angle) * outerRadius,
      y: cy + Math.sin(angle) * outerRadius,
      r: radiusFor(category),
      raw: category,
    };
  });
}

function drawEdges(edges, nodeById, maxEdge, density = "normal") {
  const theme = currentTheme();
  const isSpoke = density === "ego-spoke";
  const isContext = density === "ego-context";
  const baseWidth = isSpoke ? 0.65 : isContext ? 0.25 : 0.8;
  const weightWidth = isSpoke ? 4.8 : isContext ? 1.7 : 7;
  const opacity = isSpoke ? ".34" : isContext ? ".16" : theme.edgeOpacity.high;
  return edges.map((edge) => {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    if (!source || !target) return "";
    return '<line class="graph-edge" x1="' + source.x + '" y1="' + source.y + '" x2="' + target.x + '" y2="' + target.y + '" stroke="' + theme.edge + '" stroke-width="' + (baseWidth + (edge.weight / maxEdge) * weightWidth).toFixed(1) + '" opacity="' + opacity + '"></line>';
  }).join("");
}

function drawRelationshipEdges(relationships, nodeById, maxEdge, density = "normal") {
  const theme = currentTheme();
  const baseWidth = density === "drill" ? 0.45 : 0.8;
  const weightWidth = density === "drill" ? 2.6 : 7;
  const opacity = density === "drill" ? ".24" : theme.edgeOpacity.relationship;
  return relationships.map((relationship) => {
    const source = nodeById.get(relationship.source);
    const target = nodeById.get(relationship.target);
    if (!source || !target) return "";
    return '<line class="graph-edge" data-edge="' + esc(relationship.id) + '" x1="' + source.x + '" y1="' + source.y + '" x2="' + target.x + '" y2="' + target.y + '" stroke="' + theme.edge + '" stroke-width="' + (baseWidth + (relationship.weight / maxEdge) * weightWidth).toFixed(1) + '" opacity="' + opacity + '"><title>' + esc(connectionCategoryText(relationship)) + '</title></line>';
  }).join("");
}

function mergeCandidates(entity, query = "") {
  const normalizedQuery = query.trim().toLowerCase();
  const sourceName = normalizeText(entity.name);
  return DATA.entities
    .filter((candidate) => {
      if (candidate.id === entity.id) return false;
      if (!normalizedQuery) return true;
      return [candidate.name, candidate.categoryLabel, candidate.topCategoryLabel].join(" ").toLowerCase().includes(normalizedQuery);
    })
    .sort((a, b) => {
      const aSameName = normalizeText(a.name) === sourceName ? 1 : 0;
      const bSameName = normalizeText(b.name) === sourceName ? 1 : 0;
      if (aSameName !== bSameName) return bSameName - aSameName;
      const aSameTop = a.topCategory === entity.topCategory ? 1 : 0;
      const bSameTop = b.topCategory === entity.topCategory ? 1 : 0;
      if (aSameTop !== bSameTop) return bSameTop - aSameTop;
      return (b.count || 0) - (a.count || 0);
    })
    .slice(0, 80);
}

function mergeResultButtons(entity, query = "") {
  const candidates = mergeCandidates(entity, query);
  if (!candidates.length) return '<div class="meta">No matches.</div>';
  return candidates.slice(0, 8).map((candidate) => {
    return '<button type="button" data-merge-target="' + esc(candidate.id) + '" aria-pressed="false">' +
      esc(candidate.name) +
      '<div class="meta">' + esc(candidate.categoryLabel) + ' · ' + (candidate.count || 0).toLocaleString() + ' mentions</div>' +
    '</button>';
  }).join("");
}

function mergeRemovalDecisions(entity) {
  const review = readReview();
  const removed = { ...(review.removedMerges || {}), ...(review.removedNameMerges || {}) };
  const decisions = mergeReviews(BUILT_REVIEW, review);
  const rows = [];
  const seen = new Set();
  for (const [key, merge] of Object.entries(decisions.merges || {})) {
    if (!merge || typeof merge !== "object") continue;
    if (removed[key]) continue;
    const targetMatches = merge.targetId === entity.id || normalizeText(merge.targetName || "") === normalizeText(entity.name);
    if (!targetMatches || seen.has(key)) continue;
    rows.push({ key, nameKey: normalizeText(merge.sourceName || key), merge });
    seen.add(key);
  }
  return rows.sort((a, b) => String(a.merge.sourceName || a.key).localeCompare(String(b.merge.sourceName || b.key)));
}

function mergeRemovalControls(entity) {
  const rows = mergeRemovalDecisions(entity);
  if (!rows.length) return "";
  return '<h3 class="merge-heading">Merged into this node</h3>' +
    '<div class="card-actions">' + rows.slice(0, 12).map((row) => {
      return '<button type="button" data-remove-merge="' + esc(row.key) + '" data-remove-name-merge="' + esc(row.nameKey) + '">' +
        'Remove merge: ' + esc(row.merge.sourceName || row.key) +
        '<div class="meta">' + esc(row.merge.sourceCategory || "Entity") + '</div>' +
      '</button>';
    }).join("") + '</div>';
}

function manualConnectionResultButtons(entity, query = "") {
  const candidates = mergeCandidates(entity, query);
  if (!candidates.length) return '<div class="meta">No matches.</div>';
  return candidates.slice(0, 8).map((candidate) => {
    return '<button type="button" data-manual-target="' + esc(candidate.id) + '" aria-pressed="false">' +
      esc(candidate.name) +
      '<div class="meta">' + esc(candidate.topCategoryLabel || candidate.categoryLabel) + '</div>' +
    '</button>';
  }).join("");
}

function falsePositiveRows() {
  const review = mergeReviews(BUILT_REVIEW, readReview());
  return Object.entries(review.falsePositives || {})
    .map(([id, item]) => ({
      id,
      name: item && item.name ? item.name : reviewEntryName(id, item)[0] || id,
      categoryLabel: item && item.categoryLabel ? item.categoryLabel : DATA.categoryLabels[item?.category] || item?.category || "Entity",
      built: Object.prototype.hasOwnProperty.call(BUILT_REVIEW.falsePositives || {}, id),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function renderFalsePositiveReviewCard() {
  const rows = falsePositiveRows();
  cardEl.classList.add("open");
  cardEl.setAttribute("aria-labelledby", "card-title");
  cardEl.innerHTML = '<button class="card-close" id="close-card" aria-label="Close info window">x</button>' +
    '<div class="node-card-body"><h2 id="card-title">False positives</h2>' +
    '<p><span class="tag">Review</span> ' + rows.length.toLocaleString() + ' marked false positive</p>' +
    (rows.length ? '<div class="entity-directory">' + rows.map((row) => {
      return '<button type="button" data-restore-false-positive="' + esc(row.id) + '">' +
        esc(row.name) +
        '<div class="meta">' + esc(row.categoryLabel) + (row.built ? ' · restores on rebuild' : '') + '</div>' +
      '</button>';
    }).join("") + '</div>' : '<div class="meta">No false positives in the current review data.</div>') +
    '</div>';
  cardEl.querySelectorAll("[data-restore-false-positive]").forEach((button) => {
    button.addEventListener("click", () => restoreFalsePositive(button.dataset.restoreFalsePositive));
  });
  wireCardClose();
  focusDetailsCard();
}

function resetDataFromReview() {
  DATA = applyReviewDecisions(normalizeData(RAW));
  rebuildIndexes();
}

function restoreFalsePositive(entityId) {
  const review = readReview();
  const merged = mergeReviews(BUILT_REVIEW, review);
  const item = (merged.falsePositives || {})[entityId];
  if (!item) return;
  review.falsePositives = review.falsePositives || {};
  review.removedFalsePositives = review.removedFalsePositives || {};
  delete review.falsePositives[entityId];
  if (Object.prototype.hasOwnProperty.call(BUILT_REVIEW.falsePositives || {}, entityId)) {
    review.removedFalsePositives[entityId] = item;
  }
  saveReview(review);
  resetDataFromReview();
  render();
  renderFalsePositiveReviewCard();
}

function renderCard(entity, relationships) {
  const evidence = (entity.evidenceIds || []).map((id) => mentionsById.get(id)).filter(Boolean).slice(0, 6);
  cardEl.classList.add("open");
  cardEl.setAttribute("aria-labelledby", "card-title");
  cardEl.innerHTML = '<button class="card-close" id="close-card" aria-label="Close info window">x</button>' +
    '<div class="node-card-body"><h2 id="card-title">' + esc(entity.name) + '</h2>' +
    '<p><span class="tag">' + esc(entity.topCategoryLabel) + '</span> <span class="tag">' + esc(entity.categoryLabel) + '</span> ' + (entity.count || 0).toLocaleString() + ' mentions · ' + Math.round((entity.confidence || 0) * 100) + '% confidence</p>' +
    '<p>' + esc(entity.significance || "") + '</p>' +
    '<h3>Transcript snippets</h3>' +
    (evidence.length ? evidence.map((mention) => {
      return '<div class="evidence"><div class="meta">' + esc(mention.transcript_title) + ' · ' + esc(mention.timestamp) + ' · ' + esc(mention.detector) + '</div><div>' + esc(mention.excerpt) + '</div></div>';
    }).join("") : '<div class="meta">No snippets available for this entity.</div>') +
    '<h3>Connections</h3>' +
    '<div class="relationship-list">' + relationships.slice(0, CARD_RELATIONSHIP_LIMIT).map((relationship) => {
      const otherId = relationship.source === entity.id ? relationship.target : relationship.source;
      const other = entitiesById.get(otherId);
      const otherName = other ? other.name : otherId;
      const manualKey = relationship.type === "manual" ? manualRelationshipKey(relationship.source, relationship.target) : "";
      return '<div class="relationship-row">' +
        '<button class="relationship-target" data-card-entity="' + esc(otherId) + '">' + esc(otherName) + '<div class="meta">' + esc(other ? other.topCategoryLabel : "Entity") + '</div></button>' +
        (manualKey ? '<button class="remove-connection" type="button" data-remove-manual-connection="' + esc(manualKey) + '" aria-label="Remove manual connection to ' + esc(otherName) + '">x</button>' : '') +
      '</div>';
    }).join("") + '</div>' +
    '<h3 class="action-heading">Reclassify</h3>' +
    '<div class="card-actions"><label class="card-field"><span>Category</span><select id="review-category">' + Object.entries(DATA.categoryLabels).map(([id, label]) => '<option value="' + esc(id) + '"' + (id === entity.category ? ' selected' : '') + '>' + esc(label) + '</option>').join("") + '</select></label></div>' +
    '<h3 class="action-heading">Rename node</h3>' +
    '<div class="card-actions"><label class="card-field"><span>Display name</span><input id="rename-node-input" type="text" autocomplete="off" value="' + esc(entity.name) + '"></label><button id="rename-node">Rename</button></div>' +
    '<h3 class="action-heading false-positive-heading">False positive</h3>' +
    '<div class="card-actions false-positive-actions"><button id="false-positive">Mark false positive</button></div>' +
    '<h3 class="merge-heading">Merge duplicate</h3>' +
    '<div class="card-actions"><label class="card-field"><span>Find entity to merge into</span><input id="merge-target-search" type="search" autocomplete="off" aria-controls="merge-results" placeholder="Search by name or category"></label><div id="merge-results" class="merge-results" aria-label="Merge target results">' + mergeResultButtons(entity) + '</div><button id="merge-entity" disabled>Merge</button></div>' +
    mergeRemovalControls(entity) +
    '<h3 class="merge-heading">Add connection</h3>' +
    '<div class="card-actions"><label class="card-field"><span>Find entity to connect</span><input id="manual-connection-search" type="search" autocomplete="off" aria-controls="manual-connection-results" placeholder="Search by name or category"></label><div id="manual-connection-results" class="merge-results" aria-label="Manual connection results">' + manualConnectionResultButtons(entity) + '</div><button id="add-manual-connection" disabled>Add connection</button></div></div>';
  cardEl.querySelectorAll("[data-card-entity]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedEntityId = button.dataset.cardEntity;
      mode = "neighborhood";
      render();
      focusDetailsCard();
    });
  });
  cardEl.querySelectorAll("[data-remove-manual-connection]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const key = button.dataset.removeManualConnection;
      const relationship = DATA.relationships.find((candidate) => candidate.type === "manual" && manualRelationshipKey(candidate.source, candidate.target) === key);
      const source = relationship ? entitiesById.get(relationship.source) : null;
      const target = relationship ? entitiesById.get(relationship.target) : null;
      const review = readReview();
      review.manualRelationships = review.manualRelationships || {};
      review.removedManualRelationships = review.removedManualRelationships || {};
      const manual = review.manualRelationships[key] || {
        sourceId: relationship?.source || key.split("--")[0],
        sourceName: source?.name || "",
        sourceCategory: source?.category || "",
        targetId: relationship?.target || key.split("--")[1],
        targetName: target?.name || "",
        targetCategory: target?.category || "",
      };
      review.removedManualRelationships[key] = manual;
      delete review.manualRelationships[key];
      saveReview(review);
      DATA.relationships = DATA.relationships.filter((candidate) => candidate.type !== "manual" || manualRelationshipKey(candidate.source, candidate.target) !== key);
      rebuildIndexes();
      render();
      focusDetailsCard();
    });
  });
  wireCardClose();
  document.getElementById("review-category").addEventListener("change", (event) => {
    const review = readReview();
    const targetCategory = event.target.value;
    review.reclassifications[entity.id] = targetCategory;
    review.nameReclassifications = review.nameReclassifications || {};
    review.nameReclassifications[entity.name.toLowerCase()] = targetCategory;
    if (review.falsePositives) delete review.falsePositives[entity.id];
    saveReview(review);
    applyEntityCategory(entity, targetCategory);
    activeCategory = entity.topCategory;
    rebuildIndexes();
    render();
  });
  document.getElementById("rename-node").addEventListener("click", () => {
    const input = document.getElementById("rename-node-input");
    const nextName = input.value.trim();
    if (!nextName || nextName === entity.name) return;
    const previousName = entity.name;
    const review = readReview();
    review.aliases = review.aliases || {};
    review.aliases[entity.id] = nextName;
    review.aliases[normalizeText(previousName)] = nextName;
    if (review.falsePositives) delete review.falsePositives[entity.id];
    saveReview(review);
    applyEntityRename(entity, nextName);
    rebuildIndexes();
    render();
    focusDetailsCard();
  });
  document.getElementById("false-positive").addEventListener("click", () => {
    const confirmed = window.confirm('Mark "' + entity.name + '" as a false positive? This removes it from the graph and downloaded review data.');
    if (!confirmed) return;
    const review = readReview();
    review.falsePositives[entity.id] = { name: entity.name, category: entity.category, categoryLabel: entity.categoryLabel };
    if (review.reclassifications) delete review.reclassifications[entity.id];
    saveReview(review);
    DATA.entities = DATA.entities.filter((candidate) => candidate.id !== entity.id);
    DATA.relationships = DATA.relationships.filter((relationship) => relationship.source !== entity.id && relationship.target !== entity.id);
    selectedEntityId = null;
    mode = "categories";
    activeCategory = null;
    cardEl.classList.remove("open");
    rebuildIndexes();
    render();
  });
  const mergeSearch = document.getElementById("merge-target-search");
  const mergeResults = document.getElementById("merge-results");
  const mergeButton = document.getElementById("merge-entity");
  let selectedMergeTargetId = "";

  function selectMergeTarget(targetId) {
    const target = entitiesById.get(targetId);
    selectedMergeTargetId = target ? target.id : "";
    mergeButton.disabled = !selectedMergeTargetId;
    mergeResults.querySelectorAll("[data-merge-target]").forEach((button) => {
      const selected = button.dataset.mergeTarget === selectedMergeTargetId;
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    if (target) mergeSearch.value = target.name;
  }

  function wireMergeResults() {
    mergeResults.querySelectorAll("[data-merge-target]").forEach((button) => {
      button.addEventListener("click", () => selectMergeTarget(button.dataset.mergeTarget));
    });
  }

  mergeSearch.addEventListener("input", () => {
    selectedMergeTargetId = "";
    mergeButton.disabled = true;
    mergeResults.innerHTML = mergeResultButtons(entity, mergeSearch.value);
    wireMergeResults();
  });
  mergeSearch.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const first = mergeResults.querySelector("[data-merge-target]");
    if (!first) return;
    event.preventDefault();
    selectMergeTarget(first.dataset.mergeTarget);
  });
  wireMergeResults();
  document.getElementById("merge-entity").addEventListener("click", () => {
    const target = entitiesById.get(selectedMergeTargetId);
    if (!target || target.id === entity.id) return;
    const review = readReview();
    review.merges = review.merges || {};
    review.nameMerges = review.nameMerges || {};
    const merge = {
      sourceId: entity.id,
      sourceName: entity.name,
      sourceCategory: entity.category,
      targetId: target.id,
      targetName: target.name,
      targetCategory: target.category,
    };
    review.merges[entity.id] = merge;
    review.nameMerges[normalizeText(entity.name)] = merge;
    if (review.reclassifications) delete review.reclassifications[entity.id];
    if (review.falsePositives) delete review.falsePositives[entity.id];
    saveReview(review);
    mergeEntityInto(entity, target);
    selectedEntityId = target.id;
    activeCategory = null;
    mode = "neighborhood";
    rebuildIndexes();
    render();
    focusDetailsCard();
  });

  cardEl.querySelectorAll("[data-remove-merge]").forEach((button) => {
    button.addEventListener("click", () => {
      const review = readReview();
      review.removedMerges = review.removedMerges || {};
      review.removedNameMerges = review.removedNameMerges || {};
      const key = button.dataset.removeMerge;
      const nameKey = button.dataset.removeNameMerge;
      const decisions = mergeReviews(BUILT_REVIEW, review);
      const merge = (decisions.merges || {})[key] || (decisions.nameMerges || {})[nameKey] || { sourceName: nameKey, targetName: entity.name };
      review.removedMerges[key] = merge;
      if (nameKey) review.removedNameMerges[nameKey] = merge;
      if (review.merges) delete review.merges[key];
      if (review.nameMerges && nameKey) delete review.nameMerges[nameKey];
      saveReview(review);
      render();
      focusDetailsCard();
    });
  });

  const manualSearch = document.getElementById("manual-connection-search");
  const manualResults = document.getElementById("manual-connection-results");
  const manualButton = document.getElementById("add-manual-connection");
  let selectedManualTargetId = "";

  function selectManualTarget(targetId) {
    const target = entitiesById.get(targetId);
    selectedManualTargetId = target ? target.id : "";
    manualButton.disabled = !selectedManualTargetId;
    manualResults.querySelectorAll("[data-manual-target]").forEach((button) => {
      const selected = button.dataset.manualTarget === selectedManualTargetId;
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    if (target) manualSearch.value = target.name;
  }

  function wireManualResults() {
    manualResults.querySelectorAll("[data-manual-target]").forEach((button) => {
      button.addEventListener("click", () => selectManualTarget(button.dataset.manualTarget));
    });
  }

  manualSearch.addEventListener("input", () => {
    selectedManualTargetId = "";
    manualButton.disabled = true;
    manualResults.innerHTML = manualConnectionResultButtons(entity, manualSearch.value);
    wireManualResults();
  });
  manualSearch.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const first = manualResults.querySelector("[data-manual-target]");
    if (!first) return;
    event.preventDefault();
    selectManualTarget(first.dataset.manualTarget);
  });
  wireManualResults();
  manualButton.addEventListener("click", () => {
    const target = entitiesById.get(selectedManualTargetId);
    if (!target || target.id === entity.id) return;
    const review = readReview();
    review.manualRelationships = review.manualRelationships || {};
    const ids = [entity.id, target.id].sort();
    const key = manualRelationshipKey(ids[0], ids[1]);
    if (review.removedManualRelationships) delete review.removedManualRelationships[key];
    review.manualRelationships[key] = {
      sourceId: ids[0],
      sourceName: (entitiesById.get(ids[0]) || entity).name,
      sourceCategory: (entitiesById.get(ids[0]) || entity).category,
      targetId: ids[1],
      targetName: (entitiesById.get(ids[1]) || target).name,
      targetCategory: (entitiesById.get(ids[1]) || target).category,
    };
    saveReview(review);
    applyManualRelationships(DATA, { [key]: review.manualRelationships[key] });
    rebuildIndexes();
    render();
    focusDetailsCard();
  });
}

function renderCategoryListCard(categoryId) {
  const label = DATA.topCategoryLabels[categoryId] || categoryId;
  const entities = DATA.entities
    .filter((entity) => entity.topCategory === categoryId)
    .sort((a, b) => entityGraphScore(b) - entityGraphScore(a) || a.name.localeCompare(b.name));
  const mentions = entities.reduce((total, entity) => total + (entity.count || 0), 0);
  cardEl.classList.add("open");
  cardEl.setAttribute("aria-labelledby", "card-title");
  cardEl.innerHTML = '<button class="card-close" id="close-card" aria-label="Close info window">x</button>' +
    '<div class="node-card-body"><h2 id="card-title">' + esc(label) + '</h2>' +
    '<p><span class="tag">' + esc(label) + '</span> ' + entities.length.toLocaleString() + ' entities · ' + mentions.toLocaleString() + ' mentions</p>' +
    '<h3>All entities</h3>' +
    '<div class="entity-directory">' + entities.map((entity) => {
      return '<button data-card-entity="' + esc(entity.id) + '">' +
        esc(entity.name) +
        '<div class="meta">' + esc(entity.categoryLabel) + ' · ' + (entity.count || 0).toLocaleString() + ' mentions</div>' +
      '</button>';
    }).join("") + '</div></div>';
  cardEl.querySelectorAll("[data-card-entity]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedEntityId = button.dataset.cardEntity;
      mode = "neighborhood";
      render();
      focusDetailsCard();
    });
  });
  wireCardClose();
}

function renderEdgeCard(relationship) {
  const source = entitiesById.get(relationship.source);
  const target = entitiesById.get(relationship.target);
  const evidence = relationship.evidence || [];
  cardEl.classList.add("open");
  cardEl.setAttribute("aria-labelledby", "card-title");
  cardEl.innerHTML = '<button class="card-close" id="close-card" aria-label="Close info window">x</button>' +
    '<div class="node-card-body"><h2 id="card-title">' + esc(source ? source.name : relationship.sourceName) + ' ↔ ' + esc(target ? target.name : relationship.targetName) + '</h2>' +
    '<p><span class="tag">' + esc(connectionCategoryText(relationship)) + '</span></p>' +
    '<h3>Evidence</h3>' +
    (evidence.length ? evidence.map((item) => {
      return '<div class="evidence"><div class="meta">' + esc(item.transcript) + ' · ' + esc(item.timestamp) + '</div><div>' + esc(item.excerpt) + '</div></div>';
    }).join("") : '<div class="meta">No relationship snippets available.</div>') +
    '<div class="card-actions"><button data-card-entity="' + esc(relationship.source) + '">' + esc(source ? source.name : "Source") + '</button><button data-card-entity="' + esc(relationship.target) + '">' + esc(target ? target.name : "Target") + '</button></div></div>';
  cardEl.querySelectorAll("[data-card-entity]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedEntityId = button.dataset.cardEntity;
      mode = "neighborhood";
      render();
      focusDetailsCard();
    });
  });
  wireCardClose();
}

function focusDetailsCard() {
  if (cardEl.classList.contains("open")) cardEl.focus({ preventScroll: true });
}

function focusSelectedGraphLabel() {
  const selectors = selectedEntityId
    ? ['[data-label-entity="' + cssEscape(selectedEntityId) + '"]']
    : activeCategory
      ? ['[data-label-category="' + cssEscape(activeCategory) + '"]', '[data-label-category-list="' + cssEscape(activeCategory) + '"]']
      : [".html-graph-label"];
  const label = selectors.map((selector) => graphLabelsEl.querySelector(selector)).find(Boolean);
  if (label) label.focus({ preventScroll: true });
}

function wireCardClose() {
  const closeButton = document.getElementById("close-card");
  if (!closeButton) return;
  closeButton.addEventListener("click", () => {
    cardEl.classList.remove("open");
    cardEl.removeAttribute("aria-labelledby");
    focusSelectedGraphLabel();
  });
}

function wireCategoryNodes() {
  svg.querySelectorAll("[data-category]").forEach((node) => {
    node.addEventListener("click", () => activateGraphNode(node));
  });
}

function wireCategoryListNodes() {
  svg.querySelectorAll("[data-category-list]").forEach((node) => {
    node.addEventListener("click", () => activateGraphNode(node, { focusGraph: true }));
  });
}

function wireEntityNodes() {
  svg.querySelectorAll("[data-entity]").forEach((node) => {
    node.addEventListener("click", () => activateGraphNode(node));
  });
  svg.querySelectorAll("[data-edge]").forEach((edge) => {
    edge.addEventListener("click", (event) => {
      event.stopPropagation();
      const relationship = relationshipsById.get(edge.dataset.edge);
      if (relationship) renderEdgeCard(relationship);
    });
  });
}

function activateGraphNode(node, options = {}) {
  if (!node) return false;
  if (node.dataset.category) {
    activeCategory = node.dataset.category;
    selectedEntityId = null;
    mode = "categories";
  } else if (node.dataset.categoryList) {
    activeCategory = node.dataset.categoryList;
    selectedEntityId = null;
    mode = "category-list";
    hideHoverPreview();
    render();
    if (options.focusGraph) focusSelectedGraphLabel();
    return true;
  } else if (node.dataset.entity) {
    selectedEntityId = node.dataset.entity;
    mode = "neighborhood";
  } else {
    return false;
  }
  hideHoverPreview();
  render();
  if (options.focusCard && node.dataset.entity) {
    focusDetailsCard();
  } else if (options.focusGraph) {
    focusSelectedGraphLabel();
  }
  return true;
}

function promoteNode(node) {
  if (node && node.parentNode === svg) {
    svg.appendChild(node);
  }
}

function clearConnectionHighlights() {
  svg.querySelectorAll(".connection-highlight, .connection-dim").forEach((element) => {
    element.classList.remove("connection-highlight", "connection-dim");
  });
  graphLabelsEl.querySelectorAll(".connection-highlight, .connection-dim").forEach((element) => {
    element.classList.remove("connection-highlight", "connection-dim");
  });
}

function highlightEntityConnections(entityId) {
  clearConnectionHighlights();
  const relationships = relationshipsByEntity.get(entityId) || [];
  if (!entityId || !relationships.length) return;
  const connectedIds = new Set([entityId]);
  const connectedRelationshipIds = new Set();
  relationships.forEach((relationship) => {
    connectedRelationshipIds.add(relationship.id);
    connectedIds.add(relationship.source === entityId ? relationship.target : relationship.source);
  });

  svg.querySelectorAll("[data-entity]").forEach((node) => {
    const isConnected = connectedIds.has(node.dataset.entity);
    node.classList.toggle("connection-highlight", isConnected);
    node.classList.toggle("connection-dim", !isConnected);
  });
  graphLabelsEl.querySelectorAll("[data-label-entity]").forEach((label) => {
    const isConnected = connectedIds.has(label.dataset.labelEntity);
    label.classList.toggle("connection-highlight", isConnected);
    label.classList.toggle("connection-dim", !isConnected);
  });
  svg.querySelectorAll("[data-edge]").forEach((edge) => {
    const isConnected = connectedRelationshipIds.has(edge.dataset.edge);
    edge.classList.toggle("connection-highlight", isConnected);
    edge.classList.toggle("connection-dim", !isConnected);
  });
}

function setHoveredNode(node) {
  clearConnectionHighlights();
  svg.querySelectorAll(".graph-node.hover").forEach((current) => {
    if (current !== node) current.classList.remove("hover");
  });
  graphLabelsEl.querySelectorAll(".html-graph-label.hover").forEach((current) => {
    current.classList.remove("hover");
  });
  if (!node) return;
  promoteNode(node);
  node.classList.add("hover");
  if (node.dataset.entity) highlightEntityConnections(node.dataset.entity);
  const labelKind = node.dataset.entity ? "labelEntity" : node.dataset.categoryList ? "labelCategoryList" : "labelCategory";
  const id = node.dataset.entity || node.dataset.categoryList || node.dataset.category;
  Array.from(graphLabelsEl.querySelectorAll(".html-graph-label")).forEach((label) => {
    if (label.dataset[labelKind] === id) label.classList.add("hover");
  });
}

function graphNodeFromTarget(target) {
  let node = target;
  while (node && node !== svg) {
    if (node.classList && node.classList.contains("graph-node")) return node;
    node = node.parentNode;
  }
  return null;
}

function graphLabelFromTarget(target) {
  let label = target;
  while (label && label !== graphLabelsEl) {
    if (label.classList && label.classList.contains("html-graph-label")) return label;
    label = label.parentNode;
  }
  return null;
}

function svgNodeFromLabel(label) {
  if (!label) return null;
  const isEntity = Boolean(label.dataset.labelEntity);
  const isCategoryList = Boolean(label.dataset.labelCategoryList);
  const id = label.dataset.labelEntity || label.dataset.labelCategoryList || label.dataset.labelCategory;
  const nodes = svg.querySelectorAll(isEntity ? "[data-entity]" : isCategoryList ? "[data-category-list]" : "[data-category]");
  return Array.from(nodes).find((node) => {
    if (isEntity) return node.dataset.entity === id;
    if (isCategoryList) return node.dataset.categoryList === id;
    return node.dataset.category === id;
  }) || null;
}

function interactionNodeFromTarget(target) {
  return graphNodeFromTarget(target) ||
    svgNodeFromLabel(graphLabelFromTarget(target)) ||
    svg.querySelector(".graph-node.hover");
}

function graphNodeKey(node) {
  if (!node) return "";
  return node.dataset.entity
    ? "entity:" + node.dataset.entity
    : node.dataset.categoryList
      ? "category-list:" + node.dataset.categoryList
      : node.dataset.category
        ? "category:" + node.dataset.category
        : node.dataset.homeRoot
          ? "home-root"
          : "";
}

function resetHoverZoomActivation() {
  hoverZoomTarget = null;
  hoverZoomDelta = 0;
}

function categoryPreview(categoryId) {
  const label = DATA.topCategoryLabels[categoryId] || categoryId;
  const entities = DATA.entities.filter((entity) => entity.topCategory === categoryId);
  const mentions = entities.reduce((total, entity) => total + (entity.count || 0), 0);
  const topEntities = entities
    .slice()
    .sort((a, b) => (b.count || 0) - (a.count || 0))
    .slice(0, 4)
    .map((entity) => entity.name)
    .join(", ");
  return {
    title: label,
    meta: entities.length.toLocaleString() + " entities · " + mentions.toLocaleString() + " mentions",
    body: topEntities ? "Top entities: " + topEntities : "No entities in this group.",
  };
}

function entityPreview(entityId) {
  const entity = entitiesById.get(entityId);
  if (!entity) return null;
  const relCount = (relationshipsByEntity.get(entity.id) || []).length;
  const evidence = (entity.evidenceIds || []).map((id) => mentionsById.get(id)).find(Boolean);
  const body = evidence
    ? truncate(evidence.excerpt, 180)
    : truncate(entity.significance || "No transcript snippet available.", 180);
  return {
    title: entity.name,
    meta: entity.categoryLabel + " · " + (entity.count || 0).toLocaleString() + " mentions · " + relCount + " links",
    body,
  };
}

function homePreview() {
  const counts = DATA.manifest.counts || {};
  return {
    title: "UFO Files",
    meta: (counts.entities || DATA.entities.length).toLocaleString() + " entities · " + (counts.relationships || DATA.relationships.length).toLocaleString() + " relationships",
    body: Object.keys(DATA.topCategoryLabels).length.toLocaleString() + " top-level groups · " + (counts.mentions || DATA.mentions.length).toLocaleString() + " mentions",
  };
}

function showHoverPreview(node, event) {
  if (!node || dragStart) {
    hideHoverPreview();
    return;
  }
  const preview = node.dataset.homeRoot
    ? homePreview()
    : node.dataset.entity
    ? entityPreview(node.dataset.entity)
    : categoryPreview(node.dataset.categoryList || node.dataset.category);
  if (!preview) {
    hideHoverPreview();
    return;
  }
  hoverCardEl.innerHTML = '<h2>' + esc(preview.title) + '</h2>' +
    '<div class="meta">' + esc(preview.meta) + '</div>' +
    '<p>' + esc(preview.body) + '</p>';
  hoverCardEl.classList.add("open");
  positionHoverPreview(event);
}

function hideHoverPreview() {
  hoverCardEl.classList.remove("open");
}

function positionHoverPreview(event) {
  if (!hoverCardEl.classList.contains("open")) return;
  const margin = 12;
  const offset = 16;
  const rect = hoverCardEl.getBoundingClientRect();
  let x = event.clientX + offset;
  let y = event.clientY + offset;
  if (x + rect.width + margin > window.innerWidth) x = event.clientX - rect.width - offset;
  if (y + rect.height + margin > window.innerHeight) y = event.clientY - rect.height - offset;
  hoverCardEl.style.left = Math.max(margin, x) + "px";
  hoverCardEl.style.top = Math.max(margin, y) + "px";
}

function searchGraph() {
  const query = searchEl.value.trim().toLowerCase();
  if (!query) return;
  const category = Object.entries(DATA.topCategoryLabels).find(([id, label]) => label.toLowerCase().includes(query) || id.toLowerCase().includes(query));
  const entity = DATA.entities.find((item) => item.name.toLowerCase().includes(query));
  if (entity) {
    selectedEntityId = entity.id;
    activeCategory = null;
    mode = "neighborhood";
  } else if (category) {
    activeCategory = category[0];
    selectedEntityId = null;
    mode = "categories";
  } else {
    statusEl.textContent = "No graph result for " + query;
    return;
  }
  render();
  focusSelectedGraphLabel();
}

function stepBackGraph() {
  if (cardEl.classList.contains("open")) {
    cardEl.classList.remove("open");
    cardEl.removeAttribute("aria-labelledby");
    focusSelectedGraphLabel();
    return true;
  }
  if (mode === "neighborhood") {
    selectedEntityId = null;
    mode = "categories";
    render();
    focusSelectedGraphLabel();
    return true;
  }
  if (mode === "category-list") {
    selectedEntityId = null;
    mode = "categories";
    render();
    focusSelectedGraphLabel();
    return true;
  }
  if (activeCategory) {
    activeCategory = null;
    selectedEntityId = null;
    mode = "categories";
    renderCategories();
    focusSelectedGraphLabel();
    return true;
  }
  return false;
}

function defaultReview() {
  return {
    reclassifications: {},
    nameReclassifications: {},
    falsePositives: {},
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
  };
}

function normalizeReview(review) {
  const normalized = defaultReview();
  if (!review || typeof review !== "object") return normalized;
  for (const key of ["reclassifications", "nameReclassifications", "falsePositives", "removedFalsePositives", "omissions", "aliases", "merges", "nameMerges", "removedMerges", "removedNameMerges", "removedManualRelationships", "manualRelationships", "notes"]) {
    normalized[key] = review[key] && typeof review[key] === "object" && !Array.isArray(review[key]) ? review[key] : {};
  }
  normalized.manualRelationships = normalizeManualRelationshipDecisions(normalized.manualRelationships);
  normalized.removedManualRelationships = normalizeManualRelationshipDecisions(normalized.removedManualRelationships, true);
  if (review.generatedAt) normalized.generatedAt = review.generatedAt;
  if (review.note) normalized.note = review.note;
  if (review.basePipelineHash) normalized.basePipelineHash = review.basePipelineHash;
  return normalized;
}

function normalizeManualRelationshipDecisions(decisions, allowFallbackKey = false) {
  const normalized = {};
  for (const [key, item] of Object.entries(decisions || {})) {
    if (item && typeof item === "object" && item.sourceId && item.targetId && item.sourceId !== item.targetId) {
      normalized[manualRelationshipKey(item.sourceId, item.targetId)] = item;
    } else if (allowFallbackKey && key) {
      normalized[key] = item;
    }
  }
  return normalized;
}

function mergeReviews(base, overlay) {
  const merged = normalizeReview(base);
  const next = normalizeReview(overlay);
  for (const key of ["reclassifications", "nameReclassifications", "falsePositives", "removedFalsePositives", "omissions", "aliases", "merges", "nameMerges", "removedMerges", "removedNameMerges", "removedManualRelationships", "manualRelationships", "notes"]) {
    merged[key] = { ...(merged[key] || {}), ...(next[key] || {}) };
  }
  for (const key of Object.keys(merged.removedFalsePositives || {})) delete merged.falsePositives[key];
  for (const key of Object.keys(merged.removedMerges || {})) delete merged.merges[key];
  for (const key of Object.keys(merged.removedNameMerges || {})) delete merged.nameMerges[key];
  for (const key of Object.keys(merged.removedManualRelationships || {})) delete merged.manualRelationships[key];
  if (next.generatedAt) merged.generatedAt = next.generatedAt;
  if (next.note) merged.note = next.note;
  if (next.basePipelineHash) merged.basePipelineHash = next.basePipelineHash;
  return merged;
}

function sameReviewValue(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function reviewEntryName(id, value) {
  const names = [];
  if (id) {
    const textId = String(id);
    names.push(textId.includes(":") ? textId.split(":").slice(1).join(" ").replace(/-/g, " ") : textId);
  }
  if (value && typeof value === "object" && value.name) names.push(value.name);
  if (value && typeof value === "object" && value.sourceName) names.push(value.sourceName);
  return names.map(normalizeText).filter(Boolean);
}

function rawEntityById(id) {
  return (RAW.entities || []).find((entity) => entity.id === id);
}

function rawEntityByName(name) {
  const normalized = normalizeText(name);
  if (!normalized) return null;
  return (RAW.entities || []).find((entity) => normalizeText(entity.name) === normalized) || null;
}

function reviewCategoryIsBaked(id, category) {
  if (Object.prototype.hasOwnProperty.call(BUILT_REVIEW.reclassifications || {}, id) && BUILT_REVIEW.reclassifications[id] === category) {
    return true;
  }
  for (const name of reviewEntryName(id, category)) {
    if ((BUILT_REVIEW.nameReclassifications || {})[name] === category) return true;
    const entity = rawEntityById(id) || rawEntityByName(name);
    if (entity && entity.category === category) return true;
  }
  return false;
}

function reviewAliasIsBaked(id, alias) {
  if (Object.prototype.hasOwnProperty.call(BUILT_REVIEW.aliases || {}, id) && sameReviewValue(alias, BUILT_REVIEW.aliases[id])) {
    return true;
  }
  const aliasName = normalizeText(alias);
  if (!aliasName) return false;
  return Boolean(rawEntityById(id) && normalizeText(rawEntityById(id).name) === aliasName) || Boolean(rawEntityByName(aliasName));
}

function reviewFalsePositiveIsBaked(id, value) {
  if (Object.prototype.hasOwnProperty.call(BUILT_REVIEW.falsePositives || {}, id) && sameReviewValue(value, BUILT_REVIEW.falsePositives[id])) {
    return true;
  }
  const entity = rawEntityById(id);
  return !entity && reviewEntryName(id, value).every((name) => !rawEntityByName(name));
}

function reviewMergeIsBaked(id, value) {
  const built = (BUILT_REVIEW.merges || {})[id] || (BUILT_REVIEW.nameMerges || {})[id];
  if (built && sameReviewValue(value, built)) return true;
  if (!value || typeof value !== "object") return false;
  const source = rawEntityById(value.sourceId) || rawEntityByName(value.sourceName);
  const target = rawEntityById(value.targetId) || rawEntityByName(value.targetName);
  return !source && Boolean(target);
}

function reviewKeyExistsInBuiltReview(key, id) {
  return Object.prototype.hasOwnProperty.call(BUILT_REVIEW[key] || {}, id);
}

function removeBuiltReviewEntries(review) {
  const cleaned = normalizeReview(review);
  let changed = false;
  const staleBrowserReview = CURRENT_REVIEW_BASE && cleaned.basePipelineHash !== CURRENT_REVIEW_BASE;
  for (const key of ["reclassifications", "nameReclassifications", "falsePositives", "removedFalsePositives", "omissions", "aliases", "merges", "nameMerges", "removedManualRelationships", "manualRelationships"]) {
    for (const [id, value] of Object.entries(cleaned[key] || {})) {
      const builtKey = reviewKeyExistsInBuiltReview(key, id);
      const exactBuilt = builtKey && sameReviewValue(value, BUILT_REVIEW[key][id]);
      const staleBuiltOverride = staleBrowserReview && builtKey;
      const bakedCategory = key === "reclassifications" || key === "nameReclassifications" ? reviewCategoryIsBaked(id, value) : false;
      const bakedFalsePositive = key === "falsePositives" ? reviewFalsePositiveIsBaked(id, value) : false;
      const bakedAlias = key === "aliases" ? reviewAliasIsBaked(id, value) : false;
      const bakedMerge = key === "merges" || key === "nameMerges" ? reviewMergeIsBaked(id, value) : false;
      if (exactBuilt || staleBuiltOverride || bakedCategory || bakedFalsePositive || bakedAlias || bakedMerge) {
        delete cleaned[key][id];
        changed = true;
      }
    }
  }
  return { cleaned, changed };
}

function initializeReviewStorage() {
  const previousRaw = localStorage.getItem(PREVIOUS_REVIEW_KEY);
  if (!localStorage.getItem(REVIEW_KEY) && previousRaw) {
    localStorage.setItem(REVIEW_KEY, previousRaw);
  }
  if (previousRaw) localStorage.removeItem(PREVIOUS_REVIEW_KEY);
  const legacyRaw = localStorage.getItem(LEGACY_REVIEW_KEY);
  if (!localStorage.getItem(REVIEW_KEY) && legacyRaw) {
    localStorage.setItem(REVIEW_KEY, legacyRaw);
  }
  if (legacyRaw) localStorage.removeItem(LEGACY_REVIEW_KEY);
  const storedRaw = localStorage.getItem(REVIEW_KEY);
  if (!storedRaw) return;
  try {
    const { cleaned, changed } = removeBuiltReviewEntries(JSON.parse(storedRaw));
    if (changed) {
      if (hasReviewDecisions(cleaned)) {
        localStorage.setItem(REVIEW_KEY, JSON.stringify(cleaned));
      } else {
        localStorage.removeItem(REVIEW_KEY);
      }
    }
  } catch {
    localStorage.removeItem(REVIEW_KEY);
  }
}

function readReview() {
  try {
    return normalizeReview(JSON.parse(localStorage.getItem(REVIEW_KEY) || "{}"));
  } catch {
    return defaultReview();
  }
}

function saveReview(review) {
  const next = normalizeReview(review);
  if (CURRENT_REVIEW_BASE) next.basePipelineHash = CURRENT_REVIEW_BASE;
  localStorage.setItem(REVIEW_KEY, JSON.stringify(next));
  updateReviewButton();
}

function hasReviewDecisions(review) {
  return reviewDecisionCount(review) > 0;
}

function reviewDecisionCount(review) {
  return (
    Object.keys(review.reclassifications || {}).length +
    Object.keys(review.nameReclassifications || {}).length +
    Object.keys(review.falsePositives || {}).length +
    Object.keys(review.removedFalsePositives || {}).length +
    Object.keys(review.omissions || {}).length +
    Object.keys(review.aliases || {}).length +
    Object.keys(review.merges || {}).length +
    Object.keys(review.nameMerges || {}).length +
    Object.keys(review.removedMerges || {}).length +
    Object.keys(review.removedNameMerges || {}).length +
    Object.keys(review.removedManualRelationships || {}).length +
    Object.keys(review.manualRelationships || {}).length
  );
}

function updateReviewButton() {
  const button = document.getElementById("download-review");
  const review = readReview();
  const count = reviewDecisionCount(review);
  if (button) button.hidden = count === 0;
  if (reviewFalsePositivesButton) reviewFalsePositivesButton.hidden = falsePositiveRows().length === 0;
  if (reviewStatusEl) reviewStatusEl.textContent = count ? count.toLocaleString() + " new reclass changes" : "";
}

function download(filename, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function cssEscape(value) {
  if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(String(value ?? ""));
  return String(value ?? "").replace(/["\\]/g, "\\$&");
}

function truncate(value, length) {
  const text = String(value ?? "");
  return text.length > length ? text.slice(0, length - 1) + "..." : text;
}

function entityDisplayName(entity) {
  if (!entity || !entity.name) return "";
  const name = String(entity.name);
  if (entity.category === "document_names") {
    const releaseMatch = name.match(/^Document\s+Dow\s+Release\s+(\d+)\s+(.+)$/i);
    if (releaseMatch) return releaseMatch[2].trim() + " (DoW Release " + releaseMatch[1] + ")";
  }
  return name;
}

function normalizeText(value) {
  return String(value ?? "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function touchPoint(touch) {
  return { x: touch.clientX, y: touch.clientY };
}

function midpoint(a, b) {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function setZoomFromScreenPoint(screenPoint, startViewBox, nextW, nextH) {
  const pointer = screenToGraph(screenPoint.x, screenPoint.y);
  const pointerRatioX = (pointer.x - startViewBox.x) / startViewBox.w;
  const pointerRatioY = (pointer.y - startViewBox.y) / startViewBox.h;
  setViewBox(pointer.x - pointerRatioX * nextW, pointer.y - pointerRatioY * nextH, nextW, nextH);
}

function startTouch(event) {
  if (!event.touches.length) return;
  event.preventDefault();
  resetHoverZoomActivation();
  hideHoverPreview();
  if (event.touches.length >= 2) {
    const first = touchPoint(event.touches[0]);
    const second = touchPoint(event.touches[1]);
    touchState = {
      mode: "pinch",
      startDistance: Math.max(1, distance(first, second)),
      startMidpoint: midpoint(first, second),
      startViewBox: { ...viewBox },
    };
    svg.classList.add("dragging");
    return;
  }
  const point = touchPoint(event.touches[0]);
  touchState = {
    mode: "pan",
    startPoint: point,
    startViewBox: { ...viewBox },
    moved: false,
    tapNode: interactionNodeFromTarget(event.target),
  };
  svg.classList.add("dragging");
}

function moveTouch(event) {
  if (!touchState || !event.touches.length) return;
  event.preventDefault();
  if (event.touches.length >= 2) {
    const first = touchPoint(event.touches[0]);
    const second = touchPoint(event.touches[1]);
    if (touchState.mode !== "pinch") {
      touchState = {
        mode: "pinch",
        startDistance: Math.max(1, distance(first, second)),
        startMidpoint: midpoint(first, second),
        startViewBox: { ...viewBox },
      };
    }
    const scale = Math.max(0.1, distance(first, second) / touchState.startDistance);
    const nextW = clamp(touchState.startViewBox.w / scale, MIN_ZOOM_WIDTH, MAX_ZOOM_WIDTH);
    const nextH = clamp(touchState.startViewBox.h / scale, MIN_ZOOM_HEIGHT, MAX_ZOOM_HEIGHT);
    setZoomFromScreenPoint(midpoint(first, second), touchState.startViewBox, nextW, nextH);
    return;
  }
  if (touchState.mode !== "pan") return;
  const point = touchPoint(event.touches[0]);
  const dx = point.x - touchState.startPoint.x;
  const dy = point.y - touchState.startPoint.y;
  if (Math.hypot(dx, dy) > 8) touchState.moved = true;
  const transform = graphViewportTransform();
  setViewBox(
    touchState.startViewBox.x - dx / transform.scale,
    touchState.startViewBox.y - dy / transform.scale,
    touchState.startViewBox.w,
    touchState.startViewBox.h
  );
}

function endTouch(event) {
  if (!touchState) return;
  event.preventDefault();
  if (touchState.mode === "pan" && !touchState.moved && touchState.tapNode) {
    activateGraphNode(touchState.tapNode);
  }
  touchState = null;
  svg.classList.remove("dragging");
}

graphLabelsEl.addEventListener("pointermove", (event) => {
  const label = graphLabelFromTarget(event.target);
  const node = svgNodeFromLabel(label);
  setHoveredNode(node);
  showHoverPreview(node, event);
});
graphLabelsEl.addEventListener("pointerleave", () => {
  setHoveredNode(null);
  hideHoverPreview();
});
graphLabelsEl.addEventListener("click", (event) => {
  const label = graphLabelFromTarget(event.target);
  if (!label) return;
  activateGraphNode(svgNodeFromLabel(label));
});
graphLabelsEl.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const label = graphLabelFromTarget(event.target);
  if (!label) return;
  event.preventDefault();
  activateGraphNode(svgNodeFromLabel(label), { focusCard: true, focusGraph: true });
});
graphLabelsEl.addEventListener("focusin", (event) => {
  const label = graphLabelFromTarget(event.target);
  const node = svgNodeFromLabel(label);
  if (!node || !label) return;
  setHoveredNode(node);
  const rect = label.getBoundingClientRect();
  showHoverPreview(node, { clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 });
});
graphLabelsEl.addEventListener("focusout", (event) => {
  if (graphLabelsEl.contains(event.relatedTarget)) return;
  setHoveredNode(null);
  hideHoverPreview();
});
window.addEventListener("resize", renderLabelLayer);

function handleGraphWheel(event) {
  event.preventDefault();
  const interactionNode = event.deltaY < 0 ? interactionNodeFromTarget(event.target) : null;
  const interactionNodeKey = graphNodeKey(interactionNode);
  if (event.deltaY >= 0 || !interactionNodeKey) {
    resetHoverZoomActivation();
  } else if (hoverZoomTarget !== interactionNodeKey) {
    hoverZoomTarget = interactionNodeKey;
    hoverZoomDelta = 0;
  }
  const pointer = screenToGraph(event.clientX, event.clientY);
  const pointerX = pointer.x;
  const pointerY = pointer.y;
  const intensity = event.deltaMode === 1 ? 0.08 : 0.0015;
  const factor = clamp(Math.exp(event.deltaY * intensity), 0.82, 1.22);
  const nextW = clamp(viewBox.w * factor, MIN_ZOOM_WIDTH, MAX_ZOOM_WIDTH);
  const nextH = clamp(viewBox.h * factor, MIN_ZOOM_HEIGHT, MAX_ZOOM_HEIGHT);
  const pointerRatioX = (pointerX - viewBox.x) / viewBox.w;
  const pointerRatioY = (pointerY - viewBox.y) / viewBox.h;
  setViewBox(pointerX - pointerRatioX * nextW, pointerY - pointerRatioY * nextH, nextW, nextH);
  if (event.deltaY < 0 && interactionNodeKey) {
    hoverZoomDelta += Math.abs(event.deltaY) * (event.deltaMode === 1 ? 16 : 1);
    if (hoverZoomDelta >= HOVER_ZOOM_ACTIVATE_DELTA && activateGraphNode(interactionNode)) {
      resetHoverZoomActivation();
      return;
    }
  }
  if (event.deltaY > 0 && mode === "neighborhood" && nextW >= ENTITY_ZOOM_OUT_STEP_UP_WIDTH) {
    selectedEntityId = null;
    mode = "categories";
    hideHoverPreview();
    if (activeCategory) {
      renderCategory(activeCategory);
    } else {
      renderCategories();
    }
    return;
  }
  if (event.deltaY > 0 && mode === "category-list" && nextW >= ENTITY_ZOOM_OUT_STEP_UP_WIDTH) {
    selectedEntityId = null;
    mode = "categories";
    hideHoverPreview();
    renderCategory(activeCategory);
    return;
  }
  if (event.deltaY > 0 && activeCategory && mode === "categories" && nextW >= CATEGORY_ZOOM_OUT_STEP_UP_WIDTH) {
    activeCategory = null;
    selectedEntityId = null;
    hideHoverPreview();
    renderCategories();
  }
}

svg.addEventListener("wheel", handleGraphWheel, { passive: false });
graphLabelsEl.addEventListener("wheel", handleGraphWheel, { passive: false });
svg.addEventListener("touchstart", startTouch, { passive: false });
svg.addEventListener("touchmove", moveTouch, { passive: false });
svg.addEventListener("touchend", endTouch, { passive: false });
svg.addEventListener("touchcancel", endTouch, { passive: false });
graphLabelsEl.addEventListener("touchstart", startTouch, { passive: false });
graphLabelsEl.addEventListener("touchmove", moveTouch, { passive: false });
graphLabelsEl.addEventListener("touchend", endTouch, { passive: false });
graphLabelsEl.addEventListener("touchcancel", endTouch, { passive: false });
svg.addEventListener("pointermove", (event) => {
  const node = graphNodeFromTarget(event.target);
  setHoveredNode(node);
  showHoverPreview(node, event);
});
svg.addEventListener("pointerleave", () => {
  setHoveredNode(null);
  hideHoverPreview();
});
svg.addEventListener("pointerdown", (event) => {
  if (graphNodeFromTarget(event.target) || event.target.closest(".graph-edge")) return;
  hideHoverPreview();
  dragStart = { x: event.clientX, y: event.clientY, viewBox: { ...viewBox } };
  svg.classList.add("dragging");
  svg.setPointerCapture(event.pointerId);
});
svg.addEventListener("pointermove", (event) => {
  if (!dragStart) return;
  const scaleX = viewBox.w / svg.clientWidth;
  const scaleY = viewBox.h / svg.clientHeight;
  setViewBox(dragStart.viewBox.x - (event.clientX - dragStart.x) * scaleX, dragStart.viewBox.y - (event.clientY - dragStart.y) * scaleY, viewBox.w, viewBox.h);
});
svg.addEventListener("pointerup", (event) => {
  if (dragStart && svg.hasPointerCapture(event.pointerId)) {
    svg.releasePointerCapture(event.pointerId);
  }
  dragStart = null;
  svg.classList.remove("dragging");
});
document.getElementById("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  searchGraph();
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (stepBackGraph()) event.preventDefault();
});
document.getElementById("download-review").addEventListener("click", () => {
  const review = mergeReviews(BUILT_REVIEW, readReview());
  review.generatedAt = new Date().toISOString();
  review.note = "Replace data/reclass.json with this file before rebuilding.";
  delete review.basePipelineHash;
  download("reclass.json", review);
});
reviewFalsePositivesButton.addEventListener("click", () => renderFalsePositiveReviewCard());
document.getElementById("download-data").addEventListener("click", () => download("relationship-graph-data.json", DATA));
appSwitcher.addEventListener("change", () => {
  if (appSwitcher.value && appSwitcher.value !== window.location.href) {
    window.location.href = appSwitcher.value;
  }
});
updateReviewButton();
render();
