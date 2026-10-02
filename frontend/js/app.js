"use strict";

(() => {
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
    if (message) setHint(message);
    else if (state.origin && state.destination) setHint("Both places are set. You can change either pin or swap them.");
    else if (place) setHint(`${key === "origin" ? "Starting point" : "Destination"} set. Choose the other place to complete your pair.`);
    else setHint("Search for a place or choose “Pick on map”.");
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
