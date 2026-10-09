import stringWidth from "string-width";
import { graphemes, literal } from "./input";

export interface Layout { rows: string[]; cursorRow: number; cursorColumn: number }

export function layout(text: string, cursor: number, columns: number): Layout {
  // Leave one column unused to avoid the terminal's deferred auto-wrap state.
  const width = Math.max(6, columns - 1);
  const rows = ["riz> "];
  let column = 5;
  let cursorRow = 0;
  let cursorColumn = column;
  for (const { segment, index } of graphemes(text)) {
    const size = stringWidth(segment);
    if (segment !== "\n" && column + size > width) {
      rows.push("");
      column = 0;
    }
    if (index === cursor) {
      cursorRow = rows.length - 1;
      cursorColumn = column;
    }
    if (segment === "\n") {
      rows.push("...| ");
      column = 5;
    } else {
      rows[rows.length - 1] += segment;
      column += size;
    }
  }
  if (cursor === text.length) {
    cursorRow = rows.length - 1;
    cursorColumn = column;
  }
  return { rows, cursorRow, cursorColumn };
}

export function displayText(text: string): string {
  // Preserve newlines; show tabs with predictable spacing. Escape sequences from
  // a Riz program must not be able to clear the transcript or change terminal modes.
  return literal(text).replace(/\t/g, "  ");
}
