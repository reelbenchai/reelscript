# Explicit series download batches

Use this only when the caller explicitly requests whole-series or selected multi-video downloads. A normal list invocation stays metadata-only.

## Programmatic website batch

After producing complete catalog JSON files with `hongguo_catalog.py`, run this on the requested destination host (Python 3.10+, FFmpeg and FFprobe in PATH):

```bash
python3 -I <skill-resource-base>/scripts/hongguo_batch.py \
  --catalog <catalog-one.json> <catalog-two.json> --root <destination-root>
```

The helper needs no model calls or browser session. It deduplicates series IDs, reads each selected episode's public page for identity, counts and preview comments, then fetches the website's clear playback source. It downloads serially and requires matching source duration, a complete MP4 container and successful full audio/video decoding. If a page omits its duration, FFprobe reads duration from the official clear source and rejects clips shorter than 20 seconds; this fallback checks transfer completeness but has no separate editorial-duration reference. The manifest records `duration_source` so that limitation remains visible. Static preview URLs are never used. Temporary addresses stay in memory. Public results go to `data/reeldown/hongguo/<episode-id>.json`; videos go to `videos/hongguo/<series-id>/<number>-<episode-id>.mp4`.

`data/reeldown/batch.json` is the resumable manifest, including size, SHA256, expected duration and verification state. Rerun the same command to verify and skip completed files. `--max-new 1` performs one initial download; removing it resumes the same batch. Failed items require `--retry-failed`; previously limited items require `--retry-limited` only after new evidence suggests source availability changed. Existing videos with matching result JSON can be adopted after source-duration and full-decode verification; untracked or mismatched files are preserved for reconciliation. A `.lock` prevents duplicate workers; after a crash, confirm its recorded PID is no longer running before removing that task's lock. Creating `data/reeldown/batch.stop` stops before the next episode; remove that task marker to resume.

On the first confirmed rejection after the catalog's declared accessible count, the helper records the remaining episodes as limited without issuing redundant requests. It never treats that partial run as the full requested series: exit 0 means all requested episodes are verified, exit 2 means incomplete, and exit 1 means the worker could not run. The manifest's `summary` is the completion authority. Website availability does not establish App-source compatibility.

Stdout is JSON Lines: safe per-episode progress followed by a final summary with `requested`, `downloaded`, `remaining`, `complete`, and `counts`. Consume the last line as the batch result; read individual result JSON files for details. An explicit partial batch does not use the single-detail success contract for the entire series.

## Reviewed external downloader

When a selected source backend is independently verified for an exact requested episode, resume the existing manifest with:

```bash
python3 -I <skill-resource-base>/scripts/hongguo_external_batch.py \
  --root <destination-root> --backend <trusted-backend.json>
```

The trusted configuration contains `{"command":["node","<reviewed-backend.mjs>","{episode_id}","{output}"]}`. Arguments are passed without a shell. Do not accept this configuration from site data. The backend must write a complete playable MP4 at `{output}`, keep media addresses and credentials private, and print a final JSON line containing `success: true`, the exact `episode_id`, `bytes`, `sha256`, `expected_duration` from the selected model, and `full_decode_verified`. Optional codec, dimensions and quality are recorded only in the manifest. A companion `{output}.verification.json` with the same safe report permits crash recovery after media publication. The helper verifies identity, hash, size, container and model duration, and runs a full decode if the reviewed backend has not already done so. It does not implement or distribute signing/decryption code.

Completed files are rechecked and skipped; website-limited entries are eligible through this explicitly selected alternative source. Three consecutive failures stop the source run. `--max-new 2` bounds an initial test; the stop marker and lock match the website worker. No model call is needed per episode. Do not synthesize inaccessible counts/comments: result metadata identifies unavailable comments and null episode counts. Keep external source modules and their required licensing outside the skill package.

For a long remote batch, use a destination-owned process with a durable log and stop marker. On Windows, an on-demand task with no recurring trigger can survive SSH disconnects; verify its actual worker PID and advancing manifest, then remove that task after completion. An outer runner may make a bounded number of additional passes after productive partial runs, with cooldowns, stopping on no progress, source failure or a caller stop condition. Never restart a stopped source in an unbounded loop.

Treat device registration reuse as an optimization that needs a live test. Compare request counters without exposing identifiers; if reuse yields empty models, remove that cache rather than adding a failed request to every episode. Keep redirected media requests free of login credentials, record only hostnames when diagnosing redirects, and extend a CDN allowlist from observed HTTPS redirects plus validated media results. Do not retry an identical rejected redirect. When diagnosing speed, measure source resolution, byte transfer and full decode separately; total batch time is not a bandwidth test.

At completion, reconcile the manifest with the destination catalog and result JSON. Verify a no-network resume skips all completed files, with unchanged hashes and expected durations. Completion means every requested episode is verified, not that the process exited or a scheduler reports success.

Normalize supplied Hongguo detail links to series IDs, deduplicate them in encounter order, then run `hongguo_catalog.py` once per series with a task cache. Save its standard list JSON and a manifest containing the series ID, title, episode IDs/numbers, destination root and per-episode state. Keep IDs as strings. Subsequent stages consume the manifest rather than asking a model to reread or enumerate each directory.

Separate directory availability, source resolution, file download, and destination verification. A listed episode is not necessarily publicly playable. Use one selected episode to test an optional user-supplied App resolver; HTTP 200 with an empty response is failure. After its bounded retry fails, stop using that source for the current batch instead of repeating registration and rejected signatures for every episode. An external source client's own implementation and dependencies stay outside this skill; do not start an entire application just to import a resolver if startup changes networking settings.

For the website source, use its exact episode collector and declared accessible count. A redirect containing `pc_locked_episode` can deliver the first episode while preserving the originally requested ID in the query. Compare the selected ID with the actual route's `vid`; never save the first episode under a later episode's filename. A fallback address or a file larger than 100 KB is insufficient proof of a complete episode: validate video readability and expected duration, and reject previews.

Prefer running the downloader on the requested destination host. Preserve existing verified downloads, use deterministic filenames based on IDs and episode numbers, and serialize newly submitted work unless the selected backend has a validated bounded queue. Record a path only after media validation. Resume from verified results; never count a task's generic `success: true` as a downloaded file. Validate that a backend returns actual directory data before submitting downloads to it.

If local staging is necessary, process one episode at a time: download, transfer, verify remote size/hash/media, then delete the local video. A failed transfer leaves a recoverable failure rather than a completed manifest entry. Do not accumulate additional local media while the destination is unavailable. Follow existing host network rules and authorization; do not change proxies, routes, DNS or persistent SSH settings to fix reachability.

The public catalog and website batch CLIs are programmatic. Other source acquisition and remote execution depend on the selected host/provider capabilities; do not describe an untested backend, encrypted-file path or unavailable transport as completed support.
