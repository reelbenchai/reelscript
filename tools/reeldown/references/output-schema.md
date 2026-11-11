# Output contract

Return raw JSON without a Markdown fence or surrounding prose.

## List success

Lists return page links and do not download media:

```json
{
  "page_type": "list",
  "platform": "douyin",
  "source_url": "https://www.douyin.com/user/profile-id",
  "title": "Profile page title",
  "item_count": 1,
  "items": [
    {"item_id": "7693980128359107886", "title": "Original post text", "page_url": "https://www.douyin.com/video/7693980128359107886"}
  ],
  "has_more": true,
  "metadata": {
    "source": "web",
    "scope": "user_posts",
    "limit": 50,
    "total_count": 100,
    "accessible_episode_count": null,
    "stop_reason": "stalled"
  }
}
```

`item_count` equals `items.length`; preserve source order and deduplicate IDs. Return at most **50** Douyin works. A caller may request a smaller limit. Unknown title/count/`has_more` values are `null`; do not expand rounded counts into exact integers. `has_more: false` needs an explicit end or an exact total already fully collected. `stop_reason` is `limit`, `exhausted`, `stalled`, `request_failed`, or `loaded`; a limit stop contains the requested number of entries. `source` is `web` or `android_ui`. No list result includes `video_path`, a media address, or per-item detail/comment results.

Hongguo uses the same list keys with `platform: "hongguo"`, canonical `source_url: "https://hongguoduanju.com/detail?series_id=<id>"`, `scope: "series_episodes"`, `limit: null`, the series name as `title`, and exact `episode_cnt`/`accessible_episode_cnt` values when exposed. Every item adds `episode_number` (one-based) and uses `page_url: "https://hongguoduanju.com/player/<series-id>/<episode-id>"`. `item_id` is the episode ID. Missing episode titles stay `null`; do not substitute other series recommendations. A missing directory is an error, not an empty successful list.

## Detail success

```json
{
  "video_path": "downloads/reeldown/douyin-7693980128359107886.mp4",
  "title": "Video title",
  "content": "Full original post text #hashtags",
  "video_like_count": 123,
  "comment_count": 45,
  "favorite_count": 67,
  "top_comments": [
    {
      "content": "comment text",
      "like_count": 120
    }
  ]
}
```

Rules:

- A Douyin detail has exactly the seven keys shown above. A Hongguo detail uses the five common data fields (`video_path`, the three counts, `top_comments`) plus `episodes` and `metadata` for the series directory and episode/series scopes. These detail objects keep the previous contract; `page_type` is only added to list objects.
- Count values are non-negative JSON integers from the loaded video/episode data. Unknown Hongguo counts are `null` and listed in `metadata.unavailable_fields`, never guessed as zero.
- `top_comments` contains 0–3 accessible top-level comments, each with `like_count > 100` (100 itself is excluded). Entries are deduplicated and sorted by `like_count` descending; ties are deterministic.
- Stop fetching pages once a page supplies enough qualifying comments. Choose the three most liked entries from the pages examined; this is a bounded sample, not a global top-three ranking. Examine at most 5 pages and return fewer entries, or `[]`, when fewer qualify. A low-liked page does not prove later pages have no qualifying comments.
- Each comment has exactly `content` and `like_count`. Do not include usernames, account IDs, IP labels, avatars, or raw API data.
- Empty comment text is excluded.
- `video_path` uses forward slashes and is relative to the directory recorded when this invocation started, not the skill directory or a temporary browser directory. It must point to the fully downloaded, non-empty MP4 inside that root; absolute paths, URLs, parent traversal, and partial files are invalid. Only report success after checking the file.
- `title` uses the platform's explicit title when present. If `desc` ends with the separately supplied `caption`, the prefix before that caption is the headline; otherwise use the first line of the original description without truncation. `content` preserves the full original Douyin description, hashtags, emoji, and newlines. Use empty text only when the platform actually provides none.
- Media URLs remain private intermediate values. The downloader replaces `video_download_url` with `video_path` before emitting the final JSON. The validator's `--staged` option is only for private pre-download data.

## Hongguo metadata

Hongguo's public website exposes an episode comment preview rather than the entire App comment list. Add this object to the five data fields:

```json
{
  "metadata": {
    "platform": "hongguo",
    "series_id": "7673888102712101950",
    "episode_id": "7673903720362429502",
    "video_like_count_scope": "episode",
    "comment_count_scope": "episode",
    "favorite_count_scope": "series",
    "comment_scope": "web_preview",
    "comments_examined": 15,
    "comments_complete": false,
    "ranking_scope": "collected_comments",
    "comment_page_limit": 5,
    "unavailable_fields": []
  }
}
```

Return up to 3 preview comments with more than 100 likes, sorted descending. Native Android UI comments instead use `comment_scope: "app_visible"`; never label App observations as website previews. If a verified external downloader has no readable comment source, use `comment_scope: "unavailable"`, `comments_examined: 0`, `comments_complete: false`, and `top_comments: []`. Unknown episode counts remain null, never copied from a redirected first episode. A previously verified series-wide favorite count may be reused within the batch. The favorite count is for the whole series; the likes and comment count are for the selected episode. `comments_complete` stays false unless the source explicitly indicates the end, including an explicit zero comment count. Fewer than 3 matching comments is a valid success.

## Hongguo episode directory

Every Hongguo success object also includes `episodes`, copied in order from the current series page's `seriesDetail.vid_list`:

```json
{
  "episodes": [
    {
      "episode_number": 1,
      "episode_id": "7673903720362429502",
      "page_url": "https://hongguoduanju.com/player/7673888102712101950/7673903720362429502"
    }
  ]
}
```

Return all entries exposed in that directory, in their original order; `episode_number` is one-based. The directory contains navigable page links, while `video_path` points only to the selected downloaded episode. Reading the directory must not download or fetch playback/social data for the other episodes. If the page lacks a usable directory, set `episodes` to `null` and list `"episodes"` in `metadata.unavailable_fields`; do not invent episode IDs or silently return an empty list.

## Error

When a trustworthy success object cannot be produced, return:

```json
{
  "error": {
    "code": "short_machine_code",
    "message": "Concise user-facing explanation"
  }
}
```

Use one of these stable codes when applicable: `invalid_url`, `browser_unavailable`, `audio_control_unavailable`, `login_required`, `challenge_required`, `template_unavailable`, `request_rejected`, `pagination_incomplete`, `video_unavailable`, `result_invalid`, `download_unavailable`, `download_url_expired`, `download_failed`, `download_incomplete`, `media_invalid`, `list_unavailable`, `page_mismatch`, `episode_mismatch`, `web_access_limited`, `device_unavailable`, `device_selection_required`, `device_authorization_required`, `app_not_visible`, or `device_data_unavailable`.

Never put cookies, request headers, signed query strings, browser-storage values, or raw platform responses in an error message.
