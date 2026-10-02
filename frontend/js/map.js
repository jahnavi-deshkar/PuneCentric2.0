"use strict";

(() => {
  const PUNE_CENTER = [18.5204, 73.8567];
  const map = L.map("map", { zoomControl: false, preferCanvas: true }).setView(PUNE_CENTER, 12);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
    subdomains: "abc",
    maxZoom: 19,
  }).addTo(map);
  L.control.zoom({ position: "bottomright" }).addTo(map);

  const markerColors = { origin: "#47674d", destination: "#bd4d49" };
  const markers = { origin: null, destination: null };
  const routeLayer = L.featureGroup().addTo(map);
  let selectionMode = null;
  let selectionHandler = () => {};

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
  }

  function createIcon(kind) {
    const color = markerColors[kind];
    const svg = `<svg viewBox="0 0 36 46" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M18 1.5c-8.2 0-14.5 6.3-14.5 14.2 0 10.2 14.5 28.1 14.5 28.1s14.5-17.9 14.5-28.1C32.5 7.8 26.2 1.5 18 1.5Z" fill="${color}" stroke="#fffefa" stroke-width="2"/><circle cx="18" cy="15.5" r="5.2" fill="#fffefa"/></svg>`;
    return L.divIcon({ className: "", html: `<span class="map-pin map-pin-${kind}">${svg}</span>`, iconSize: [36, 46], iconAnchor: [18, 45], popupAnchor: [0, -41] });
  }

  function popupContent(label, kind) {
    const role = kind === "origin" ? "Starting point" : "Destination";
    return `<div class="map-popup-title">${escapeHtml(label || role)}</div><span class="map-popup-kind">${role}</span>`;
  }

  function setMarker(kind, lat, lng, label) {
    const point = [Number(lat), Number(lng)];
    if (!point.every(Number.isFinite) || point[0] < -90 || point[0] > 90 || point[1] < -180 || point[1] > 180) return null;
    const content = popupContent(label, kind);
    if (markers[kind]) {
      markers[kind].setLatLng(point).setIcon(createIcon(kind)).setPopupContent(content);
    } else {
      markers[kind] = L.marker(point, { icon: createIcon(kind), keyboard: true, title: label || kind }).addTo(map).bindPopup(content, { closeButton: false, offset: [0, -2] });
    }
    markers[kind].openPopup();
    return { lat: point[0], lng: point[1] };
  }

  function asLatLng(coords) {
    if (!coords) return null;
    if (Array.isArray(coords)) return L.latLng(Number(coords[0]), Number(coords[1]));
    return L.latLng(Number(coords.lat), Number(coords.lng));
  }

  function fitMapToBounds(originCoords, destCoords) {
    const points = [originCoords, destCoords].filter(Boolean).map(asLatLng).filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lng));
    if (points.length === 2) {
      const panel = document.querySelector(".control-panel");
      const isMobile = window.matchMedia("(max-width: 680px)").matches;
      const panelBounds = panel?.getBoundingClientRect();
      const topLeft = isMobile ? [18, 78] : [Math.max(24, (panelBounds?.right || 420) + 18), 88];
      const bottomRight = isMobile && panelBounds ? [18, Math.max(30, window.innerHeight - panelBounds.top + 18)] : [35, 58];
      map.fitBounds(L.latLngBounds(points), { paddingTopLeft: topLeft, paddingBottomRight: bottomRight, maxZoom: 15, animate: true });
    } else if (points.length === 1) {
      map.flyTo(points[0], Math.max(map.getZoom(), 14), { duration: 0.5 });
    }
  }

  function renderRoutePolyline(coordinates, modeColor = "#47674d") {
    clearRoutes();
    if (!Array.isArray(coordinates) || coordinates.length < 2) return null;
    const validCoordinates = coordinates.filter((point) => Array.isArray(point) && point.length >= 2 && point.every((value) => Number.isFinite(Number(value))));
    if (validCoordinates.length < 2) return null;
    const line = L.polyline(validCoordinates, {
      color: modeColor,
      weight: 5,
      opacity: 0.88,
      lineCap: "round",
      lineJoin: "round",
      smoothFactor: 1.2,
    }).addTo(routeLayer);
    const panel = document.querySelector(".control-panel");
    const isMobile = window.matchMedia("(max-width: 680px)").matches;
    const panelBounds = panel?.getBoundingClientRect();
    const paddingTopLeft = isMobile ? [18, 78] : [Math.max(24, (panelBounds?.right || 420) + 18), 88];
    const paddingBottomRight = isMobile && panelBounds ? [18, Math.max(30, window.innerHeight - panelBounds.top + 18)] : [35, 58];
    map.fitBounds(line.getBounds(), { paddingTopLeft, paddingBottomRight, maxZoom: 15, animate: true });
    return line;
  }

  function clearRoutes() {
    routeLayer.clearLayers();
  }

  map.on("click", (event) => {
    if (selectionMode) {
      selectionHandler(selectionMode, { lat: event.latlng.lat, lng: event.latlng.lng });
    }
  });

  function clearMarker(kind) {
    if (markers[kind]) {
      map.removeLayer(markers[kind]);
      markers[kind] = null;
    }
  }

  window.PuneMap = {
    map,
    setOriginMarker: (lat, lng, label) => setMarker("origin", lat, lng, label),
    setDestinationMarker: (lat, lng, label) => setMarker("destination", lat, lng, label),
    clearMarker,
    fitMapToBounds,
    renderRoutePolyline,
    clearRoutes,
    setSelectionMode(mode, handler) {
      selectionMode = mode === "origin" || mode === "destination" ? mode : null;
      selectionHandler = typeof handler === "function" ? handler : () => {};
      map.getContainer().style.cursor = selectionMode ? "crosshair" : "";
    },
    async loadMajorLocations() {
      const response = await fetch("/api/locations", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Could not load map regions");
      return response.json();
    },
  };
})();
