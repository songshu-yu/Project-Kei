let mountedRoot = null;

function node(root, tag, className, text) {
  const value = root.ownerDocument.createElement(tag);
  if (className) value.className = className;
  if (text !== undefined) value.textContent = text;
  return value;
}

function safeUrl(value) {
  try {
    const parsed = new URL(String(value || ""));
    return ["http:", "https:"].includes(parsed.protocol) &&
      !parsed.username && !parsed.password ? parsed.href : "";
  } catch {
    return "";
  }
}

function render(root, payload) {
  const heading = node(root, "h2", "", "今日论文");
  const meta = node(root, "p", "hint");
  const list = node(root, "div", "module-grid");
  const items = payload?.ready && Array.isArray(payload.items) ? payload.items : [];
  meta.textContent = items.length
    ? `${items.length} 篇 · 仅来自当天缓存`
    : "今日暂无论文";
  for (const paper of items) {
    const card = node(root, "article", "module-card");
    const title = node(root, "h3", "", paper.title || "未命名论文");
    const summary = node(root, "p", "detail", paper.summary || "摘要暂缺");
    const byline = node(
      root,
      "p",
      "hint",
      [paper.author, paper.source_id, paper.published_at].filter(Boolean).join(" · "),
    );
    const url = safeUrl(paper.url);
    if (url) {
      const link = node(root, "a", "", "查看来源");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      byline.append(" · ", link);
    }
    card.append(title, summary, byline);
    list.append(card);
  }
  const warnings = Array.isArray(payload?.warnings) ? payload.warnings : [];
  const warning = node(root, "p", "hint", warnings.join("；"));
  const script = node(root, "p", "detail", payload?.script || "");
  script.hidden = !script.textContent;
  const refresh = node(root, "button", "secondary", "刷新论文（会联网）");
  refresh.type = "button";
  refresh.dataset.papersRole = "refresh";
  root.replaceChildren(heading, meta, list, warning, script, refresh);
}

async function load(context, root) {
  const payload = await context.request("/api/v1/papers/today");
  if (mountedRoot === root) render(root, payload);
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== "function") {
    throw new TypeError("papers 面板缺少受限挂载上下文");
  }
  await unmount();
  const root = context.root;
  mountedRoot = root;
  render(root, {ready: false, items: []});
  await load(context, root);
  let armed = false;
  const refresh = root.querySelector('[data-papers-role="refresh"]');
  refresh.addEventListener("click", async () => {
    if (!armed) {
      armed = true;
      refresh.textContent = "再次点击确认联网刷新";
      context.notify("刷新会访问 arXiv、Crossref 和 Semantic Scholar。", "error");
      return;
    }
    refresh.disabled = true;
    try {
      const payload = await context.request("/api/v1/papers/refresh", {method: "POST"});
      if (mountedRoot === root) render(root, payload);
      context.notify("论文刷新完成。");
    } catch (error) {
      refresh.disabled = false;
      context.notify(`论文刷新失败：${error.message}`, "error");
    }
  });
}

export async function unmount() {
  if (mountedRoot) mountedRoot.replaceChildren();
  mountedRoot = null;
}
