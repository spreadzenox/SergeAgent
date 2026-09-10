// MC lot 0 : preuve de vie (santé du serveur). Routeur au lot 2.
const target = document.getElementById('health');
try {
  const response = await fetch('/healthz', {cache: 'no-store'});
  const data = await response.json();
  target.textContent =
    data.status === 'ok' ? 'Serveur : en ligne' : 'Serveur : ?';
} catch {
  target.textContent = 'Serveur : injoignable';
}
