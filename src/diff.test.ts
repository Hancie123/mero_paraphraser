import { describe, expect, it } from "vitest";
import { diffCounts, diffWords, type DiffOp } from "./diff";
import { caretAfterChange, initHistory, record, redo, undo } from "./history";

const side = (ops: DiffOp[], skip: DiffOp["type"]) =>
  ops
    .filter((o) => o.type !== skip)
    .map((o) => o.text)
    .join("");

describe("diffWords", () => {
  it("finds a single word swap", () => {
    expect(diffWords("the big dog ran", "the large dog ran")).toEqual([
      { type: "equal", text: "the " },
      { type: "delete", text: "big" },
      { type: "insert", text: "large" },
      { type: "equal", text: " dog ran" },
    ]);
  });

  it("groups neighbouring changes into one region", () => {
    const ops = diffWords("a big red dog", "a large brown dog");
    expect(ops).toContainEqual({ type: "delete", text: "big red" });
    expect(ops).toContainEqual({ type: "insert", text: "large brown" });
  });

  it("rebuilds both texts", () => {
    const before = "We did not see it.\n\nThe results suggest that it may work, e.g. in the U.S.";
    const after = "We didn't see it.\n\nThe findings suggest it may work, for example in the U.S.!";
    const ops = diffWords(before, after);
    expect(side(ops, "insert")).toBe(before);
    expect(side(ops, "delete")).toBe(after);
    expect(diffCounts(ops).added).toBeGreaterThan(0);
  });

  it("handles empty and identical text", () => {
    expect(diffWords("", "")).toEqual([]);
    expect(diffWords("same text", "same text")).toEqual([{ type: "equal", text: "same text" }]);
    expect(diffWords("", "new")).toEqual([{ type: "insert", text: "new" }]);
  });

  it("falls back to one replacement when the texts are too different", () => {
    const ops = diffWords("one two three", "four five six", 1);
    expect(side(ops, "insert")).toBe("one two three");
    expect(side(ops, "delete")).toBe("four five six");
  });
});

describe("history", () => {
  it("coalesces typing and undoes/redoes", () => {
    let h = initHistory("");
    h = record(h, "a", 1000, true);
    h = record(h, "ab", 1200, true);
    h = record(h, "ab pasted", 1300, false);
    expect(h.past).toEqual(["", "ab"]);
    h = undo(h);
    expect(h.present).toBe("ab");
    h = undo(h);
    expect(h.present).toBe("");
    h = redo(h);
    expect(h.present).toBe("ab");
    h = record(h, "abc", 5000, true);
    expect(h.future).toEqual([]);
  });

  it("puts the caret at the end of the change", () => {
    expect(caretAfterChange("hello world", "hello brave world")).toBe(12);
    expect(caretAfterChange("abc", "")).toBe(0);
  });
});
