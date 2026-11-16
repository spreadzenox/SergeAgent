// L'essai du captcha (page Système, « Essayer le captcha avec un humain ») :
// le clic d'un humain montre un code à quatre chiffres, que Serge doit
// ensuite lire sur la page. Le code change à chaque clic.
const bouton = document.getElementById('humain');
bouton.addEventListener('click', () => {
  const code = String(1000 + Math.floor(Math.random() * 9000));
  document.getElementById('code').textContent = code;
  document.getElementById('resultat').hidden = false;
  bouton.disabled = true;
});
