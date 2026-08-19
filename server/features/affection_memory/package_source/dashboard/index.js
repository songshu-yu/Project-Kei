const RELATIONSHIP_API = "/api/v1/relationship";
const MEMORIES_API = "/api/v1/memories";

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function mount(context) {
  if (!context?.root || typeof context.request !== "function") {
    throw new TypeError("好感度与长期记忆面板缺少受限挂载上下文");
  }
  const root = context.root;
  const requestJson = (url, options = {}) =>
    context.request(url, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
  root.replaceChildren();
  const panels = element("div", "affection-memory-panels module-owned-panels");
  const relationshipPanel = element("section", "section affection-panel");
  relationshipPanel.dataset.panelId = "module-affection";
  relationshipPanel.dataset.panelSummary = "查看好感度、信任、心情与精力，并显式触发一次互动";
  relationshipPanel.dataset.panelAvatar = "/dashboard/static/default-avatars/affection.png";
  relationshipPanel.dataset.panelAvatarAlt = "好感度系统组件插图";
  relationshipPanel.append(
    element("h2", "", "好感度系统"),
    element("p", "hint", relationshipPanel.dataset.panelSummary),
  );
  const relationshipBody = element("div", "module-feature-body");
  const relationship = element("p", "panel-summary", "正在读取关系状态…");
  const eventBox = element("div", "panel-actions");
  const refreshButton = element("button", "ghost", "刷新");
  const eventButton = element("button", "", "触发互动");
  const memoryList = element("ul", "memory-list");
  const memoryPanel = element("section", "section memory-panel");
  memoryPanel.dataset.panelId = "module-long-term-memory";
  memoryPanel.dataset.panelSummary = "查看、添加和删除长期记忆；关系状态与记忆存储保持独立";
  memoryPanel.dataset.panelAvatar = "/dashboard/static/default-avatars/memory.png";
  memoryPanel.dataset.panelAvatarAlt = "长期记忆组件插图";
  memoryPanel.append(
    element("h2", "", "长期记忆"),
    element("p", "hint", memoryPanel.dataset.panelSummary),
  );
  const memoryBody = element("div", "module-feature-body");
  const form = element("form", "panel-actions");
  const input = element("input");
  input.type = "text";
  input.maxLength = 500;
  input.placeholder = "添加一条长期记忆";
  const addButton = element("button", "", "保存");
  addButton.type = "submit";
  form.append(input, addButton);
  eventBox.append(refreshButton, eventButton);
  relationshipBody.append(relationship, eventBox);
  relationshipPanel.append(relationshipBody);
  memoryBody.append(form, memoryList);
  memoryPanel.append(memoryBody);
  panels.append(relationshipPanel, memoryPanel);
  root.append(panels);

  let disposed = false;

  const notifyError = (error) => {
    context.notify?.(error instanceof Error ? error.message : "操作失败", "error");
  };

  const loadRelationship = async () => {
    const status = await requestJson(`${RELATIONSHIP_API}/status`);
    if (disposed) return;
    const stats = status.stats || status;
    relationship.textContent =
      `好感度 ${stats.affection ?? "—"} · 信任 ${stats.trust ?? "—"} · ` +
      `心情 ${stats.mood ?? "—"} · 精力 ${stats.energy ?? "—"}`;
  };

  const renderMemories = async () => {
    const payload = await requestJson(MEMORIES_API);
    if (disposed) return;
    memoryList.replaceChildren();
    const memories = Array.isArray(payload.memories) ? payload.memories : [];
    if (!memories.length) {
      memoryList.append(element("li", "muted", "还没有长期记忆"));
      return;
    }
    for (const memory of memories) {
      const item = element("li", "memory-row");
      const content = element("span", "", memory.content || "");
      const remove = element("button", "ghost", "删除");
      remove.type = "button";
      remove.addEventListener("click", async () => {
        try {
          await requestJson(`${MEMORIES_API}/${encodeURIComponent(memory.id)}`, {
            method: "DELETE",
          });
          await renderMemories();
        } catch (error) {
          notifyError(error);
        }
      });
      item.append(content, remove);
      memoryList.append(item);
    }
  };

  refreshButton.addEventListener("click", () => {
    Promise.all([loadRelationship(), renderMemories()]).catch(notifyError);
  });

  eventButton.addEventListener("click", async () => {
    try {
      const event = await requestJson(`${RELATIONSHIP_API}/events`, {
        method: "POST",
        body: JSON.stringify({ context: "dashboard", force_event: false }),
      });
      if (!event.triggered) {
        context.notify?.("这次没有触发互动", "info");
        return;
      }
      const choices = event.event?.choices || [];
      const choice = choices[0];
      if (choice?.id) {
        await requestJson(`${RELATIONSHIP_API}/choices`, {
          method: "POST",
          body: JSON.stringify({ choice_id: choice.id, with_audio: false }),
        });
      }
      await loadRelationship();
    } catch (error) {
      notifyError(error);
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const content = input.value.trim();
    if (!content) return;
    addButton.disabled = true;
    try {
      await requestJson(MEMORIES_API, {
        method: "POST",
        body: JSON.stringify({
          content,
          tags: ["dashboard"],
          source: "api",
          request_id: globalThis.crypto?.randomUUID?.() || `${Date.now()}`,
        }),
      });
      input.value = "";
      await renderMemories();
    } catch (error) {
      notifyError(error);
    } finally {
      addButton.disabled = false;
    }
  });

  Promise.all([loadRelationship(), renderMemories()]).catch(notifyError);

  return () => {
    disposed = true;
    root.replaceChildren();
  };
}

export function unmount(context) {
  context.root?.replaceChildren();
}
