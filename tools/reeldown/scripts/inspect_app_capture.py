#!/usr/bin/env python3
"""Inspect an authorized Hongguo HAR; export an exact request/response privately.

No network requests or signature generation. Stdout never contains header values,
query values, response bodies, media URLs, account IDs, or content keys.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urlsplit

SIGNATURES = {"x-gorgon", "x-medusa", "x-helios", "x-ladon", "x-argus", "x-khronos", "x-ss-req-ticket"}
PATHS = {"/novel/player/multi_video_model/v1", "/novel/player/multi_video_model/preload/v1"}


def decoded_response(entry: dict) -> dict | None:
    content = entry.get("response", {}).get("content", {})
    text = content.get("text", "")
    if not isinstance(text, str) or len(text) > 8 * 1024 * 1024:
        return None
    try:
        if content.get("encoding") == "base64":
            text = base64.b64decode(text, validate=True).decode("utf-8")
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except (ValueError, UnicodeError):
        return None


def inspect(capture: dict, episode: str) -> tuple[dict, dict | None]:
    entries = capture.get("log", {}).get("entries")
    if not isinstance(entries, list):
        raise ValueError("invalid HAR")
    matches = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        req = entry.get("request", {})
        parsed = urlsplit(req.get("url", ""))
        host = parsed.hostname or ""
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or not any(host == d or host.endswith("." + d) for d in ("fqnovel.com", "snssdk.com"))
                or parsed.path.rstrip("/") not in PATHS or req.get("method") != "POST"):
            continue
        try:
            body = json.loads(req.get("postData", {}).get("text", ""))
            requested = body.get("mixed_video_id_map", {}).get("1004", [])
        except (ValueError, AttributeError):
            continue
        if not isinstance(requested, list) or episode not in [str(v) for v in requested]:
            continue
        response = decoded_response(entry)
        data = response.get("data") if response else None
        item = data.get(episode) if isinstance(data, dict) else None
        model = item.get("video_model") if isinstance(item, dict) else None
        try:
            model = json.loads(model) if isinstance(model, str) else model
        except ValueError:
            model = None
        business_ok = response is not None and str(response.get("code", response.get("Code", 0))) == "0"
        matched_model = bool(isinstance(model, dict) and model and business_ok)
        header_names = {str(h.get("name", "")).lower() for h in req.get("headers", []) if isinstance(h, dict)}
        query = parse_qs(parsed.query)
        row = {"entry_index": index, "api_host": host, "api_path": parsed.path,
               "http_status": entry.get("response", {}).get("status"),
               "device_identity_fields_present": sorted(k for k in ("device_id", "iid", "cdid") if query.get(k)),
               "signature_header_names": sorted(SIGNATURES & header_names),
               "response_json_available": response is not None, "selected_episode_model_available": matched_model}
        matches.append((row, entry))
    # Prefer the latest captured success; an unrelated response cannot supply this episode.
    selected = next((pair for pair in reversed(matches) if pair[0]["http_status"] == 200
                     and pair[0]["selected_episode_model_available"]), None)
    report = {"source": "android_app_capture", "observation_only": True,
              "episode_id": episode, "matching_request_count": len(matches),
              "response_available": selected is not None, "network_requests_sent": 0,
              "signature_replay_supported": False, "requests": [row for row, _ in matches[-10:]]}
    return report, selected[1] if selected else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="Private HAR from an authorized target-App capture")
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--private-output", type=Path, help="New private JSON file for the matched exact entry; never a public result")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"\d{10,30}", args.episode_id) or args.capture.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("invalid input")
        report, entry = inspect(json.loads(args.capture.read_text(encoding="utf-8")), args.episode_id)
        if args.private_output:
            if entry is None:
                report["private_entry_written"] = False
            else:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(args.private_output, flags, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as out:
                    json.dump(entry, out, ensure_ascii=False)
                report["private_entry_written"] = True
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError, AttributeError):
        print(json.dumps({"error": {"code": "device_data_unavailable",
                                  "message": "The private App capture or output location is invalid."}}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
