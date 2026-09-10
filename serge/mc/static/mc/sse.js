// SSE MC : stream + backoff + fallback poll + ?snapshot + visibilité.
const BACKOFF_S = [1, 2, 5, 10, 30];
const POLL_MS = 5000;

export function connectStream({page, onEvent, onStatus}) {
  const params = new URLSearchParams(location.search);
  const state = {closed: false, failures: 0, source: null, timer: null};
  function status(mode) {
    if (onStatus) {
      onStatus(mode);
    }
  }
  async function fetchOnce() {
    const res = await fetch(
      `/owner/api/state?page=${encodeURIComponent(page)}`,
      {cache: 'no-store'},
    );
    if (!res.ok) {
      throw new Error(`state ${res.status}`);
    }
    const data = await res.json();
    for (const [section, env] of Object.entries(data.sections || {})) {
      onEvent({section, sig: env.sig, age_ms: env.age_ms, payload: env.payload});
    }
  }
  function poll() {
    status('poll');
    const tick = () => {
      if (state.closed) {
        return;
      }
      fetchOnce().catch(() => {});
      state.timer = setTimeout(tick, POLL_MS);
    };
    tick();
  }
  function stream() {
    if (state.closed) {
      return;
    }
    status(state.failures === 0 ? 'live' : 'reconnect');
    const source = new EventSource(
      `/owner/api/stream?page=${encodeURIComponent(page)}`,
    );
    state.source = source;
    source.addEventListener('section', (ev) => {
      state.failures = 0;
      const env = JSON.parse(ev.data);
      onEvent({
        section: env.section,
        sig: env.sig,
        age_ms: env.age_ms,
        payload: env.payload,
      });
    });
    source.onerror = () => {
      source.close();
      state.source = null;
      if (state.closed) {
        return;
      }
      if (state.failures >= 3) {
        poll();
        return;
      }
      const wait = BACKOFF_S[Math.min(state.failures, BACKOFF_S.length - 1)];
      state.failures += 1;
      state.timer = setTimeout(stream, wait * 1000);
    };
  }
  function onVisibility() {
    if (document.hidden) {
      if (state.source) {
        state.source.close();
        state.source = null;
      }
      if (state.timer) {
        clearTimeout(state.timer);
        state.timer = null;
      }
    } else if (!state.closed) {
      stream();
    }
  }
  document.addEventListener('visibilitychange', onVisibility);
  if (params.has('snapshot')) {
    status('snapshot');
    fetchOnce().catch(() => status('error'));
  } else {
    stream();
  }
  return {
    close() {
      state.closed = true;
      document.removeEventListener('visibilitychange', onVisibility);
      if (state.source) {
        state.source.close();
      }
      if (state.timer) {
        clearTimeout(state.timer);
      }
    },
  };
}
