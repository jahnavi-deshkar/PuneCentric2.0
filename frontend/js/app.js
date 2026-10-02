"use strict";

const healthLabel = document.querySelector("#health-status");
const serviceNote = document.querySelector(".service-note");

async function checkHealth() {
  try {
    const response = await fetch("/api/health", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`Health check returned ${response.status}`);

    const health = await response.json();
    if (health.status !== "healthy") throw new Error("Service is not healthy");

    healthLabel.textContent = `${health.city} service is healthy`;
    serviceNote.dataset.state = "healthy";
  } catch {
    healthLabel.textContent = "Service status unavailable";
    serviceNote.dataset.state = "unhealthy";
  }
}

checkHealth();
