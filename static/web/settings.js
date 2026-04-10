/* ── Settings page logic ─────────────────────────────────────────────── */

function getToken() {
  return localStorage.getItem("booking_token") || "";
}

async function loadSettings() {
  const token = getToken();
  const loginAlert = document.getElementById("settings-login-alert");
  const panel = document.getElementById("settings-panel");

  if (!token) {
    loginAlert.classList.remove("d-none");
    panel.classList.add("d-none");
    return;
  }

  loginAlert.classList.add("d-none");
  panel.classList.remove("d-none");

  try {
    const response = await fetch("/users/me/settings", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("Failed to load settings");
    const data = await response.json();

    document.getElementById("setting-premium-i18n").checked = data.premium_i18n;

    // Persist locally so the concierge can send it without an extra API call
    localStorage.setItem("premium_i18n", data.premium_i18n ? "true" : "false");
  } catch (err) {
    setSettingsStatus("Could not load settings: " + err.message, true);
  }
}

async function saveSettings() {
  const token = getToken();
  if (!token) return;

  const premiumI18n = document.getElementById("setting-premium-i18n").checked;

  try {
    const response = await fetch("/users/me/settings", {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ premium_i18n: premiumI18n }),
    });
    if (!response.ok) throw new Error("Failed to save settings");
    const data = await response.json();

    // Update local cache
    localStorage.setItem("premium_i18n", data.premium_i18n ? "true" : "false");
    setSettingsStatus(t("settingsSaved"), false);
  } catch (err) {
    setSettingsStatus("Error: " + err.message, true);
  }
}

function setSettingsStatus(message, isError = false) {
  const el = document.getElementById("settings-status");
  if (!el) return;
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.classList.toggle("ok", !isError && Boolean(message));
}

document.addEventListener("DOMContentLoaded", () => {
  loadSettings();

  const saveBtn = document.getElementById("settings-save");
  if (saveBtn) saveBtn.addEventListener("click", saveSettings);

  // Reload settings when user logs in/out
  document.addEventListener("booking-auth-changed", () => loadSettings());
});
