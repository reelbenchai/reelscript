# List pages

List mode returns metadata and navigable item page links. It never runs comment collection, calls playback endpoints, invokes the media downloader, or opens item details.

- Douyin: `/user/<profile>`. Remove query parameters when creating the task's list URL, including `vid`, `modal_id`, and tracking fields. Stay in list mode for a supplied user-page link.
- Hongguo: `/detail?series_id=<numeric-id>`. Keep only `series_id`. The `/player/...` URL is an episode detail page even when it displays an episode selector.

Prepare silence and task-owned browser cleanup as described in `browser-adapters.md`. Save the original link, navigate to the canonical list page once, and wait for its list container/route data. For Hongguo wait until a route object's `seriesDetail.series_id` matches the supplied ID. Do not load the player just to obtain the directory.

When local Python is available, a public Hongguo directory can instead be read with `python3 -I <skill-base>/scripts/hongguo_catalog.py <url> --cache-dir <task-cache>`. This path reads server-rendered JSON and needs no browser or login. It returns the same list contract, rejects wrong-series redirects and duplicate episode IDs, and preserves 64-bit IDs. The optional cache lasts one hour and contains only public directory fields. A challenge or missing route data should use the browser workflow once; do not loop HTTP requests. Douyin continues to use the browser or authorized App workflow.

Set configuration after navigation, retaining the originally supplied link:

```js
() => {
  window.__reeldown_config = { sourceUrl: "<original-list-link>", maxItems: 50 };
  return true;
}
```

Execute `scripts/page_collect_list.js` in the main world. Poll `window.__reeldown_runtime.publicState` every 10–20 seconds. `complete` means the final list JSON is in `resultText`; `error` supplies a safe `code` and `message` for the standard error JSON. Read long results in ordered chunks as in the detail workflow. Validate the returned JSON with `validate_result.py`; lists do not need a media file.

Hongguo reads the ordered `vid_list` already in the requested series's route data and returns all entries. `accessible_episode_count` is the website's declared access count, not a promise that the phone App has the same restriction. Listing later episodes does not request their playback.

Douyin reads only cards inside `[data-e2e="user-post-list"]`, preserving source encounter order and deduplicating by video ID. It scrolls the list with a delay only while fewer than the requested limit have been collected. The limit cannot exceed **50**, including Android sources. The collector stops after enough items, an explicit end, three rounds without new items, at most eight scrolls, or its time limit. Do not rerun the collector to accumulate more than 50 items for the same request. Do not collect page-wide video links: footer recommendations can belong to other authors.

An empty explicit works list is valid. A missing list, challenge, or failed site request is an error; it must not become an empty successful list. If some items were collected before loading failed, return that bounded sample with `stop_reason: "request_failed"`. `has_more: null` means the page does not establish whether more items exist. Never claim the list is complete merely because scrolling stopped. Do not refresh repeatedly when the site reports a service error; use one authorized alternative source or return the error.
