(() => {
  const STORAGE_KEY = "hpt-theme";
  const mediaQuery = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)");

  const normalize = (value) =>
    value === "dark" || value === "light" || value === "system" ? value : null;

  const getEffectiveTheme = (mode) => {
    if (mode === "dark") return "dark";
    if (mode === "light") return "light";
    return mediaQuery && mediaQuery.matches ? "dark" : "light";
  };

  const refreshButtons = (mode, effective) => {
    document.querySelectorAll("[data-theme-select]").forEach((btn) => {
      const target = btn.dataset.themeSelect;
      const isActive = target === mode;
      btn.dataset.active = isActive ? "true" : "false";
      btn.setAttribute("aria-pressed", String(isActive));
      if (target === "system") {
        btn.title = "Следовать системным настройкам";
      } else {
        btn.title = target === "dark" ? "Переключить на тёмную тему" : "Переключить на светлую тему";
      }
    });

    document
      .querySelectorAll("[data-theme-state]")
      .forEach((label) => (label.textContent = mode === "system" ? `Системная (${effective === "dark" ? "тёмная" : "светлая"})` : mode === "dark" ? "Тёмная" : "Светлая"));
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
