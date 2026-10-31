(function () {
  try {
    var KEY = "librarian.ui_theme";
    var FONT_KEY = "librarian.ui_font_step";
    var STEPS = ["15px", "16px", "17px", "18.5px", "20px", "22px"];
    var stored = localStorage.getItem(KEY) || "lights_up";
    if (stored !== "lights_up" && stored !== "lights_down" && stored !== "system") {
      stored = "lights_up";
    }
    var effective = stored;
    if (stored === "system") {
      effective =
        window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches
          ? "lights_up"
          : "lights_down";
    }
    var attr = effective === "lights_up" ? "lights-up" : "lights-down";
    document.documentElement.setAttribute("data-theme", attr);
    document.documentElement.style.colorScheme = effective === "lights_up" ? "light" : "dark";
    var step = parseInt(localStorage.getItem(FONT_KEY) || "0", 10);
    if (!isFinite(step) || step < 0) step = 0;
    if (step > 5) step = 5;
    document.documentElement.style.setProperty("--base-font-size", STEPS[step]);
    document.documentElement.dataset.fontStep = String(step);
  } catch (e) {
    document.documentElement.setAttribute("data-theme", "lights-up");
    document.documentElement.style.colorScheme = "light";
  }
})();
