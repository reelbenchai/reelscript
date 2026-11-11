() => {
  "use strict";

  const runtime = window.__reeldown_runtime;
  const config = window.__reeldown_config || {};

  if (!runtime?.installed) return "capture-not-installed";
  if (!runtime.template) {
    Object.assign(runtime.publicState, {
      phase: "need-template",
      message: "Open the comment panel and wait for comments to load."
    });
    return "need-template";
  }
  if (runtime.running) return "already-running";

  const videoId = String(config.videoId || "");
  const maxPages = Math.max(1, Math.min(Math.floor(Number(config.maxPages)) || 5, 5));
  const commentLimit = 3;
  const minimumLikesExclusive = 100;
  if (!/^\d{10,30}$/.test(videoId)) {
    Object.assign(runtime.publicState, {
      phase: "error",
      message: "The video ID is invalid."
    });
    return "invalid-config";
  }

  runtime.running = true;
  runtime.resultText = "";
  Object.assign(runtime.publicState, {
    phase: "starting",
    pages: 0,
    comments: 0,
    qualifyingComments: 0,
    requests: 0,
    resultLength: 0,
    stopReason: "",
    message: "Starting collection."
  });

  const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
  const asCount = (value) => {
    const parsed = Number.parseInt(value ?? 0, 10);
    return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
  };
  const pace = async () => {
    if (runtime.publicState.requests % 15 === 0) {
      await sleep(8000 + Math.random() * 7000);
    } else {
      await sleep(2000 + Math.random() * 2000);
    }
  };

  const unsignedUrl = (path, patch, removeBusinessFields = false) => {
    const url = new URL(runtime.template.url, location.href);
    url.pathname = path || url.pathname;

    for (const key of [...url.searchParams.keys()]) {
      const lower = key.toLowerCase();
      if (lower === "a_bogus" || lower === "x-bogus" || lower === "_signature") {
        url.searchParams.delete(key);
      }
    }

    if (removeBusinessFields) {
      for (const key of ["cursor", "count", "comment_id", "item_id"]) {
        url.searchParams.delete(key);
      }
    }

    const liveToken = localStorage.getItem("xmst");
    if (liveToken && url.searchParams.has("msToken")) {
      url.searchParams.set("msToken", liveToken);
    }

    for (const [key, value] of Object.entries(patch || {})) {
      url.searchParams.set(key, String(value));
    }
    return `${url.pathname}${url.search}`;
  };

  const requestJson = (url) => new Promise((resolve, reject) => {
      runtime.publicState.requests += 1;
      let settled = false;
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        callback(value);
      };
      const timer = setTimeout(
        () => finish(reject, new Error("The page request timed out.")),
        25000
      );
      const request = new XMLHttpRequest();
      request.open("GET", url, true);
      request.__reeldownInternal = true;
      request.withCredentials = true;

      const blocked = new Set([
        "accept-encoding", "connection", "content-length", "cookie", "host",
        "origin", "referer", "user-agent"
      ]);
      for (const [name, value] of Object.entries(runtime.template.headers || {})) {
        const lower = String(name).toLowerCase();
        if (blocked.has(lower) || lower.startsWith("sec-")) continue;
        try { request.setRequestHeader(name, value); } catch (_) {}
      }

      request.onload = () => {
        try {
          const data = JSON.parse(request.responseText);
          if (request.status >= 200 && request.status < 300 && data?.status_code === 0) {
            finish(resolve, data);
          } else {
            finish(reject, new Error("The signed page request was rejected."));
          }
        } catch (_) {
          finish(reject, new Error("The page returned an unreadable response."));
        }
      };
      request.onerror = () => finish(reject, new Error("The page request failed."));
      request.send();
  });

  const firstHttpUrl = (address) => {
    const values = Array.isArray(address?.url_list) ? address.url_list : [];
    return values.find((value) => typeof value === "string" && /^https?:\/\//.test(value)) || "";
  };

  const bestVideoUrl = (detail) => {
    const video = detail?.video;
    if (!video || typeof video !== "object") return "";
    const candidates = [];
    const add = (address, sourcePriority, bitrate = 0) => {
      const url = firstHttpUrl(address);
      if (!url) return;
      const width = asCount(address?.width || video.width);
      const height = asCount(address?.height || video.height);
      const size = asCount(address?.data_size);
      candidates.push({ url, score: [sourcePriority, width * height, asCount(bitrate), size] });
    };

    for (const rate of Array.isArray(video.bit_rate) ? video.bit_rate : []) {
      add(rate?.play_addr, 3, rate?.bit_rate);
    }
    add(video.play_addr, 2);
    add(video.play_addr_h264, 2);
    add(video.download_addr, 1);

    candidates.sort((left, right) => {
      for (let index = 0; index < left.score.length; index += 1) {
        if (left.score[index] !== right.score[index]) {
          return right.score[index] - left.score[index];
        }
      }
      return left.url.localeCompare(right.url);
    });
    return candidates[0]?.url || "";
  };

  const looksLikeChallenge = () => {
    const text = document.body?.innerText || "";
    return /验证码|安全验证|完成验证|拖动滑块/.test(text);
  };

  const loadedDetail = () => {
    // Read only the current video's view-model; no cookie or account stores.
    const elements = document.querySelectorAll('[data-e2e="detail-video-info"], [data-e2e="video-detail"]');
    for (const element of elements) {
      const key = Object.keys(element).find((name) => name.startsWith("__reactFiber$"));
      let fiber = key ? element[key] : null;
      for (let depth = 0; fiber && depth < 40; depth += 1, fiber = fiber.return) {
        const info = fiber.memoizedProps?.awemeInfo;
        if (String(info?.awemeId || "") !== videoId || !info?.stats || !info?.video) continue;
        const video = info.video;
        const urls = Array.isArray(video.playAddr)
          ? video.playAddr.map((entry) => typeof entry === "string" ? entry : entry?.src).filter(Boolean)
          : [];
        if (!urls.some((url) => /^https?:\/\//.test(url))) continue;
        return {
          aweme_id: videoId,
          item_title: info.itemTitle || info.title || (
            typeof info.desc === "string" && typeof info.caption === "string" &&
            info.caption && info.desc.endsWith(info.caption)
              ? info.desc.slice(0, info.desc.length - info.caption.length).trim()
              : ""
          ),
          desc: typeof info.desc === "string" ? info.desc : (typeof info.name === "string" ? info.name : ""),
          statistics: {
            digg_count: info.stats.diggCount,
            comment_count: info.stats.commentCount,
            collect_count: info.stats.collectCount
          },
          video: {
            width: video.width,
            height: video.height,
            play_addr: { url_list: urls, width: video.width, height: video.height }
          }
        };
      }
    }
    return null;
  };

  (async () => {
    try {
      runtime.publicState.phase = "detail";
      runtime.publicState.message = "Reading video details.";
      const detailUrl = unsignedUrl(
        "/aweme/v1/web/aweme/detail/",
        { aweme_id: videoId },
        true
      );
      let detail = loadedDetail();
      if (!detail) {
        const detailPayload = await requestJson(detailUrl);
        detail = detailPayload?.aweme_detail;
        await pace();
      }
      const stats = detail?.statistics;
      if (detail && String(detail.aweme_id || "") !== videoId) {
        throw new Error("The returned video does not match the requested video ID.");
      }
      const videoUrl = bestVideoUrl(detail);
      if (!detail || !stats || !videoUrl) {
        throw new Error("The video detail response has no usable media address or statistics.");
      }

      runtime.publicState.phase = "comments";
      runtime.publicState.message = "Looking for three comments with more than 100 likes.";
      const originalPath = new URL(runtime.template.url, location.href).pathname;
      const commentsById = new Map();
      const seenIds = new Set();
      let cursor = 0;
      let hasMore = true;
      let page = 0;
      let stagnantPages = 0;
      let stopReason = "exhausted";

      while (hasMore && page < maxPages) {
        const url = unsignedUrl(originalPath, {
          aweme_id: videoId,
          cursor,
          count: 20
        });
        const payload = await requestJson(url);
        const comments = Array.isArray(payload.comments) ? payload.comments : [];
        let added = 0;

        for (const comment of comments) {
          const content = String(comment?.text || "").trim();
          const rawId = String(comment?.cid || "");
          const fallbackId = `${content}\u0000${comment?.create_time || 0}`;
          const id = rawId || fallbackId;
          if (!seenIds.has(id)) added += 1;
          seenIds.add(id);
          if (!content) continue;
          const likeCount = asCount(comment?.digg_count);
          if (likeCount <= minimumLikesExclusive) {
            commentsById.delete(id);
            continue;
          }
          commentsById.set(id, {
            id,
            content,
            like_count: likeCount,
            create_time: asCount(comment?.create_time)
          });
        }

        page += 1;
        runtime.publicState.pages = page;
        runtime.publicState.comments = seenIds.size;
        runtime.publicState.qualifyingComments = commentsById.size;
        stagnantPages = added === 0 ? stagnantPages + 1 : 0;

        if (commentsById.size >= commentLimit) {
          stopReason = "target-reached";
          break;
        }

        const nextCursor = Number(payload.cursor);
        hasMore = Boolean(payload.has_more);
        if (hasMore && comments.length === 0) {
          stopReason = "empty-page";
          break;
        }
        if (hasMore && (!Number.isFinite(nextCursor) || nextCursor === Number(cursor))) {
          stopReason = "cursor-stalled";
          break;
        }
        if (hasMore && stagnantPages >= 3) {
          stopReason = "repeated-pages";
          break;
        }
        cursor = nextCursor;
        if (hasMore && page < maxPages) await pace();
      }

      if (hasMore && stopReason === "exhausted" && page >= maxPages) {
        stopReason = "page-limit";
      }

      const topComments = [...commentsById.values()]
        .sort((left, right) =>
          right.like_count - left.like_count ||
          right.create_time - left.create_time ||
          left.id.localeCompare(right.id)
        )
        .slice(0, commentLimit)
        .map(({ content, like_count }) => ({ content, like_count }));

      const result = {
        video_download_url: videoUrl,
        title: String(detail.item_title || detail.preview_title || (detail.desc || "").split("\n")[0]),
        content: String(detail.desc || ""),
        video_like_count: asCount(stats.digg_count),
        comment_count: asCount(stats.comment_count),
        favorite_count: asCount(stats.collect_count),
        top_comments: topComments
      };
      runtime.resultText = JSON.stringify(result);
      Object.assign(runtime.publicState, {
        phase: "ready-to-download",
        resultLength: runtime.resultText.length,
        stopReason,
        message: "Metadata collected. Download the video before returning the final JSON."
      });
    } catch (error) {
      const challenge = looksLikeChallenge();
      Object.assign(runtime.publicState, {
        phase: challenge ? "challenge" : "error",
        message: challenge
          ? "Complete the visible browser challenge, then retry once."
          : String(error?.message || "Collection failed.")
      });
    } finally {
      runtime.running = false;
    }
  })();

  return "started";
}
