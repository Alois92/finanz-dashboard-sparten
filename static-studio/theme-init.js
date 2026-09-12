// Theme so frueh wie moeglich setzen, damit nichts aufblitzt.
// Ausgelagert aus index.html: die CSP (script-src 'self') erlaubt kein
// Inline-Skript ohne Nonce/Hash.
(function () {
  try {
    var t = localStorage.getItem("studio-theme");
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
  } catch (e) {}
})();
