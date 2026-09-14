(function () {
  "use strict";

  const storageKey = "training-platform.theme";
  const root = document.documentElement;

  // Only pages that opt in through the shared template participate.
  if (!root.hasAttribute("data-theme")) {
    return;
  }

  function applyTheme(value) {
    const theme = value === "light" ? "light" : "dark";
    root.dataset.theme = theme;

    const button = document.getElementById("theme-toggle");
    if (button) {
      const label = theme === "light"
        ? "Включить тёмную тему"
        : "Включить светлую тему";

      button.setAttribute("aria-pressed", String(theme === "light"));
      button.setAttribute("aria-label", label);
      button.title = label;
    }
  }

  // This script runs before stylesheets to avoid flashing the default theme.
  let savedTheme = "dark";
  try {
    savedTheme = window.localStorage.getItem(storageKey);
  } catch (error) {
    // Switching still works when browser storage is unavailable.
  }
  applyTheme(savedTheme);

  document.addEventListener("DOMContentLoaded", function () {
    const button = document.getElementById("theme-toggle");
    if (!button) {
      return;
    }

    applyTheme(root.dataset.theme);
    button.hidden = false;
    button.addEventListener("click", function () {
      const theme = root.dataset.theme === "dark" ? "light" : "dark";
      applyTheme(theme);
      try {
        window.localStorage.setItem(storageKey, theme);
      } catch (error) {
        // Keep the chosen theme for this page even if it cannot be saved.
      }
    });
  });

  window.addEventListener("storage", function (event) {
    if (event.key !== storageKey && event.key !== null) {
      return;
    }
    try {
      if (event.storageArea === window.localStorage) {
        applyTheme(event.newValue);
      }
    } catch (error) {
      // Access to localStorage may have been disabled since page load.
    }
  });
})();
