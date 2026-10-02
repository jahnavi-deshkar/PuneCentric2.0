"use strict";

(() => {
  const defaults = { max_budget_inr: 300, max_walk_distance_km: 5, max_transfers: null };
  function init({ onChange } = {}) {
    const drawer = document.querySelector("#route-filters");
    const toggle = document.querySelector("#filter-toggle");
    const budget = document.querySelector("#budget-filter");
    const walking = document.querySelector("#walking-filter");
    const transfers = document.querySelector("#transfers-filter");
    const setOpen = (open) => {
      drawer.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
      toggle.classList.toggle("is-open", open);
    };
    const paintValues = () => {
      document.querySelector("#budget-value").value = `₹${budget.value}`;
      document.querySelector("#walking-value").value = `${Number(walking.value).toFixed(1).replace(/\.0$/, "")} km`;
    };
    const getConstraints = () => ({
      max_budget_inr: Number(budget.value),
      max_walk_distance_km: Number(walking.value),
      max_transfers: transfers.value === "" ? null : Number(transfers.value),
    });
    budget.addEventListener("input", paintValues);
    walking.addEventListener("input", paintValues);
    [budget, walking, transfers].forEach((control) => control.addEventListener("change", () => onChange?.(getConstraints())));
    toggle.addEventListener("click", () => setOpen(drawer.hidden));
    document.querySelector("#filter-close").addEventListener("click", () => setOpen(false));
    document.querySelector("#filter-reset").addEventListener("click", () => {
      budget.value = String(defaults.max_budget_inr);
      walking.value = String(defaults.max_walk_distance_km);
      transfers.value = "";
      paintValues();
      onChange?.(getConstraints());
    });
    paintValues();
    return { getConstraints, setOpen };
  }
  window.PuneFilters = { init };
})();
