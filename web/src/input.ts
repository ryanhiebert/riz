const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });

export function graphemes(text: string): { segment: string; index: number }[] {
  return Array.from(segmenter.segment(text), ({ segment, index }) => ({ segment, index }));
}

// User text is always literal; only the renderer emits terminal control codes.
export function literal(text: string): string {
  return text.replace(/\r\n?/g, "\n").replace(/[\x00-\x08\x0b-\x1f\x7f-\x9f]/g, "");
}

export class Input {
  text = "";
  cursor = 0;
  readonly history: string[] = [];
  private historyIndex = 0;
  private draft = "";

  insert(text: string) {
    text = literal(text).replace(/\t/g, "  ");
    this.text = this.text.slice(0, this.cursor) + text + this.text.slice(this.cursor);
    this.cursor += text.length;
  }

  replace(text: string) {
    this.text = literal(text);
    this.cursor = this.text.length;
  }

  left() {
    this.cursor = graphemes(this.text).filter(({ index }) => index < this.cursor).at(-1)?.index ?? 0;
  }

  right() {
    this.cursor = graphemes(this.text).find(({ index }) => index > this.cursor)?.index ?? this.text.length;
  }

  backspace() {
    const end = this.cursor;
    this.left();
    this.text = this.text.slice(0, this.cursor) + this.text.slice(end);
  }

  delete() {
    const start = this.cursor;
    this.right();
    this.text = this.text.slice(0, start) + this.text.slice(this.cursor);
    this.cursor = start;
  }

  home() { this.cursor = this.text.lastIndexOf("\n", this.cursor - 1) + 1; }
  end() {
    const newline = this.text.indexOf("\n", this.cursor);
    this.cursor = newline < 0 ? this.text.length : newline;
  }

  up() {
    const start = this.text.lastIndexOf("\n", this.cursor - 1) + 1;
    if (start === 0) { this.browse(-1); return; }
    const previous = this.text.lastIndexOf("\n", start - 2) + 1;
    this.cursor = previous + Math.min(this.cursor - start, start - previous - 1);
    this.snapCursor();
  }

  down() {
    const start = this.text.lastIndexOf("\n", this.cursor - 1) + 1;
    const end = this.text.indexOf("\n", this.cursor);
    if (end < 0) { this.browse(1); return; }
    const nextEnd = this.text.indexOf("\n", end + 1);
    this.cursor = end + 1 + Math.min(this.cursor - start,
      (nextEnd < 0 ? this.text.length : nextEnd) - end - 1);
    this.snapCursor();
  }

  private snapCursor() {
    if (this.cursor === this.text.length) return;
    this.cursor = graphemes(this.text).filter(({ index }) => index <= this.cursor).at(-1)?.index ?? 0;
  }

  private browse(direction: number) {
    if (this.historyIndex === this.history.length) this.draft = this.text;
    this.historyIndex = Math.max(0, Math.min(this.history.length, this.historyIndex + direction));
    this.replace(this.history[this.historyIndex] ?? this.draft);
  }

  finish(remember: boolean = true) {
    const entry = this.text.trimEnd();
    if (remember && entry && this.history.at(-1) !== entry) {
      this.history.push(entry);
      if (this.history.length > 100) this.history.shift();
    }
    this.text = "";
    this.cursor = 0;
    this.draft = "";
    this.historyIndex = this.history.length;
  }
}
