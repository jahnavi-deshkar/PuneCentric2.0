"use strict";

(() => {
  const routeLayer = L.layerGroup();

  async function fetchRoute(mode, origin, destination, signal) {
    const response = await fetch(`/api/routes/${encodeURIComponent(mode)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        origin: { lat: origin.lat, lng: origin.lng, label: origin.label || origin.name },
        destination: { lat: destination.lat, lng: destination.lng, label: destination.label || destination.name },
      }),
      signal,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `Could not find a ${mode} route`);
    return body;
  }

  function clearMapRoutes() {
    if (routeLayer) routeLayer.clearLayers();
  }

  function renderMap(route) {
    const map = window.PuneMap.map;
    routeLayer.clearLayers();
    if (!map.hasLayer(routeLayer)) routeLayer.addTo(map);
    const lines = [];
    (route.legs || []).forEach((leg) => {
      if (leg.mode === "transfer") return;
      if (!Array.isArray(leg.geometry) || leg.geometry.length < 2) return;
      let style;
      if ((route.mode === "bus" || route.mode === "metro") && leg.mode === "walking") {
        style = { color: "#888f89", weight: 4, opacity: 0.9, dashArray: "7 8", lineCap: "round", lineJoin: "round" };
      } else if (leg.mode === "bus") {
        style = { color: "#397eae", weight: 5, opacity: 0.95, lineCap: "round", lineJoin: "round" };
      } else if (leg.mode === "metro") {
        style = { color: leg.line_color || "#008B8B", weight: 5, opacity: 0.96, lineCap: "round", lineJoin: "round" };
      } else if (leg.mode === "auto") {
        style = { color: "#E65100", weight: 5, opacity: 0.96, lineCap: "round", lineJoin: "round" };
      } else {
        style = { color: "#47674d", weight: 5, opacity: 0.9, lineCap: "round", lineJoin: "round" };
      }
      const line = L.polyline(leg.geometry, { ...style, smoothFactor: 1.2 }).addTo(routeLayer);
      lines.push(line);
    });
    if (!lines.length) throw new Error("The route response did not include drawable geometry");

    const bounds = L.latLngBounds([]);
    lines.forEach((line) => bounds.extend(line.getBounds()));
    const panelBounds = document.querySelector(".control-panel")?.getBoundingClientRect();
    const isMobile = window.matchMedia("(max-width: 680px)").matches;
    const paddingTopLeft = isMobile ? [18, 78] : [Math.max(24, (panelBounds?.right || 420) + 18), 88];
    const paddingBottomRight = isMobile && panelBounds ? [18, Math.max(30, window.innerHeight - panelBounds.top + 18)] : [350, 58];
    map.fitBounds(bounds, { paddingTopLeft, paddingBottomRight, maxZoom: 15, animate: true });
  }

  function addMetric(container, label, value) {
    const item = document.createElement("div");
    const title = document.createElement("span");
    title.className = "route-metric-label";
    title.textContent = label;
    const text = document.createElement("span");
    text.className = "route-metric-value";
    text.textContent = value;
    item.append(title, text);
    container.append(item);
  }

  function renderSummary(route, mode, container) {
    container.replaceChildren();
    const heading = document.createElement("div");
    heading.className = "route-summary-head";
    const intro = document.createElement("div");
    const kicker = document.createElement("p");
    kicker.className = "route-summary-kicker";
    kicker.textContent = mode === "bus" ? "PMPML bus · estimate" : mode === "metro" ? "Pune Metro · estimate" : mode === "auto" ? "Auto-rickshaw · estimate" : "Walking · estimate";
    const title = document.createElement("h2");
    title.className = "route-summary-title";
    title.textContent = mode === "bus" ? "Bus journey" : mode === "metro" ? "Metro journey" : mode === "auto" ? "Auto ride" : "Walking route";
    const caption = document.createElement("p");
    caption.className = "route-summary-caption";
    caption.textContent = mode === "bus" ? "Walk · ride · walk" : mode === "metro" ? "Walk · metro · walk" : mode === "auto" ? "Direct road journey · fare estimate" : "At an average pace of 4.5 km/h";
    intro.append(kicker, title, caption);
    heading.append(intro);
    container.append(heading);

    if (mode === "bus") {
      const busLeg = (route.legs || []).find((leg) => leg.mode === "bus");
      if (busLeg) {
        const details = document.createElement("dl");
        details.className = "bus-route-details";
        [
          ["Route", busLeg.route_name || "PMPML bus"],
          ["Board", busLeg.board_stop?.name || "—"],
          ["Alight", busLeg.alight_stop?.name || "—"],
        ].forEach(([label, value]) => {
          const row = document.createElement("div");
          const term = document.createElement("dt");
          term.textContent = label;
          const description = document.createElement("dd");
          description.textContent = value;
          row.append(term, description);
          details.append(row);
        });
        container.append(details);
      }
    } else if (mode === "auto") {
      const autoLeg = (route.legs || []).find((leg) => leg.mode === "auto");
      if (autoLeg) {
        const details = document.createElement("dl");
        details.className = "auto-fare-details";
        const rows = [
          ["Base · first 1.5 km", `₹${Number(autoLeg.fare_base_inr || 0).toFixed(2)}`],
          [`Distance · ₹${Number(autoLeg.fare_rate_per_km || 0).toFixed(0)}/km`, `₹${Number(autoLeg.fare_distance_inr || 0).toFixed(2)}`],
          ["Night surcharge · 25%", autoLeg.night_surcharge_applied ? `₹${Number(autoLeg.fare_night_surcharge_inr || 0).toFixed(2)}` : "Not applied"],
        ];
        rows.forEach(([label, value]) => {
          const row = document.createElement("div");
          const term = document.createElement("dt");
          term.textContent = label;
          const description = document.createElement("dd");
          description.textContent = value;
          row.append(term, description);
          details.append(row);
        });
        container.append(details);
      }
    } else if (mode === "metro") {
      const details = document.createElement("div");
      details.className = "metro-route-details";
      (route.legs || []).forEach((leg) => {
        if (leg.mode === "transfer") {
          const warning = document.createElement("div");
          warning.className = "metro-interchange-note";
          warning.textContent = `⇄ Change at ${leg.transfer_station?.name || "Civil Court"} · allow 3 min`;
          details.append(warning);
          return;
        }
        if (leg.mode !== "metro") return;
        const item = document.createElement("div");
        item.className = "metro-leg-detail";
        const lineHeading = document.createElement("div");
        lineHeading.className = "metro-line-heading";
        const swatch = document.createElement("span");
        swatch.className = "metro-line-swatch";
        swatch.style.backgroundColor = leg.line_color || "#008B8B";
        const lineName = document.createElement("span");
        lineName.textContent = leg.line_name || "Metro line";
        lineHeading.append(swatch, lineName);
        const pair = document.createElement("div");
        pair.className = "metro-station-pair";
        const board = document.createElement("span");
        board.textContent = leg.board_station?.name || "Boarding station";
        const arrow = document.createElement("span");
        arrow.textContent = "→";
        const alight = document.createElement("span");
        alight.textContent = leg.alight_station?.name || "Alighting station";
        pair.append(board, arrow, alight);
        item.append(lineHeading, pair);
        details.append(item);
      });
      if (details.childElementCount) container.append(details);
    }

    const grid = document.createElement("div");
    grid.className = "route-summary-metrics";
    const distance = Number(route.total_distance_km || 0);
    addMetric(grid, "Total distance", distance < 1 ? `${Math.round(distance * 1000)} m` : `${distance.toFixed(2)} km`);
    addMetric(grid, "Duration", `${Math.round(Number(route.total_duration_min || 0))} min`);
    addMetric(grid, "Fare", `₹${Number(route.total_fare_inr || 0).toFixed(0)}`);
    addMetric(grid, "CO₂", `${Math.round(Number(route.total_co2_grams || 0))} g`);
    container.append(grid);
    container.hidden = false;
  }

  function renderError(container, error, mode) {
    container.replaceChildren();
    const kicker = document.createElement("p");
    kicker.className = "route-summary-kicker";
    kicker.textContent = mode === "bus" ? "PMPML bus" : mode === "metro" ? "Pune Metro" : mode === "auto" ? "Auto-rickshaw" : "Walking";
    const title = document.createElement("h2");
    title.className = "route-summary-title";
    title.textContent = "Route unavailable";
    const caption = document.createElement("p");
    caption.className = "route-summary-caption route-summary-error";
    caption.textContent = error.message || "Could not calculate this route.";
    container.append(kicker, title, caption);
    container.hidden = false;
  }

  window.PuneRoutes = { fetchRoute, renderMap, renderSummary, renderError, clearMapRoutes };
})();
