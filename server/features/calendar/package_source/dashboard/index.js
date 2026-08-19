let mountedRoot = null;

function element(root, role) {
  return root.querySelector(`[data-calendar-role="${role}"]`);
}

function createField(root, labelText, control) {
  const label = root.ownerDocument.createElement('label');
  label.className = 'field';
  label.append(labelText, control);
  return label;
}

function renderStatus(root, status) {
  const summary = element(root, 'summary');
  const rows = [
    ['日期', `${status.date} ${status.weekday}`],
    ['备忘', `${status.events_count} 条`],
    ['技能', `${status.skills_count} 项`],
  ];
  summary.replaceChildren(...rows.map(([label, value]) => {
    const card = root.ownerDocument.createElement('div');
    const name = root.ownerDocument.createElement('span');
    const detail = root.ownerDocument.createElement('strong');
    card.className = 'stat-chip';
    name.className = 'label';
    name.textContent = label;
    detail.textContent = value;
    card.append(name, detail);
    return card;
  }));

  const events = element(root, 'events');
  const eventItems = status.today.today_events.map((item) => {
    const row = root.ownerDocument.createElement('li');
    row.textContent = item.note ? `${item.title} — ${item.note}` : item.title;
    return row;
  });
  events.replaceChildren(...eventItems);
  if (!eventItems.length) {
    const row = root.ownerDocument.createElement('li');
    row.textContent = '当天没有备忘。';
    events.append(row);
  }

  const skills = element(root, 'skills');
  skills.replaceChildren(...status.skills.slice(0, 8).map((item) => {
    const row = root.ownerDocument.createElement('li');
    row.textContent = `${item.name}：${item.total_hours} 小时 · ${item.level.name}`;
    return row;
  }));
  if (!status.skills.length) {
    const row = root.ownerDocument.createElement('li');
    row.textContent = '还没有修炼记录。';
    skills.append(row);
  }
  element(root, 'message').textContent = status.today.message || '';
}

function buildPanel(root) {
  const dateInput = root.ownerDocument.createElement('input');
  const refresh = root.ownerDocument.createElement('button');
  const summary = root.ownerDocument.createElement('div');
  const message = root.ownerDocument.createElement('pre');
  const eventsHeading = root.ownerDocument.createElement('h4');
  const events = root.ownerDocument.createElement('ul');
  const skillsHeading = root.ownerDocument.createElement('h4');
  const skills = root.ownerDocument.createElement('ul');
  const eventForm = root.ownerDocument.createElement('form');
  const eventTitle = root.ownerDocument.createElement('input');
  const eventRepeat = root.ownerDocument.createElement('select');
  const eventNote = root.ownerDocument.createElement('input');
  const eventSubmit = root.ownerDocument.createElement('button');
  const practiceForm = root.ownerDocument.createElement('form');
  const practiceSkill = root.ownerDocument.createElement('input');
  const practiceHours = root.ownerDocument.createElement('input');
  const practiceNote = root.ownerDocument.createElement('input');
  const practiceSubmit = root.ownerDocument.createElement('button');

  dateInput.type = 'date';
  dateInput.dataset.calendarRole = 'date';
  refresh.type = 'button';
  refresh.textContent = '查看';
  refresh.dataset.calendarRole = 'refresh';
  summary.className = 'module-grid';
  summary.dataset.calendarRole = 'summary';
  message.className = 'detail';
  message.dataset.calendarRole = 'message';
  eventsHeading.textContent = '当天备忘';
  events.dataset.calendarRole = 'events';
  skillsHeading.textContent = '修炼进度';
  skills.dataset.calendarRole = 'skills';

  eventForm.className = 'schedule-grid';
  eventForm.dataset.calendarRole = 'event-form';
  eventTitle.type = 'text';
  eventTitle.required = true;
  eventTitle.placeholder = '备忘标题';
  eventTitle.dataset.calendarRole = 'event-title';
  [['none', '不重复'], ['yearly', '每年重复']].forEach(([value, text]) => {
    const option = root.ownerDocument.createElement('option');
    option.value = value;
    option.textContent = text;
    eventRepeat.append(option);
  });
  eventRepeat.dataset.calendarRole = 'event-repeat';
  eventNote.type = 'text';
  eventNote.placeholder = '备注（可选）';
  eventNote.dataset.calendarRole = 'event-note';
  eventSubmit.type = 'submit';
  eventSubmit.textContent = '添加备忘';
  eventForm.append(
    createField(root, '标题', eventTitle),
    createField(root, '重复', eventRepeat),
    createField(root, '备注', eventNote),
    eventSubmit,
  );

  practiceForm.className = 'schedule-grid';
  practiceForm.dataset.calendarRole = 'practice-form';
  practiceSkill.type = 'text';
  practiceSkill.required = true;
  practiceSkill.placeholder = '技能名称';
  practiceSkill.dataset.calendarRole = 'practice-skill';
  practiceHours.type = 'number';
  practiceHours.required = true;
  practiceHours.min = '0.01';
  practiceHours.step = '0.01';
  practiceHours.placeholder = '小时';
  practiceHours.dataset.calendarRole = 'practice-hours';
  practiceNote.type = 'text';
  practiceNote.placeholder = '备注（可选）';
  practiceNote.dataset.calendarRole = 'practice-note';
  practiceSubmit.type = 'submit';
  practiceSubmit.textContent = '记录修炼';
  practiceForm.append(
    createField(root, '技能', practiceSkill),
    createField(root, '小时', practiceHours),
    createField(root, '备注', practiceNote),
    practiceSubmit,
  );

  root.replaceChildren(
    createField(root, '日期', dateInput),
    refresh,
    summary,
    message,
    eventsHeading,
    events,
    skillsHeading,
    skills,
    eventForm,
    practiceForm,
  );
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== 'function') {
    throw new TypeError('calendar 面板缺少受限挂载上下文');
  }
  await unmount();
  const root = context.root;
  mountedRoot = root;
  buildPanel(root);

  const selectedDate = () => element(root, 'date').value;
  const refresh = async () => {
    const query = selectedDate() ? `?date=${encodeURIComponent(selectedDate())}` : '';
    const status = await context.request(`/api/v1/calendar/status${query}`);
    if (mountedRoot === root) {
      element(root, 'date').value = status.date;
      renderStatus(root, status);
    }
  };

  element(root, 'refresh').addEventListener('click', async () => {
    try {
      await refresh();
    } catch (error) {
      context.notify(`读取日历失败：${error.message}`, 'error');
    }
  });
  element(root, 'event-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await context.request('/api/v1/calendar/events', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          title: element(root, 'event-title').value.trim(),
          date: selectedDate(),
          repeat: element(root, 'event-repeat').value,
          note: element(root, 'event-note').value.trim(),
          tags: [],
        }),
      });
      element(root, 'event-title').value = '';
      element(root, 'event-note').value = '';
      context.notify('备忘已保存。');
      await refresh();
    } catch (error) {
      context.notify(`保存备忘失败：${error.message}`, 'error');
    }
  });
  element(root, 'practice-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await context.request('/api/v1/calendar/practice', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          skill: element(root, 'practice-skill').value.trim(),
          hours: Number(element(root, 'practice-hours').value),
          date: selectedDate(),
          note: element(root, 'practice-note').value.trim(),
        }),
      });
      element(root, 'practice-hours').value = '';
      element(root, 'practice-note').value = '';
      context.notify('修炼记录已保存。');
      await refresh();
    } catch (error) {
      context.notify(`保存修炼记录失败：${error.message}`, 'error');
    }
  });
  await refresh();
}

export async function unmount() {
  if (mountedRoot) {
    mountedRoot.replaceChildren();
  }
  mountedRoot = null;
}
