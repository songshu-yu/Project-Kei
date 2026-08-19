export function createModuleRegistry() {
  const entries = new Map();

  function register(moduleId, lifecycle) {
    if (typeof moduleId !== 'string' || !moduleId) throw new TypeError('模块 ID 不能为空');
    if (!lifecycle || typeof lifecycle.mount !== 'function') {
      throw new TypeError(`模块 ${moduleId} 必须导出 mount(context)`);
    }
    entries.set(moduleId, { lifecycle, mounted: false, context: null });
  }

  async function mount(moduleId, context) {
    const entry = entries.get(moduleId);
    if (!entry) throw new Error(`模块 ${moduleId} 尚未注册`);
    if (entry.mounted) return;
    await entry.lifecycle.mount(context);
    entry.context = context;
    entry.mounted = true;
  }

  async function unmount(moduleId) {
    const entry = entries.get(moduleId);
    if (!entry?.mounted) return;
    if (typeof entry.lifecycle.unmount === 'function') {
      await entry.lifecycle.unmount(entry.context);
    }
    entry.mounted = false;
    entry.context = null;
  }

  async function unmountAll() {
    await Promise.allSettled([...entries.keys()].map((moduleId) => unmount(moduleId)));
  }

  async function unregister(moduleId) {
    await unmount(moduleId);
    entries.delete(moduleId);
  }

  return Object.freeze({ register, mount, unmount, unmountAll, unregister });
}
