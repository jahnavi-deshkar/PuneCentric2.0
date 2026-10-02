"use strict";

(() => {
  const chartIds = { time: "timeChart", cost: "costChart", emissions: "emissionsChart" };
  const charts = {};
  let routes = [];
  let activeChart = "time";
  const drawer = () => document.querySelector("#comparison-drawer");

  function destroyCharts() {
    Object.keys(charts).forEach((key) => {
      charts[key]?.destroy();
      delete charts[key];
    });
  }

  function routeLabels(rows) {
    return rows.map((route, index) => {
      const name = route.candidate_name || route.candidate_id || `Route ${index + 1}`;
      return name.length > 27 ? `${name.slice(0, 24)}…` : name;
    });
  }

  function routeColor(route, index) {
    const modes = (route.legs || []).map((leg) => leg.mode);
    if (modes.includes("metro")) return "#7652a3";
    if (modes.includes("bus")) return "#397eae";
    if (modes.includes("auto")) return "#d58b26";
    if (modes.includes("walking")) return "#66816c";
    return ["#47674d", "#397eae", "#7652a3", "#d58b26", "#008b8b"][index % 5];
  }

  function createChart(kind, config) {
    if (!window.Chart || !routes.length) return;
    destroyCharts();
    const canvas = document.getElementById(chartIds[kind]);
    if (!canvas) return;
    charts[kind] = new window.Chart(canvas.getContext("2d"), config);
  }

  function renderDurationChart(rows = routes) {
    createChart("time", {
      type: "bar",
      data: {
        labels: routeLabels(rows),
        datasets: [{ label: "Travel time (min)", data: rows.map((route) => Number(route.total_duration_min || 0)),
          backgroundColor: rows.map(routeColor), borderRadius: 5, borderSkipped: false, barThickness: 18 }],
      },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (item) => ` ${Math.round(item.raw)} min` } } },
        scales: { x: { beginAtZero: true, grid: { color: "#e8e5dc" }, title: { display: true, text: "Minutes" } },
          y: { grid: { display: false } } },
      },
    });
  }

  function renderCostChart(rows = routes) {
    createChart("cost", {
      type: "bar",
      data: {
        labels: routeLabels(rows),
        datasets: [{ label: "Estimated fare (₹)", data: rows.map((route) => Number(route.total_fare_inr || 0)),
          backgroundColor: rows.map(routeColor), borderRadius: 5, borderSkipped: false, maxBarThickness: 34 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (item) => ` ₹${Number(item.raw).toFixed(2)}` } } },
        scales: { y: { beginAtZero: true, grid: { color: "#e8e5dc" }, title: { display: true, text: "Indian rupees (₹)" } },
          x: { grid: { display: false } } },
      },
    });
  }

  function renderEmissionsChart(rows = routes) {
    createChart("emissions", {
      type: "bar",
      data: {
        labels: routeLabels(rows),
        datasets: [
          { label: "Selected route", data: rows.map((route) => Number(route.total_co2_grams || 0)),
            backgroundColor: rows.map(routeColor), borderRadius: 4, maxBarThickness: 30 },
          { label: "Private car baseline", data: rows.map((route) => Number(route.private_car_baseline_co2_grams || (Number(route.total_distance_km || 0) * 120))),
            backgroundColor: "#a7aaa1", borderRadius: 4, maxBarThickness: 30 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8, padding: 16 } },
          tooltip: { callbacks: { label: (item) => ` ${item.dataset.label}: ${Math.round(item.raw)} g CO₂` } } },
        scales: { y: { beginAtZero: true, grid: { color: "#e8e5dc" }, title: { display: true, text: "Grams of CO₂" } },
          x: { grid: { display: false } } },
      },
    });
  }

  function renderActiveChart() {
    if (activeChart === "cost") renderCostChart();
    else if (activeChart === "emissions") renderEmissionsChart();
    else renderDurationChart();
  }

  function open() {
    const panel = drawer();
    panel.hidden = false;
    panel.setAttribute("aria-hidden", "false");
    document.querySelectorAll(".visual-analytics-toggle").forEach((button) => button.setAttribute("aria-expanded", "true"));
    renderActiveChart();
  }

  function close() {
    const panel = drawer();
    panel.hidden = true;
    panel.setAttribute("aria-hidden", "true");
    document.querySelectorAll(".visual-analytics-toggle").forEach((button) => button.setAttribute("aria-expanded", "false"));
  }

  function updateRoutes(nextRoutes) {
    routes = Array.isArray(nextRoutes) ? nextRoutes : [];
    destroyCharts();
    if (!routes.length) {
      close();
      return;
    }
    if (!drawer().hidden) renderActiveChart();
  }

  document.querySelectorAll(".comparison-tab").forEach((button) => {
    button.addEventListener("click", () => {
      activeChart = button.dataset.chart;
      document.querySelectorAll(".comparison-tab").forEach((tab) => {
        const selected = tab === button;
        tab.classList.toggle("is-active", selected);
        tab.setAttribute("aria-selected", String(selected));
      });
      document.querySelectorAll(".chart-panel").forEach((panel) => { panel.hidden = panel.id !== `${activeChart}-chart-panel`; });
      renderActiveChart();
    });
  });
  document.querySelector("#comparison-close").addEventListener("click", close);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !drawer().hidden) close(); });

  window.RouteCharts = { renderDurationChart, renderCostChart, renderEmissionsChart, destroyCharts, updateRoutes, open, close };
})();
