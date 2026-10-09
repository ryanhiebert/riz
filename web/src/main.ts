import "./style.css";
import { ShellTerminal } from "./terminal";
import type { Command, Event } from "./protocol";

const shell = new ShellTerminal(document.querySelector<HTMLElement>("#terminal")!);
const status = document.querySelector<HTMLElement>("#status")!;
const run = document.querySelector<HTMLButtonElement>("#run")!;
const stop = document.querySelector<HTMLButtonElement>("#stop")!;
const reset = document.querySelector<HTMLButtonElement>("#reset")!;
const examples = Array.from(document.querySelectorAll<HTMLButtonElement>("[data-example]"));
const sources: Record<string, string> = {
  ratio: "5 / 2",
  function: "fn half(n):\n  n / 2\nhalf(5)",
  python: 'match use.python.import("math"):\n'
    + '  Ok(math):\n'
    + '    match math.attr("isqrt"):\n'
    + '      Ok(isqrt):\n'
    + '        match isqrt(9):\n'
    + '          Ok(value): value.integer()\n'
    + '          Err(error): None\n'
    + '      Err(error): None\n'
    + '  Err(error): None',
};
let worker: Worker;
let ready = false;
let active: number | null = null;
let nextId = 0;
let watchdog: ReturnType<typeof setTimeout> | undefined;
let loadingTimer: ReturnType<typeof setTimeout> | undefined;

function controls() {
  run.disabled = !ready || active !== null;
  stop.disabled = !ready || active === null;
  for (const button of examples) button.disabled = run.disabled;
}

function send(command: Command) { worker.postMessage(command); }

function failure(text: string) {
  clearTimeout(watchdog);
  clearTimeout(loadingTimer);
  ready = false;
  active = null;
  if (shell.input.text) shell.commit(false);
  shell.enabled = false;
  worker.terminate();
  status.textContent = "Could not start or continue the shell. Use Reset to retry.";
  shell.write(text + "\n");
  controls();
}

function start() {
  clearTimeout(watchdog);
  clearTimeout(loadingTimer);
  ready = false;
  active = null;
  status.textContent = "Starting the shell…";
  controls();
  const current = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
  worker = current;
  loadingTimer = setTimeout(() => {
    status.textContent = "Still loading. Check your connection, or use Reset to retry.";
  }, 30_000);
  current.onerror = (event) => {
    if (current === worker) { console.error(event); failure("The browser runtime failed to load. Check your connection and reset."); }
  };
  current.onmessage = (message: MessageEvent<Event>) => {
    if (current !== worker) return;
    const event = message.data;
    if (event.type === "loading") { status.textContent = event.text; return; }
    if (event.type === "ready") {
      clearTimeout(loadingTimer);
      ready = true;
      status.textContent = "Ready";
      shell.prompt();
      controls();
      return;
    }
    if (event.type === "failure") { failure(event.text); return; }
    if (event.id !== active) return;
    if (event.type === "accepted") { shell.commit(); return; }
    if (event.type === "output") { shell.write(event.text); return; }
    clearTimeout(watchdog);
    active = null;
    if (event.type === "continuation") {
      status.textContent = "Continue the block, or press Run";
      shell.continuation();
    } else {
      if (event.type === "finished") {
        if (event.text) shell.write(event.text + "\n");
        status.textContent = event.error ? "Ready · entry failed" : "Ready";
      } else {
        shell.write("Stopped. Unfinished bindings were discarded.\n");
        status.textContent = "Ready";
      }
      shell.prompt();
    }
    controls();
  };
}

shell.onSubmit = (source, force) => {
  if (!ready || active !== null) return;
  active = ++nextId;
  // Keep the draft until the worker says it is a complete entry. The worker uses
  // Riz's lexer to detect a block opener; the UI contains no copy of the grammar.
  status.textContent = "Running…";
  controls();
  send({ type: "execute", id: active, source, force });
};

// Commit input before the first execution output, but after continuation checks.
// The worker's accepted response supplies this boundary before output or results.
shell.onStop = () => {
  if (active === null || !ready) return;
  send({ type: "stop", id: active });
  status.textContent = "Stopping…";
  stop.disabled = true;
  clearTimeout(watchdog);
  watchdog = setTimeout(() => {
    status.textContent = "This entry cannot reach a checkpoint. Use Reset to restart the shell.";
  }, 1000);
};
run.addEventListener("click", () => shell.submit(true));
stop.addEventListener("click", () => shell.onStop());
reset.addEventListener("click", () => {
  worker.terminate();
  shell.reset();
  start();
});
for (const button of examples) {
  button.addEventListener("click", () => shell.example(sources[button.dataset.example!]));
}

start();
