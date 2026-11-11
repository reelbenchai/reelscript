# Android over USB

Run on the machine physically connected to the phone. Requires Python 3 and existing Android Platform Tools (ADB). The helper searches PATH and standard SDK locations; it does not install software, enable USB debugging, change network settings, create port forwarding, root the phone, or extract private App files.

## Detect once

```bash
python3 -I <skill-base>/scripts/mobile_android.py devices
```

On Windows use a working `python` executable if `python3` is a Store alias. The response lists ephemeral `device_id`, model, and status without hardware serial numbers. No device or missing ADB means use the browser. An `unauthorized` phone requires the user to accept its on-device USB debugging prompt; do not click authorization for them or keep retrying. Multiple devices require selecting one `device_id`, rather than silently choosing a phone. Do not restart a shared ADB server or establish wireless debugging.

## Read the App's current page

For device and App compatibility, run `scripts/mobile_android.py profile --device <device_id>` once. It returns public model/build/ABI fields and installed App versions. It excludes hardware serial numbers, account values, App registration identifiers, cookies, and signatures. `app_identity_available: false` and `request_signature_available: false` describe this ADB probe, not a claim that the App has no identity or signatures. Do not replace App `device_id`/`iid` with the ADB transport ID, hardware serial, or a random number. For actual request data, use [android-capture.md](android-capture.md).

```bash
python3 -I <skill-base>/scripts/mobile_android.py snapshot --device <device_id>
```

This reads the accessibility hierarchy for the currently visible official Douyin or Hongguo App, without starting playback or changing the foreground App. It filters password/input fields and unrelated applications. The temporary XML is removed from the phone in a `finally` path and is never saved locally. The returned `observation_only: true` JSON is **private working data**, not the skill's final success object. Do not save or return the whole UI hierarchy. Keep only the requested public list/detail fields.

Use the visible title, full expanded post content, counts, comments, and item/share links when exposed. Preserve the list/detail mode selected by the user. Match a detail's video/episode ID through an observed item/share link or an available browser source before associating phone observations with it; a matching title alone is insufficient. Do not fabricate item IDs from list positions. For lists, return only entries with verifiable item links; at most 50 Douyin works. For detail comments, inspect at most five comment pages and retain at most three with strictly more than 100 likes. Use ordinary observed App UI interactions only when the execution host supplies that capability; never guess coordinates or hidden endpoints.

Rounded display counts such as `1.2万` do not establish an exact count. Get exact values from a matching authorized page/source when available. A node's `truncated: true` means its text is incomplete; it cannot supply full post content. Unknown Hongguo values may be `null` under its existing contract; unknown Douyin values or missing full content cannot be passed off as a complete detail result. If native UI omits required fields or identity, use the browser for those fields or return `device_data_unavailable`.

### Live players and automatic controls

Continuous player updates can prevent `uiautomator dump` from becoming idle. Do not repeatedly retry the same failed dump or assume that USB access is gone. Use the host's live accessibility/screenshot capability when available. The optional source `scripts/android-ui/reeldownui.java` supports a live `snapshot` and exact visible `semantic_id`, `semantic_text`, or observed `semantic_point` actions. It restricts the foreground package to the supported Apps and capture tool, filters off-screen duplicate controls, and requires one unambiguous target. A successful command or click still needs a resulting-page check. Ordinary ADB input may work or fail depending on the current device state; test its actual effect before switching methods or asking the user to perform routine clicks.

This legacy helper needs an existing Android SDK with `android.jar`, `uiautomator.jar`, and `optional/android.test.base.jar`, a compatible Java compiler, and a DEX builder. It is an optional fallback; do not install SDKs just to read a connected phone. Compile the included Java source to a temporary build directory, convert its class with the available DEX builder, and push the resulting `reeldown-ui.jar` to `/data/local/tmp/`. With a single selected device, a read looks like:

```bash
adb -t <transport-id> shell uiautomator runtest reeldown-ui.jar \
  /system/framework/android.test.base.jar /system/framework/android.test.runner.jar \
  -c reeldownui -e pkg com.phoenix.read -e mode snapshot
```

Use the device transport from the current connection, not a saved ID. Wait for each UI automation process to exit before starting another read/action; overlapping sessions fail. Remove the task-owned device JAR after use. The source was exercised on a Hongguo player; other App/version behavior requires an observed UI check. No automatic click authorizes a new certificate, network setting, purchase, or message to another person.

Do not automatically launch an audible native player. Read an already-open App page, or use a capable authorized mobile UI provider that can keep task playback silent. If the current App is not relevant, use the browser or ask the user to open the desired page when mobile-only access is necessary.

## Import an official saved video

A phone App that can play a video does not necessarily expose a downloadable clear MP4. Use a real clear media source through the existing downloader, or the App's ordinary authorized **save/export** feature. For an MP4 already exported to shared storage:

```bash
python3 -I <skill-base>/scripts/mobile_android.py pull --device <device_id> \
  --remote /sdcard/Movies/exported.mp4 --input <public-detail-fields.json> \
  --root <invocation-directory> --output downloads/reeldown/<platform>-<id>.mp4
```

The input contains the existing detail JSON fields except `video_path`, with identity and data already verified. It must contain no temporary URL or extra private UI fields. The helper validates the schema, imports into a `.part`, checks MP4/video streams, publishes without overwriting existing files, and only then returns the normal final JSON with `video_path`. It accepts only shared Download/Movies/DCIM MP4 exports. It does not read App sandboxes or decrypt offline caches. The phone's original export is preserved. No MP4 export and no usable clear source means no detail-download success.

When the caller requests remote delivery followed by local deletion, transfer and verify the imported file under that caller's storage workflow before deleting the local copy; do not bake a particular host or directory into the skill.

The supported transport follows [Android's ADB documentation](https://developer.android.com/tools/adb). A connected Android device is a data-source option; native UI access and media-download access are separate capabilities.
