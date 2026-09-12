// Theme so frueh wie moeglich setzen, damit nichts aufblitzt.
// Ausgelagert aus index.html: die CSP (script-src 'self') erlaubt kein
// Inline-Skript ohne Nonce/Hash.
try {
  const t = localStorage.getItem('neu-theme');
  if (t) document.documentElement.dataset.theme = t;
} catch (e) {}
