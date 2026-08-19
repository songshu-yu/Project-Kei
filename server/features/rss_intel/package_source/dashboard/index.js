let mountedRoot = null;

export function mount(context) {
  const root = context?.root;
  if (!root) {
    throw new Error("rss_intel dashboard root is unavailable");
  }
  root.replaceChildren();
  root.dataset.panelSettings =
    "来源 ID：money|Feed：仅应用组装的受信 HTTPS 来源|网络：仅显式采集";

  const heading = document.createElement("h2");
  heading.textContent = "RSS/Atom 情报来源";
  const summary = document.createElement("p");
  summary.textContent =
    "通用 RSS/Atom、关键词过滤、发布时间与稳定 ID；未配置来源时保持停用态。";
  const boundary = document.createElement("p");
  boundary.className = "muted";
  boundary.textContent =
    "此面板不接收 Feed URL，不读取缓存或凭据，也不会在打开时发起网络请求。";
  root.append(heading, summary, boundary);
  mountedRoot = root;
}

export function unmount() {
  if (mountedRoot) {
    mountedRoot.replaceChildren();
    mountedRoot = null;
  }
}
