# Browser adapter routing

The workflow needs four semantic operations: navigate, inspect page UI, interact with the comment panel, and evaluate an arbitrary JavaScript function in the current page.

The host also needs Python 3, local file access, and shell/code execution for the bundled downloader. Browser tools alone cannot produce a verified local relative path. Page collection's `ready-to-download` state is not final success; follow `downloading.md` before returning JSON. This same host-side download step applies to every provider below.

Always evaluate the collectors in the main page world. Some extension or Apple-event browser surfaces execute in an isolated world: DOM content remains visible but the site SDK, route globals, and React view-model do not. Use the provider's documented main-world capability. Never diagnose this as a missing login merely because page globals are absent.

## Silence before navigation

Create a task tab on `about:blank`, then prepare audio control before visiting the share/video URL. Prefer the provider's native per-tab mute, which also silences Web Audio and survives redirects. Keep it enabled for the whole run. Otherwise, register the function in `scripts/page_silence.js` to run at document start in the task tab and its frames; reinject it in the current document as a backup. Verify media elements remain muted with zero volume, including after the player attempts to unmute.

With a Playwright code-execution tool, read its actual schema and call `await page.addInitScript({ content: '(' + silenceFunctionText + ')()' })` on the blank task page before `page.goto(...)`. Register this only on the task page, not on the user's entire browser context. With a CDP surface that exposes initialization commands, `Page.addScriptToEvaluateOnNewDocument` serves the same purpose; use the provider's documented command surface.

An ordinary evaluation call on `about:blank` does not survive navigation. If the surface only exposes evaluation in an already loaded page and has no per-tab mute or document-start hook, return `audio_control_unavailable` before navigation. Do not change system volume, browser preferences, or another tab's audio settings. A native tab mute is required if the site emits audio through Web Audio rather than media elements.

## Cleanup

Copy the final result out of page memory, then close all task-created tabs. Close a task-launched browser and verify its process exits. For an externally attached browser, release the task's session/connection and keep the external browser running. If the provider's close operation quits an attached browser, do not call it; use per-tab close and documented attachment release instead. Apply cleanup on success, failure, and cancellation, after any user challenge handoff has ended.

## Provider-based harnesses

Use the single browser provider already registered for the live Agent Session. Do not try to switch providers at runtime. Browser ownership and state belong to that exact Session; after a Session reload, resume, or fork, inspect the current pages and reinject the capture script.

### Playwright MCP provider

- Use the visible `mcp__playwright-mcp__*` tools.
- Navigate and inspect with the provider's navigation and snapshot tools.
- Use its page-evaluation tool for the complete function text from each `.js` file.
- An attached existing Chromium session is preferred because it retains the user's login. A launched browser works only after the user logs in there.

### Chrome DevTools MCP provider

- Use the visible `mcp__chrome-devtools-mcp__*` tools.
- Select the correct page before navigation or evaluation.
- Use the provider's script-evaluation tool for the complete function text from each `.js` file.
- Prefer attach mode to the user's existing logged-in Chromium session.

### Stagehand-only provider

The Stagehand action/observe/extract surface does not guarantee arbitrary page-JavaScript evaluation. If no raw evaluation tool is visible, return the `browser_unavailable` JSON error. Natural-language extraction cannot replace the signed in-page pagination workflow.

## Other browser surfaces

Match tools by capability rather than brand. The same page scripts work when the surface can execute a JavaScript function in the logged-in tab and preserve page state across calls. Do not paste scripts into the address bar or DevTools manually on the user's behalf.
