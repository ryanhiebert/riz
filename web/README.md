# Browser shell

An experimental xterm.js shell for the current Riz interpreter. It uses Python
3.14 through pinned Pyodide in a module Web Worker. The language and public
embedding API are unchanged.

## Local preview

Install Node.js 24 and uv. From this directory:

```console
npm ci
npm run build
npm run preview
```

Open <http://127.0.0.1:4173/>. `npm run dev` instead builds the wheel and starts
the development server at <http://127.0.0.1:5173/>. Rebuild/restart it after
changing the Python interpreter; the browser uses the built wheel, not your
live Python checkout. The first browser load needs internet access to download
Pyodide and micropip from jsDelivr.

Use Enter for ordinary entries. A line ending in a block opener starts a
multiline entry; finish with a blank line. Ctrl/Command Enter or Run submits the
entire entry immediately. Tab inserts two spaces. Arrow keys, Home/End,
Backspace/Delete, and Ctrl+A/E/U/K edit input. Up at the first line recalls
history, Down at the last line returns toward the draft. Pasting inserts text
without executing it. Example buttons fill the prompt without running it.

Ctrl+C abandons input, or requests Stop while execution is running. Selecting
text and using the platform copy shortcut copies the selection instead.
Reset clears runtime bindings and restarts the worker. Input history remains
available for rerunning entries after a reset.

## Verification and manual QA

From the repository root:

```console
uv run pytest
uv run basedpyright
```

From this directory:

```console
npm run check
npm test
npm run build
npx playwright install chromium firefox webkit
npm run test:browser
```

Playwright starts a production preview automatically. To run only Chromium,
append `-- --project=chromium`. Browser tests load the real wheel into Pyodide,
not a mocked interpreter. Paste tests dispatch clipboard events into xterm's
paste handler; Firefox's synthetic clipboard protection requires supplying the
event's payload explicitly. Tests also exercise ordinary keyboard input.
`npx playwright show-report` opens the HTML report; failures retain traces.
Desktop/mobile screenshots are saved under `test-results/`.
To verify repository-path hosting too:

```console
SITE_BASE_PATH=/riz/ npm run build
SITE_BASE_PATH=/riz/ npm run test:browser
```

For manual QA, try:

- `5 / 2`, then `x = 5 / 2`, then `x + x`: exact results and persistent bindings.
- Enter `fn half(n):`, then `  n / 2`, then a blank line; run `half(5)`.
- Paste a function and a call together; nothing executes until Run.
- `print("héllo 🐍")`: Unicode output, exactly one newline, silent Unit result.
- `True + 1` and `1 / 0`, then `2 + 3`: errors leave the shell usable.
- Define `n = 42`, run `n = 99` followed by `while True: ()` as one entry,
  Stop, then evaluate `n`: it is still 42. Reset, then `n`: a name error.
- Recall history, edit the middle of a wrapped line, resize the window, and
  submit with Ctrl/Command Enter.

## Boundaries and limitations

`src/protocol.ts` carries source strings and text events between the UI and
worker. Only `src/worker.ts` knows about Pyodide. `browser_adapter.py` implements
host execution policy using `Runtime.start`, `advance`, and `resume`. A future
Zig/Wasm worker can implement the same playground messages; the terminal and
observable-behavior browser tests can remain.

The adapter yields to the worker event loop between bounded batches of runtime
checkpoints and flushes each output request before resuming execution. Stop
drops the unfinished computation, preserving previously
completed entries. Printed output and foreign side effects are not rolled back.
This is an experiment in host policy, not Riz cancellation or exception semantics.
Parsing, checking, or an expensive operation may not reach a checkpoint; Reset
can terminate the worker regardless. There are no hard CPU or memory quotas.

Python imports retain their normal browser-Python capabilities, including access
to JavaScript. A worker keeps computation off the UI thread; it is not a security
boundary for adversarial programs. Unknown suspension requests and Python host
exceptions fail the worker and offer Reset; they are not translated into Riz
errors. Output is displayed as literal text, with terminal control characters
removed. Syntax highlighting is deferred.

The wheel is built from the checkout with `uv build` and placed under a SHA-256
directory. This prevents stale wheels when the package version has not changed.
Generated wheels and site files are ignored by Git.

## GitHub Pages

`.github/workflows/browser.yml` checks Python, builds the site, and runs Playwright
in Chromium, Firefox, and WebKit. On every push to `main`, a successful check job
is followed by a Pages build and deployment. Pull requests only run checks.
Both jobs use the pinned official Playwright container with browsers and system
libraries preinstalled; its version must match `@playwright/test` in `package.json`.
The deployment build uses Pages' configured base path and gets another Chromium
run before upload. The workflow uses the built-in GitHub token and OIDC; no
Cloudflare keys or GitHub secrets are needed.

Before the first deployment, set the repository's **Settings → Pages → Build and
deployment → Source** to **GitHub Actions**. Configure a custom domain in those
settings and its DNS separately when ready. No domain is hardcoded in the site.
When proxying through a CDN, keep HTML and `runtime/riz-wheel.json` fresh;
content-addressed assets and wheel directories can be cached for longer.
