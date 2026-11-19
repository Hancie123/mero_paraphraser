import { describe, expect, it } from "vitest";
import type { Segment } from "./api";
import { countWords, replaceSegment, wantsAn } from "./text";

const join = (segments: Segment[]) => segments.map((s) => s.text).join("");

describe("wantsAn", () => {
  it.each([
    ["apple", true],
    ["Elephant", true],
    ["banana", false],
    ["hour", true],
    ["honest", true],
    ["unique", false],
    ["university", false],
    ["European", false],
    ["one", false],
    ["umbrella", true],
    ["", false],
  ])("%s -> %s", (word, expected) => {
    expect(wantsAn(word)).toBe(expected);
  });
});

describe("replaceSegment", () => {
  it("replaces the text without mutating the input", () => {
    const segments: Segment[] = [{ text: "The " }, { text: "cat", original: "dog" }];
    const next = replaceSegment(segments, 1, "bird");
    expect(join(next)).toBe("The bird");
    expect(segments[1].text).toBe("cat");
  });

  it("switches 'a' to 'an' at the end of the previous chunk", () => {
    const next = replaceSegment([{ text: "It is a " }, { text: "big" }, { text: " deal." }], 1, "enormous");
    expect(join(next)).toBe("It is an enormous deal.");
  });

  it("switches 'an' to 'a'", () => {
    expect(join(replaceSegment([{ text: "It is an " }, { text: "easy" }], 1, "simple"))).toBe("It is a simple");
  });

  it("keeps the article's capitalisation", () => {
    expect(join(replaceSegment([{ text: "A " }, { text: "cat" }], 1, "owl"))).toBe("An owl");
    expect(join(replaceSegment([{ text: "An " }, { text: "owl" }], 1, "cat"))).toBe("A cat");
  });

  it("handles exceptions like 'an hour' and 'a unique'", () => {
    expect(join(replaceSegment([{ text: "a " }, { text: "day" }], 1, "hour"))).toBe("an hour");
    expect(join(replaceSegment([{ text: "an " }, { text: "odd" }], 1, "unique"))).toBe("a unique");
  });

  it("does not touch words that merely end in 'a'", () => {
    expect(join(replaceSegment([{ text: "Use a banana " }, { text: "cake" }], 1, "apple"))).toBe("Use a banana apple");
  });

  it("fixes an article that is its own changed segment", () => {
    const segments: Segment[] = [{ text: "a", original: "the" }, { text: " " }, { text: "test" }];
    expect(join(replaceSegment(segments, 2, "exam"))).toBe("an exam");
  });

  it("leaves the article alone when the span is deleted", () => {
    expect(join(replaceSegment([{ text: "an " }, { text: "old" }, { text: " car" }], 1, ""))).toBe("an  car");
  });

  it("leaves the first segment's neighbours alone", () => {
    expect(join(replaceSegment([{ text: "cat" }, { text: " sat" }], 0, "owl"))).toBe("owl sat");
  });
});

describe("countWords", () => {
  it.each([
    ["", 0],
    ["one", 1],
    ["Hello, world!", 2],
    ["don't stop", 2],
    ["It’s 2026 now", 3],
    ["  spaced   out  ", 2],
    ["नमस्ते संसार", 2],
  ])("%j has %i words", (text, expected) => {
    expect(countWords(text)).toBe(expected);
  });
});
