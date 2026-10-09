import { test, expect, type Page } from "@playwright/test";

const transcript = (page: Page) => page.locator(".xterm-accessibility-tree");
const outputRow = (page: Page, text: string) => transcript(page).locator('[role="listitem"]')
  .filter({ hasText: new RegExp(`^${text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`) }).last();
async function ready(page: Page) {
  await expect(page.getByRole("status")).toHaveText("Ready", { timeout: 90_000 });
}
async function entry(page: Page, source: string) {
  await page.locator(".xterm-helper-textarea").focus();
  await paste(page, source);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(/^Ready/);
}
async function paste(page: Page, source: string) {
  await page.locator(".xterm-helper-textarea").evaluate((element, source) => {
    const data = new DataTransfer();
    data.setData("text/plain", source);
    const event = new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true });
    // Firefox protects DataTransfer data in synthetic clipboard events. Supply
    // the same clipboard payload there; xterm's real paste handler still runs.
    if (event.clipboardData?.getData("text/plain") !== source) {
      Object.defineProperty(event, "clipboardData", { value: { getData: () => source } });
    }
    element.dispatchEvent(event);
  }, source);
}

test.beforeEach(async ({ page }) => {
  await page.goto("./");
  await ready(page);
});

test("exact arithmetic and bindings persist across entries", async ({ page }) => {
  await entry(page, "x = 5 / 2");
  await entry(page, "x + x");
  await expect(outputRow(page, "5")).toBeVisible();
  await entry(page, "x");
  await expect(outputRow(page, "5/2")).toBeVisible();
});

test("block prompts use blank-line submission and definitions remain callable", async ({ page }) => {
  await page.keyboard.type("fn half(n):");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("Continue the block, or press Run");
  await expect(transcript(page)).toContainText("...|");
  await page.keyboard.type("  n / 2");
  await page.keyboard.press("Enter");
  await expect(transcript(page)).toContainText("n / 2");
  await page.keyboard.press("Enter");
  await ready(page);
  await entry(page, "half(5)");
  await expect(transcript(page)).toContainText("5/2");
});

test("pasting never executes and nested prints arrive before the result", async ({ page }) => {
  const source = 'fn inner(): print("héllo 🐍")\nfn outer(): inner()\nouter()\nprint("second")\n5 / 2\n';
  await paste(page, source);
  await expect(page.getByRole("status")).toHaveText("Ready");
  await expect(page.getByRole("button", { name: "Stop", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await ready(page);
  await expect(transcript(page)).toContainText("héllo 🐍");
  await expect(transcript(page)).toContainText("second");
  await expect(transcript(page)).toContainText("5/2");
  const text = await transcript(page).innerText();
  expect(text.lastIndexOf("héllo 🐍")).toBeLessThan(text.lastIndexOf("second"));
  expect(text.lastIndexOf("second")).toBeLessThan(text.lastIndexOf("5/2"));
});

test("errors recover and a failed entry does not define names", async ({ page }) => {
  await entry(page, "n = 42\n1 / 0");
  await expect(transcript(page)).toContainText("error: RizDivisionByZeroError");
  await entry(page, "n");
  await expect(transcript(page)).toContainText("error: RizNameError");
  await entry(page, "True + 1");
  await expect(transcript(page)).toContainText("error: RizTypeError");
  await entry(page, "1 +");
  await expect(transcript(page)).toContainText("error: RizParseError");
  await entry(page, "2 + 3");
  await expect(transcript(page)).toContainText("5");
});

test("Python interoperability output keeps its order with Riz print", async ({ page }) => {
  await entry(page, 'print("first")\n'
    + 'match use.python.import("builtins"):\n'
    + '  Ok(module):\n'
    + '    match module.attr("print"):\n'
    + '      Ok(write): write("second")\n'
    + '      Err(error): Err(error)\n'
    + '  Err(error): Err(error)\n'
    + 'print("third")');
  await expect(transcript(page)).not.toContainText("error:");
  for (const text of ["first", "second", "third"]) {
    await expect(outputRow(page, text)).toBeVisible();
  }
  const text = await transcript(page).innerText();
  expect(text.lastIndexOf("first")).toBeLessThan(text.lastIndexOf("second"));
  expect(text.lastIndexOf("second")).toBeLessThan(text.lastIndexOf("third"));
});

test("Stop breaks a runaway loop and Reset clears the session", async ({ page }) => {
  await entry(page, "n = 42");
  await paste(page, "n = 99\nwhile True: ()");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Running…");
  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await ready(page);
  await entry(page, "n");
  await expect(outputRow(page, "42")).toBeVisible();
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await ready(page);
  await entry(page, "n");
  await expect(transcript(page)).toContainText("error: RizNameError");
});

test("history, cursor edits and Unicode survive a narrow terminal", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await entry(page, 'print("a sufficiently long string to wrap the prompt: héllo 🐍")');
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("Home");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Backspace");
  await page.keyboard.type("p");
  await page.keyboard.press("Control+Enter");
  await ready(page);
  await expect(transcript(page)).toContainText("héllo 🐍");
  await expect(transcript(page)).not.toContainText("error:");
  await page.screenshot({ path: testInfo.outputPath("mobile.png"), fullPage: true });
});

test("examples fill input without running it", async ({ page }, testInfo) => {
  await page.getByRole("button", { name: "A function" }).click();
  await expect(page.getByRole("status")).toHaveText("Ready");
  await expect(transcript(page)).toContainText("half(5)");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await ready(page);
  await expect(transcript(page)).toContainText("5/2");
  await page.screenshot({ path: testInfo.outputPath("desktop.png"), fullPage: true });
});

test("Python interop example imports math and projects the result", async ({ page }, testInfo) => {
  await page.getByRole("button", { name: "Python interop" }).click();
  await ready(page);
  await expect(transcript(page)).toContainText('use.python.import("math")');
  await expect(transcript(page)).toContainText("isqrt(9)");
  await expect(outputRow(page, "Some(3)")).toHaveCount(0);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await ready(page);
  await expect(outputRow(page, "Some(3)")).toBeVisible();
  await expect(transcript(page)).not.toContainText("error:");
  await page.screenshot({ path: testInfo.outputPath("python-interop.png"), fullPage: true });
});

test("long pasted entries and editing a joined emoji keep input intact", async ({ page }) => {
  const source = Array.from({ length: 30 }, (_, i) => `n${i} = ${i}`).join("\n") + "\nn29 + 1";
  await paste(page, source);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await ready(page);
  await expect(transcript(page)).toContainText("30");
  await entry(page, 'print("👨‍👩‍👧‍👦")');
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("Backspace");
  await page.keyboard.type("hello");
  await page.keyboard.press("Control+Enter");
  await ready(page);
  await expect(outputRow(page, "hello")).toBeVisible();
  await expect(transcript(page)).not.toContainText("error:");
});

test("Reset remains available when a Python host call cannot yield", async ({ page }) => {
  const source = 'match use.python.import("builtins"):\n'
    + '  Ok(module):\n'
    + '    match module.attr("eval"):\n'
    + '      Ok(evaluate): evaluate("sum(iter(int, 1))")\n'
    + '      Err(error): Err(error)\n'
    + '  Err(error): Err(error)';
  await paste(page, source);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Running…");
  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("cannot reach a checkpoint");
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await ready(page);
  await entry(page, "2 + 3");
  await expect(transcript(page)).toContainText("5");
});

test("worker load failures offer Reset and can recover", async ({ page }) => {
  await page.route("**/pyodide.mjs", (route) => route.abort());
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Could not start");
  await expect(page.getByRole("button", { name: "Run", exact: true })).toBeDisabled();
  await page.unroute("**/pyodide.mjs");
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await ready(page);
  await entry(page, "6 / 4");
  await expect(transcript(page)).toContainText("3/2");
});
