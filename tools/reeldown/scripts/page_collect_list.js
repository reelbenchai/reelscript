() => {
  "use strict";
  if (window.__reeldown_runtime?.running) return "already-running";
  const runtime = { installed: true, running: true, resultText: "", publicState: {
    phase: "list", code: null, items: 0, scrolls: 0, requests: 0, resultLength: 0,
    message: "Reading the selected list without opening its detail pages."
  } };
  window.__reeldown_runtime = runtime;
  const stop = (code, message) => { throw Object.assign(new Error(message), { code }); };
  const numeric = (v) => /^\d+$/.test(String(v ?? ""));
  const count = (v) => v !== null && v !== undefined && v !== "" &&
    Number.isSafeInteger(Number(v)) && Number(v) >= 0 ? Number(v) : null;
  const wait = () => new Promise(resolve => setTimeout(resolve, 2000 + Math.random() * 1500));
  const finish = (result) => {
    runtime.resultText = JSON.stringify(result);
    Object.assign(runtime.publicState, { phase: "complete", items: result.item_count,
      resultLength: runtime.resultText.length, message: "List collected. No detail page was opened or video downloaded." });
  };
  (async () => {
    let scrollNode, originalTop;
    try {
      let source;
      try { source = new URL(window.__reeldown_config?.sourceUrl); }
      catch (_) { stop("invalid_url", "Set sourceUrl to the original list link before collecting."); }
      if (!['https:', 'http:'].includes(source.protocol) || source.username || source.password) {
        stop("invalid_url", "The list link is invalid.");
      }
      if (['hongguoduanju.com', 'www.hongguoduanju.com'].includes(source.hostname) && source.pathname === '/detail') {
        const seriesId = source.searchParams.get('series_id');
        if (!numeric(seriesId)) stop("invalid_url", "The series ID is invalid.");
        if (!['hongguoduanju.com', 'www.hongguoduanju.com'].includes(location.hostname) || location.pathname !== '/detail' ||
            new URL(location.href).searchParams.get('series_id') !== seriesId) {
          stop("page_mismatch", "The loaded page does not match the requested series list.");
        }
        const route = Object.values(window._ROUTER_DATA?.loaderData || {}).find(v =>
          String(v?.seriesDetail?.series_id || '') === seriesId);
        if (!route || route.isSuccess === false) stop("list_unavailable", "The series directory is not available yet.");
        const series = route.seriesDetail;
        const ids = series.vid_list;
        if (!Array.isArray(ids) || !ids.length || !ids.every(numeric) || new Set(ids.map(String)).size !== ids.length) {
          stop("list_unavailable", "The series page has no usable episode directory.");
        }
        const total = count(series.episode_cnt);
        finish({ page_type: "list", platform: "hongguo", source_url: `https://hongguoduanju.com/detail?series_id=${seriesId}`,
          title: typeof series.series_name === 'string' ? series.series_name : null,
          item_count: ids.length, items: ids.map((id, i) => ({ item_id: String(id), title: null,
            page_url: `https://hongguoduanju.com/player/${seriesId}/${id}`, episode_number: i + 1 })),
          has_more: total === null ? null : total > ids.length,
          metadata: { source: "web", scope: "series_episodes", limit: null, total_count: total,
            accessible_episode_count: count(series.accessible_episode_cnt), stop_reason: "loaded" }
        });
        return;
      }
      const user = source.hostname === 'www.douyin.com' || source.hostname === 'douyin.com'
        ? source.pathname.match(/^\/user\/([^/]+)\/?$/) : null;
      if (!user) stop("invalid_url", "Only a Douyin user page or Hongguo series directory is a supported list.");
      if (!['douyin.com', 'www.douyin.com'].includes(location.hostname) ||
          location.pathname.replace(/\/$/, '') !== source.pathname.replace(/\/$/, '')) {
        stop("page_mismatch", "The loaded page does not match the requested user list.");
      }
      const configured = Math.floor(Number(window.__reeldown_config?.maxItems));
      const limit = Number.isFinite(configured) && configured > 0 ? Math.min(configured, 50) : 50;
      const found = new Map();
      let stagnant = 0, total = null, hasMore = null, reason = "stalled";
      const started = Date.now();
      for (let round = 0; round <= 8 && Date.now() - started < 45000; round++) {
        const root = document.querySelector('[data-e2e="user-post-list"]');
        if (!root) {
          if (/验证码|安全验证|完成验证|拖动滑块/.test(document.body?.innerText || '')) {
            stop("challenge_required", "Complete the visible browser challenge to read this list.");
          }
          if (round >= 3) stop("list_unavailable", "The user's works list is not available in this session.");
          await wait(); continue;
        }
        const before = found.size;
        const add = (id, title) => {
          if (!numeric(id) || found.size >= limit || found.has(String(id))) return;
          found.set(String(id), { item_id: String(id), title: typeof title === 'string' && title.trim() ? title.trim() : null,
            page_url: `https://www.douyin.com/video/${id}` });
        };
        // Scope strictly to the works list: recommendation/footer links are unrelated.
        for (const link of root.querySelectorAll('a[href]')) {
          let url;
          try { url = new URL(link.getAttribute('href'), location.href); } catch (_) { continue; }
          const match = ['douyin.com', 'www.douyin.com'].includes(url.hostname) && url.pathname.match(/^\/video\/(\d+)\/?$/);
          if (match) add(match[1], link.getAttribute('title') || link.querySelector('img[alt]')?.getAttribute('alt') || null);
          if (found.size >= limit) break;
        }
        // Some card variants navigate through React rather than an anchor.
        for (const card of root.querySelectorAll('li')) {
          if (found.size >= limit) break;
          const key = Object.keys(card).find(k => k.startsWith('__reactFiber$'));
          let fiber = key ? card[key] : null;
          for (let depth = 0; fiber && depth < 12; depth++, fiber = fiber.return) {
            const props = fiber.memoizedProps || {};
            for (const info of [props.awemeInfo, props.aweme, props.item, props.data]) {
              const id = info?.awemeId || info?.aweme_id;
              const author = info?.author?.secUid || info?.author?.sec_uid;
              if (author && author !== user[1]) continue;
              if (numeric(id)) add(id, info.desc || info.itemTitle || null);
            }
          }
        }
        runtime.publicState.items = found.size;
        const totalText = document.querySelector('[data-e2e="user-work-tab"]')?.innerText || '';
        const totalMatch = totalText.match(/^作品\s*(\d+)\s*$/);
        if (totalMatch) total = count(totalMatch[1]);
        if (found.size >= limit) { hasMore = total === null ? null : total > found.size; reason = 'limit'; break; }
        const text = root.innerText || '';
        if (/服务异常|加载失败|请求失败/.test(text)) {
          if (!found.size) stop("request_rejected", "The site's works list request failed. No unrelated videos were collected.");
          reason = 'request_failed'; break;
        }
        if (/没有更多|暂无作品|还没有作品|暂时没有作品/.test(text) || (total !== null && found.size >= total)) {
          hasMore = false; reason = 'exhausted'; break;
        }
        stagnant = found.size === before ? stagnant + 1 : 0;
        if (stagnant >= 3) break;
        if (round === 8) break;
        if (!scrollNode) {
          scrollNode = root;
          while (scrollNode && (!/auto|scroll/.test(getComputedStyle(scrollNode).overflowY) ||
                 scrollNode.scrollHeight <= scrollNode.clientHeight)) scrollNode = scrollNode.parentElement;
          scrollNode ||= document.scrollingElement;
          originalTop = scrollNode?.scrollTop;
        }
        if (scrollNode) scrollNode.scrollTop = scrollNode.scrollHeight;
        runtime.publicState.scrolls += 1;
        await wait();
      }
      if (!found.size && hasMore !== false) stop("list_unavailable", "No works could be verified in the user's list.");
      if (hasMore === null && total !== null) hasMore = total > found.size;
      finish({ page_type: "list", platform: "douyin", source_url: `https://www.douyin.com/user/${user[1]}`,
        title: document.title || null, item_count: found.size, items: [...found.values()], has_more: hasMore,
        metadata: { source: "web", scope: "user_posts", limit, total_count: total,
          accessible_episode_count: null, stop_reason: reason }
      });
    } catch (error) {
      const codes = ['invalid_url', 'page_mismatch', 'list_unavailable', 'request_rejected', 'challenge_required'];
      const known = codes.includes(error?.code);
      Object.assign(runtime.publicState, { phase: "error", code: known ? error.code : "list_unavailable",
        message: known ? error.message : "The requested list could not be read." });
    } finally {
      if (scrollNode && originalTop !== undefined) scrollNode.scrollTop = originalTop;
      runtime.running = false;
    }
  })();
  return "started";
}
