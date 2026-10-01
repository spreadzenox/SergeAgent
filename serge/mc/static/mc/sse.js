// SSE MC : stream + backoff + fallback poll + ?snapshot + visibilité.

export async function fetchState(page) {
  const res = await fetch(
    `/owner/api/state?page=${encodeURIComponent(page)}`,
    {cache: 'no-store'},
  );
  if (!res.ok) {
    const error = new Error(`state ${res.status}`);
    error.status = res.status;
    throw error;
  }
  return res.json();
}
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
  function fail(error) {
    if (state.closed) return;
    if (error.status === 401) {
      state.closed = true;
      state.source?.close();
      clearTimeout(state.timer);
      status('auth');
    } else {
      status('error');
    }
  }
  async function fetchOnce() {
    const data = await fetchState(page);
    if (state.closed || document.hidden) return;
    for (const [section, env] of Object.entries(data.sections || {})) {
      onEvent({section, sig: env.sig, age_ms: env.age_ms, payload: env.payload});
    }
  }
  function poll() {
    const tick = () => {
      if (state.closed) {
        return;
      }
      fetchOnce().then(() => {
        if (!state.closed && !document.hidden) status('poll');
      }).catch(fail);
      state.timer = setTimeout(tick, POLL_MS);
    };
    tick();
  }
  function stream() {
    if (state.closed) {
      return;
    }
    status('reconnect');
    const source = new EventSource(
      `/owner/api/stream?page=${encodeURIComponent(page)}`,
    );
    state.source = source;
    source.addEventListener('section', (ev) => {
      if (state.closed || document.hidden) return;
      state.failures = 0;
      status('live');
      const env = JSON.parse(ev.data);
      onEvent({
        section: env.section,
        sig: env.sig,
        age_ms: env.age_ms,
        payload: env.payload,
      });
    });
    source.addEventListener('auth', () => {
      source.close();
      state.closed = true;
      status('auth');
    });
    source.onerror = async () => {
      source.close();
      state.source = null;
      if (state.closed) {
        return;
      }
      status('error');
      // EventSource masque le code HTTP d'un refus à l'ouverture.
      try { await fetchState(page); } catch (error) { fail(error); }
      if (state.closed) return;
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
    if (state.closed) return;
    if (document.hidden) {
      status('paused');
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
    fetchOnce().then(() => {
      if (!state.closed && !document.hidden) status('snapshot');
    }).catch(fail);
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
