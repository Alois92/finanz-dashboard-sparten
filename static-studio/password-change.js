"use strict";

const form = document.getElementById("password-form");
const currentPassword = document.getElementById("current-password");
const newPassword = document.getElementById("new-password");
const repeatPassword = document.getElementById("repeat-password");
const submitButton = document.getElementById("submit-button");
const message = document.getElementById("meldung");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  message.textContent = "";
  try {
    const response = await fetch("/api/auth/change-password", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      credentials: "same-origin",
      body: JSON.stringify({
        current_password: currentPassword.value,
        new_password: newPassword.value,
        repeat_password: repeatPassword.value,
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "Vorgang fehlgeschlagen.");
    currentPassword.value = "";
    newPassword.value = "";
    repeatPassword.value = "";
    window.location.replace("/login.html");
  } catch (error) {
    message.textContent = error.message || "Der Finanz-Server ist gerade nicht erreichbar.";
  } finally {
    submitButton.disabled = false;
  }
});
