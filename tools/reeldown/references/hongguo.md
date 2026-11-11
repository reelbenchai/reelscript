# Hongguo episode workflow

Supported hosts: `hongguoduanju.com` and `www.hongguoduanju.com`.

Supported paths:

- `/player/<series_id>` selects the episode the website opens by default (normally episode 1).
- `/player/<series_id>/<episode_id>` selects that episode.
- `/player/_/<episode_id>` is accepted only when the page resolves a concrete series and episode.

These `/player/...` links select one episode to download and inspect. A `/detail?series_id=...` link selects list mode instead; use [listing.md](listing.md) without downloading a video. A player page's episode selector does not change its detail mode. Also return the series page's existing episode directory as `episodes`, with episode number, episode ID, and canonical page URL. Do not automatically visit or download the other episodes.

1. Follow the main skill's silence and browser-ownership rules before navigation. Navigate to the supplied URL and wait for the route data to load. Use the browser provider's main-world JavaScript evaluation.
2. Set `window.__reeldown_config = { sourceUrl: "<original-supplied-player-link>" }` after navigation. Keep the original requested link, even if the website redirected to another episode. Execute `scripts/page_silence.js` as an additional guard, then execute `scripts/page_collect_hongguo.js`.
3. Poll `window.__reeldown_runtime.publicState` until `ready-to-download` or `error`. Read the private collected JSON from `window.__reeldown_runtime.resultText` using the same chunking mechanism as the Douyin workflow.
4. Follow [downloading.md](downloading.md): run `scripts/download_video.py` using `--platform hongguo --video-id <metadata.episode_id>` and the fixed invocation root. The helper downloads only the selected episode and replaces its temporary URL with `video_path`.
5. Validate the final JSON using `scripts/validate_result.py --root <invocation-directory>`. Remove private intermediate data, keep the downloaded MP4, close only task-owned browser resources, and return the public JSON.

The collector reads `_ROUTER_DATA.loaderData` for the selected episode's social data. It uses the website's public clear-playback endpoint `/api/video/protected/fallback-play-info?aid=8662` with the resolved episode's `item_id`, just as the website's fallback player does. The page URL contains a series ID; never substitute that ID for the episode ID.

The current website can provide `blob:` media from its normal player. The collector retains only an HTTP(S) clear-media URL from the public playback response as private download input. The skill returns the downloaded file's relative `video_path`. It does not process encrypted media or authentication keys.

Use the collector's `publicState.code` for failures. `episode_mismatch` means the requested episode was redirected or replaced; the collector makes no playback request for the replacement. `web_access_limited` means the public playback endpoint explicitly rejected this episode as unavailable. Do not refresh or repeat the same public request. A matching authorized Android App source may be tried once using `mobile.md`; App playback availability alone does not supply a downloadable file. Other playback failures use `video_unavailable`.

For a caller-requested mobile device/signature or capture workflow, follow [android-capture.md](android-capture.md). It can consume a genuinely readable captured App response; public device properties and a separate anonymous-client registration do not establish the phone's App credentials. Reuse a captured response before considering a fresh API request.

When an explicitly authorized series batch hits a confirmed website access boundary, retain the directory and completed items, report remaining items as unavailable from that source, and stop trying the same rejected route for every later episode. Do not hard-code an access limit of five: use the current page's `seriesDetail.accessible_episode_cnt` and observed response. Do not download a redirected first episode under a later episode's filename.

The public page currently embeds a limited preview of comments and directs users to the App for more. Read this preview once, filter to strictly more than 100 likes, and return up to 3 entries. Do not invent pagination or imply a global top-three ranking. Its total comment count can be much higher than the preview size.

The like count and comment count are episode-level. The favorite count is series-level. Preserve these distinctions in the `metadata` described by `output-schema.md`.

Read `seriesDetail.vid_list` from the same route object to build `episodes` in source order. Index 0 is episode 1. Use `https://hongguoduanju.com/player/<series_id>/<episode_id>` for each `page_url`; this is a navigable page link, not a direct media download URL.
