let mountedRoot = null;

function element(root, role) {
  return root.querySelector(`[data-fitness-role="${role}"]`);
}

function createStat(root, labelText, value) {
  const card = root.ownerDocument.createElement('div');
  const label = root.ownerDocument.createElement('span');
  const detail = root.ownerDocument.createElement('strong');
  card.className = 'stat-chip';
  label.className = 'label';
  label.textContent = labelText;
  detail.textContent = String(value);
  card.append(label, detail);
  return card;
}

function render(root, status) {
  const summary = element(root, 'summary');
  summary.replaceChildren(
    createStat(root, '今日状态', status.checked_today ? '已完成' : '待完成'),
    createStat(root, '连续天数', status.streak ?? 0),
    createStat(root, '累计打卡', status.total_checkins ?? 0),
    createStat(root, '下次奖励', `${status.next_reward_in ?? 0} 天后`),
  );
  element(root, 'status').textContent = status.checked_today
    ? '今天已经完成运动打卡。不错，记得补水和放松。'
    : '今天还没有运动打卡，完成后回来让 Kei 记录。';
  element(root, 'checkin').disabled = Boolean(status.checked_today);
}

function buildPanel(root) {
  const hint = root.ownerDocument.createElement('p');
  const summary = root.ownerDocument.createElement('div');
  const controls = root.ownerDocument.createElement('div');
  const field = root.ownerDocument.createElement('label');
  const note = root.ownerDocument.createElement('input');
  const checkin = root.ownerDocument.createElement('button');
  const status = root.ownerDocument.createElement('div');

  hint.className = 'hint';
  hint.textContent = '记录今天是否完成运动，连续打卡会沿用既有六日奖励规则。';
  summary.className = 'module-grid';
  summary.dataset.fitnessRole = 'summary';
  controls.className = 'schedule-grid';
  field.className = 'field';
  field.style.gridColumn = 'span 2';
  field.append('今日备注（可选）', note);
  note.type = 'text';
  note.maxLength = 500;
  note.placeholder = '例如：跑步 3 公里、拉伸 15 分钟';
  note.dataset.fitnessRole = 'note';
  checkin.type = 'button';
  checkin.textContent = '完成今日运动';
  checkin.dataset.fitnessRole = 'checkin';
  status.className = 'detail hint';
  status.dataset.fitnessRole = 'status';
  controls.append(field, checkin);
  root.dataset.panelSettings = '今日备注|完成今日运动';
  root.replaceChildren(hint, summary, controls, status);
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== 'function') {
    throw new TypeError('fitness 面板缺少受限挂载上下文');
  }
  await unmount();
  const root = context.root;
  mountedRoot = root;
  buildPanel(root);

  const refresh = async () => {
    const status = await context.request('/api/v1/fitness/status');
    if (mountedRoot === root) render(root, status);
    return status;
  };

  element(root, 'checkin').addEventListener('click', async () => {
    const button = element(root, 'checkin');
    const note = element(root, 'note');
    button.disabled = true;
    try {
      const result = await context.request('/api/v1/fitness/checkins', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({note: note.value.trim()}),
      });
      note.value = '';
      if (result.reward_unlocked) {
        context.notify(result.reward_text);
      } else if (result.already_checked_in) {
        context.notify('今天已经记录过了。');
      } else {
        context.notify(`运动打卡完成，当前连续 ${result.streak} 天。`);
      }
      await refresh();
    } catch (error) {
      context.notify(`健身打卡失败：${error.message}`, 'error');
      if (mountedRoot === root) button.disabled = false;
    }
  });

  await refresh();
}

export async function unmount() {
  if (mountedRoot) {
    delete mountedRoot.dataset.panelSettings;
    mountedRoot.replaceChildren();
  }
  mountedRoot = null;
}
