#!/usr/bin/env python3
"""Download private collected media and emit public JSON containing a relative path."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

# Isolated Python (-I) does not add this script's directory to the import path.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_result import resolve_video_path, validate_result  # noqa: E402


class DownloadError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


def verify_mp4(path: Path, expected_duration: float | None = None) -> None:
    """Check top-level MP4 boxes; reject HTML and incomplete containers."""
    size = path.stat().st_size
    boxes = set()
    offset = 0
    with path.open("rb") as handle:
        while offset + 8 <= size:
            handle.seek(offset)
            length, kind = struct.unpack(">I4s", handle.read(8))
            header_size = 8
            if length == 1:
                extra = handle.read(8)
                if len(extra) != 8:
                    break
                length, header_size = struct.unpack(">Q", extra)[0], 16
            elif length == 0:
                length = size - offset
            if length < header_size or offset + length > size:
                break
            boxes.add(kind)
            offset += length
    if offset != size or not {b"ftyp", b"moov", b"mdat"}.issubset(boxes):
        raise DownloadError("media_invalid", "The downloaded response is not a complete MP4 video.")
    probe = shutil.which("ffprobe")
    if expected_duration is not None and not probe:
        raise DownloadError("download_unavailable", "FFprobe is required to verify the expected full video duration.")
    if probe:
        try:
            check = subprocess.run(
                [probe, "-v", "error", "-show_entries", "stream=codec_type,codec_name,codec_tag_string:format=duration", "-of", "json", str(path)],
                check=True, capture_output=True, timeout=30, text=True,
            )
            info = json.loads(check.stdout)
            streams = info.get("streams", [])
            if not any(stream.get("codec_type") == "video" and stream.get("codec_name")
                       and stream.get("codec_name") != "unknown" for stream in streams):
                raise ValueError("no video stream")
            if any(stream.get("codec_tag_string") in {"encv", "enca"} for stream in streams):
                raise DownloadError("media_invalid", "The captured source is encrypted media, not a clear playable MP4.")
            if expected_duration is not None:
                actual = float(info.get("format", {}).get("duration", 0))
                if abs(actual - expected_duration) > max(2.0, expected_duration * 0.02):
                    raise DownloadError("download_incomplete", "The video duration does not match the selected full episode.")
        except (subprocess.SubprocessError, OSError, ValueError):
            raise DownloadError("media_invalid", "The downloaded MP4 has no readable video stream.") from None


class ScopedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        before, after = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if after.scheme not in {"http", "https"} or after.username or after.password:
            raise DownloadError("download_failed", "The media redirect is not supported.")
        if before.scheme == "https" and after.scheme != "https":
            raise DownloadError("download_failed", "The media redirect would downgrade the connection.")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        def origin(url):
            return url.scheme, url.hostname, url.port or (443 if url.scheme == "https" else 80)
        if redirected and origin(before) != origin(after):
            for name in list(redirected.headers):
                if name.lower() in {"authorization", "cookie"}:
                    redirected.remove_header(name)
        return redirected


def request_context(value: dict | None, video_id: str) -> tuple[dict, float | None]:
    if value is None:
        return {}, None
    if (not isinstance(value, dict) or set(value) - {"source", "video_id", "headers", "expected_duration"}
            or value.get("source") not in {"android_app_capture", "hongguo_public_web"}
            or value.get("video_id") != video_id):
        raise ValueError("context does not match the selected media source")
    allowed = {"user-agent": "User-Agent", "referer": "Referer", "origin": "Origin",
               "accept": "Accept", "authorization": "Authorization", "cookie": "Cookie"}
    if value["source"] == "hongguo_public_web":
        allowed.pop("authorization")
        allowed.pop("cookie")
    raw = value.get("headers", {})
    if not isinstance(raw, dict):
        raise ValueError("invalid media headers")
    headers = {}
    for name, content in raw.items():
        if (name.lower() not in allowed or not isinstance(content, str)
                or "\r" in content or "\n" in content or len(content) > 16384):
            raise ValueError("unsupported media header")
        headers[allowed[name.lower()]] = content
    duration = value.get("expected_duration")
    if value["source"] == "hongguo_public_web" and duration is None:
        raise ValueError("verified website duration is required")
    if duration is not None and (isinstance(duration, bool) or not isinstance(duration, (int, float))
                                 or not 0 < duration < 86400):
        raise ValueError("invalid expected duration")
    return headers, duration


def download(data: dict, root: Path, platform: str, video_id: str, output: str | None,
             context: dict | None = None) -> dict:
    validate_result(data, root, staged=True)
    metadata = data.get("metadata")
    inferred = "hongguo" if metadata else "douyin"
    if platform != inferred or (metadata and video_id != metadata["episode_id"]):
        raise ValueError("platform or episode ID does not match collected data")
    extra_headers, expected_duration = request_context(context, video_id)
    destination = resolve_video_path(output or f"downloads/reeldown/{platform}-{video_id}.mp4", root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".reeldown-", suffix=".part", dir=destination.parent)
    temporary = Path(temporary_name)
    published: Path | None = None
    try:
        headers = {
            "Referer": "https://www.douyin.com/" if platform == "douyin" else "https://hongguoduanju.com/",
            "User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity",
        }
        headers.update(extra_headers)
        request = urllib.request.Request(data["video_download_url"], headers=headers)
        started = time.monotonic()
        with os.fdopen(descriptor, "wb") as handle:
            try:
                with urllib.request.build_opener(ScopedRedirect()).open(request, timeout=30) as response:
                    if response.status != 200:
                        raise DownloadError("download_incomplete", "The server did not return a complete video response.")
                    length = response.headers.get("Content-Length")
                    expected = int(length) if length is not None else None
                    received = 0
                    while True:
                        if time.monotonic() - started > 900:
                            raise DownloadError("download_failed", "The video download exceeded its time limit.")
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        received += len(chunk)
                    if received == 0 or (expected is not None and received != expected):
                        raise DownloadError("download_incomplete", "The video transfer was empty or incomplete.")
            except urllib.error.HTTPError as error:
                if error.code in {401, 403, 410}:
                    raise DownloadError("download_url_expired", "Refresh the media address in the browser and retry once.") from None
                raise DownloadError("download_failed", "The media server rejected the download.") from None
            handle.flush()
            os.fsync(handle.fileno())
        verify_mp4(temporary, expected_duration)

        # Hard-link publication is atomic and refuses to overwrite existing files.
        while True:
            try:
                os.link(temporary, destination)
                published = destination
                break
            except FileExistsError:
                destination = destination.with_name(f"{destination.stem}-{uuid.uuid4().hex[:8]}.mp4")
        result = {key: value for key, value in data.items() if key != "video_download_url"}
        result = {"video_path": destination.relative_to(root.resolve()).as_posix(), **result}
        validate_result(result, root)
        return result
    except BaseException:
        if published is not None:
            published.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="-", help="Private collected JSON file, or - for stdin")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Invocation directory used for relative paths")
    parser.add_argument("--platform", required=True, choices=("douyin", "hongguo"))
    parser.add_argument("--video-id", required=True, help="Video/episode ID, not a series ID")
    parser.add_argument("--output", help="Optional relative MP4 path under --root")
    parser.add_argument("--request-context", type=Path, help="Verified media source, scoped request headers and expected duration; never browser cookies")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"\d{10,30}", args.video_id):
            raise ValueError("invalid video ID")
        root = args.root.resolve()
        if not root.is_dir():
            raise ValueError("invocation root is not a directory")
        if args.input == "-":
            data = json.load(sys.stdin)
        else:
            with open(args.input, encoding="utf-8") as handle:
                data = json.load(handle)
        context = json.loads(args.request_context.read_text(encoding="utf-8")) if args.request_context else None
        result = download(data, root, args.platform, args.video_id, args.output, context)
    except DownloadError as error:
        result = {"error": {"code": error.code, "message": error.message}}
    except ValueError:
        result = {"error": {"code": "result_invalid", "message": "The collected data, selected video ID, or output path is invalid."}}
    except OSError:
        result = {"error": {"code": "download_failed", "message": "The video could not be downloaded or the local result was invalid."}}
    except Exception:
        result = {"error": {"code": "download_incomplete", "message": "The video transfer did not complete."}}
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    if "error" in result:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
