# Real Android requests and playback sources

Read this for an explicitly requested mobile capture/signature workflow, or when an authorized App source is available after the website rejects the selected episode. It supplements the list/detail contract and does not turn a list request into a download batch.

## Separate the three sources

| Source | What it establishes | What it does not establish |
| --- | --- | --- |
| ADB `profile` | Public device build and installed App versions | The App's `device_id`, `iid`, login state, or a request signature |
| Original App traffic | The exact request, its session context, and response, when readable | A general signing key or a signature reusable with different parameters |
| A separate registered client | Its own server-issued identity and locally signed requests | The connected phone's identity or App session |

Keep App version, User-Agent, device fields, query bytes, request body, timestamps, and signatures from the same real request. Changing an episode ID, JSON serialization, parameter order, or timestamp can invalidate a signature. ADB cannot invoke an arbitrary private signing SDK inside a release App. Do not fabricate identifiers from model/build properties, combine credentials from unrelated sessions, or report a successful device registration as successful playback retrieval.

An explicitly selected anonymous registered client is an alternative source, not a phone-capture result. Its generated `cdid` must stay with the server-issued IDs from that registration. See [registered-source.md](registered-source.md) for the optional adapter, required model-duration evidence and single-attempt test.

An existing user-authorized source client can be evaluated separately with one selected episode and its own bounded recovery policy. HTTP 200 with an empty body is a failed response. Do not start a whole application merely to call its resolver: startup code may alter proxy settings or write unrelated application state. Inspect the isolated module and preserve the host's current networking configuration.

## Capture one real request

Login, transport encryption, and media encryption are separate. Anonymous requests can still use HTTPS and device signatures. A working public playback endpoint avoids interception, but omitting account credentials does not expose a URL inside TLS. A user CA enables inspection only when the target client trusts it; it does not decrypt an encrypted video container.

Reuse authorization already present in the conversation. If a necessary step adds new certificate trust, changes a proxy/VPN, modifies an App, or deletes phone downloads beyond that authorization, explain the exact additional operation before requesting permission. User instructions override this guide.

1. Select the connected device once, read `profile`, and establish the selected series/episode identity using its directory or observed item link. Record the current download count and relevant playback settings. A cached episode may generate no media request; approved removal of one episode or a temporary quality change can trigger a fresh request. Restore only task changes and respect subsequent user edits to their downloads.
2. When already installed and authorized, PCAPdroid can capture only the target package through its local VPN and save a bounded PCAP. Its official [App API](https://github.com/emanuele-f/PCAPdroid/blob/master/docs/app_api.md) exposes the `CaptureCtrl` activity. Use typed extras: strings via `--es`, booleans via `--ez`, integers via `--ei`. Keep root capture, extra proxies, private-DNS blocking and QUIC blocking disabled unless the task requires and authorizes them. Verify the actual VPN UID scope. Do not capture unrelated Apps to look for credentials.
3. Trigger the selected official App action once and confirm the resulting UI and new media traffic. A TLS hostname or HTTP `CONNECT host:443` identifies a server, not the media path. Look for ClientHello records inside CONNECT tunnels as well as at the beginning of a TCP stream. Captured TLS ciphertext cannot be turned into an MP4 or a signed request without the relevant decryption capability.
4. HTTPS inspection is a distinct capability. The official [TLS setup](https://emanuele-f.github.io/PCAPdroid/tls_decryption) uses an addon and a local CA. A user CA may still be rejected by a release App or its native media SDK. Android's [`debug-overrides`](https://developer.android.com/privacy-and-security/security-config#debug-overrides) applies only to debuggable builds; its presence does not prove that this release trusts user certificates. Without a successful authorized decryption test, report `device_data_unavailable` instead of claiming signatures or media addresses were obtained.
5. If readable HTTP requests and responses are available, export only the selected App/episode traffic to a private temporary HAR. Keep raw requests, media query strings, session values, and keys out of stdout, final JSON, the skill bundle, and ordinary logs. First use the response already captured; this avoids a second signed API request.
6. Stop only the task capture and verify its VPN is inactive. Remove temporary raw captures, private request files, and task-created helpers after processing. Remove any task-installed temporary CA when the authorized test ends, using the recorded exact certificate identity; do not delete pre-existing user certificates. Never call phone cache completion remote download completion.

## Read a captured Hongguo playback response

```bash
python3 -I <skill-base>/scripts/inspect_app_capture.py <private.har> \
  --episode-id <selected-episode-id> --private-output <new-private-entry.json>
```

The helper matches the original playback request's `mixed_video_id_map["1004"]` and the exact response `data[episode_id].video_model`, preserving large numeric IDs. It handles HAR base64 response encoding, rejects wrong-episode responses, and prefers the latest captured success. Stdout contains counts and header names only. The optional private entry retains the original request and response without rewriting their bytes; it is created with private permissions and never overwritten. A PCAP containing only TLS records is not a HAR containing decrypted HTTP data.

The helper does not generate signatures, replay requests, decrypt TLS, or obtain a login from ADB. Its `observation_only` report is not a final video-download result. If `response_available` is false, stop that source rather than replacing the target with a different episode. If playback data contains a fallback model, validate its episode/video identity and expected duration before using it.

## Use playback media immediately

A valid clear HTTP(S) MP4 playback URL can be streamed to a file by `download_video.py`; it need not come from a Download button. Select a compatible clear rendition for the exact episode. Preserve actual codec, dimensions, and expected full duration privately for validation. Do not silently use a preview or lower-quality source when the caller requested a specific full rendition.

Use only the headers from the selected **CDN media request**. API signature headers belong to the API request and must not be copied wholesale onto CDN downloads. When needed, pass a private `--request-context` file as described in [downloading.md](downloading.md). Do not retrieve browser cookies to populate it. The download retains the same public JSON contract and outputs a relative `video_path` only after validation.

Encrypted MP4 (`encv`/`enca`, CENC, content-key metadata) is a separate content-encryption issue even after HTTPS is readable. The bundled downloader accepts clear MP4 and does not implement content decryption. Likewise, an HLS playlist is not an MP4 file: a host with a validated clear VOD-remux workflow may use it and then run the same MP4/identity/duration checks, but the bundled HTTP MP4 helper must reject a playlist instead of saving it with an `.mp4` extension. Do not claim untested encrypted-stream or HLS support.

For an explicitly requested remote destination, download directly there when possible. If a local intermediate file is necessary, transfer one video, verify remote byte size, SHA256 and media readability, then delete that local video before proceeding. Keep final relative paths based on the actual destination root. Record no completed path for an unavailable source.
