#!/usr/bin/env python3
"""Validate ReelDown's public success JSON contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


EXPECTED_KEYS = {
    "video_like_count",
    "comment_count",
    "favorite_count",
    "top_comments",
}


def fail(message: str) -> None:
    raise ValueError(message)


def is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def resolve_video_path(value: Any, root: Path) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        fail("video_path must be a non-empty relative path using forward slashes")
    path = PurePosixPath(value)
    if path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts:
        fail("video_path must stay inside the invocation root")
    resolved = (root / value).resolve()
    if not resolved.is_relative_to(root.resolve()) or resolved.suffix.lower() != ".mp4":
        fail("video_path must point to an MP4 inside the invocation root")
    return resolved


def validate_list(data: dict) -> None:
    keys = {"page_type", "platform", "source_url", "title", "item_count", "items", "has_more", "metadata"}
    if set(data) != keys or data["page_type"] != "list" or data["platform"] not in {"douyin", "hongguo"}:
        fail("list keys or platform are invalid")
    if data["title"] is not None and not isinstance(data["title"], str):
        fail("list title must be text or null")
    if data["has_more"] is not None and not isinstance(data["has_more"], bool):
        fail("list has_more must be boolean or null")
    items = data["items"]
    if not isinstance(items, list) or not is_count(data["item_count"]) or data["item_count"] != len(items):
        fail("list item_count must equal the number of items")
    metadata = data["metadata"]
    if not isinstance(metadata, dict) or set(metadata) != {"source", "scope", "limit", "total_count", "accessible_episode_count", "stop_reason"}:
        fail("list metadata keys are invalid")
    if metadata["source"] not in {"web", "android_ui"} or metadata["stop_reason"] not in {"loaded", "limit", "exhausted", "stalled", "request_failed"}:
        fail("list source or stop_reason is invalid")
    for key in ("total_count", "accessible_episode_count"):
        if metadata[key] is not None and not is_count(metadata[key]):
            fail(f"list metadata.{key} must be a count or null")
    if metadata["total_count"] is not None and metadata["total_count"] < len(items):
        fail("list total_count cannot be less than the returned count")
    if metadata["total_count"] is not None and data["has_more"] is not None and data["has_more"] != (metadata["total_count"] > len(items)):
        fail("list has_more contradicts its exact total_count")
    if metadata["stop_reason"] == "exhausted" and data["has_more"] is not False:
        fail("an exhausted list must explicitly have no more items")
    source = data["source_url"]
    if not isinstance(source, str):
        fail("list source_url must be text")
    if data["platform"] == "douyin":
        if not re.fullmatch(r"https://www\.douyin\.com/user/[^/?#]+", source):
            fail("list source_url must be the canonical user page")
        if metadata["scope"] != "user_posts" or not is_count(metadata["limit"]) or not 1 <= metadata["limit"] <= 50:
            fail("Douyin list limit must be between 1 and 50")
        if len(items) > metadata["limit"] or metadata["accessible_episode_count"] is not None:
            fail("Douyin list exceeds its limit or contains episode-only metadata")
        if metadata["stop_reason"] == "limit" and len(items) != metadata["limit"]:
            fail("a limit stop must contain the requested number of items")
        series_id = None
    else:
        match = re.fullmatch(r"https://hongguoduanju\.com/detail\?series_id=(\d+)", source)
        if not match or metadata["scope"] != "series_episodes" or metadata["limit"] is not None:
            fail("Hongguo list must describe a canonical series directory")
        if not items:
            fail("an unavailable episode directory must not be reported as an empty success")
        series_id = match[1]
    seen = set()
    for index, item in enumerate(items):
        expected_keys = {"item_id", "title", "page_url"} | ({"episode_number"} if series_id else set())
        if not isinstance(item, dict) or set(item) != expected_keys:
            fail(f"items[{index}] keys are invalid")
        item_id = item["item_id"]
        if not isinstance(item_id, str) or not item_id.isascii() or not item_id.isdigit() or item_id in seen:
            fail("list item IDs must be unique numeric strings")
        seen.add(item_id)
        if item["title"] is not None and not isinstance(item["title"], str):
            fail("list item title must be text or null")
        expected_url = f"https://hongguoduanju.com/player/{series_id}/{item_id}" if series_id else f"https://www.douyin.com/video/{item_id}"
        if item["page_url"] != expected_url:
            fail("list item link does not match its identity")
        if series_id and (not is_count(item["episode_number"]) or item["episode_number"] != index + 1):
            fail("list episode number does not match its one-based position")


def validate_result(data: Any, root: Path, *, staged: bool = False, check_file: bool = True) -> None:
    if isinstance(data, dict) and data.get("page_type") == "list":
        if staged:
            fail("a list has no staged media payload")
        validate_list(data)
        return
    media_key = "video_download_url" if staged else "video_path"
    expected = EXPECTED_KEYS | {media_key}
    allowed = (expected | {"title", "content"}, expected | {"metadata", "episodes"})
    if not isinstance(data, dict) or set(data) not in allowed:
        fail("top-level keys do not match the public contract")

    metadata = data.get("metadata")
    if "metadata" in data:
        if not isinstance(metadata, dict) or metadata.get("platform") != "hongguo":
            fail("metadata must describe a Hongguo result")
        if set(metadata) != {"platform", "series_id", "episode_id", "video_like_count_scope", "comment_count_scope",
                             "favorite_count_scope", "comment_scope", "comments_examined", "comments_complete",
                             "ranking_scope", "comment_page_limit", "unavailable_fields"}:
            fail("Hongguo metadata keys are invalid")
        missing = metadata.get("unavailable_fields")
        if not isinstance(missing, list) or any(not isinstance(field, str) for field in missing) or len(set(missing)) != len(missing):
            fail("metadata.unavailable_fields must be a unique list of field names")
        expected_missing = {field for field in ("video_like_count", "comment_count", "favorite_count", "episodes") if data.get(field) is None}
        if set(missing) != expected_missing:
            fail("metadata.unavailable_fields must match the unknown fields")
        for key, expected in (
            ("video_like_count_scope", "episode"),
            ("comment_count_scope", "episode"),
            ("favorite_count_scope", "series"),
            ("ranking_scope", "collected_comments"),
        ):
            if metadata.get(key) != expected:
                fail(f"metadata.{key} must be {expected}")
        if metadata.get("comment_scope") not in {"web_preview", "app_visible", "unavailable"}:
            fail("metadata.comment_scope must identify the observed web or App comments")
        if metadata.get("comment_scope") == "unavailable" and (data.get("top_comments") != []
                or metadata.get("comments_examined") != 0 or metadata.get("comments_complete") is not False):
            fail("unavailable comments must not claim observations or completeness")
        if not isinstance(metadata.get("comments_complete"), bool):
            fail("metadata.comments_complete must be boolean")
        if not is_count(metadata.get("comments_examined")):
            fail("metadata.comments_examined must be a non-negative integer")
        if metadata.get("comment_page_limit") != 5:
            fail("metadata.comment_page_limit must be 5")
        for key in ("series_id", "episode_id"):
            value = metadata.get(key)
            if not isinstance(value, str) or not value.isdigit():
                fail(f"metadata.{key} must be a numeric string")

        episodes = data.get("episodes")
        if episodes is None:
            if "episodes" not in metadata.get("unavailable_fields", []):
                fail("unknown episodes must be listed in metadata.unavailable_fields")
        elif not isinstance(episodes, list):
            fail("episodes must be a list or null")
        else:
            if not episodes:
                fail("a missing episode directory must be null, not an empty list")
            episode_ids = set()
            for index, episode in enumerate(episodes):
                if not isinstance(episode, dict) or set(episode) != {"episode_number", "episode_id", "page_url"}:
                    fail(f"episodes[{index}] has invalid keys")
                number = episode["episode_number"]
                if not is_count(number) or number != index + 1:
                    fail(f"episodes[{index}].episode_number must match its one-based position")
                episode_id = episode["episode_id"]
                if not isinstance(episode_id, str) or not episode_id.isdigit():
                    fail(f"episodes[{index}].episode_id must be a numeric string")
                if episode_id in episode_ids:
                    fail("episode directory contains a duplicate episode ID")
                episode_ids.add(episode_id)
                expected_url = f"https://hongguoduanju.com/player/{metadata['series_id']}/{episode_id}"
                if episode["page_url"] != expected_url:
                    fail(f"episodes[{index}].page_url does not match its series and episode IDs")
            if metadata["episode_id"] not in episode_ids:
                fail("selected episode is absent from its series directory")

    if metadata is None:
        for key in ("title", "content"):
            if not isinstance(data.get(key), str):
                fail(f"{key} must be text")

    if staged:
        url = data.get(media_key)
        if not isinstance(url, str):
            fail("staged video address must be text")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            fail("staged video address must be an HTTP(S) URL without user credentials")
    else:
        video = resolve_video_path(data.get(media_key), root)
        if check_file and (not video.is_file() or video.stat().st_size == 0):
            fail("video_path does not point to a non-empty downloaded file")

    for key in ("video_like_count", "comment_count", "favorite_count"):
        if data.get(key) is None and metadata is not None:
            if key not in metadata.get("unavailable_fields", []):
                fail(f"unknown {key} must be listed in metadata.unavailable_fields")
            continue
        if not is_count(data.get(key)):
            fail(f"{key} must be a non-negative integer")

    comments = data.get("top_comments")
    if not isinstance(comments, list) or len(comments) > 3:
        fail("top_comments must be a list with at most 3 entries")

    previous = None
    for index, comment in enumerate(comments):
        if not isinstance(comment, dict) or set(comment) != {"content", "like_count"}:
            fail(f"top_comments[{index}] has invalid keys")
        if not isinstance(comment["content"], str) or not comment["content"].strip():
            fail(f"top_comments[{index}].content must be non-empty text")
        if not is_count(comment["like_count"]):
            fail(f"top_comments[{index}].like_count must be a non-negative integer")
        if comment["like_count"] <= 100:
            fail(f"top_comments[{index}].like_count must be greater than 100")
        if previous is not None and comment["like_count"] > previous:
            fail("top_comments is not sorted by like_count descending")
        previous = comment["like_count"]

def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("result")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--staged", action="store_true", help="Validate private pre-download data only")
    args = parser.parse_args()
    try:
        if args.result == "-":
            data = json.load(sys.stdin)
        else:
            with open(args.result, encoding="utf-8") as handle:
                data = json.load(handle)
        validate_result(data, args.root, staged=args.staged)
    except (OSError, ValueError):
        raise SystemExit("invalid result: schema, file, or relative path validation failed")
    print("valid staged data" if args.staged else "valid")


if __name__ == "__main__":
    main()
