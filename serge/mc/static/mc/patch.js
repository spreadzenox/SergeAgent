// Patch DOM par data-sig (C3 : skip si inchangée, compte les mutations).
// SEUL module autorisé à innerHTML (A4) — inutilisé au lot 1b.
export function patchSection(root, section, sig, payload) {
  const node = root.querySelector(`[data-section="${section}"]`);
  if (!node) {
    return 0;
  }
  if (node.dataset.sig === sig) {
    return 0;
  }
  let mutations = 0;
  for (const field of node.querySelectorAll('[data-field]')) {
    const value = field.dataset.field.split('.').reduce(
      (obj, key) => (obj && typeof obj === 'object' ? obj[key] : undefined),
      payload,
    );
    const text = value === undefined || value === null ? '' : String(value);
    if (field.textContent !== text) {
      field.textContent = text;
      mutations += 1;
    }
  }
  node.dataset.sig = sig;
  return mutations;
}
