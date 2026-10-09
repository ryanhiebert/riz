// The UI only sees text and session events. Python/Wasm values stay in the worker.
// This is a playground protocol, not a new public Riz embedding API.
export type Command =
  | { type: "execute"; id: number; source: string; force: boolean }
  | { type: "stop"; id: number };

export type Event =
  | { type: "loading"; text: string }
  | { type: "ready" }
  | { type: "accepted"; id: number }
  | { type: "continuation"; id: number }
  | { type: "output"; id: number; text: string }
  | { type: "finished"; id: number; text: string; error: boolean }
  | { type: "stopped"; id: number }
  | { type: "failure"; text: string };
