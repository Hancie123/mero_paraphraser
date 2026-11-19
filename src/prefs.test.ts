import { describe, expect, it } from "vitest";
import { addTo, formatPreferred, parseList, parsePreferred, toRequest } from "./prefs";

describe("word preferences", () => {
  it("parses one entry per line, dropping blanks and duplicates", () => {
    expect(parseList("Mero  Paraphraser\n\n  p-value \nmero paraphraser")).toEqual(["Mero Paraphraser", "p-value"]);
  });

  it("parses preferred synonyms with =, -> or →", () => {
    expect(parsePreferred("Utilize = use\nin order to -> to\nbig → huge\nno separator\nsame = Same")).toEqual({
      utilize: "use",
      "in order to": "to",
      big: "huge",
    });
  });

  it("round-trips preferred synonyms", () => {
    const p = { utilize: "use", "in order to": "to" };
    expect(parsePreferred(formatPreferred(p))).toEqual(p);
  });

  it("adds to a list once, ignoring case", () => {
    expect(addTo(["Foo"], "foo")).toEqual(["Foo"]);
    expect(addTo(["Foo"], " bar ")).toEqual(["Foo", "bar"]);
  });

  it("maps to the engine's request fields", () => {
    expect(toRequest({ locked: ["a"], preferred: { b: "c" }, banned: ["d"] })).toEqual({
      locked_terms: ["a"],
      preferred: { b: "c" },
      banned: ["d"],
    });
  });
});
