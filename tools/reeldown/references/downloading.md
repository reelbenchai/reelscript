# Download before returning JSON

The page collectors finish in `ready-to-download` and retain a private JSON payload in `window.__reeldown_runtime.resultText`. It contains a temporary `video_download_url`. Download immediately; never expose that private payload as the skill's final answer.

Record the calling Session's working directory before browsing. This is the fixed root for both saving the MP4 and interpreting its returned relative path. Default files are `downloads/reeldown/douyin-<video_id>.mp4` or `downloads/reeldown/hongguo-<episode_id>.mp4`. Use `--output <relative-path>.mp4` for a caller-specified directory or repository artifact convention. Do not place outputs in the skill bundle.

Run the local Python helper with the private data supplied through stdin or a temporary JSON file:

```bash
python3 -I <skill-resource-base>/scripts/download_video.py \
  --input <private-collected.json> --root <invocation-directory> \
  --platform douyin --video-id <video-id>
```

For Hongguo use `--platform hongguo --video-id <metadata.episode_id>`. A series ID is not an episode ID. The series directory stays in the final JSON without downloading the other episodes.

The helper follows the media URL using the platform's Referer, streams the response into a private `.part` file, checks the complete transfer and MP4 container, and checks the video stream with `ffprobe` when available. It then publishes the file without overwriting an existing video. A name collision receives a unique suffix. It prints final JSON with `video_path` and removes `video_download_url`; stdout contains no progress logs or raw HTTP errors.

For a real authorized App **media** request, optionally add `--request-context <private-context.json>`. This file has `source: "android_app_capture"`, `video_id` matching `--video-id`, optional `headers`, and optional `expected_duration` in seconds from the full episode's metadata. Allowed headers are `User-Agent`, `Referer`, `Origin`, `Accept`, `Authorization`, and `Cookie`; include only those actually needed by that captured CDN request. Browser cookie extraction remains prohibited. Never supply API signing headers as media headers or write this private file into the skill or public output. Authorization/Cookie headers are dropped across origin-changing redirects, and HTTPS-to-HTTP redirects are rejected.

With `expected_duration`, FFprobe is required and the complete file must match within the larger of two seconds or two percent. The helper rejects known encrypted media tags and does not implement media decryption or HLS remuxing. An unavailable clear source produces an error, even when a protected video plays successfully in the App.

Validate that final JSON using the same root:

```bash
python3 -I <skill-resource-base>/scripts/validate_result.py <result.json> \
  --root <invocation-directory>
```

The file must exist, be non-empty, and remain inside the root. Public JSON must not contain an absolute path, media URL, `..` traversal, or `.part` file. Preserve Douyin `title` and `content` and the collected social/comment data throughout the conversion. Unknown counts and Hongguo directory metadata retain their existing meanings.

On `download_url_expired`, refresh only the media address in the browser and retry once. Preserve the already collected comments; never repeat the whole comment crawl just to renew a media URL. For any other download error, return the helper's error JSON. If Python, local filesystem access, or command execution is unavailable, return `download_unavailable` instead of returning a link.

After success, keep the MP4 and final JSON. Delete any private collected-data file and close task-owned browser resources. The helper removes incomplete `.part` data on failure; never invent a local path for an incomplete download.
