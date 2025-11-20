(() => {
  const STORAGE_KEY = "hpt-theme";
  const mediaQuery = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)");

  const srOnly = document.createElement("style");
  srOnly.textContent =
    ".sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;}";
  document.head.appendChild(srOnly);

  const normalize = (value) =>
    value === "dark" || value === "light" || value === "system" ? value : null;

  const getEffectiveTheme = (mode) => {
    if (mode === "dark") return "dark";
    if (mode === "light") return "light";
    return mediaQuery && mediaQuery.matches ? "dark" : "light";
  };

  const ICONS = {
    light: "☀️",
    dark: "🌙",
    system: "🖥️",
  };

  const TITLES = {
    light: "Светлая тема",
    dark: "Тёмная тема",
    system: "Системная тема",
  };

  const refreshButtons = (mode, effective) => {
    document.querySelectorAll("[data-theme-select]").forEach((btn) => {
      const target = btn.dataset.themeSelect;
      const isActive = target === mode;
      btn.dataset.active = isActive ? "true" : "false";
      btn.setAttribute("aria-pressed", String(isActive));
      btn.title = TITLES[target] || "";
      btn.setAttribute("aria-label", TITLES[target] || "");
      const glyph = btn.querySelector("[data-theme-icon]");
      if (glyph) {
        glyph.textContent = ICONS[target] || "🌗";
      }
    });

    document.querySelectorAll("[data-theme-state]").forEach((label) => {
      label.textContent = ICONS[effective] || "🌗";
      label.setAttribute("title", TITLES[mode] || "");
      label.setAttribute("aria-label", TITLES[mode] || "");
    });
  };

  const applyTheme = (theme, { persist = true } = {}) => {
    const normalized = normalize(theme) || "system";
    const effective = getEffectiveTheme(normalized);
    document.documentElement.dataset.theme = effective;
    document.documentElement.dataset.themeMode = normalized;
    document.documentElement.style.colorScheme = effective === "dark" ? "dark" : "light";
    if (persist) {
      localStorage.setItem(STORAGE_KEY, normalized);
    }
    refreshButtons(normalized, effective);
  };

  const stored = normalize(localStorage.getItem(STORAGE_KEY));
  const initial = stored || "system";
  applyTheme(initial, { persist: Boolean(stored) });

  if (mediaQuery) {
    mediaQuery.addEventListener("change", (event) => {
      const userChoice = normalize(localStorage.getItem(STORAGE_KEY));
      if (!userChoice || userChoice === "system") {
        applyTheme("system", { persist: Boolean(userChoice) });
      }
    });
  }

  window.hptTheme = {
    set(theme) {
      applyTheme(theme);
    },
    system() {
      applyTheme("system");
    },
    toggle() {
      const currentMode = document.documentElement.dataset.themeMode || "system";
      const next = currentMode === "dark" ? "light" : currentMode === "light" ? "system" : "dark";
      applyTheme(next);
    },
    refresh() {
      const mode = document.documentElement.dataset.themeMode || "system";
      const effective = getEffectiveTheme(mode);
      refreshButtons(mode, effective);
    },
  };

  window.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-theme-select]").forEach((btn) => {
      if (!btn.querySelector("[data-theme-icon]")) {
        const glyph = document.createElement("span");
        glyph.dataset.themeIcon = "true";
        glyph.setAttribute("aria-hidden", "true");
        const sr = document.createElement("span");
        sr.className = "sr-only";
        sr.textContent = TITLES[btn.dataset.themeSelect] || "";
        btn.textContent = "";
        btn.append(glyph, sr);
      }
    });

    document.querySelectorAll(".theme-menu summary").forEach((summary) => {
      const indicator = summary.querySelector("[data-theme-state]");
      if (indicator) {
        summary.innerHTML = "";
        summary.appendChild(indicator);
      }
      summary.setAttribute("title", TITLES[document.documentElement.dataset.themeMode || "system"] || "");
      summary.setAttribute("aria-label", TITLES[document.documentElement.dataset.themeMode || "system"] || "");
    });

    const mode = document.documentElement.dataset.themeMode || "system";
    refreshButtons(mode, getEffectiveTheme(mode));
    document.querySelectorAll("[data-theme-select]").forEach((btn) =>
      btn.addEventListener("click", () => window.hptTheme.set(btn.dataset.themeSelect || "system"))
    );
    document.querySelectorAll("[data-theme-toggle]").forEach((btn) =>
      btn.addEventListener("click", () => window.hptTheme.toggle())
    );
  });
})();
