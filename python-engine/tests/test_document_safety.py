"""Tests for section-aware locking, code comment rewriting, invisible characters, em dashes and .docx files."""

import io
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.paraphrase import handle  # noqa: E402
from app.pipeline.code_guard import _tokens, rewrite_block, verify  # noqa: E402
from app.pipeline.language_refiner import LanguageRefiner, clean_dashes  # noqa: E402
from app.pipeline.sections import analyze  # noqa: E402
from app.utils.docx import build_docx, clean_docx, read_docx  # noqa: E402
from app.utils.invisible import purge  # noqa: E402


class InvisibleTests(unittest.TestCase):
    def test_removes_zero_width_and_friends(self):
        text, n = purge("a​b⁠c﻿d­e‌f‍g")
        self.assertEqual(text, "abcdefg")
        self.assertEqual(n, 6)

    def test_keeps_devanagari_joiners(self):
        nepali = "क्‍ष र क्‌ष"
        self.assertEqual(purge(nepali), (nepali, 0))

    def test_keeps_emoji_sequences(self):
        emoji = "👩‍💻 1️⃣ ❤️"
        self.assertEqual(purge(emoji)[0], emoji)

    def test_odd_spaces_become_spaces(self):
        self.assertEqual(purge("a b c")[0], "a b c")

    def test_removes_hidden_tag_characters(self):
        hidden = "hi" + "".join(chr(0xE0000 + ord(c)) for c in "secret")
        self.assertEqual(purge(hidden)[0], "hi")


class SectionTests(unittest.TestCase):
    def test_locks_declaration_sections_and_keeps_prose(self):
        text = (
            "Abstract\nWe study things.\n\nConclusion\nIt works.\n\nDeclarations\nFunding: none.\n\n"
            "Conflict of interest\nNone declared."
        )
        layout = analyze(text)
        locked = [text[b.start : b.end] for b in layout.blocks if b.kind == "locked"]
        self.assertEqual(locked, ["Declarations\nFunding: none.\n\nConflict of interest\nNone declared."])
        self.assertEqual([n for n, l in layout.sections if not l], ["Abstract", "Conclusion"])

    def test_finds_code_tables_and_math(self):
        text = (
            "Some prose here.\n\nimport os\nfor f in os.listdir('.'):\n    print(f)\n\n"
            "| a | b |\n|---|---|\n| 1 | 2 |\n\n$$x^2$$\n\nKeywords: remote work; wellbeing"
        )
        kinds = [b.kind for b in analyze(text).blocks]
        self.assertEqual(kinds, ["codeblock", "data", "math", "locked"])

    def test_plain_prose_is_not_code(self):
        self.assertEqual(analyze("We tested it; it worked.\n\nIf it rains, we stay in.").blocks, [])


PY = '''import os  # noqa: F401

def size(path):
    """Return the total size of all the files that are found in the folder."""
    # We utilize the os module in order to walk through every folder here.
    s = "# not a comment"
    return sum(os.path.getsize(p) for p in os.listdir(path))  # add up every file size
'''


class CodeGuardTests(unittest.TestCase):
    def code_tokens(self, src, lang):
        return [t for k, t in _tokens(src, lang) if k == "code"]

    def test_python_comments_reworded_code_identical(self):
        res = rewrite_block(PY, "python", 80, 3)
        self.assertGreater(res.rewritten, 0)
        self.assertNotEqual(res.text, PY)
        self.assertEqual(self.code_tokens(PY, "python"), self.code_tokens(res.text, "python"))
        self.assertIn("# noqa: F401", res.text)  # directives are never touched
        self.assertIn('s = "# not a comment"', res.text)

    def test_verify_rejects_code_changes(self):
        self.assertFalse(verify("x = 1  # set x\n", "x = 2  # set x\n", "python"))
        self.assertFalse(verify("int x = 1; // c\n", "int y = 1; // c\n", "c"))
        self.assertTrue(verify("x = 1  # set x\n", "x = 1  # sets x\n", "python"))

    def test_js_regex_literal_is_not_a_comment(self):
        js = "const re = /\\/*x/g; // match the special pattern in the input text\n"
        toks = _tokens(js, "js")
        self.assertEqual([k for k, _ in toks], ["code", "line", "code"])

    def test_shell_heredoc_and_strings(self):
        sh = "echo 'a # b' # say hello to everyone in the room\ncat <<EOF\n# data\nEOF\n"
        kinds = [k for k, _ in _tokens(sh, "bash".replace("bash", "shell"))]
        self.assertEqual(kinds.count("line"), 1)

    def test_rust_lifetimes(self):
        rs = "fn f<'a>(x: &'a str) -> char { 'x' } // first char\n"
        self.assertEqual([k for k, _ in _tokens(rs, "rust")], ["code", "line", "code"])

    def test_unknown_language_untouched(self):
        src = "foo bar ; baz // a comment that is long enough to rewrite\n"
        self.assertEqual(rewrite_block(src, "cobol", 80, 1).text, src)

    def test_doctests_untouched(self):
        src = 'def f():\n    """Return one value.\n\n    >>> f()\n    1\n    """\n    return 1\n'
        self.assertIn(">>> f()\n    1", rewrite_block(src, "python", 100, 1).text)


class SignatureAndDashTests(unittest.TestCase):
    def test_signatures_replaced_even_from_source(self):
        src = "Teachers play a pivotal role in learning. It delves into data and showcases a myriad of ideas."
        out = LanguageRefiner().refine(src, src).text
        self.assertEqual(out, "Teachers play a major part in learning. It looks at data and shows many ideas.")

    def test_dashes(self):
        self.assertEqual(
            clean_dashes("The results—which were clear—surprised us.")[0],
            "The results, which were clear, surprised us.",
        )
        self.assertEqual(clean_dashes("Three things — cost, time and risk.")[0], "Three things: cost, time and risk.")
        self.assertEqual(
            clean_dashes("It was clear — nobody came to the event.")[0], "It was clear. Nobody came to the event."
        )
        self.assertEqual(clean_dashes("From 2010–2020, pp. 4–7.")[0], "From 2010–2020, pp. 4–7.")


class PipelineTests(unittest.TestCase):
    def test_locked_sections_and_code_survive_the_pipeline(self):
        doc = (
            "Abstract\nThis study delves into remote work — and its costs.\n\n```js\n"
            "const x = 1; // we utilize this value in order to start the counter\n```\n\n"
            "Funding\nThis work was funded by the National Science Foundation (grant 12345)."
        )
        r = handle({"cmd": "paraphrase", "text": doc, "strength": 70, "seed": 2})
        self.assertIn("Funding\nThis work was funded by the National Science Foundation (grant 12345).", r["text"])
        self.assertIn("const x = 1; //", r["text"])
        self.assertNotIn("—", r["text"])
        self.assertNotIn("delves", r["text"])


class DocxTests(unittest.TestCase):
    def test_export_has_no_metadata_and_round_trips(self):
        blob = build_docx("# Title\n\nAbstract\nFirst paragraph.\n\n```\ncode line\n```")
        z = zipfile.ZipFile(io.BytesIO(blob))
        self.assertFalse(any(n.startswith("docProps/") for n in z.namelist()))
        self.assertTrue(all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in z.infolist()))
        self.assertEqual(read_docx(blob), "# Title\n\n# Abstract\n\nFirst paragraph.\n\ncode line")

    def test_export_is_deterministic(self):
        self.assertEqual(build_docx("Same text."), build_docx("Same text."))

    def test_clean_removes_personal_metadata(self):
        core = (
            '<?xml version="1.0"?><cp:coreProperties xmlns:cp="x" xmlns:dc="y"><dc:creator>Jane Doe</dc:creator>'
            "</cp:coreProperties>"
        )
        doc = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            '<w:p w:rsidR="00AB12CD"><w:ins w:author="Jane Doe" w:date="2026-01-01T00:00:00Z"><w:r><w:t>Hi</w:t></w:r></w:ins></w:p>'
            "</w:body></w:document>"
        )
        rels = (
            '<Relationships><Relationship Id="r1" Target="docProps/core.xml"/>'
            '<Relationship Id="r2" Target="docProps/custom.xml"/></Relationships>'
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(
                "[Content_Types].xml", '<Types><Override PartName="/docProps/custom.xml" ContentType="x"/></Types>'
            )
            z.writestr("_rels/.rels", rels)
            z.writestr("docProps/core.xml", core)
            z.writestr("docProps/custom.xml", "<Properties>secret</Properties>")
            z.writestr("word/document.xml", doc)
        cleaned, report = clean_docx(buf.getvalue())
        z = zipfile.ZipFile(io.BytesIO(cleaned))
        everything = b"".join(z.read(n) for n in z.namelist())
        self.assertNotIn(b"Jane Doe", everything)
        self.assertNotIn(b"rsid", everything)
        self.assertNotIn(b"custom.xml", everything)
        self.assertNotIn("docProps/custom.xml", z.namelist())
        self.assertIn(b"<w:t>Hi</w:t>", z.read("word/document.xml"))
        self.assertTrue(report)
        self.assertEqual(read_docx(cleaned), "Hi")

    def test_engine_commands(self):
        out = handle({"cmd": "export_docx", "text": "Hello."})
        self.assertEqual(handle({"cmd": "read_docx", "data": out["data"]})["text"], "Hello.")
        self.assertIn("removed", handle({"cmd": "clean_docx", "data": out["data"]}))


if __name__ == "__main__":
    unittest.main()
