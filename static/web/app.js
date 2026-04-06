function setStatus(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("error", isError);
  element.classList.toggle("ok", !isError && Boolean(message));
}

const authApi = window.bookingAuth || {
  getToken: () => localStorage.getItem("booking_token") || "",
};

let selectedRoomId = null;
let selectedRoomTitle = "";

function getToken() {
  return localStorage.getItem("booking_token") || "";
}

function closeBookingModal() {
  const modal = document.getElementById("booking-modal");
  if (!modal) {
    return;
  }
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
}

function openBookingModal() {
  const modal = document.getElementById("booking-modal");
  if (!modal) {
    return;
  }
  setDefaultBookingDates();
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
}

function formatDate(date) {
  return date.toISOString().split("T")[0];
}

function setDefaultBookingDates() {
  const startInput = document.getElementById("start-date");
  const endInput = document.getElementById("end-date");
  if (!startInput || !endInput) {
    return;
  }

  const today = new Date();
  const endDate = new Date(today);
  endDate.setDate(today.getDate() + 2);

  startInput.value = formatDate(today);
  endInput.value = formatDate(endDate);
}

function setSelectedRoom(room, selectedCard) {
  const roomId = room.id ?? room.room_id;
  if (!roomId) {
    setStatus(document.getElementById("booking-status"), "Could not select this room. Reload and try again.", true);
    return;
  }

  selectedRoomId = roomId;
  selectedRoomTitle = room.title;
  document.getElementById("room-id").value = String(roomId);
  document.getElementById("selected-room").value = `${room.title} (ID ${roomId})`;

  document.querySelectorAll(".room-card").forEach((card) => card.classList.remove("selected"));
  if (selectedCard) {
    selectedCard.classList.add("selected");
  }

  setStatus(document.getElementById("booking-status"), "");
  openBookingModal();
}

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

async function parseResponsePayload(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return await response.json();
  }
  return await response.text();
}

async function loadRooms() {
  const roomsGrid = document.getElementById("rooms-grid");
  roomsGrid.innerHTML = "Loading rooms...";
  try {
    const rooms = await fetchJson("/rooms");
    if (!rooms.length) {
      roomsGrid.innerHTML = "No available rooms found.";
      return;
    }

    roomsGrid.innerHTML = "";
    for (const room of rooms) {
      const roomId = room.id ?? room.room_id;
      const card = document.createElement("article");
      card.className = "room-card";
      card.innerHTML = `
        <h3>${room.title}</h3>
        <p>${room.description || "No description"}</p>
        <p class="room-meta">ID: ${roomId} | ${room.price_per_night} EUR/night</p>
        <p class="room-meta">${room.location.address_line}, ${room.location.city}, ${room.location.country}</p>
      `;

      const quickBook = document.createElement("button");
      quickBook.type = "button";
      quickBook.className = "quick-book";
      quickBook.textContent = "Use this room in booking form";
      quickBook.addEventListener("click", () => {
        setSelectedRoom(room, card);
        window.scrollTo({ top: document.getElementById("booking-form").offsetTop - 40, behavior: "smooth" });
      });

      card.appendChild(quickBook);
      roomsGrid.appendChild(card);
    }
  } catch (error) {
    roomsGrid.innerHTML = "Could not load rooms.";
  }
}

function wireBooking() {
  const bookingForm = document.getElementById("booking-form");
  const bookingStatus = document.getElementById("booking-status");

  bookingForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedRoomId) {
      setStatus(bookingStatus, "Choose a room first using 'Use this room in booking form'.", true);
      return;
    }

    let token = authApi.getToken();
    if (!token) {
      setStatus(bookingStatus, "Login first from the top header button.", true);
      return;
    }

    const payload = {
      room_id: Number(selectedRoomId),
      start_date: document.getElementById("start-date").value,
      end_date: document.getElementById("end-date").value,
    };

    try {
      const booking = await fetchJson("/bookings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });

      const bookingId = booking.id ?? booking.booking_id;
      setStatus(bookingStatus, `Booking created with id ${bookingId}`);
      window.location.href = `/my-bookings?created=${bookingId}`;
    } catch (error) {
      setStatus(bookingStatus, `Booking failed: ${error.message}`, true);
    }
  });
}

function wireModalControls() {
  document.getElementById("booking-modal-close").addEventListener("click", closeBookingModal);
  document.getElementById("booking-close-button").addEventListener("click", closeBookingModal);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeBookingModal();
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  wireBooking();
  wireModalControls();

  document.getElementById("refresh-rooms").addEventListener("click", loadRooms);

  await loadRooms();
});
