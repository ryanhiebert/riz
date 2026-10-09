import type { PyodideInterface } from "pyodide";
import adapter from "../browser_adapter.py?raw";
import type { Command, Event } from "./protocol";

// Pin Python 3.14. The CDN download is lazy and only occurs when the shell starts.
const indexURL = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const send = (event: Event) => self.postMessage(event);
interface Reply { status: string; output: string; text: string; error: boolean }
interface Session {
  start(source: string, force: boolean): string;
  step(): string;
  stop(): void;
}
let session: Session;
let active: number | null = null;
let ready = false;

function fail(error: unknown) {
  active = null;
  ready = false;
  console.error(error);
  send({ type: "failure", text: "The browser runtime failed. Reset the shell to try again." });
}

function publish(id: number, reply: Reply) {
  if (reply.output) send({ type: "output", id, text: reply.output });
  if (reply.status === "continuation") {
    active = null;
    send({ type: "continuation", id });
  } else if (reply.status === "finished") {
    active = null;
    send({ type: "finished", id, text: reply.text, error: reply.error });
  } else {
    // A task boundary (not just a resolved Promise) lets Stop messages be handled.
    setTimeout(() => drive(id), 0);
  }
}

function drive(id: number) {
  if (active !== id) return;
  try { publish(id, JSON.parse(session.step()) as Reply); }
  catch (error) { fail(error); }
}

self.onmessage = (message: MessageEvent<Command>) => {
  if (!ready) return;
  const command = message.data;
  try {
    if (command.type === "stop") {
      if (active !== command.id) return;
      session.stop();
      active = null;
      send({ type: "stopped", id: command.id });
    } else if (active === null) {
      active = command.id;
      const reply = JSON.parse(session.start(command.source, command.force)) as Reply;
      if (reply.status !== "continuation") send({ type: "accepted", id: command.id });
      publish(command.id, reply);
    }
  } catch (error) { fail(error); }
};

async function initialize() {
  send({ type: "loading", text: "Loading Python for the browser…" });
  const module = await import(/* @vite-ignore */ `${indexURL}pyodide.mjs`) as {
    loadPyodide(options: { indexURL: string }): Promise<PyodideInterface>;
  };
  const pyodide = await module.loadPyodide({ indexURL });
  send({ type: "loading", text: "Loading Riz…" });
  const manifestURL = new URL(`${import.meta.env.BASE_URL}runtime/riz-wheel.json`, self.location.origin);
  const response = await fetch(manifestURL, { cache: "no-store" });
  if (!response.ok) throw new Error(`Wheel manifest: ${response.status}`);
  const manifest = await response.json() as { wheel: string };
  await pyodide.loadPackage("micropip");
  pyodide.globals.set("_wheel_url", new URL(manifest.wheel, manifestURL).href);
  await pyodide.runPythonAsync("import micropip\nawait micropip.install(_wheel_url)");
  pyodide.runPython(adapter);
  pyodide.runPython("_browser_session = Session()");
  session = pyodide.globals.get("_browser_session") as Session;
  // Python interoperability may write to stdout independently of Riz print.
  pyodide.setStdout({ batched: (text) => {
    if (active !== null) send({ type: "output", id: active, text: text + "\n" });
  } });
  pyodide.setStderr({ batched: (text) => {
    if (active !== null) send({ type: "output", id: active, text: text + "\n" });
  } });
  ready = true;
  send({ type: "ready" });
}

void initialize().catch(fail);
