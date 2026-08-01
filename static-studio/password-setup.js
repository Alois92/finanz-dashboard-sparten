"use strict";

const form = document.getElementById("password-form");
const newPassword = document.getElementById("new-password");
const repeatPassword = document.getElementById("repeat-password");
const submitButton = document.getElementById("submit-button");
const message = document.getElementById("meldung");
const recoveryPanel = document.getElementById("recovery-panel");
const recoveryCode = document.getElementById("recovery-code");
const downloadCode = document.getElementById("download-code");
const copyCode = document.getElementById("copy-code");
const copyStatus = document.getElementById("copy-status");

function errorMessage(error) {
  return error instanceof TypeError
    ? "Der Finanz-Server ist gerade nicht erreichbar."
    : error.message || "Vorgang fehlgeschlagen.";
}

function showRecoveryCode(code) {
  recoveryCode.textContent = code;
  form.hidden = true;
  recoveryPanel.hidden = false;
  recoveryPanel.focus();
}

copyCode.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(recoveryCode.textContent);
    copyStatus.textContent = "Wiederherstellungscode wurde kopiert.";
  } catch (_error) {
    copyStatus.textContent = "Kopieren war nicht moeglich. Bitte markiere den Code manuell.";
  }
});

downloadCode.addEventListener("click", () => {
  const code = recoveryCode.textContent;
  const blob = new Blob(
    [`Hohenegg Finanzstudio – Wiederherstellungscode\n\n${code}\n`],
    {type: "text/plain;charset=utf-8"},
  );
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "Hohenegg-Finanzstudio-Wiederherstellungscode.txt";
  link.click();
  URL.revokeObjectURL(link.href);
});

document.getElementById("print-code").addEventListener("click", () => window.print());

async function checkSetupState() {
  try {
    const response = await fetch("/api/auth/state", {credentials: "same-origin"});
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "Vorgang fehlgeschlagen.");
    if (!body.must_change_password) window.location.replace("/");
  } catch (error) {
    message.textContent = errorMessage(error);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  message.textContent = "";
  try {
    const response = await fetch("/api/auth/initial-password", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      credentials: "same-origin",
      body: JSON.stringify({
        new_password: newPassword.value,
        repeat_password: repeatPassword.value,
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "Vorgang fehlgeschlagen.");
    newPassword.value = "";
    repeatPassword.value = "";
    showRecoveryCode(body.recovery_code);
  } catch (error) {
    message.textContent = errorMessage(error);
  } finally {
    submitButton.disabled = false;
  }
});

checkSetupState();
