// État MC par section : applique si sig neuve, skip sinon (contrat C3).
export function createStore() {
  const sections = new Map();
  const listeners = new Map();
  function notify(section, payload, sig) {
    for (const fn of listeners.get(section) || []) {
      fn(payload, sig);
    }
  }
  return {
    apply(section, sig, payload) {
      const current = sections.get(section);
      if (current && current.sig === sig) {
        return 'skipped';
      }
      sections.set(section, {sig, payload});
      notify(section, payload, sig);
      return 'updated';
    },
    subscribe(section, fn) {
      if (!listeners.has(section)) {
        listeners.set(section, []);
      }
      listeners.get(section).push(fn);
      return () => {
        const kept = (listeners.get(section) || []).filter((g) => g !== fn);
        listeners.set(section, kept);
      };
    },
    get(section) {
      return sections.get(section);
    },
    all() {
      return [...sections.entries()];
    },
  };
}
