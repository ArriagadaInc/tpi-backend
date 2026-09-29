// Light/dark theme for CRM Lite (H3.3.7). Client-side only: the preference lives
// in localStorage and is never sent to the server.
//
// Loaded synchronously from <head> (not deferred) so the stored theme is applied
// to <html data-theme> before the body is painted, avoiding a flash of the light
// theme. It is an external same-origin file so it stays compatible with a strict
// `script-src 'self'` Content-Security-Policy.
(function (global) {
  "use strict";

  var STORAGE_KEY = "tpi-theme";
  var LIGHT = "light";
  var DARK = "dark";

  // Only the two known values are accepted; anything else (missing, tampered or
  // legacy) falls back to the light theme.
  function normalize(value) {
    return value === DARK ? DARK : LIGHT;
  }

  function getStorage() {
    try {
      return global.localStorage || null;
    } catch (error) {
      // Accessing localStorage can throw (privacy mode, blocked storage).
      return null;
    }
  }

  function readStored() {
    var storage = getStorage();
    if (!storage) {
      return LIGHT;
    }
    try {
      return normalize(storage.getItem(STORAGE_KEY));
    } catch (error) {
      return LIGHT;
    }
  }

  function store(theme) {
    var storage = getStorage();
    if (!storage) {
      return false;
    }
    try {
      storage.setItem(STORAGE_KEY, normalize(theme));
      return true;
    } catch (error) {
      // Quota or security errors: the theme still applies to the current page.
      return false;
    }
  }

  function current() {
    return normalize(global.document.documentElement.getAttribute("data-theme"));
  }

  function syncToggles(theme) {
    var toggles = global.document.querySelectorAll("[data-theme-toggle]");
    for (var index = 0; index < toggles.length; index += 1) {
      toggles[index].setAttribute("aria-pressed", theme === DARK ? "true" : "false");
    }
  }

  function apply(theme) {
    var normalized = normalize(theme);
    global.document.documentElement.setAttribute("data-theme", normalized);
    syncToggles(normalized);
    return normalized;
  }

  function toggle() {
    var next = current() === DARK ? LIGHT : DARK;
    apply(next);
    store(next);
    return next;
  }

  apply(readStored());

  global.document.addEventListener("DOMContentLoaded", function () {
    syncToggles(current());
  });

  global.document.addEventListener("click", function (event) {
    var target = event.target;
    if (target && typeof target.closest === "function" && target.closest("[data-theme-toggle]")) {
      toggle();
    }
  });

  global.TpiTheme = {
    STORAGE_KEY: STORAGE_KEY,
    normalize: normalize,
    readStored: readStored,
    store: store,
    current: current,
    apply: apply,
    toggle: toggle,
  };
})(window);
