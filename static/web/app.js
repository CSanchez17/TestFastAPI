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
let latestRooms = [];
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
    let errorMessage = "Request failed";
    if (isJson && payload && payload.detail) {
      if (Array.isArray(payload.detail)) {
        errorMessage = payload.detail.map(err => err.msg || err.message || JSON.stringify(err)).join("; ");
      } else if (typeof payload.detail === "string") {
        errorMessage = payload.detail;
      } else {
        errorMessage = JSON.stringify(payload.detail);
      }
    } else if (typeof payload === "string") {
      errorMessage = payload;
    }
    throw new Error(errorMessage);
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
  roomsGrid.innerHTML = t("loading");
  try {
    const citySelect = document.getElementById("room-city-filter");
    const countrySelect = document.getElementById("room-country-filter");
    const minPriceInput = document.getElementById("room-min-price");
    const maxPriceInput = document.getElementById("room-max-price");
    const availableInput = document.getElementById("room-available-filter");
    const params = new URLSearchParams();

    if (citySelect && citySelect.value) {
      params.set("city", citySelect.value);
    }
    if (countrySelect && countrySelect.value) {
      params.set("country", countrySelect.value);
    }
    if (minPriceInput && minPriceInput.value.trim()) {
      params.set("min_price", minPriceInput.value.trim());
    }
    if (maxPriceInput && maxPriceInput.value.trim()) {
      params.set("max_price", maxPriceInput.value.trim());
    }
    if (availableInput) {
      params.set("available", availableInput.checked.toString());
    }

    const url = `/rooms${params.toString() ? `?${params.toString()}` : ""}`;
    const rooms = await fetchJson(url);
    latestRooms = rooms;
    if (!rooms.length) {
      roomsGrid.innerHTML = t("noRooms");
      return;
    }

    roomsGrid.innerHTML = "";
    for (const room of rooms) {
      const roomId = room.id ?? room.room_id;
      const card = document.createElement("article");
      card.className = "room-card";
      card.innerHTML = `
        <h3>${room.title}</h3>
        <p>${room.description || t("noDesc")}</p>
        <p class="room-meta">ID: ${roomId} | ${room.price_per_night} EUR/night</p>
        <p class="room-meta">${room.location.address_line}, ${room.location.city}, ${room.location.country}</p>
      `;

      const quickBook = document.createElement("button");
      quickBook.type = "button";
      quickBook.className = "quick-book";
      quickBook.textContent = t("useRoom");
      quickBook.addEventListener("click", () => {
        setSelectedRoom(room, card);
        window.scrollTo({ top: document.getElementById("booking-form").offsetTop - 40, behavior: "smooth" });
      });

      card.appendChild(quickBook);
      roomsGrid.appendChild(card);
    }
  } catch (error) {
    roomsGrid.innerHTML = t("loadError");
  }
}

function appendChatBubble(text, role = "assistant") {
  const chat = document.getElementById("concierge-chat");
  if (!chat) {
    return null;
  }

  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}`;
  bubble.textContent = text;
  chat.appendChild(bubble);
  chat.scrollTop = chat.scrollHeight;
  return bubble;
}

function renderConciergeRecommendations(payload) {
  const chat = document.getElementById("concierge-chat");
  if (!chat) {
    return;
  }

  const lang = payload.detected_language || browserLang;

  if (!payload.recommendations || payload.recommendations.length === 0) {
    appendChatBubble(tLang("noMatch", lang), "assistant");
    return;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "chat-recommendations";

  payload.recommendations.forEach((item) => {
    const card = document.createElement("article");
    card.className = "chat-rec-card";
    card.innerHTML = `
      <h3>${item.title}</h3>
      <p>${item.city}, ${item.country} | ${item.price_per_night} EUR/night</p>
      <p class="chat-reason">${item.description}</p>
    `;

    const action = document.createElement("button");
    action.type = "button";
    action.className = "quick-book";
    action.textContent = tLang("bookThis", lang);
    action.addEventListener("click", () => {
      const room = latestRooms.find((r) => (r.id ?? r.room_id) === item.room_id);
      if (!room) {
        appendChatBubble(tLang("notAvailable", lang), "assistant");
        loadRooms();
        return;
      }
      setSelectedRoom(room, null);
    });

    card.appendChild(action);
    wrapper.appendChild(card);
  });

  chat.appendChild(wrapper);

  // ── Render suggested follow-up queries as clickable chips ──
  if (payload.suggested_queries && payload.suggested_queries.length > 0) {
    const suggestionsWrapper = document.createElement("div");
    suggestionsWrapper.className = "chat-suggestions";

    const label = document.createElement("span");
    label.className = "chat-suggestions-label";
    label.textContent = tLang("tryAsking", lang);
    suggestionsWrapper.appendChild(label);

    payload.suggested_queries.forEach((suggestion) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "suggestion-chip";
      chip.textContent = suggestion;
      chip.addEventListener("click", () => {
        const input = document.getElementById("concierge-input");
        const form = document.getElementById("concierge-form");
        if (input && form) {
          input.value = suggestion;
          form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
        }
      });
      suggestionsWrapper.appendChild(chip);
    });

    chat.appendChild(suggestionsWrapper);
  }

  chat.scrollTop = chat.scrollHeight;
}

function wireConciergeChat() {
  const form = document.getElementById("concierge-form");
  const input = document.getElementById("concierge-input");
  const send = document.getElementById("concierge-send");

  if (!form || !input || !send) {
    return;
  }

  appendChatBubble(t("greeting"), "assistant");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = input.value.trim();
    if (!query) {
      return;
    }
    if (query.length < 5) {
      appendChatBubble(t("tooShort"), "assistant");
      return;
    }

    appendChatBubble(query, "user");
    input.value = "";
    send.disabled = true;
    const thinking = appendChatBubble(t("thinking"), "assistant");
    if (thinking) thinking.classList.add("thinking");

    // Remove previous suggestions on new query
    document.querySelectorAll(".chat-suggestions").forEach(el => el.remove());

    try {
      const payload = await fetchJson("/ai/concierge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          max_results: 3,
          language: browserLang,
          premium_i18n: localStorage.getItem("premium_i18n") === "true",
        }),
      });

      if (thinking) {
        thinking.remove();
      }
      appendChatBubble(payload.assistant_message || t("foundOptions"), "assistant");
      renderConciergeRecommendations(payload);
    } catch (error) {
      if (thinking) {
        thinking.remove();
      }
      const errorMsg = error.message.includes("at least 5 characters")
        ? t("tooShort")
        : `${t("errorPrefix")}${error.message}`;
      appendChatBubble(errorMsg, "assistant");
    } finally {
      send.disabled = false;
    }
  });
}

async function loadRoomFilters(country = "") {
  try {
    const url = country ? `/rooms/filters?country=${encodeURIComponent(country)}` : "/rooms/filters";
    const filters = await fetchJson(url);
    const citySelect = document.getElementById("room-city-filter");
    const countrySelect = document.getElementById("room-country-filter");
    const minPriceInput = document.getElementById("room-min-price");
    const maxPriceInput = document.getElementById("room-max-price");

    if (countrySelect && filters.countries) {
      const selectedCountry = countrySelect.value;
      countrySelect.innerHTML = `<option value="">${t("allCountries")}</option>`;
      filters.countries.forEach((countryOption) => {
        const option = document.createElement("option");
        option.value = countryOption;
        option.textContent = countryOption;
        if (countryOption === selectedCountry) option.selected = true;
        countrySelect.appendChild(option);
      });
    }

    if (citySelect) {
      const selectedCity = citySelect.value;
      citySelect.innerHTML = `<option value="">${t("allCities")}</option>`;
      if (filters.cities && filters.cities.length > 0) {
        filters.cities.forEach((city) => {
          const option = document.createElement("option");
          option.value = city;
          option.textContent = city;
          if (city === selectedCity) option.selected = true;
          citySelect.appendChild(option);
        });
        citySelect.disabled = !country;
      } else {
        citySelect.disabled = true;
      }
    }

    // Update price range inputs
    if (minPriceInput && maxPriceInput && filters.price_range) {
      minPriceInput.min = filters.price_range.min;
      minPriceInput.max = filters.price_range.max;
      minPriceInput.placeholder = filters.price_range.min;
      maxPriceInput.min = filters.price_range.min;
      maxPriceInput.max = filters.price_range.max;
      maxPriceInput.placeholder = filters.price_range.max;

      // Clear current values if they are out of range
      if (minPriceInput.value && parseFloat(minPriceInput.value) < filters.price_range.min) {
        minPriceInput.value = "";
      }
      if (maxPriceInput.value && parseFloat(maxPriceInput.value) > filters.price_range.max) {
        maxPriceInput.value = "";
      }
    }
  } catch (error) {
    console.warn("Unable to load room filters:", error);
  }
}

function wireBooking() {
  const bookingForm = document.getElementById("booking-form");
  const bookingStatus = document.getElementById("booking-status");

  bookingForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedRoomId) {
      setStatus(bookingStatus, t("chooseFirst"), true);
      return;
    }

    let token = authApi.getToken();
    if (!token) {
      setStatus(bookingStatus, t("loginFirst"), true);
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
  wireConciergeChat();

  const countrySelect = document.getElementById("room-country-filter");
  if (countrySelect) {
    countrySelect.addEventListener("change", () => {
      loadRoomFilters(countrySelect.value);
    });
  }

  document.getElementById("refresh-rooms").addEventListener("click", async () => {
    await loadRoomFilters(countrySelect?.value || "");
    await loadRooms();
  });
  document.getElementById("apply-room-filters").addEventListener("click", loadRooms);
  document.getElementById("clear-room-filters").addEventListener("click", () => {
    const cityInput = document.getElementById("room-city-filter");
    const countryInput = document.getElementById("room-country-filter");
    const minPriceInput = document.getElementById("room-min-price");
    const maxPriceInput = document.getElementById("room-max-price");
    const availableInput = document.getElementById("room-available-filter");

    if (cityInput) {
      cityInput.value = "";
      cityInput.disabled = true;
    }
    if (countryInput) {
      countryInput.value = "";
    }
    if (minPriceInput) {
      minPriceInput.value = "";
    }
    if (maxPriceInput) {
      maxPriceInput.value = "";
    }
    if (availableInput) {
      availableInput.checked = true;
    }
    loadRoomFilters();
    loadRooms();
  });

  await loadRoomFilters();
  await loadRooms();
});
