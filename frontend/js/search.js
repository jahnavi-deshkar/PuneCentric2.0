"use strict";

(() => {
  const DEBOUNCE_MS = 260;

  function initSearch({ onSelect }) {
    const fields = ["origin", "destination"].map((key) => {
      const wrapper = document.querySelector(`[data-search-field="${key}"]`);
      return {
        key,
        wrapper,
        input: wrapper.querySelector("input"),
        clear: wrapper.querySelector(".clear-input"),
        list: wrapper.querySelector(".suggestions"),
        timer: null,
        controller: null,
        options: [],
        activeIndex: -1,
      };
    });

    function close(field) {
      field.list.hidden = true;
      field.list.replaceChildren();
      field.options = [];
      field.activeIndex = -1;
      field.input.removeAttribute("aria-activedescendant");
    }

    function message(field, text) {
      field.list.replaceChildren();
      const item = document.createElement("li");
      item.className = "suggestion-message";
      item.setAttribute("role", "status");
      item.textContent = text;
      field.list.append(item);
      field.list.hidden = false;
    }

    function updateActive(field, nextIndex) {
      const buttons = [...field.list.querySelectorAll(".suggestion-option")];
      if (!buttons.length) return;
      field.activeIndex = (nextIndex + buttons.length) % buttons.length;
      buttons.forEach((button, index) => button.setAttribute("aria-selected", String(index === field.activeIndex)));
      buttons[field.activeIndex].scrollIntoView({ block: "nearest" });
      field.input.setAttribute("aria-activedescendant", buttons[field.activeIndex].id);
    }

    function render(field, results) {
      field.options = results;
      field.activeIndex = -1;
      field.list.replaceChildren();
      if (!results.length) {
        message(field, "No places found. Try another name or locality.");
        return;
      }

      results.forEach((location, index) => {
        const item = document.createElement("li");
        item.setAttribute("role", "presentation");
        const button = document.createElement("button");
        button.type = "button";
        button.className = "suggestion-option";
        button.id = `${field.key}-suggestion-${index}`;
        button.setAttribute("role", "option");
        button.setAttribute("aria-selected", "false");

        const name = document.createElement("span");
        name.className = "suggestion-name";
        name.textContent = location.name || "Unnamed place";
        const locality = document.createElement("span");
        locality.className = "suggestion-locality";
        locality.textContent = location.locality || "Pune";
        const category = document.createElement("span");
        category.className = "category-tag";
        category.textContent = String(location.category || "place").replaceAll("_", " ");
        button.append(name, locality, category);
        button.addEventListener("click", () => {
          close(field);
          field.input.value = location.name || "";
          field.clear.hidden = !field.input.value;
          onSelect(field.key, location);
        });
        item.append(button);
        field.list.append(item);
      });
      field.list.hidden = false;
    }

    async function search(field, query) {
      field.controller?.abort();
      field.controller = new AbortController();
      message(field, "Searching Pune places…");
      try {
        const params = new URLSearchParams({ q: query, limit: "8" });
        const response = await fetch(`/api/search?${params.toString()}`, {
          headers: { Accept: "application/json" },
          signal: field.controller.signal,
        });
        if (!response.ok) throw new Error("Search service unavailable");
        const data = await response.json();
        if (!Array.isArray(data)) throw new Error("Unexpected search response");
        render(field, data);
      } catch (error) {
        if (error.name === "AbortError") return;
        message(field, "Search is unavailable right now. You can choose a point on the map.");
      }
    }

    fields.forEach((field) => {
      field.input.addEventListener("input", () => {
        field.clear.hidden = !field.input.value;
        window.clearTimeout(field.timer);
        const query = field.input.value.trim();
        if (query.length < 2) {
          field.controller?.abort();
          close(field);
          return;
        }
        field.timer = window.setTimeout(() => search(field, query), DEBOUNCE_MS);
      });

      field.input.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown" && !field.list.hidden) {
          event.preventDefault();
          updateActive(field, field.activeIndex + 1);
        } else if (event.key === "ArrowUp" && !field.list.hidden) {
          event.preventDefault();
          updateActive(field, field.activeIndex < 0 ? field.options.length - 1 : field.activeIndex - 1);
        } else if (event.key === "Enter" && field.activeIndex >= 0) {
          event.preventDefault();
          field.list.querySelectorAll(".suggestion-option")[field.activeIndex]?.click();
        } else if (event.key === "Escape") {
          close(field);
        }
      });

      field.clear.addEventListener("click", () => {
        field.input.value = "";
        field.clear.hidden = true;
        field.controller?.abort();
        close(field);
        field.input.focus();
        onSelect(field.key, null);
      });
      field.input.addEventListener("focus", () => {
        fields.filter((other) => other !== field).forEach(close);
      });
    });

    document.addEventListener("pointerdown", (event) => {
      fields.forEach((field) => {
        if (!field.wrapper.contains(event.target)) close(field);
      });
    });

    return {
      setValue(key, value) {
        const field = fields.find((item) => item.key === key);
        if (!field) return;
        field.input.value = value || "";
        field.clear.hidden = !value;
        close(field);
      },
      focus(key) { fields.find((item) => item.key === key)?.input.focus(); },
    };
  }

  window.PuneSearch = { init: initSearch };
})();
