() => {
  "use strict";

  const existing = window.__reeldown_runtime;
  if (existing?.installed) {
    return JSON.stringify(existing.publicState);
  }

  const runtime = {
    installed: true,
    template: null,
    running: false,
    resultText: "",
    publicState: {
      phase: "waiting-for-template",
      templateReady: false,
      pages: 0,
      comments: 0,
      requests: 0,
      resultLength: 0,
      message: "Open the comment panel to capture a normal page request."
    }
  };
  window.__reeldown_runtime = runtime;

  const isTopCommentRequest = (value) => {
    try {
      const path = new URL(String(value), location.href).pathname;
      return path.includes("/aweme/v1/web/comment/list/") &&
        !path.includes("/comment/list/reply/");
    } catch (_) {
      return false;
    }
  };

  const saveTemplate = (url, headers) => {
    if (runtime.template || !isTopCommentRequest(url)) return;
    runtime.template = {
      url: String(url),
      headers: headers && typeof headers === "object" ? { ...headers } : {}
    };
    Object.assign(runtime.publicState, {
      templateReady: true,
      phase: "ready",
      message: "Request template captured in page memory."
    });
  };

  const xhr = XMLHttpRequest.prototype;
  const originalOpen = xhr.open;
  const originalSend = xhr.send;
  const originalSetHeader = xhr.setRequestHeader;

  xhr.open = function (method, url) {
    this.__reeldownUrl = url;
    this.__reeldownHeaders = Object.create(null);
    return originalOpen.apply(this, arguments);
  };

  xhr.setRequestHeader = function (name, value) {
    if (this.__reeldownHeaders) {
      this.__reeldownHeaders[String(name)] = String(value);
    }
    return originalSetHeader.apply(this, arguments);
  };

  xhr.send = function () {
    if (!this.__reeldownInternal) {
      saveTemplate(this.__reeldownUrl, this.__reeldownHeaders);
    }
    return originalSend.apply(this, arguments);
  };

  const originalFetch = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === "string" || input instanceof URL
      ? String(input)
      : input?.url || "";
    if (isTopCommentRequest(url)) {
      try {
        const source = input instanceof Request ? input.headers : init?.headers;
        const headers = source ? Object.fromEntries(new Headers(source).entries()) : {};
        saveTemplate(url, headers);
      } catch (_) {
        saveTemplate(url, {});
      }
    }
    return originalFetch.apply(this, arguments);
  };

  // A page may have loaded its first comment page before injection.
  // Reuse that genuine request URL in memory; never export its query string.
  for (const entry of performance.getEntriesByType("resource").slice().reverse()) {
    if (isTopCommentRequest(entry.name)) {
      saveTemplate(entry.name, {});
      break;
    }
  }

  return JSON.stringify(runtime.publicState);
}
