(() => {
  const STORAGE_KEY = "hpt-theme";
  const mediaQuery = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)");

  const refreshButtons = (isDark) => {
    document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
      btn.textContent = isDark ? "\ud83c\udf1e Светлая тема" : "\ud83c\udf19 Тёмная тема";
      btn.setAttribute("aria-pressed", String(isDark));
      btn.title = isDark ? "Переключить на светлую тему" : "Переключить на тёмную тему";
    });
  };

  const applyTheme = (theme, { persist = true } = {}) => {
    const normalized = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = normalized;
    document.documentElement.style.colorScheme = normalized === "dark" ? "dark" : "light";
    if (persist) {
      localStorage.setItem(STORAGE_KEY, normalized);
    }
    refreshButtons(normalized === "dark");
  };

  const stored = localStorage.getItem(STORAGE_KEY);
  const prefersDark = mediaQuery && mediaQuery.matches;
  const initial = stored || (prefersDark ? "dark" : "light");
  applyTheme(initial, { persist: Boolean(stored) });

  if (mediaQuery) {
    mediaQuery.addEventListener("change", (event) => {
      const userChoice = localStorage.getItem(STORAGE_KEY);
      if (!userChoice) {
        applyTheme(event.matches ? "dark" : "light", { persist: false });
      }
    });
  }

  window.hptTheme = {
    set(theme) {
      applyTheme(theme);
    },
    toggle() {
      applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
    },
    refresh() {
      refreshButtons(document.documentElement.dataset.theme === "dark");
    },
  };

  window.addEventListener("DOMContentLoaded", () => {
    refreshButtons(document.documentElement.dataset.theme === "dark");
    document.querySelectorAll("[data-theme-toggle]").forEach((btn) =>
      btn.addEventListener("click", () => window.hptTheme.toggle())
    );
  });
})();
