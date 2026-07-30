"use strict";

const formular = document.getElementById("login-form");
const passwort = document.getElementById("password");
const button = document.getElementById("login-button");
const meldung = document.getElementById("meldung");

formular.addEventListener("submit", async (event) => {
  event.preventDefault();
  button.disabled = true;
  meldung.textContent = "";
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      credentials: "same-origin",
      body: JSON.stringify({password: passwort.value}),
    });
    passwort.value = "";
    if (response.status === 204) {
      window.location.replace("/");
      return;
    }
    const body = await response.json().catch(() => ({}));
    meldung.textContent = body.detail || "Anmeldung nicht möglich.";
  } catch (_) {
    meldung.textContent = "Der Finanz-Server ist gerade nicht erreichbar.";
  } finally {
    button.disabled = false;
    passwort.focus();
  }
});
