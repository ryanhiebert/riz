import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { UnicodeGraphemesAddon } from "@xterm/addon-unicode-graphemes";
import { Input } from "./input";
import { displayText, layout, type Layout } from "./layout";

export class ShellTerminal {
  readonly input = new Input();
  private readonly term: Terminal;
  private readonly fit = new FitAddon();
  private drawn: Layout | null = null;
  private transcript = "";
  enabled = false;
  onSubmit: (source: string, force: boolean) => void = () => {};
  onStop: () => void = () => {};

  constructor(element: HTMLElement) {
    this.term = new Terminal({
      allowProposedApi: true,
      convertEol: true,
      cursorBlink: true,
      cursorStyle: "bar",
      fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", monospace',
      fontSize: 15,
      lineHeight: 1.35,
      scrollback: 3000,
      screenReaderMode: true,
      theme: { background: "#111b24", foreground: "#e4edf2", cursor: "#a4e1bc",
        selectionBackground: "#375163" },
    });
    this.term.loadAddon(this.fit);
    this.term.loadAddon(new UnicodeGraphemesAddon());
    this.term.open(element);
    this.fit.fit();
    this.term.write("\x1b[?2004h"); // Bracketed paste: pasting never executes code.
    this.term.attachCustomKeyEventHandler((event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        if (event.type === "keydown") this.submit(true);
        return false;
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "c" && this.term.hasSelection()) {
        return false; // Let the browser copy the selected transcript.
      }
      return true;
    });
    this.term.onData((data) => this.receive(data));
    new ResizeObserver(() => {
      const oldColumns = this.term.cols;
      this.fit.fit();
      if (this.term.cols !== oldColumns) this.redrawTranscript();
    }).observe(element);
  }

  focus() { this.term.focus(); }

  prompt() {
    this.enabled = true;
    this.render();
    this.focus();
  }

  private receive(data: string) {
    if (data === "\x03") {
      if (!this.enabled) { this.onStop(); return; }
      this.commit(false);
      this.write("^C\n");
      this.prompt();
      return;
    }
    if (!this.enabled) return;
    if (data.startsWith("\x1b[200~") && data.endsWith("\x1b[201~")) {
      this.input.insert(data.slice(6, -6));
    } else {
      switch (data) {
        case "\r": this.submit(false); return;
        case "\x7f": this.input.backspace(); break;
        case "\x1b[3~": this.input.delete(); break;
        case "\x1b[D": this.input.left(); break;
        case "\x1b[C": this.input.right(); break;
        case "\x1b[A": this.input.up(); break;
        case "\x1b[B": this.input.down(); break;
        case "\x1b[H": case "\x1b[1~": case "\x01": this.input.home(); break;
        case "\x1b[F": case "\x1b[4~": case "\x05": this.input.end(); break;
        case "\x15": this.input.finish(false); break;
        case "\x0b": {
          const cursor = this.input.cursor;
          this.input.end();
          this.input.text = this.input.text.slice(0, cursor) + this.input.text.slice(this.input.cursor);
          this.input.cursor = cursor;
          break;
        }
        case "\t": this.input.insert("  "); break;
        default:
          if (data.startsWith("\x1b")) return;
          this.input.insert(data);
      }
    }
    this.render();
  }

  submit(force: boolean) {
    if (!this.enabled) return;
    if (!force && this.input.cursor < this.input.text.length) {
      this.input.insert("\n");
      this.render();
      return;
    }
    this.enabled = false;
    this.onSubmit(this.input.text, force);
  }

  continuation() {
    this.input.cursor = this.input.text.length;
    this.input.insert("\n");
    this.prompt();
  }

  example(source: string) {
    if (!this.enabled) return;
    this.input.replace(source);
    this.render();
    this.focus();
  }

  commit(remember: boolean = true) {
    const entry = this.input.text.split("\n").map((line, i) => `${i ? "...| " : "riz> "}${line}`).join("\n");
    this.term.write(this.eraseInput() + entry + "\r\n");
    this.record(entry + "\n");
    this.drawn = null;
    this.input.finish(remember);
    this.enabled = false;
  }

  write(text: string) {
    const displayed = displayText(text);
    this.term.write(displayed);
    this.record(displayed);
  }

  private record(text: string) {
    // Bound the replay buffer too, so resize cannot grow memory without limit.
    this.transcript += text;
    if (this.transcript.length > 200_000) {
      const start = this.transcript.length - 150_000;
      const newline = this.transcript.indexOf("\n", start);
      this.transcript = this.transcript.slice(newline < 0 ? start : newline + 1);
    }
  }

  private eraseInput() {
    const previous = this.drawn;
    let control = previous?.cursorRow ? `\x1b[${previous.cursorRow}A` : "";
    control += "\r\x1b[J";
    return control;
  }

  private render() {
    let control = this.eraseInput();
    const next = layout(this.input.text, this.input.cursor, this.term.cols);
    // Keep the editable region in the viewport even for a long pasted program.
    // The complete source is retained and printed into scrollback on submission.
    const maxRows = Math.max(1, this.term.rows - 1);
    const firstRow = Math.max(0, next.cursorRow - maxRows + 1);
    next.rows = next.rows.slice(firstRow, firstRow + maxRows);
    next.cursorRow -= firstRow;
    control += next.rows.join("\r\n");
    const up = next.rows.length - 1 - next.cursorRow;
    if (up) control += `\x1b[${up}A`;
    control += "\r";
    if (next.cursorColumn) control += `\x1b[${next.cursorColumn}C`;
    this.term.write(control);
    this.drawn = next;
  }

  private redrawTranscript() {
    this.term.reset();
    this.term.write("\x1b[?2004h" + this.transcript);
    this.drawn = null;
    if (this.enabled || this.input.text) this.render();
  }

  reset() {
    this.input.finish(false);
    this.enabled = false;
    this.drawn = null;
    this.transcript = "";
    this.term.reset();
    this.term.write("\x1b[?2004h");
  }
}
