function setStatus(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("error", isError);
  element.classList.toggle("ok", !isError && Boolean(message));
}

const authApi = window.bookingAuth || {
  getToken: () => localStorage.getItem("booking_token") || "",
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const isJson = (response.headers.get("content-type") || "").includes("application/json");
  const payload = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const detail = typeof payload === "object" && payload && payload.detail ? payload.detail : payload;
    throw new Error(String(detail || "Request failed"));
  }

  return payload;
}

async function loadMyBookings() {
  const bookingList = document.getElementById("bookings-list");
  const token = authApi.getToken();
  bookingList.innerHTML = "";

  if (!token) {
    const li = document.createElement("li");
    li.textContent = "Login first to view your bookings.";
    bookingList.appendChild(li);
    return;
  }

  try {
    const bookings = await fetchJson("/bookings/me", {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!bookings.length) {
      const li = document.createElement("li");
      li.textContent = "No bookings yet.";
      bookingList.appendChild(li);
      return;
    }

    for (const booking of bookings) {
      const li = document.createElement("li");
      li.textContent = `Booking #${booking.booking_id} | Room ${booking.room_id} | ${booking.start_date} -> ${booking.end_date} | ${booking.status}`;
      bookingList.appendChild(li);
    }
  } catch (error) {
    const li = document.createElement("li");
    li.textContent = `Could not load bookings: ${error.message}`;
    bookingList.appendChild(li);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const urlParams = new URLSearchParams(window.location.search);
  const created = urlParams.get("created");
  if (created) {
    const bookingList = document.getElementById("bookings-list");
    const success = document.createElement("li");
    success.textContent = `Booking #${created} created successfully.`;
    success.classList.add("status", "ok");
    bookingList.appendChild(success);
  }

  document.getElementById("refresh-bookings").addEventListener("click", loadMyBookings);
  document.addEventListener("booking-auth-changed", loadMyBookings);
  await loadMyBookings();
});
