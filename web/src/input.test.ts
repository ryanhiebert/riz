import { describe, expect, it } from "vitest";
import { Input, literal } from "./input";
import { displayText, layout } from "./layout";

describe("entry editing", () => {
  it("inserts, deletes and moves without splitting Unicode graphemes", () => {
    const input = new Input();
    input.insert("a🐍e\u0301");
    input.backspace();
    expect(input.text).toBe("a🐍");
    input.left();
    expect(input.cursor).toBe(1);
    input.insert("b");
    input.delete();
    expect(input.text).toBe("ab");
  });

  it("pastes multiple lines literally and converts tabs to indentation", () => {
    const input = new Input();
    input.insert("fn half(n):\r\n\tn / 2\r\nhalf(5)\n");
    expect(input.text).toBe("fn half(n):\n  n / 2\nhalf(5)\n");
  });

  it("navigates multiline entries and restores the draft after browsing history", () => {
    const input = new Input();
    input.insert("fn half(n):\n  n / 2");
    input.finish();
    input.insert("draft");
    input.up();
    expect(input.text).toBe("fn half(n):\n  n / 2");
    input.down();
    expect(input.text).toBe("draft");
    input.insert("\nsecond");
    input.home();
    input.up();
    expect(input.cursor).toBe(0);
    input.down();
    expect(input.cursor).toBe(6);
  });

  it("does not remember abandoned input", () => {
    const input = new Input();
    input.insert("abandoned");
    input.finish(false);
    input.up();
    expect(input.text).toBe("");
  });
});

describe("terminal layout", () => {
  it("places a cursor on wrapped input with wide and combining characters", () => {
    expect(layout("ab🐍e\u0301", 2, 9)).toEqual({
      rows: ["riz> ab", "🐍e\u0301"], cursorRow: 1, cursorColumn: 0,
    });
    expect(layout("ab🐍e\u0301", 6, 9).cursorColumn).toBe(3);
  });

  it("renders logical continuation prompts and reserves an unused column", () => {
    expect(layout("1\n2", 3, 80)).toEqual({
      rows: ["riz> 1", "...| 2"], cursorRow: 1, cursorColumn: 6,
    });
  });

  it("strips terminal controls from program output", () => {
    expect(literal("\x1b[2Jhello\r\n")).toBe("[2Jhello\n");
    expect(displayText("a\tb\n")).toBe("a  b\n");
  });
});
