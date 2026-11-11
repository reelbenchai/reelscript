#!/usr/bin/env python3
"""Read an authorized Android App UI or import an officially exported MP4 over USB."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_video import DownloadError, verify_mp4  # noqa: E402
from validate_result import resolve_video_path, validate_result  # noqa: E402

PACKAGES = {"com.ss.android.ugc.aweme": "douyin", "com.phoenix.read": "hongguo"}


class MobileError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


def adb_path() -> str | None:
    found = shutil.which("adb")
    if found:
        return found
    executable = "adb.exe" if os.name == "nt" else "adb"
    bases = [os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME"),
             str(Path.home() / "Library/Android/sdk"), str(Path.home() / "AppData/Local/Android/Sdk"),
             str(Path.home() / "Android/Sdk")]
    return next((str(Path(base) / "platform-tools" / executable) for base in bases
                 if base and (Path(base) / "platform-tools" / executable).is_file()), None)


def run(adb: str, args: list[str], timeout: int = 20) -> bytes:
    try:
        result = subprocess.run([adb, *args], capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise MobileError("device_unavailable", "The Android device command did not complete.") from None
    if result.returncode:
        raise MobileError("device_unavailable", "The authorized Android device is not available for this operation.")
    return result.stdout


def devices(adb: str) -> list[dict]:
    rows = []
    for line in run(adb, ["devices", "-l"]).decode("utf-8", "replace").splitlines():
        fields = line.split()
        if len(fields) < 2 or line.startswith("List of devices") or fields[0].startswith("*"):
            continue
        serial, state = fields[:2]
        # Support USB phones. Do not select emulators or establish wireless connections.
        if serial.startswith("emulator-") or ":" in serial:
            continue
        info = dict(part.split(":", 1) for part in fields[2:] if ":" in part)
        transport = info.get("transport_id")
        rows.append({"device_id": f"android-{transport}" if transport and transport.isdigit() else f"android-slot-{len(rows)+1}",
                     "status": state if state in {"device", "unauthorized", "offline"} else "unavailable",
                     "model": info.get("model"), "_serial": serial, "_transport": transport})
    return rows


def select(rows: list[dict], key: str | None) -> list[str]:
    candidates = [row for row in rows if key is None or row["device_id"] == key]
    if not candidates:
        raise MobileError("device_unavailable", "No matching Android phone is connected over USB.")
    if len(candidates) > 1:
        raise MobileError("device_selection_required", "Select one of the connected Android phones using --device.")
    row = candidates[0]
    if row["status"] == "unauthorized":
        raise MobileError("device_authorization_required", "Unlock the phone and accept its USB debugging authorization prompt.")
    if row["status"] != "device":
        raise MobileError("device_unavailable", "The Android phone is offline or unavailable.")
    transport = row["_transport"]
    return ["-t", transport] if transport and transport.isdigit() else ["-s", row["_serial"]]


def profile(adb: str, target: list[str]) -> dict:
    """Read public build and installed-App versions, never App identity secrets."""
    fields = {
        "model": "ro.product.model", "brand": "ro.product.brand",
        "manufacturer": "ro.product.manufacturer", "product": "ro.product.device",
        "android_version": "ro.build.version.release", "sdk": "ro.build.version.sdk",
        "abi": "ro.product.cpu.abi", "build_id": "ro.build.display.id",
    }
    properties = run(adb, [*target, "shell", "getprop"]).decode("utf-8", "replace")
    values = dict(re.findall(r"^\[([^\]]+)\]: \[(.*)\]$", properties, re.M))
    apps = []
    for package, platform in PACKAGES.items():
        dump = run(adb, [*target, "shell", "dumpsys", "package", package]).decode("utf-8", "replace")
        version = re.search(r"\bversionName=([^\s]+)", dump)
        code = re.search(r"\bversionCode=(\d+)", dump)
        target_sdk = re.search(r"\btargetSdk=(\d+)", dump)
        apps.append({"platform": platform, "package": package, "installed": bool(version and code),
                     "version": version[1] if version else None,
                     "version_code": int(code[1]) if code else None,
                     "target_sdk": int(target_sdk[1]) if target_sdk else None})
    return {"source": "android_adb", "observation_only": True,
            "device": {field: values.get(prop) or None for field, prop in fields.items()},
            "apps": apps, "app_identity_available": False, "request_signature_available": False,
            "request_source_required": "An authorized real App request or decrypted capture; build properties are not App credentials."}


def parse_ui(xml: bytes) -> dict:
    hierarchy = ET.fromstring(xml)
    nodes = list(hierarchy.iter("node"))
    platforms = {PACKAGES[n.get("package")] for n in nodes if n.get("package") in PACKAGES}
    if len(platforms) != 1:
        raise MobileError("app_not_visible", "Open the relevant Douyin or Hongguo page on the phone, then read it again.")
    platform = platforms.pop()
    result, seen = [], set()
    for node in nodes:
        if PACKAGES.get(node.get("package")) != platform or node.get("password") == "true":
            continue
        resource = node.get("resource-id", "")
        if re.search(r"password|cookie|token|session|avatar|username|account|phone|email", resource, re.I):
            continue
        if "EditText" in node.get("class", ""):
            continue
        text, description = node.get("text", "").strip(), node.get("content-desc", "").strip()
        if not (text or description) or (text, description, resource) in seen:
            continue
        # This is a private UI observation, never a final skill success object.
        seen.add((text, description, resource))
        result.append({"text": text[:4000], "description": description[:4000],
                       "resource_id": resource, "bounds": node.get("bounds", ""),
                       "clickable": node.get("clickable") == "true",
                       "truncated": len(text) > 4000 or len(description) > 4000})
        if len(result) >= 300:
            break
    return {"source": "android_ui", "platform": platform, "observation_only": True,
            "nodes": result, "truncated": len(result) >= 300}


def snapshot(adb: str, target: list[str]) -> dict:
    remote = f"/sdcard/Download/.reeldown-ui-{uuid.uuid4().hex}.xml"
    try:
        run(adb, [*target, "shell", "uiautomator", "dump", "--compressed", remote], timeout=30)
        xml = run(adb, [*target, "exec-out", "cat", remote])
        if len(xml) > 4 * 1024 * 1024:
            raise MobileError("device_data_unavailable", "The App UI observation is too large.")
        try:
            return parse_ui(xml)
        except ET.ParseError:
            raise MobileError("device_data_unavailable", "The player did not provide an idle UI snapshot. Use an available live accessibility reader instead of repeatedly dumping it.") from None
    finally:
        try:
            run(adb, [*target, "shell", "rm", "-f", remote])
        except MobileError:
            pass


def pull(adb: str, target: list[str], remote: str, data: dict, root: Path, output: str) -> dict:
    path = PurePosixPath(remote)
    shared = ("/sdcard/Download/", "/sdcard/Movies/", "/sdcard/DCIM/",
              "/storage/emulated/0/Download/", "/storage/emulated/0/Movies/", "/storage/emulated/0/DCIM/")
    if ".." in path.parts or not remote.startswith(shared) or path.suffix.lower() != ".mp4":
        raise MobileError("device_data_unavailable", "Use an official MP4 export in the phone's shared Download, Movies, or DCIM directory.")
    if not root.is_dir():
        raise ValueError("root is not a directory")
    destination = resolve_video_path(output, root)
    result = {**data, "video_path": destination.relative_to(root.resolve()).as_posix()}
    validate_result(result, root, check_file=False)
    if result.get("page_type") == "list":
        raise ValueError("a list must not import a video")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".reeldown-phone-", suffix=".part", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(name)
    published = None
    try:
        run(adb, [*target, "pull", remote, str(temporary)], timeout=900)
        verify_mp4(temporary)
        # Never overwrite an unrelated file and do not delete the user's phone export.
        while True:
            try:
                os.link(temporary, destination)
                published = destination
                break
            except FileExistsError:
                destination = destination.with_name(f"{destination.stem}-{uuid.uuid4().hex[:8]}.mp4")
        result["video_path"] = destination.relative_to(root.resolve()).as_posix()
        validate_result(result, root)
        return result
    except BaseException:
        if published:
            published.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("devices", "profile", "snapshot", "pull"))
    parser.add_argument("--device", help="Ephemeral device_id returned by devices")
    parser.add_argument("--remote", help="Officially exported MP4 in shared phone storage")
    parser.add_argument("--input", default="-", help="Public detail fields as JSON, or - for stdin")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", help="Relative MP4 path for pull")
    args = parser.parse_args()
    try:
        adb = adb_path()
        if not adb:
            if args.action != "devices":
                raise MobileError("device_unavailable", "ADB is not installed on this execution host.")
            result = {"adb_available": False, "devices": []}
        else:
            rows = devices(adb)
            if args.action == "devices":
                result = {"adb_available": True, "devices": [{k: v for k, v in row.items() if not k.startswith('_')} for row in rows]}
            else:
                target = select(rows, args.device)
                if args.action == "profile":
                    result = profile(adb, target)
                elif args.action == "snapshot":
                    result = snapshot(adb, target)
                else:
                    if not args.remote or not args.output:
                        raise ValueError("pull requires --remote and --output")
                    if args.input == "-":
                        data = json.load(sys.stdin)
                    else:
                        with open(args.input, encoding="utf-8") as handle:
                            data = json.load(handle)
                    result = pull(adb, target, args.remote, data, args.root.resolve(), args.output)
    except (MobileError, DownloadError) as error:
        result = {"error": {"code": error.code, "message": error.message}}
    except (OSError, ValueError, ET.ParseError):
        result = {"error": {"code": "result_invalid", "message": "The phone data, public detail fields, or output path could not be validated."}}
    except Exception:
        result = {"error": {"code": "device_data_unavailable", "message": "The phone did not provide usable App data or an exported MP4."}}
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    if "error" in result:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
