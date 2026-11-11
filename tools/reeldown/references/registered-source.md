# Registered anonymous playback source

Use this when the caller supplies a reviewed source client for a selected Hongguo
episode or an explicitly requested series batch. This is a separate anonymous
client, not the connected phone's identity or login. Browser and phone credentials
are not required by this mode.

## Device and request ownership

Locally generated `openudid`, `clientudid` and `cdid` describe an anonymous device.
The registration response supplies playback `device_id` and `iid`; random numbers
used by a catalog implementation do not establish a registered playback identity.
Preserve large numeric identifiers as strings. Reject zero, missing or rounded IDs.
Keep the registration's `cdid` with its returned IDs in memory. Do not mix fields
from different registrations or persist identities in skill resources.

Some reviewed clients also require anonymous session cookies returned by that same
registration response. Retain only their documented allowlist (for example,
`install_id`, `ttreq`, `store-region`, `store-region-src`) in process memory and send
them only to the reviewed playback endpoint. Do not substitute account cookies,
read a browser store, print values, or include them in a receipt. A registration
token need not be forwarded merely because it exists: follow actual source usage.

The reviewed resolver owns the full request profile: application versions, device
fields, exact query/body bytes, timestamps and signatures. Use its tested profile
together; a version mismatch is evidence to investigate, not permission to change
individual fields blindly. Check that its signature implementation is current;
timestamp-only placeholder signatures can produce HTTP 200 with an empty body.
Sign the exact final query/body and keep the request ticket and signature timestamp
consistent. If a reviewed source replaces the signature scheme, do not leave the
superseded signature headers attached alongside the new ones.

A primary request and one independently signed request to a source-documented
alternate route or host may form one bounded recovery attempt. For a reviewed
client supporting both, try the current single-episode GET route, then its POST
fallback only on an empty response; do not multiply host, method and identity
combinations. Preserve exact episode matching in both response shapes. Do not
forward a signed body through an arbitrary redirect or multiply the resolver's
retry loop in the adapter. Registration success alone is not playback success.

## Optional executable adapter

`scripts/hongguo_registered_backend.mjs` runs with Node.js 20+, FFmpeg and FFprobe.
It imports a caller-reviewed local module rather than starting an application.
The module implements `fetchAppPlayUrl(episodeId, {quality})` and owns registration,
signing, model selection and its bounded recovery. Its dependencies must already
be installed. Review imports for startup side effects before selecting the module.

The resolver returns a private object with:

```js
{
  vid: "<exact-requested-episode-id>",
  url: "<temporary-HTTPS-media-address>",
  codec: "h264",                 // or a supported HEVC alias
  duration: 123.4,                // full duration from the selected model, required
  size: 1234567,                  // selected transfer size; 0 or absent if unknown
  contentKey: null,              // optional 32-digit hex value, stays in memory
  userAgent: "<selected-media-user-agent>"
}
```

Use the caller's requested quality; otherwise keep `auto` rather than introducing
an unrequested minimum. Platform labels and actual dimensions may differ slightly
(for example a rendition labeled 1080p can be 1920 × 1078). Preserve and report the
actual dimensions; a strict pixel minimum can reject such a full-length rendition.
Do not alter the duration or dimensions to satisfy a quality check.

An optional `variants` array uses the same fields and contains only renditions
meeting the selected quality. The resolver must match the requested episode before
returning, and validate any fallback model against the original media identity and
duration. Some source clients omit duration for ordinary H.264/HEVC output: adapt
a reviewed external copy to retain `video_duration`, selected `size` and dimensions
for every rendition. Do not replace missing model duration with the downloaded
file's own duration or a preview's duration merely to make validation pass.

Create a task-local configuration outside the skill:

```json
{
  "resolver_module": "/path/to/reviewed/app-source.js",
  "media_module": "/path/to/reviewed/media-processor.js",
  "quality": "auto"
}
```

Paths may be absolute or relative to this configuration. `media_module` is optional
for clear MP4; when needed it exports `decryptMp4File(inputPath, outputPath, keyBuffer)`.
The skill does not contain the signing, registration or decryption implementation.
Optional `ffmpeg` and `ffprobe` fields select those executables. Do not package a
user's actual paths or credentials with the skill.

A diagnostic-only probe makes a bounded resolver call and prints no URL or identity:

```bash
node <skill-base>/scripts/hongguo_registered_backend.mjs \
  --config <task-source.json> --probe <episode-id>
```

`available: true, probe_only: true` means model resolution succeeded, not that a
video was downloaded. For initial end-to-end validation, prefer one actual download
over probing and immediately resolving the same episode again. Do not run a probe
before every episode in a batch.

Configure the existing external batch helper with:

```json
{
  "command": ["node", "/path/to/skill/scripts/hongguo_registered_backend.mjs",
    "--config", "/path/to/task-source.json", "{episode_id}", "{output}"]
}
```

Run the first attempt with `hongguo_external_batch.py --root <root> --backend
<backend.json> --max-new 1 --max-attempts 1` (also pass `--state` for a non-default
manifest). The attempt limit counts failed backend launches as well as successes;
recovering an already published verification receipt does not make a source call.
Only remove these test limits after the selected episode has passed transfer,
identity, model-duration and full-decode validation. See [batch.md](batch.md).

For a reviewed resolver that supports reusing a valid in-memory registration,
select the optional persistent child protocol to avoid restarting it per episode:

```json
{
  "protocol": "jsonl",
  "command": ["node", "/path/to/skill/scripts/hongguo_registered_backend.mjs",
    "--config", "/path/to/task-source.json", "--serve"]
}
```

The helper starts one child lazily for unfinished downloads, passes sequential
JSON lines over stdin/stdout, and closes it on completion, stopping or failure.
There are no listening sockets and no identity files. Request IDs correlate each
reply, and a timeout or malformed reply closes the child. `--max-attempts` counts
download requests in both modes. Already completed files or receipts need no child.
This mode preserves a resolver's process memory; the resolver still owns session
validity and bounded renewal. Test that multiple episodes reuse a registration
with the current signature/session scheme before relying on it. Reuse that failed
under a different scheme does not establish the behavior of the current one.

The adapter accepts HTTPS media only from its reviewed CDN list, uses only the media
User-Agent, and rejects unknown redirects, playlists and unsupported codecs. It
does not silently lower quality or fall back to a static website preview. It checks
model size when known, HTTP length when supplied, container, duration and full
audio/video decoding. Publication refuses existing files and supplies a safe receipt
for crash recovery. Successful receipts mark `source_kind: "registered_client"`;
the batch manifest preserves it while final public JSON keeps its existing schema.

## Evidence and stopping

Record registration acceptance, model availability, download verification and batch
completion separately. HTTP 200 with an empty body remains a source failure; do not
label it as network slowness, a quota limit, rate limiting or a stale signature
without corresponding evidence. A different reviewed request profile is a new
candidate to test, not a proven recovery. Leave the old backend configuration intact
until the candidate passes a full episode test. After bounded source failure, retain
all completed files and stop repeating the unchanged source. After a successful
experimental download, adopt its verification receipt into the existing manifest
instead of requesting the same media again. Resume only unfinished entries.

A successful change involving both signatures and session state establishes that
combination as working. Without a controlled comparison it does not establish
which individual field caused the earlier failure. Record the tested revision and
safe model/transfer evidence in the task, separately from this generic skill.

Source modules and their notices stay outside this skill. If redistributed with an
adapter, preserve the applicable license, attribution and change notices; placing
files in separate directories does not by itself settle licensing obligations.
