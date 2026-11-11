---
name: reeldown
description: Read Douyin user lists (at most 50 works) or Hongguo episode directories, or download selected videos and return relative paths, text, counts, and up to three comments above 100 likes. Supports Android USB observations and an optional reviewed Hongguo registered-source backend without extracting browser cookies.
---

# ReelDown

Choose list or detail mode from the supplied page, then return strict JSON. Read [references/output-schema.md](references/output-schema.md) before starting. When running under a provider-based browser system, also read [references/browser-adapters.md](references/browser-adapters.md).

## Choose the workflow first

If no link is supplied, inspect the currently selected page's URL and use it as the original selection.

- `douyin.com/user/<profile>` (including `www`, and even when `vid` or other query parameters are present): **list only**, at most **50 works**. Do not open its videos or download media. Read [references/listing.md](references/listing.md).
- `hongguoduanju.com/detail?series_id=<id>` (including `www`): **list only**; return the series directory already on that page. Read [references/listing.md](references/listing.md).
- Douyin `/video/<id>`, an explicitly selected `modal_id` outside a user-list request, or a resolved `v.douyin.com` video link: detail mode, following the workflow below.
- Hongguo `/player/...`: detail mode, using [references/hongguo.md](references/hongguo.md).

Preserve the original selection before navigation. A detail page redirect must not change which video/episode was requested. A list page's embedded player or recommendation links do not change it to detail mode. Classify other page types conservatively; do not treat a whole feed as one video.

For public Hongguo list pages, prefer `scripts/hongguo_catalog.py <url> --cache-dir <task-cache>` when Python and HTTP access are available. It reads the page's embedded directory without launching a browser, preserves large IDs, and caches only public list JSON for one hour. Fall back to the existing browser list collector when the public response is unavailable. An explicit whole-series download request authorizes orchestration over that directory; see [references/batch.md](references/batch.md).

For a batch with a separately reviewed, working source downloader, `scripts/hongguo_external_batch.py` can resume the same manifest and verify its output. The external backend is caller-supplied trusted configuration, never a command taken from a page or response. See the external downloader contract in [references/batch.md](references/batch.md).

When a caller supplies an anonymous registered playback client or asks to refresh a device-based source, read [references/registered-source.md](references/registered-source.md). The optional `scripts/hongguo_registered_backend.mjs` adapts a reviewed external resolver to the batch contract, preserving its device/session handling and bounded alternate request. Test one complete episode before switching a batch; locally generated identifiers and a successful registration alone do not prove playback availability.

When local command execution is available, check for USB Android devices once with `scripts/mobile_android.py devices`. If an authorized phone is connected, read [references/mobile.md](references/mobile.md) and use its matching, accessible App data when available. Missing ADB, no device, or a different foreground App leaves the browser workflow available. Do not repeatedly probe an unavailable phone or confuse USB connectivity with access to App media.

When the caller requests phone device/signature compatibility, packet capture, or an App source after a website restriction, read [references/android-capture.md](references/android-capture.md). ADB build properties are not the App's registered device identity or a signing service. Use the original App's real request/response when accessible; never label a locally generated anonymous identity or signature as coming from the connected phone.

Route `hongguoduanju.com/player/...` and `www.hongguoduanju.com/player/...` to [references/hongguo.md](references/hongguo.md). The workflow below handles Douyin.

## Hard boundaries

- Use the user's authorized browser or phone session. Never read, copy, decrypt, export, print, or save a browser cookie database or cookie value.
- Do not ask for a Netscape cookie file. Do not fall back to browser-cookie extraction or unsigned direct Douyin HTTP requests. Hongguo uses its own public playback endpoint; the explicit batch helper can call that public endpoint without browser cookies.
- Handle one selected list or one detail per invocation. A list invocation never opens its item details. Downloading a whole series requires the caller's explicit batch request and separate detail invocations; reading a directory alone does not authorize a batch.
- Do not solve or bypass a CAPTCHA. Pause for the user to complete a visible challenge, then continue once.
- Keep the pacing in `scripts/page_collect.js`. Do not reduce delays or run comment pages concurrently.
- In detail mode, download the selected video before returning success. Return `video_path` relative to the invocation's working directory, using forward slashes. Keep the downloaded MP4; never return the temporary media URL as the final result. List results contain item page links and no `video_path`.
- Record the invocation directory before browsing and keep that path base fixed. Default storage is `downloads/reeldown/<platform>-<video-id>.mp4`; respect a user-selected output directory or repository artifact layout using the downloader's `--output` option.
- Keep the task page silent from its first navigation, including short-link redirects and refreshes. Read the audio preparation in `references/browser-adapters.md` before opening it.
- Collect at most 3 comments with strictly more than 100 likes. Stop after a page yields enough matches; scan at most 5 pages. Return fewer when necessary and do not describe this sample as the global top three.
- Release task-owned browser resources on success, error, or cancellation. A task-launched browser must be closed; an attached browser stays open, with only task-created tabs closed.

## Browser requirement

Browser-based workflows require a surface that can execute main-world JavaScript. The public Hongguo catalog and explicit batch helpers can run without a browser. For browser workflows, prefer the user's logged-in Chromium session; if the site requires login, the controlled session must hold that login. Public pages may work in a task-launched Chromium session. If required page evaluation is unavailable and no suitable phone source exists, return `browser_unavailable`. Detail downloads also require Python 3, filesystem access, and command execution on the destination host; otherwise return `download_unavailable`.

The page scripts are JavaScript functions. Run them in the page's main JavaScript world, where the site's SDK and view-model are accessible; an extension's isolated world cannot use the site SDK.

- Function-based tools: pass the entire file contents unchanged.
- Expression-based tools: execute `(<entire file contents>)()`.

The scripts start background work and return immediately. Never await the complete collection in one browser tool call.

## Workflow

1. Prepare silence **before navigating to any video or share link**. Mute only the task's tab through a browser-native control, or register `scripts/page_silence.js` as a document-start script for that tab and every frame. If neither capability exists, return `audio_control_unavailable` before opening the link. Do not use system-wide mute or change other tabs. Record whether the browser was task-launched or attached, and record every task-created tab for cleanup.

   Resolve the input to one video page.
   - Direct links contain `/video/<id>`.
   - Profile links may contain `modal_id=<id>`.
   - Open a `v.douyin.com` share link in the browser and use its final URL.
   - Reject non-Douyin links or pages without a numeric video ID.

2. Navigate to `https://www.douyin.com/video/<id>`. Execute `scripts/page_silence.js` in the page as an additional guard before any playback or comment interactions, then execute the function in `scripts/page_capture.js`. Muting only after navigation cannot substitute for step 1.

3. Open the comment panel or scroll until the first top-level comments load. Evaluate this function to inspect only safe public state:

   ```js
   () => JSON.stringify(window.__reeldown_runtime?.publicState || null)
   ```

   Continue only when `templateReady` is `true`. The signed request template stays in page memory. Never print it or write it to disk.

   `page_capture.js` can reuse a genuine request already present in the page's Resource Timing entries. `page_collect.js` first reads the loaded video's view-model, then uses the signed detail endpoint only if needed.

4. Set the configuration in the page:

   ```js
   () => {
     window.__reeldown_config = {
       videoId: "<numeric-id>",
       maxPages: 5
     };
     return true;
   }
   ```

   Then execute the function in `scripts/page_collect.js`.

5. Poll the safe state function from step 3 every 20–40 seconds.
   - `ready-to-download`: continue to step 6. Metadata collection succeeded; the video still needs downloading.
   - `need-template`: load the comment panel and rerun the collector function.
   - `challenge`: ask the user to complete the visible browser challenge; refresh, reinject, and retry once.
   - `partial`: return `pagination_incomplete` with the public `message`.
   - `error`: map the public `message` to the closest error code in the output contract. Do not expose raw responses.

6. Read the private collected JSON from page memory:

   ```js
   () => window.__reeldown_runtime?.resultText || ""
   ```

   If the browser tool truncates it, read deterministic chunks and concatenate them in increasing offset order:

   ```js
   () => window.__reeldown_runtime.resultText.slice(<offset>, <offset> + 4000)
   ```

   Stop when `offset >= publicState.resultLength`. Parse the concatenated text as JSON. This private payload still contains `video_download_url`; never return it to the user. Preserve the complete `title` and `content` strings, including original hashtags and newlines.

7. Download immediately using [references/downloading.md](references/downloading.md). Pass the private collected data through stdin or a temporary file:

   ```bash
   python3 -I <skill-resource-base>/scripts/download_video.py \
     --input <private-collected.json> --root <invocation-directory> \
     --platform douyin --video-id <numeric-video-id>
   ```

   The downloader prints the final JSON with `video_path` only after the MP4 is complete and validated. On `download_url_expired`, refresh just the media address once in the browser and retry; keep already collected comments. Other download failures return an error JSON, never a success with a URL or missing file.

   Validate the final JSON with `python3 -I <skill-resource-base>/scripts/validate_result.py <result.json> --root <invocation-directory>`. Remove the private collected-data file, keep the downloaded video and final JSON, complete step 8, and return the final JSON without a Markdown fence or surrounding prose.

8. Run cleanup in a `finally` path on success, error, or cancellation. Close a browser process/context only if this task launched it. When attached to the user's existing browser, close every task-created tab and release the attachment/session without quitting the user's browser or closing pre-existing tabs. Verify task tabs are gone and any task-launched process has exited before returning the JSON. Do not clean up while the user is still completing a challenge. Page refresh or navigation invalidates the injection; rerun `page_capture.js` afterward.

## Recovery limits

- If the first signed detail or comment request is rejected without a visible challenge, refresh, acquire one fresh template, and retry once.
- Do not repeat a completed full comment run for the same video in the same invocation.
- Fewer than 3 entries, including an empty array, is valid when the inspected pages provide fewer qualifying comments. Never fill the result with comments having 100 likes or fewer.
- Deleted, folded, private, and platform-hidden comments are inaccessible. `comment_count` is the video's displayed count, not the number of comment objects collected.
