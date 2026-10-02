"use strict";

(() => {
  const summaryStyles = document.createElement("style");
  summaryStyles.textContent = `
    .route-summary{position:absolute;z-index:440;right:26px;bottom:26px;width:min(320px,calc(100% - 52px));padding:18px 19px 16px;border:1px solid #ffffffc9;border-radius:7px;background:#fbfaf5e8;box-shadow:0 18px 55px #25291e1a;backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);animation:panel-arrive 300ms ease-out both}
    .route-summary[hidden]{display:none}.route-summary-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.route-summary-kicker{margin:0 0 4px;color:#47674d;font-size:9px;font-weight:700;letter-spacing:.13em;text-transform:uppercase}.route-summary-title{margin:0;color:#20251f;font:500 22px/1.15 'Playfair Display',Georgia,serif;letter-spacing:-.04em}.route-summary-caption{margin:5px 0 0;color:#85877e;font-size:10px}.route-summary-loader{color:#74776e;font-size:11px}.route-summary-metrics{display:grid;grid-template-columns:1fr 1fr;gap:10px 12px;margin-top:15px;padding-top:13px;border-top:1px solid #e7e5dc}.route-metric-label{display:block;margin-bottom:3px;color:#85877e;font-size:9px;font-weight:600;letter-spacing:.08em;text-transform:uppercase}.route-metric-value{color:#2a3029;font-size:14px;font-weight:700}.route-summary-error{margin:12px 0 0;color:#a24b45;font-size:10px;line-height:1.45}
    @media(max-width:680px){.route-summary{top:76px;right:12px;bottom:auto;width:min(250px,calc(100% - 24px));padding:13px 14px}.route-summary-title{font-size:19px}.route-summary-metrics{gap:8px;margin-top:10px;padding-top:10px}.route-metric-value{font-size:12px}}
  `;
  document.head.append(summaryStyles);

  const state = {
    origin: null,
    destination: null,
    activeSelectionMode: null,
    nextMapMode: "origin",
    regions: [],
  };

  const elements = {
    status: document.querySelector("#health-status"),
    statusPill: document.querySelector(".service-note"),
    originChip: document.querySelector("#origin-chip"),
    destinationChip: document.querySelector("#destination-chip"),
    originLabel: document.querySelector("#origin-chip-label"),
    destinationLabel: document.querySelector("#destination-chip-label"),
    hint: document.querySelector("#map-hint"),
    mapPick: document.querySelector("#map-pick"),
    currentLocation: document.querySelector("#use-location"),
  };
  const summary = document.createElement("aside");
  summary.className = "route-summary";
  summary.setAttribute("aria-live", "polite");
  summary.setAttribute("aria-label", "Walking route summary");
  summary.hidden = true;
  document.querySelector(".map-experience").append(summary);
  let routeController = null;
  let routeRequestId = 0;

  function setHint(message, stateName = "") {
    elements.hint.textContent = message;
    if (stateName) elements.hint.dataset.state = stateName;
    else delete elements.hint.dataset.state;
  }

  function coordinatesOf(place) {
    if (!place?.coordinates) return null;
    const lat = Number(place.coordinates.lat);
    const lng = Number(place.coordinates.lng);
    return Number.isFinite(lat) && Number.isFinite(lng) ? { lat, lng } : null;
  }

  function updateChips() {
    elements.originLabel.textContent = state.origin?.name || "Choose a starting point";
    elements.destinationLabel.textContent = state.destination?.name || "Choose a destination";
    elements.originChip.classList.toggle("is-selected", Boolean(state.origin));
    elements.destinationChip.classList.toggle("is-selected", Boolean(state.destination));
  }

  function drawMarkers({ fit = true } = {}) {
    const originCoordinates = coordinatesOf(state.origin);
    const destinationCoordinates = coordinatesOf(state.destination);
    if (originCoordinates) window.PuneMap.setOriginMarker(originCoordinates.lat, originCoordinates.lng, state.origin.name);
    else window.PuneMap.clearMarker("origin");
    if (destinationCoordinates) window.PuneMap.setDestinationMarker(destinationCoordinates.lat, destinationCoordinates.lng, state.destination.name);
    else window.PuneMap.clearMarker("destination");
    if (fit) window.PuneMap.fitMapToBounds(originCoordinates, destinationCoordinates);
  }

  function setPlace(key, place, { fit = true, message } = {}) {
    if (key !== "origin" && key !== "destination") return;
    state[key] = place;
    if (place) state.nextMapMode = key === "origin" ? "destination" : "origin";
    searchControls.setValue(key, place?.name || "");
    updateChips();
    drawMarkers({ fit });
    refreshWalkingRoute();
    if (message) setHint(message);
    else if (state.origin && state.destination) setHint("Both places are set. You can change either pin or swap them.");
    else if (place) setHint(`${key === "origin" ? "Starting point" : "Destination"} set. Choose the other place to complete your pair.`);
    else setHint("Search for a place or choose “Pick on map”.");
  }

  function formatDistance(kilometers) {
    const value = Number(kilometers);
    return value < 1 ? `${Math.round(value * 1000)} m` : `${value.toFixed(2)} km`;
  }

  function showRouteLoading() {
    summary.hidden = false;
    summary.innerHTML = `<div class="route-summary-head"><div><p class="route-summary-kicker">Walking route</p><h2 class="route-summary-title">Finding your way</h2><p class="route-summary-caption">Calculating distance and time…</p></div><span class="route-summary-loader" aria-hidden="true">···</span></div>`;
  }

  function renderRouteSummary(route) {
    const distance = formatDistance(route.total_distance_km);
    const duration = `${Math.max(0, Math.round(route.total_duration_min))} min`;
    summary.innerHTML = `
      <div class="route-summary-head">
        <div>
          <p class="route-summary-kicker">Walking · estimate</p>
          <h2 class="route-summary-title">Your route</h2>
          <p class="route-summary-caption">At an average pace of 4.5 km/h</p>
        </div>
      </div>
      <div class="route-summary-metrics">
        <div><span class="route-metric-label">Distance</span><span class="route-metric-value">${distance}</span></div>
        <div><span class="route-metric-label">Duration</span><span class="route-metric-value">${duration}</span></div>
        <div><span class="route-metric-label">Fare</span><span class="route-metric-value">₹0</span></div>
        <div><span class="route-metric-label">Carbon</span><span class="route-metric-value">0 g CO₂</span></div>
      </div>`;
    summary.hidden = false;
  }

  function showRouteError() {
    summary.innerHTML = `<div class="route-summary-head"><div><p class="route-summary-kicker">Walking route</p><h2 class="route-summary-title">Route unavailable</h2><p class="route-summary-caption">The route service could not calculate this journey.</p></div></div>`;
    summary.hidden = false;
  }

  async function refreshWalkingRoute() {
    routeController?.abort();
    routeController = null;
    routeRequestId += 1;
    const currentRequestId = routeRequestId;
    window.PuneMap.clearRoutes();
    const origin = coordinatesOf(state.origin);
    const destination = coordinatesOf(state.destination);
    if (!origin || !destination) {
      summary.hidden = true;
      return;
    }

    routeController = new AbortController();
    showRouteLoading();
    try {
      const response = await fetch("/api/routes/walking", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          origin: { ...origin, label: state.origin.name },
          destination: { ...destination, label: state.destination.name },
        }),
        signal: routeController.signal,
      });
      if (!response.ok) throw new Error(`Walking route request failed (${response.status})`);
      const route = await response.json();
      if (currentRequestId !== routeRequestId) return;
      const leg = route.legs?.find((item) => item.mode === "walking") || route.legs?.[0];
      if (!leg?.geometry?.length) throw new Error("The route response did not include geometry");
      window.PuneMap.renderRoutePolyline(leg.geometry, "#47674d");
      renderRouteSummary(route);
    } catch (error) {
      if (error.name === "AbortError" || currentRequestId !== routeRequestId) return;
      window.PuneMap.clearRoutes();
      showRouteError();
    }
  }

  const searchControls = window.PuneSearch.init({
    onSelect(key, place) {
      if (place && !coordinatesOf(place)) {
        setHint("This search result has no map coordinates yet.", "error");
        return;
      }
      setPlace(key, place);
    },
  });

  function updatePickButton() {
    const active = Boolean(state.activeSelectionMode);
    elements.mapPick.setAttribute("aria-pressed", String(active));
    elements.mapPick.querySelector("span").textContent = active
      ? `Click to set ${state.activeSelectionMode === "origin" ? "start" : "destination"}`
      : "Pick on map";
  }

  function startMapSelection(mode) {
    state.activeSelectionMode = mode;
    updatePickButton();
    window.PuneMap.setSelectionMode(mode, (selectedMode, coordinates) => {
      const lat = coordinates.lat;
      const lng = coordinates.lng;
      const place = {
        name: `Map pin (${lat.toFixed(5)}, ${lng.toFixed(5)})`,
        category: "map pin",
        locality: "Pune",
        coordinates,
      };
      state.activeSelectionMode = null;
      state.nextMapMode = selectedMode === "origin" ? "destination" : "origin";
      window.PuneMap.setSelectionMode(null);
      updatePickButton();
      setPlace(selectedMode, place, { message: `${selectedMode === "origin" ? "Starting point" : "Destination"} placed from the map.` });
    });
    setHint(`Click anywhere on the map to set your ${mode === "origin" ? "starting point" : "destination"}.`);
  }

  document.querySelector("#swap-button").addEventListener("click", () => {
    [state.origin, state.destination] = [state.destination, state.origin];
    searchControls.setValue("origin", state.origin?.name || "");
    searchControls.setValue("destination", state.destination?.name || "");
    updateChips();
    drawMarkers();
    refreshWalkingRoute();
    setHint(state.origin && state.destination ? "Starting point and destination swapped." : "Places swapped. Choose the missing point to complete your pair.");
  });

  elements.mapPick.addEventListener("click", () => {
    if (state.activeSelectionMode) {
      state.activeSelectionMode = null;
      window.PuneMap.setSelectionMode(null);
      updatePickButton();
      setHint("Map selection cancelled. Search for a place or choose “Pick on map”.");
      return;
    }
    startMapSelection(state.nextMapMode);
  });

  elements.currentLocation.addEventListener("click", () => {
    if (!navigator.geolocation) {
      setHint("Location access is not available in this browser. You can choose a point on the map.", "error");
      return;
    }
    elements.currentLocation.disabled = true;
    setHint("Finding your current location…");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        elements.currentLocation.disabled = false;
        const coordinates = { lat: coords.latitude, lng: coords.longitude };
        setPlace("origin", {
          name: "My current location",
          category: "current location",
          locality: "Pune",
          coordinates,
        }, { message: "Your current location is set as the starting point." });
      },
      (error) => {
        elements.currentLocation.disabled = false;
        const message = error.code === error.PERMISSION_DENIED
          ? "Location permission was not granted. You can search or choose a point on the map."
          : "Could not determine your location. You can search or choose a point on the map.";
        setHint(message, "error");
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    );
  });

  async function checkHealth() {
    try {
      const response = await fetch("/api/health", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Health endpoint unavailable");
      const health = await response.json();
      if (health.status !== "healthy") throw new Error("Service is not healthy");
      elements.status.textContent = `${health.city} service is healthy`;
      elements.statusPill.dataset.state = "healthy";
    } catch {
      elements.status.textContent = "Service status unavailable";
      elements.statusPill.dataset.state = "unhealthy";
    }
  }

  async function loadRegions() {
    try {
      state.regions = await window.PuneMap.loadMajorLocations();
      if (Array.isArray(state.regions) && state.regions.length) {
        setHint(`Map ready · ${state.regions.length} Pune regions available. Search for a place or choose “Pick on map”.`);
      }
    } catch {
      // The map and direct pin placement work even if the region endpoint is unavailable.
    }
  }

  window.PuneCentric = { state, setPlace, startMapSelection };
  checkHealth();
  loadRegions();
})();
