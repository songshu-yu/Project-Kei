let mountedRoot = null;
let editingGoalId = '';

const cadenceLabels = {
  daily: '日目标',
  weekly: '周目标',
  monthly: '月目标',
  yearly: '年目标',
};
const streakUnitLabels = {
  day: '天',
  week: '周',
  month: '月',
  year: '年',
};

function node(root, tag, text = '') {
  const value = root.ownerDocument.createElement(tag);
  if (text) value.textContent = text;
  return value;
}

function role(root, name) {
  return root.querySelector(`[data-demon-role="${name}"]`);
}

function field(root, labelText, control, wide = false) {
  const label = node(root, 'label', labelText);
  label.className = 'field';
  if (wide) label.style.gridColumn = 'span 2';
  label.append(control);
  return label;
}

function option(root, value, text) {
  const item = node(root, 'option', text);
  item.value = value;
  return item;
}

function nonNegative(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? Math.trunc(number) : 0;
}

export function formatGoalStatistics(goal) {
  const unit = streakUnitLabels[goal?.streak_unit] || '周期';
  const streak = `当前连续 ${nonNegative(goal?.current_streak)} ${unit} · 历史最长 ${nonNegative(goal?.longest_streak)} ${unit}`;
  if (goal?.repeat_mode === 'once') {
    return `临时目标不累计启用天数 · ${streak}`;
  }
  const activeSince = String(goal?.active_since || '').trim() || '未知';
  const activeDays = goal?.active_days === null
    || goal?.active_days === undefined
    || goal?.active_days === ''
    ? '未知'
    : `${nonNegative(goal.active_days)} 天`;
  return `启用起点 ${activeSince} · 已启用 ${activeDays} · ${streak}`;
}

function buildPanel(root) {
  const intro = node(
    root,
    'p',
    '日/周/月/年目标分别对应小妖、大妖、大大妖和妖王。卸载或删除目标都不会清除历史成绩。',
  );
  intro.className = 'hint';

  const summary = node(root, 'div');
  summary.className = 'module-grid';
  summary.dataset.demonRole = 'summary';

  const form = node(root, 'div');
  form.className = 'schedule-grid';
  const title = node(root, 'textarea');
  title.placeholder = '例如：每天精读一篇论文';
  title.dataset.demonRole = 'title';
  const cadence = node(root, 'select');
  cadence.dataset.demonRole = 'cadence';
  [
    ['auto', '自动判断'],
    ['daily', '日目标 · 小妖'],
    ['weekly', '周目标 · 大妖'],
    ['monthly', '月目标 · 大大妖'],
    ['yearly', '年目标 · 妖王'],
  ].forEach(([value, text]) => cadence.append(option(root, value, text)));
  const category = node(root, 'select');
  category.dataset.demonRole = 'category';
  [
    ['auto', '自动判断'],
    ['study', '学业妖'],
    ['fitness', '虚弱妖'],
    ['focus', '拖延妖'],
    ['life', '混乱妖'],
    ['creative', '枯竭妖'],
    ['general', '迷雾妖'],
  ].forEach(([value, text]) => category.append(option(root, value, text)));
  const repeatMode = node(root, 'select');
  repeatMode.dataset.demonRole = 'repeat-mode';
  repeatMode.append(
    option(root, 'recurring', '周期重复'),
    option(root, 'once', '仅一次 · 临时目标'),
  );
  const targetDate = node(root, 'input');
  targetDate.type = 'date';
  targetDate.disabled = true;
  targetDate.dataset.demonRole = 'target-date';
  const save = node(root, 'button', '登记作战目标');
  save.type = 'button';
  save.dataset.demonRole = 'save';
  const cancel = node(root, 'button', '取消编辑');
  cancel.type = 'button';
  cancel.className = 'secondary';
  cancel.hidden = true;
  cancel.dataset.demonRole = 'cancel';
  form.append(
    field(root, '作战目标（新增时可每行一条）', title, true),
    field(root, '目标周期', cadence),
    field(root, '妖怪种类', category),
    field(root, '执行方式', repeatMode),
    field(root, '临时目标日期', targetDate),
    save,
    cancel,
  );

  const reminder = node(root, 'div');
  reminder.className = 'detail hint';
  reminder.dataset.demonRole = 'reminder';
  const goals = node(root, 'div');
  goals.className = 'goal-list';
  goals.dataset.demonRole = 'goals';

  const reviewControls = node(root, 'div');
  reviewControls.className = 'schedule-grid';
  reviewControls.style.marginTop = '14px';
  const reviewPeriod = node(root, 'select');
  reviewPeriod.dataset.demonRole = 'review-period';
  [
    ['daily', '日总结'],
    ['weekly', '周总结'],
    ['monthly', '月总结'],
    ['yearly', '年总结'],
  ].forEach(([value, text]) => reviewPeriod.append(option(root, value, text)));
  const review = node(root, 'button', '让 Kei 进行复盘');
  review.type = 'button';
  review.className = 'secondary';
  review.dataset.demonRole = 'review';
  reviewControls.append(field(root, '复盘周期', reviewPeriod), review);
  const reviewResult = node(root, 'div', '选择周期后，Kei 会严格按照实际完成与未完成情况进行评价。');
  reviewResult.className = 'demon-review-box';
  reviewResult.dataset.demonRole = 'review-result';

  const rewards = node(root, 'div');
  rewards.className = 'goal-list';
  rewards.dataset.demonRole = 'rewards';
  root.replaceChildren(intro, summary, form, reminder, goals, reviewControls, reviewResult, rewards);
}

function clearEdit(root) {
  editingGoalId = '';
  role(root, 'title').value = '';
  role(root, 'cadence').value = 'auto';
  role(root, 'category').value = 'auto';
  role(root, 'repeat-mode').value = 'recurring';
  role(root, 'target-date').disabled = true;
  role(root, 'target-date').required = false;
  role(root, 'save').textContent = '登记作战目标';
  role(root, 'cancel').hidden = true;
}

function goalCompleted(goal) {
  return Boolean(goal?.completed);
}

function renderSummary(root, status, goals) {
  const rows = [
    ['总积分', status.points ?? 0],
    ['当前周期已击破', `${goals.filter(goalCompleted).length}/${goals.length}`],
    ['小妖 / 日', (status.daily_goals || []).length],
    ['大妖 / 周', (status.weekly_goals || []).length],
    ['大大妖 / 月', (status.monthly_goals || []).length],
    ['妖王 / 年', (status.yearly_goals || []).length],
  ];
  role(root, 'summary').replaceChildren(...rows.map(([label, value]) => {
    const card = node(root, 'div');
    card.className = 'stat-chip';
    const name = node(root, 'span', label);
    name.className = 'label';
    card.append(name, node(root, 'strong', String(value)));
    return card;
  }));
}

function goalCard(root, context, goal, refresh) {
  const card = node(root, 'div');
  card.className = `goal${goalCompleted(goal) ? ' done' : ''}`;
  const detail = node(root, 'div');
  const title = node(root, 'strong', goal.title || '未命名目标');
  const cadence = cadenceLabels[goal.cadence] || goal.cadence || '日目标';
  const repeat = goal.repeat_mode === 'once'
    ? `临时 · ${goal.target_date || goal.target_period || '指定周期'}`
    : '周期重复';
  const facts = node(
    root,
    'div',
    `${goal.rank || '小妖'} · ${goal.demon || '迷雾妖'} · ${cadence} · ${repeat} · ${nonNegative(goal.points)} 积分`,
  );
  facts.className = 'hint';
  const statistics = node(root, 'div', formatGoalStatistics(goal));
  statistics.className = 'hint demon-goal-statistics';
  detail.append(title, facts, statistics);

  const actions = node(root, 'div');
  actions.className = 'goal-actions';
  const checkin = node(root, 'button', goalCompleted(goal) ? '本周期已击破' : '击破');
  checkin.type = 'button';
  checkin.disabled = goalCompleted(goal);
  if (checkin.disabled) checkin.className = 'secondary';
  checkin.addEventListener('click', async () => {
    checkin.disabled = true;
    try {
      const result = await context.request('/api/v1/demon-slayer/checkins', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({goal_id: goal.id, done: true, with_encouragement: false}),
      });
      context.notify(result.message || result.encouragement || '目标已完成。');
      await refresh();
    } catch (error) {
      checkin.disabled = false;
      context.notify(`目标打卡失败：${error.message}`, 'error');
    }
  });

  const edit = node(root, 'button', '编辑');
  edit.type = 'button';
  edit.className = 'secondary';
  edit.addEventListener('click', () => {
    editingGoalId = goal.id;
    role(root, 'title').value = goal.title || '';
    role(root, 'cadence').value = goal.cadence || 'auto';
    role(root, 'category').value = goal.category || 'auto';
    role(root, 'repeat-mode').value = goal.repeat_mode || 'recurring';
    role(root, 'target-date').value = goal.target_date || '';
    role(root, 'target-date').disabled = goal.repeat_mode !== 'once';
    role(root, 'target-date').required = goal.repeat_mode === 'once';
    role(root, 'save').textContent = '保存目标修改';
    role(root, 'cancel').hidden = false;
    role(root, 'title').focus();
  });

  const remove = node(root, 'button', '删除');
  remove.type = 'button';
  remove.className = 'secondary danger';
  remove.addEventListener('click', async () => {
    const confirmed = typeof globalThis.confirm !== 'function'
      || globalThis.confirm(`确定删除目标“${goal.title}”吗？历史打卡、积分与奖励会保留。`);
    if (!confirmed) return;
    remove.disabled = true;
    try {
      const result = await context.request(
        `/api/v1/demon-slayer/goals/${encodeURIComponent(goal.id)}`,
        {method: 'DELETE'},
      );
      if (editingGoalId === goal.id) clearEdit(root);
      context.notify(result.message || '目标已停止追踪，历史记录仍保留。');
      await refresh();
    } catch (error) {
      remove.disabled = false;
      context.notify(`删除目标失败：${error.message}`, 'error');
    }
  });
  actions.append(checkin, edit, remove);
  card.append(detail, actions);
  return card;
}

function renderRewards(root, context, status, refresh) {
  const container = role(root, 'rewards');
  const heading = node(root, 'h3', '奖励');
  const wishes = Array.isArray(status.wishes) ? status.wishes : [];
  if (!wishes.length) {
    container.replaceChildren(heading, node(root, 'div', '暂无可兑换奖励。'));
    return;
  }
  container.replaceChildren(heading, ...wishes.map((wish) => {
    const card = node(root, 'div');
    card.className = 'goal';
    const detail = node(root, 'div');
    detail.append(
      node(root, 'strong', wish.title || '未命名奖励'),
      node(root, 'div', `${nonNegative(wish.cost)} 积分 · ${wish.description || '无说明'}`),
    );
    const redeem = node(root, 'button', '兑换');
    redeem.type = 'button';
    redeem.disabled = Boolean(wish.redeemed) || nonNegative(status.points) < nonNegative(wish.cost);
    redeem.addEventListener('click', async () => {
      redeem.disabled = true;
      try {
        const result = await context.request(
          `/api/v1/demon-slayer/rewards/${encodeURIComponent(wish.id)}/redeem`,
          {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: '{}',
          },
        );
        context.notify(result.message || '奖励已兑换。');
        await refresh();
      } catch (error) {
        redeem.disabled = false;
        context.notify(`兑换失败：${error.message}`, 'error');
      }
    });
    card.append(detail, redeem);
    return card;
  }));
}

function render(root, context, status, refresh) {
  const goals = status.goals || [
    ...(status.daily_goals || []),
    ...(status.weekly_goals || []),
    ...(status.monthly_goals || []),
    ...(status.yearly_goals || []),
  ];
  renderSummary(root, status, goals);
  role(root, 'reminder').textContent = status.reminder || '';
  if (!role(root, 'target-date').value) role(root, 'target-date').value = status.date || '';
  const goalContainer = role(root, 'goals');
  goalContainer.replaceChildren(...(
    goals.length
      ? goals.map(goal => goalCard(root, context, goal, refresh))
      : [node(root, 'div', '还没有作战目标。选择周期、执行方式和妖怪种类后登记一条吧。')]
  ));
  renderRewards(root, context, status, refresh);
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== 'function') {
    throw new TypeError('斩妖除魔面板缺少受限挂载上下文');
  }
  await unmount();
  const root = context.root;
  mountedRoot = root;
  buildPanel(root);

  const refresh = async () => {
    const status = await context.request('/api/v1/demon-slayer/status');
    if (mountedRoot === root) render(root, context, status, refresh);
  };

  role(root, 'repeat-mode').addEventListener('change', () => {
    const once = role(root, 'repeat-mode').value === 'once';
    role(root, 'target-date').disabled = !once;
    role(root, 'target-date').required = once;
  });
  role(root, 'cancel').addEventListener('click', () => clearEdit(root));
  role(root, 'save').addEventListener('click', async () => {
    const titles = role(root, 'title').value
      .split(/[\n;；]+/)
      .map(value => value.trim())
      .filter(Boolean);
    const repeatMode = role(root, 'repeat-mode').value;
    const targetDate = role(root, 'target-date').value;
    if (!titles.length) {
      context.notify('请至少填写一条作战目标。', 'error');
      return;
    }
    if (editingGoalId && titles.length !== 1) {
      context.notify('编辑时一次只能修改一条目标。', 'error');
      return;
    }
    if (repeatMode === 'once' && !targetDate) {
      context.notify('请为临时目标选择生效日期。', 'error');
      return;
    }
    const button = role(root, 'save');
    button.disabled = true;
    const payload = {
      cadence: role(root, 'cadence').value,
      category: role(root, 'category').value,
      repeat_mode: repeatMode,
      target_date: repeatMode === 'once' ? targetDate : null,
    };
    try {
      if (editingGoalId) {
        await context.request(
          `/api/v1/demon-slayer/goals/${encodeURIComponent(editingGoalId)}`,
          {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({...payload, title: titles[0]}),
          },
        );
        context.notify('目标已更新。');
      } else {
        for (const title of titles) {
          await context.request('/api/v1/demon-slayer/goals', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({...payload, title}),
          });
        }
        context.notify(`已登记 ${titles.length} 条作战目标。`);
      }
      clearEdit(root);
      await refresh();
    } catch (error) {
      context.notify(`保存目标失败：${error.message}`, 'error');
    } finally {
      button.disabled = false;
    }
  });
  role(root, 'review').addEventListener('click', async () => {
    const button = role(root, 'review');
    const period = role(root, 'review-period').value;
    button.disabled = true;
    button.textContent = 'Kei 正在复盘…';
    try {
      const result = await context.request(`/api/v1/demon-slayer/reviews/${period}`);
      const source = result.kei_generated ? 'Kei 实情评价' : '本地规则评价（生成能力暂不可用）';
      const facts = `实际完成 ${nonNegative(result.completed)}/${nonNegative(result.total)}`;
      const missed = Array.isArray(result.missed) && result.missed.length
        ? `\n未完成：${result.missed.join('、')}`
        : '';
      role(root, 'review-result').textContent = `${source}\n${result.message || '暂无复盘内容。'}\n${facts}${missed}`;
      context.notify('复盘已更新。');
      await refresh();
    } catch (error) {
      context.notify(`读取复盘失败：${error.message}`, 'error');
    } finally {
      button.disabled = false;
      button.textContent = '让 Kei 进行复盘';
    }
  });

  await refresh();
}

export async function unmount() {
  editingGoalId = '';
  if (mountedRoot) mountedRoot.replaceChildren();
  mountedRoot = null;
}
