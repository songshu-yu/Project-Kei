let mountedRoot = null;
let currentContext = null;

function node(root, tag, text = '') {
  const element = root.ownerDocument.createElement(tag);
  element.textContent = text;
  return element;
}

function render(snapshot) {
  if (!mountedRoot) return;
  const list = mountedRoot.querySelector('[data-vpd-role="list"]');
  list.replaceChildren();
  const releases = snapshot.releases || [];
  if (!releases.length) {
    list.append(node(
      mountedRoot,
      'p',
      '当前公开目录为空。模块不会联网；只有安装已固定目录条目时才会访问网络。',
    ));
    return;
  }
  for (const release of releases) {
    const card = node(mountedRoot, 'article');
    const title = node(
      mountedRoot,
      'h3',
      `${release.name} · ${release.id}@${release.version}`,
    );
    const meta = node(
      mountedRoot,
      'p',
      `${release.language} · ${release.size_bytes} 字节 · ${
        release.installed ? '已安装' : release.cached ? '已下载' : '未下载'
      }`,
    );
    const install = node(
      mountedRoot,
      'button',
      release.installed ? '校验安装' : '确认并安装',
    );
    const download = node(mountedRoot, 'button', '仅下载');
    meta.className = 'hint';
    install.type = 'button';
    download.type = 'button';
    download.className = 'secondary';
    install.addEventListener('click', () => runInstall(release, false, install));
    download.addEventListener('click', () => runInstall(release, true, download));
    card.append(title, meta, install, download);
    list.append(card);
  }
}

async function refresh() {
  const snapshot = await currentContext.request(
    '/api/v1/voice-pack-distribution/releases',
  );
  render(snapshot);
}

async function runInstall(release, downloadOnly, control) {
  const key = `${release.id}@${release.version}`;
  const confirmed = globalThis.confirm?.(
    `${downloadOnly ? '仅下载并校验' : '安装'} ${key}？来源、大小与 SHA-256 已由内置目录固定。`,
  );
  if (!confirmed) return;
  control.disabled = true;
  try {
    const result = await currentContext.request(
      '/api/v1/voice-pack-distribution/install',
      {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          key,
          confirmation: key,
          download_only: downloadOnly,
        }),
      },
    );
    currentContext.notify(
      result.status === 'already_installed'
        ? '相同内容已安装。'
        : downloadOnly ? '下载与校验完成。' : 'Voice Pack 安装完成。',
    );
    await refresh();
  } catch (error) {
    currentContext.notify(`Voice Pack 分发操作失败：${error.message}`, 'error');
    await refresh();
  }
}

function buildPanel(root) {
  const intro = node(
    root,
    'p',
    '仅展示随模块发布的可信目录。普通浏览和校验零网络，远程访问只发生在明确安装或仅下载操作中。',
  );
  const list = node(root, 'div');
  intro.className = 'hint';
  list.className = 'module-grid';
  list.dataset.vpdRole = 'list';
  root.replaceChildren(intro, list);
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== 'function') {
    throw new TypeError('Voice Pack 分发面板缺少受限挂载上下文');
  }
  await unmount();
  mountedRoot = context.root;
  currentContext = context;
  buildPanel(mountedRoot);
  await refresh();
}

export async function unmount() {
  if (mountedRoot) mountedRoot.replaceChildren();
  mountedRoot = null;
  currentContext = null;
}
