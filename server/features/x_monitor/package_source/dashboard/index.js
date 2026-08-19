let mountedRoot = null;
let mountedContext = null;
const userState = new Map();

function role(root, value) {
  return root.querySelector(`[data-x-role="${value}"]`);
}

function localDate() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function normalizedUser(value) {
  return String(value || '').trim().replace(/^@/, '').toLowerCase();
}

function node(root, tag, text = '', className = '') {
  const item = root.ownerDocument.createElement(tag);
  item.textContent = text;
  item.className = className;
  return item;
}

function stateFor(username) {
  const key = normalizedUser(username);
  if (!userState.has(key)) {
    userState.set(key, {
      username,
      date: localDate(),
      activeMode: 'day',
      contentView: {day: 'posts', since: 'posts'},
      results: {day: null, since: null},
      profile: null,
      cached: null,
      loading: null,
    });
  }
  return userState.get(key);
}

function linkButton(root, label, url) {
  const link = node(root, 'a', label, 'x-monitor-link-button');
  link.href = String(url);
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  Object.assign(link.style, {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 'fit-content',
    marginTop: '6px',
    padding: '6px 12px',
    border: '1px solid var(--line)',
    borderRadius: '8px',
    background: 'var(--surface-strong)',
    color: 'var(--text)',
    fontSize: '13px',
    fontWeight: '600',
    lineHeight: '1.2',
    textDecoration: 'none',
  });
  return link;
}

function appendItem(root, list, item) {
  const row = node(root, 'li', '', 'x-monitor-item');
  const kind = node(root, 'span', String(item.kind || 'post'), 'status-pill');
  const content = node(root, 'p', String(item.content || ''));
  row.append(kind, content);
  if (item.kind === 'reply' && item.parent_context) {
    const parent = item.parent_context;
    const context = node(
      root,
      'blockquote',
      `${String(parent.username || '')}：${String(parent.content || '')}`,
      'detail',
    );
    if (parent.published_at) {
      context.append(node(root, 'time', ` · ${String(parent.published_at)}`, 'hint'));
    }
    if (parent.url) {
      context.append(linkButton(root, '查看直接父帖', parent.url));
    }
    row.append(context);
  }
  if (item.published_at) row.append(node(root, 'time', String(item.published_at), 'hint'));
  if (item.url) {
    row.append(linkButton(root, '查看原文', item.url));
  }
  list.append(row);
}

function renderResult(root, state, host) {
  const result = state.results[state.activeMode];
  host.replaceChildren();
  if (!result) {
    const cachedItems = state.cached?.posts || [];
    host.append(node(
      root,
      'p',
      cachedItems.length
        ? `今日兼容缓存：${cachedItems.length} 条。点击上方按钮执行新的显式查询。`
        : '尚无该模式的查询结果。',
      'hint',
    ));
    return;
  }
  const allItems = Array.isArray(result.items) ? result.items : [];
  const postItems = allItems.filter((item) => item.kind === 'post' || item.kind === 'quote');
  const replyItems = allItems.filter((item) => item.kind === 'reply');
  const activeView = state.contentView[state.activeMode] === 'replies' ? 'replies' : 'posts';
  const visibleItems = activeView === 'replies' ? replyItems : postItems;
  const boundary = node(
    root,
    'p',
    `@${result.username} · ${result.mode === 'day' ? '该日' : '该日至今'} · `
      + `Asia/Shanghai ${result.start_at} → ${result.end_at} · `
      + `${activeView === 'replies' ? '回复' : '发帖'} ${visibleItems.length} 条`
      + `（本次共 ${result.count} 条） · 获取于 ${result.fetched_at}`,
    'hint',
  );
  const warning = node(
    root,
    'p',
    'Nitter/RSS 或 FxEmbed 只展示上游本次实际返回内容；回复最多补一层直接父帖，不保证完整历史或完整回复线程。',
    'detail',
  );
  const list = node(root, 'ul', '', 'source-list');
  for (const item of visibleItems) appendItem(root, list, item);
  if (!visibleItems.length) {
    list.append(node(root, 'li', activeView === 'replies' ? '本次没有获取到回复。' : '本次没有获取到发帖。', 'hint'));
  }
  host.append(boundary, warning, list);
}

function contentCounts(state) {
  const result = state.results[state.activeMode];
  const items = Array.isArray(result?.items) ? result.items : [];
  return {
    posts: items.filter((item) => item.kind === 'post' || item.kind === 'quote').length,
    replies: items.filter((item) => item.kind === 'reply').length,
  };
}

function styleContentTab(button, active) {
  Object.assign(button.style, {
    minWidth: '88px',
    padding: '7px 17px',
    border: `1px solid ${active ? 'var(--accent)' : 'var(--line)'}`,
    borderRadius: '999px',
    background: active ? 'rgba(164, 59, 112, 0.14)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--text)',
    fontWeight: active ? '700' : '500',
    boxShadow: active ? 'inset 0 0 0 1px rgba(164, 59, 112, 0.08)' : 'none',
  });
}

function renderUser(root, state) {
  const details = node(root, 'details', '', 'module-card');
  details.dataset.xUsername = state.username;
  const summary = node(root, 'summary');
  const profile = state.profile || {};
  const avatar = node(root, 'img');
  avatar.alt = '';
  if (profile.avatar_url) avatar.src = String(profile.avatar_url);
  const title = node(
    root,
    'strong',
    profile.name ? `${profile.name} (@${state.username})` : `@${state.username}`,
  );
  const groups = node(
    root,
    'span',
    (profile.x_config_groups || state.cached?.x_config_groups || []).join(' / '),
    'hint',
  );
  summary.append(avatar, title, groups);

  const controls = node(root, 'div', '', 'schedule-grid');
  const dateLabel = node(root, 'label', '查询日期', 'field');
  const dateInput = node(root, 'input');
  dateInput.type = 'date';
  dateInput.value = state.date;
  dateInput.dataset.xRole = 'date';
  dateInput.addEventListener('change', () => {
    state.date = dateInput.value;
  });
  dateLabel.append(dateInput);
  const profileButton = node(root, 'button', '刷新资料', 'secondary');
  const dayButton = node(root, 'button', '获取该日言论');
  const sinceButton = node(root, 'button', '获取该日至今');
  controls.append(dateLabel, profileButton, dayButton, sinceButton);

  const tabs = node(root, 'div', '', 'segmented-control');
  const dayTab = node(root, 'button', '该日结果', 'secondary');
  const sinceTab = node(root, 'button', '该日至今结果', 'secondary');
  tabs.append(dayTab, sinceTab);
  const contentTabs = node(root, 'nav', '', 'x-monitor-content-tabs');
  contentTabs.setAttribute('aria-label', `@${state.username} 言论类型`);
  Object.assign(contentTabs.style, {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '8px',
    margin: '10px 0',
  });
  const postsTab = node(root, 'button', '发帖', 'secondary');
  const repliesTab = node(root, 'button', '回复', 'secondary');
  postsTab.type = 'button';
  repliesTab.type = 'button';
  contentTabs.append(postsTab, repliesTab);
  const resultHost = node(root, 'div', '', 'x-monitor-results');

  const refresh = () => {
    const counts = contentCounts(state);
    const activeView = state.contentView[state.activeMode] === 'replies' ? 'replies' : 'posts';
    postsTab.setAttribute('aria-pressed', activeView === 'posts' ? 'true' : 'false');
    repliesTab.setAttribute('aria-pressed', activeView === 'replies' ? 'true' : 'false');
    postsTab.setAttribute('aria-label', `发帖，${counts.posts} 条`);
    repliesTab.setAttribute('aria-label', `回复，${counts.replies} 条`);
    styleContentTab(postsTab, activeView === 'posts');
    styleContentTab(repliesTab, activeView === 'replies');
    renderResult(root, state, resultHost);
  };
  dayTab.addEventListener('click', () => {
    state.activeMode = 'day';
    refresh();
  });
  sinceTab.addEventListener('click', () => {
    state.activeMode = 'since';
    refresh();
  });
  postsTab.addEventListener('click', () => {
    state.contentView[state.activeMode] = 'posts';
    refresh();
  });
  repliesTab.addEventListener('click', () => {
    state.contentView[state.activeMode] = 'replies';
    refresh();
  });

  profileButton.addEventListener('click', async () => {
    profileButton.disabled = true;
    profileButton.textContent = '正在刷新资料…';
    try {
      const response = await mountedContext.request(
        `/api/v1/x/profiles/resolve?username=${encodeURIComponent(state.username)}&refresh=true`,
        {method: 'POST'},
      );
      state.profile = response.profiles?.[normalizedUser(state.username)] || state.profile;
      mountedContext.notify(`@${state.username} 资料已刷新。`);
    } catch (error) {
      mountedContext.notify(`资料刷新失败：${error.message}`, 'error');
    } finally {
      profileButton.disabled = false;
      profileButton.textContent = '刷新资料';
    }
  });

  const query = async (mode, button) => {
    state.loading = mode;
    button.disabled = true;
    button.textContent = mode === 'day' ? '正在获取该日言论…' : '正在获取该日至今…';
    try {
      const response = await mountedContext.request('/api/v1/x/posts/query', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          username: state.username,
          mode,
          date: state.date,
        }),
      });
      state.results[mode] = response;
      state.activeMode = mode;
      refresh();
      mountedContext.notify(`@${state.username} 查询完成。`);
    } catch (error) {
      mountedContext.notify(`言论查询失败：${error.message}`, 'error');
    } finally {
      state.loading = null;
      button.disabled = false;
      button.textContent = mode === 'day' ? '获取该日言论' : '获取该日至今';
    }
  };
  dayButton.addEventListener('click', () => query('day', dayButton));
  sinceButton.addEventListener('click', () => query('since', sinceButton));

  details.append(summary, controls, tabs, contentTabs, resultHost);
  refresh();
  return details;
}

function render(root, profilesPayload, postsPayload) {
  const profiles = profilesPayload?.profiles || {};
  const cachedUsers = postsPayload?.users || {};
  const keys = new Set([...Object.keys(profiles), ...Object.keys(cachedUsers)]);
  const heading = node(root, 'p', '每个账号的资料、日期、结果和 loading 状态彼此独立。', 'hint');
  const list = node(root, 'div', '', 'x-monitor-users');
  for (const key of keys) {
    const profile = profiles[key] || null;
    const cached = cachedUsers[key] || null;
    const username = profile?.username || cached?.username || key;
    const state = stateFor(username);
    state.profile = profile;
    state.cached = cached;
    list.append(renderUser(root, state));
  }
  if (!keys.size) list.append(node(root, 'p', '尚未配置 X 用户。', 'hint'));
  root.replaceChildren(heading, list);
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== 'function') {
    throw new TypeError('x_monitor 面板缺少受限挂载上下文');
  }
  await unmount();
  mountedRoot = context.root;
  mountedContext = context;
  const [profiles, posts] = await Promise.all([
    context.request('/api/v1/x/profiles'),
    context.request('/api/v1/x/posts'),
  ]);
  if (mountedRoot === context.root) render(context.root, profiles, posts);
}

export async function unmount() {
  if (mountedRoot) mountedRoot.replaceChildren();
  mountedRoot = null;
  mountedContext = null;
  userState.clear();
}
