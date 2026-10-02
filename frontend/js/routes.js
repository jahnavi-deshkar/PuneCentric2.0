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

  async function fetchCandidates(origin, destination, signal) {
    const response = await fetch("/api/routes/multimodal", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        origin: { lat: origin.lat, lng: origin.lng, label: origin.label || origin.name },
        destination: { lat: destination.lat, lng: destination.lng, label: destination.label || destination.name },
      }),
      signal,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "Could not build route options");
    return Array.isArray(body) ? body : [];
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
      if ((route.mode === "multimodal" || route.mode === "bus" || route.mode === "metro") && leg.mode === "walking") {
        style = { color: "#858b84", weight: 4, opacity: 0.95, dashArray: "7 8", lineCap: "round", lineJoin: "round" };
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

  function fareAccordion(route) {
    const breakdown = route.fare_breakdown;
    if (!breakdown) return null;
    const details = document.createElement("details");
    details.className = "fare-breakdown";
    const summary = document.createElement("summary");
    summary.textContent = `Fare breakdown · ₹${Number(breakdown.total_fare || route.total_fare_inr || 0).toFixed(2)}`;
    const rows = document.createElement("dl");
    rows.className = "fare-breakdown-rows";
    const hasNightSurcharge = Object.hasOwn(breakdown.surcharge_details || {}, "night_surcharge");
    [
      ["Base fare", breakdown.base_fare],
      ["Distance charge", breakdown.distance_fare],
      [hasNightSurcharge ? "Night surcharge" : "Surcharges", breakdown.surcharges],
      ["Discounts", -Number(breakdown.discounts || 0)],
      ["Total fare", breakdown.total_fare],
    ].forEach(([label, amount]) => {
      const row = document.createElement("div");
      if (label === "Total fare") row.className = "fare-total-row";
      const term = document.createElement("dt");
      term.textContent = label;
      const value = document.createElement("dd");
      const number = Number(amount || 0);
      value.textContent = `${number < 0 ? "−" : ""}₹${Math.abs(number).toFixed(2)}`;
      row.append(term, value);
      rows.append(row);
    });
    Object.entries(breakdown.discount_details || {}).forEach(([name, amount]) => {
      if (!amount) return;
      const row = document.createElement("div");
      row.className = "fare-discount-detail";
      const term = document.createElement("dt");
      term.textContent = `${name} discount`;
      const value = document.createElement("dd");
      value.textContent = `−₹${Number(amount).toFixed(2)}`;
      row.append(term, value);
      rows.append(row);
    });
    details.append(summary, rows);
    return details;
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
    const breakdown = fareAccordion(route);
    if (breakdown) container.append(breakdown);
    container.append(grid);
    container.hidden = false;
  }

  function formatDistance(km) {
    return km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1)} km`;
  }

  function stageForLeg(leg) {
    if (leg.mode === "walking") return { icon: "🚶", text: "Walk", color: "#858b84" };
    if (leg.mode === "auto") {
      const endpoints = leg.from_label && leg.to_label ? ` · ${leg.from_label} → ${leg.to_label}` : "";
      return { icon: "🛺", text: `Auto-rickshaw${endpoints}`, color: "#E65100" };
    }
    if (leg.mode === "bus") return { icon: "🚌", text: leg.route_name || "PMPML bus", color: "#397eae" };
    if (leg.mode === "metro") return { icon: "🚇", text: leg.line_name || "Metro", color: leg.line_color || "#008B8B" };
    if (leg.mode === "transfer") return { icon: "⇄", text: `Transfer${leg.transfer_station?.name ? ` at ${leg.transfer_station.name}` : ""}`, color: "#777" };
    return { icon: "•", text: leg.mode, color: "#777" };
  }

  function renderCandidates(routes, container, onSelect) {
    container.replaceChildren();
    const title = document.createElement("h2");
    title.className = "route-summary-title";
    title.textContent = "All route options";
    const kicker = document.createElement("p");
    kicker.className = "route-summary-kicker";
    kicker.textContent = `${routes.length} journeys · compare time, fare & emissions`;
    container.append(kicker, title);
    if (!routes.length) {
      const empty = document.createElement("p");
      empty.className = "candidate-empty";
      empty.textContent = "No route options could be assembled for these places.";
      container.append(empty);
      container.hidden = false;
      return;
    }
    const list = document.createElement("div");
    list.className = "candidate-list";
    routes.forEach((route, index) => {
      const card = document.createElement("article");
      card.className = `candidate-card${index === 0 ? " is-selected" : ""}`;
      const heading = document.createElement("div");
      heading.className = "candidate-card-heading";
      const name = document.createElement("h3");
      name.className = "candidate-title";
      name.textContent = route.candidate_name || route.candidate_id || "Journey option";
      const badge = document.createElement("span");
      badge.className = "candidate-badge";
      badge.textContent = index === 0 ? "Fastest" : `${route.transfers_count || 0} transfers`;
      const selectButton = document.createElement("button");
      selectButton.type = "button";
      selectButton.className = "candidate-select";
      selectButton.textContent = "Show on map";
      selectButton.setAttribute("aria-pressed", String(index === 0));
      selectButton.setAttribute("aria-label", `Show ${name.textContent} on map`);
      heading.append(name, badge, selectButton);
      const metrics = document.createElement("div");
      metrics.className = "candidate-metrics";
      [
        ["Time", `${Math.round(route.total_duration_min || 0)} min`],
        ["Fare", `₹${Number(route.total_fare_inr || 0).toFixed(0)}`],
        ["Distance", formatDistance(Number(route.total_distance_km || 0))],
        ["CO₂", `${Math.round(route.total_co2_grams || 0)} g`],
      ].forEach(([label, value]) => {
        const metric = document.createElement("span");
        metric.append(`${label} `);
        const strong = document.createElement("strong");
        strong.textContent = value;
        metric.append(strong);
        metrics.append(metric);
      });
      const timeline = document.createElement("ol");
      timeline.className = "candidate-timeline";
      (route.legs || []).forEach((leg) => {
        const stage = stageForLeg(leg);
        const item = document.createElement("li");
        item.className = "candidate-stage";
        const icon = document.createElement("span");
        icon.className = "candidate-stage-icon";
        icon.textContent = stage.icon;
        const description = document.createElement("span");
        description.textContent = stage.text;
        description.style.color = stage.color;
        if (leg.mode === "bus" && leg.board_stop && leg.alight_stop) {
          description.textContent += ` · ${leg.board_stop.name} → ${leg.alight_stop.name}`;
        } else if (leg.mode === "metro" && leg.board_station && leg.alight_station) {
          description.textContent += ` · ${leg.board_station.name} → ${leg.alight_station.name}`;
        }
        const distance = document.createElement("span");
        distance.className = "candidate-stage-distance";
        distance.textContent = leg.mode === "transfer" ? `${Math.round(leg.duration_min)} min` : formatDistance(Number(leg.distance_km || 0));
        item.append(icon, description, distance);
        timeline.append(item);
      });
      const fareDetails = fareAccordion(route);
      card.append(heading, metrics, timeline);
      if (fareDetails) card.append(fareDetails);
      const selectCard = () => {
        list.querySelectorAll(".candidate-card").forEach((other) => {
          const active = other === card;
          other.classList.toggle("is-selected", active);
          other.setAttribute("aria-pressed", String(active));
        });
        onSelect(route);
      };
      selectButton.addEventListener("click", selectCard);
      list.append(card);
    });
    container.append(list);
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

  window.PuneRoutes = { fetchRoute, fetchCandidates, renderMap, renderSummary, renderCandidates, renderError, clearMapRoutes };
})();
