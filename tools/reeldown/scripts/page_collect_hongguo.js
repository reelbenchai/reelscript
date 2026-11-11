() => {
  "use strict";

  const host = location.hostname.toLowerCase();
  const match = location.pathname.match(/^\/player\/(\d+|_)\/?(\d+)?\/?$/);
  if (!['hongguoduanju.com', 'www.hongguoduanju.com'].includes(host) || !match) return "invalid-url";
  const previous = window.__reeldown_runtime;
  if (previous?.running) return "already-running";
  const runtime = {
    installed: true, running: true, resultText: "",
    publicState: { phase: "detail", code: null, pages: 0, comments: 0, requests: 0, resultLength: 0, message: "Reading episode data." }
  };
  window.__reeldown_runtime = runtime;

  const count = (value) => {
    if (value === undefined || value === null || value === "") return null;
    const n = Number(value);
    return Number.isSafeInteger(n) && n >= 0 ? n : null;
  };
  const httpUrl = (value) => typeof value === "string" && /^https?:\/\//i.test(value);
  const stop = (code, message) => { throw Object.assign(new Error(message), { code }); };

  (async () => {
    try {
      // Preserve the supplied selection across the site's episode redirects.
      let source;
      try { source = new URL(window.__reeldown_config?.sourceUrl); }
      catch (_) { stop("invalid_url", "Set sourceUrl to the original episode link before collecting."); }
      const requested = source.pathname.match(/^\/player\/(\d+|_)\/?(\d+)?\/?$/);
      if (!['hongguoduanju.com', 'www.hongguoduanju.com'].includes(source.hostname) ||
          !['http:', 'https:'].includes(source.protocol) || source.username || source.password || !requested) {
        stop("invalid_url", "The supplied link is not a supported episode page.");
      }
      const route = Object.values(window._ROUTER_DATA?.loaderData || {}).find((value) =>
        value && value.series_id && value.vid &&
        (match[1] === "_" || String(value.series_id) === match[1]) &&
        (!match[2] || String(value.vid) === match[2])
      );
      if (!route || route.isSuccess === false) throw new Error("The episode page data is unavailable.");
      const episodeId = String(route.vid);
      const seriesId = String(route.series_id);
      runtime.publicState.webAccessibleEpisodeCount = count(route.seriesDetail?.accessible_episode_cnt);
      if ((requested[1] !== "_" && requested[1] !== seriesId) || (requested[2] && requested[2] !== episodeId)) {
        stop("episode_mismatch", "The website redirected to another episode. No video was downloaded.");
      }
      // The page's directory is already ordered by episode; no per-episode fetch.
      const episodeIds = route.seriesDetail?.vid_list;
      const episodes = Array.isArray(episodeIds) && episodeIds.every((id) => /^\d+$/.test(String(id)))
        ? episodeIds.map((id, index) => ({
          episode_number: index + 1,
          episode_id: String(id),
          page_url: `https://hongguoduanju.com/player/${seriesId}/${id}`
        }))
        : null;
      let mediaUrl = route.videoDetail?.main_url || route.videoData?.main_url || "";

      if (!httpUrl(mediaUrl)) {
        // This public endpoint is used by the website's normal clear-video player.
        // Return only its clear media URL; never return a blob or encrypted stream.
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 25000);
        try {
          runtime.publicState.requests += 1;
          const response = await fetch("/api/video/protected/fallback-play-info?aid=8662", {
            method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ item_id: episodeId }), signal: controller.signal
          });
          if (!response.ok) {
            let limited = false;
            if (response.status === 403) {
              try { limited = (await response.json()).error === "public_fallback_unavailable"; } catch (_) {}
            }
            stop(limited ? "web_access_limited" : "video_unavailable", limited
              ? "This episode is unavailable through the website's public playback source."
              : "The episode playback request was rejected.");
          }
          const payload = await response.json();
          if (payload.base_resp?.StatusCode && payload.base_resp.StatusCode !== 0) {
            throw new Error("The episode playback request was rejected.");
          }
          mediaUrl = payload.main_url;
        } finally { clearTimeout(timer); }
      }
      if (!httpUrl(mediaUrl)) throw new Error("No clear downloadable episode address was returned.");

      const episode = route.episodeSocialInfo || {};
      const reviews = episode.reviews || {};
      const list = Array.isArray(reviews.reviews) ? reviews.reviews : [];
      const unique = new Map();
      for (const review of list) {
        const content = String(review?.content || "").trim();
        const likes = count(review?.digg_count);
        if (!content || likes === null || likes <= 100) continue;
        const id = String(review.review_id || review.id || `${content}\u0000${review.create_time || ""}`);
        unique.set(id, { content, like_count: likes, time: count(review.create_time) || 0, id });
      }
      const comments = [...unique.values()].sort((a, b) =>
        b.like_count - a.like_count || b.time - a.time || a.id.localeCompare(b.id)
      ).slice(0, 3).map(({ content, like_count }) => ({ content, like_count }));
      const result = {
        video_download_url: mediaUrl,
        video_like_count: count(episode.episode_like_count),
        comment_count: count(reviews.total_count),
        favorite_count: count(route.seriesSocialInfo?.series_favorite_count),
        top_comments: comments,
        episodes,
        metadata: {
          platform: "hongguo", series_id: seriesId, episode_id: episodeId,
          video_like_count_scope: "episode", comment_count_scope: "episode", favorite_count_scope: "series",
          comment_scope: "web_preview", comments_examined: list.length,
          comments_complete: reviews.has_more === false || reviews.has_more === 0 || count(reviews.total_count) === 0,
          ranking_scope: "collected_comments", comment_page_limit: 5,
          unavailable_fields: []
        }
      };
      for (const field of ["video_like_count", "comment_count", "favorite_count", "episodes"]) {
        if (result[field] === null) result.metadata.unavailable_fields.push(field);
      }
      runtime.resultText = JSON.stringify(result);
      Object.assign(runtime.publicState, {
        phase: "ready-to-download", pages: 1, comments: list.length, resultLength: runtime.resultText.length,
        message: "Metadata collected. Download the episode before returning the final JSON."
      });
    } catch (error) {
      const known = ['invalid_url', 'episode_mismatch', 'web_access_limited', 'video_unavailable'].includes(error?.code);
      Object.assign(runtime.publicState, { phase: "error", code: known ? error.code : "video_unavailable",
        message: known ? error.message : "The episode data or clear playback address is unavailable in this browser session." });
    } finally { runtime.running = false; }
  })();
  return "started";
}
