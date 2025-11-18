(() => {
  const STORAGE_KEY = "hpt-theme";

  const refreshButtons = (isDark) => {
    document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
      btn.textContent = isDark ? "\ud83c\udf1e Светлая тема" : "\ud83c\udf19 Тёмная тема";
      btn.setAttribute("aria-pressed", String(isDark));
      btn.title = isDark ? "Переключить на светлую тему" : "Переключить на тёмную тему";
    });
  };

  const applyTheme = (theme) => {
    const normalized = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = normalized;
    document.documentElement.style.colorScheme = normalized === "dark" ? "dark" : "light";
    localStorage.setItem(STORAGE_KEY, normalized);
    refreshButtons(normalized === "dark");
  };

  const stored = localStorage.getItem(STORAGE_KEY);
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const initial = stored || (prefersDark ? "dark" : "light");
  applyTheme(initial);

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
