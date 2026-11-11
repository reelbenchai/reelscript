() => {
  "use strict";

  if (window.__reeldown_silence) return "silenced";
  const mediaPrototype = HTMLMediaElement.prototype;
  const nativeMuted = Object.getOwnPropertyDescriptor(mediaPrototype, "muted");
  const nativeVolume = Object.getOwnPropertyDescriptor(mediaPrototype, "volume");

  // Keep the player silent even if it attempts to restore its saved volume.
  for (const [property, descriptor, forcedValue] of [
    ["muted", nativeMuted, true],
    ["volume", nativeVolume, 0]
  ]) {
    if (!descriptor?.get || !descriptor?.set || !descriptor.configurable) continue;
    Object.defineProperty(mediaPrototype, property, {
      ...descriptor,
      set() { descriptor.set.call(this, forcedValue); }
    });
  }
  const silence = (element) => {
    if (!(element instanceof HTMLMediaElement)) return;
    element.defaultMuted = true;
    if (!nativeMuted?.get?.call(element)) element.muted = true;
    if (nativeVolume?.get?.call(element) !== 0) element.volume = 0;
  };
  const scan = (root) => {
    silence(root);
    for (const element of root.querySelectorAll?.("video, audio") || []) silence(element);
  };
  const nativePlay = mediaPrototype.play;
  mediaPrototype.play = function () {
    silence(this);
    return nativePlay.apply(this, arguments);
  };
  for (const event of ["play", "playing", "loadedmetadata", "volumechange"]) {
    document.addEventListener(event, (entry) => silence(entry.target), true);
  }
  const observer = new MutationObserver((entries) => {
    for (const entry of entries) {
      for (const node of entry.addedNodes) scan(node);
    }
  });
  observer.observe(document, { childList: true, subtree: true });
  scan(document);
  window.__reeldown_silence = { observer };
  return "silenced";
}
