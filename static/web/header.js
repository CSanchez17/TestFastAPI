function setHeaderStatus(message, isError = false) {
  const status = document.getElementById("header-login-status");
  if (!status) {
    return;
  }
  status.textContent = message;
  status.classList.toggle("error", isError);
  status.classList.toggle("ok", !isError && Boolean(message));
}

function getToken() {
  return localStorage.getItem("booking_token") || "";
}

function setToken(token) {
  localStorage.setItem("booking_token", token);
}

function clearToken() {
  localStorage.removeItem("booking_token");
}

async function loginWithCredentials(username, password) {
  const body = new URLSearchParams();
  body.append("username", username);
  body.append("password", password);

  const response = await fetch("/auth/jwt/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof data === "object" && data ? data.detail : data;
    throw new Error(detail || "Invalid credentials");
  }

  if (typeof data !== "object" || !data.access_token) {
    throw new Error("Login response did not include an access token");
  }

  setToken(data.access_token);
  return data;
}

function updateAuthUI() {
  const hasToken = Boolean(getToken());
  const loginButton = document.getElementById("header-login-btn");
  const logoutButton = document.getElementById("header-logout-btn");
  const indicator = document.getElementById("auth-indicator");

  if (!loginButton || !logoutButton || !indicator) {
    return;
  }

  if (hasToken) {
    loginButton.classList.add("d-none");
    logoutButton.classList.remove("d-none");
    indicator.className = "badge text-bg-success";
    indicator.textContent = "Logged in";
  } else {
    loginButton.classList.remove("d-none");
    logoutButton.classList.add("d-none");
    indicator.className = "badge text-bg-secondary";
    indicator.textContent = "Logged out";
  }
}

function wireHeaderLogin() {
  const loginForm = document.getElementById("header-login-form");
  const logoutButton = document.getElementById("header-logout-btn");
  const modalElement = document.getElementById("headerLoginModal");

  if (loginForm) {
    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const username = document.getElementById("header-username").value.trim();
      const password = document.getElementById("header-password").value;

      try {
        await loginWithCredentials(username, password);
        setHeaderStatus("Logged in successfully.");
        updateAuthUI();

        if (modalElement && window.bootstrap) {
          const modal = window.bootstrap.Modal.getOrCreateInstance(modalElement);
          modal.hide();
        }

        document.dispatchEvent(new CustomEvent("booking-auth-changed", { detail: { loggedIn: true } }));
      } catch (error) {
        setHeaderStatus(`Login failed: ${error.message}`, true);
      }
    });
  }

  if (logoutButton) {
    logoutButton.addEventListener("click", () => {
      clearToken();
      updateAuthUI();
      setHeaderStatus("");
      document.dispatchEvent(new CustomEvent("booking-auth-changed", { detail: { loggedIn: false } }));
    });
  }
}

window.bookingAuth = {
  getToken,
  setToken,
  clearToken,
  loginWithCredentials,
  updateAuthUI,
};

document.addEventListener("DOMContentLoaded", () => {
  wireHeaderLogin();
  updateAuthUI();
});
