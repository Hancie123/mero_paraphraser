"""Word (.docx) files: export, import and personal-metadata cleanup. Standard library only.

build_docx     writes the result as a minimal .docx with no document properties
               at all: no author, no company, no edit time, no timestamps, no
               revision IDs. Zip entries carry a fixed date, so the file says
               nothing about when or by whom it was made.
read_docx      extracts the text (paragraphs, headings and tables) for paraphrasing.
clean_docx     removes personal information from an existing .docx, much like
               Word's "Inspect Document": author and editor names, timestamps,
               template paths, company, revision-session IDs (rsid), document
               variables, custom properties, the thumbnail and the list of
               comment authors (people.xml). Tracked changes and comments are
               kept but their author names become "Author". Text and formatting
               are not touched.
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from xml.etree import ElementTree as ET

from ..pipeline.sections import heading_name

MAX_DOCX_BYTES = 25 * 1024 * 1024
_MAX_UNCOMPRESSED = 200 * 1024 * 1024
_FIXED_DATE = (1980, 1, 1, 0, 0, 0)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {"w": W}


class DocxError(ValueError):
    pass


# ---------------------------------------------------------------- export

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\
<Default Extension="xml" ContentType="application/xml"/>\
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>\
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>\
</Types>"""
_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>\
</Relationships>"""
_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>\
</Relationships>"""


def _style(sid: str, name: str, ppr: str = "", rpr: str = "") -> str:
    return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/><w:basedOn w:val="Normal"/>'
            f'<w:next w:val="Normal"/><w:qFormat/><w:pPr>{ppr}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')


_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:styles xmlns:w="{W}">'
    '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>'
    '<w:sz w:val="22"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="276" w:lineRule="auto"/>'
    '</w:pPr></w:pPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
    + _style("Heading1", "heading 1", '<w:keepNext/><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="0"/>',
             '<w:b/><w:sz w:val="32"/>')
    + _style("Heading2", "heading 2", '<w:keepNext/><w:spacing w:before="200" w:after="60"/><w:outlineLvl w:val="1"/>',
             '<w:b/><w:sz w:val="26"/>')
    + _style("Heading3", "heading 3", '<w:keepNext/><w:spacing w:before="160" w:after="40"/><w:outlineLvl w:val="2"/>',
             '<w:b/><w:sz w:val="23"/>')
    + _style("Code", "Code", '<w:spacing w:after="0" w:line="240" w:lineRule="auto"/>',
             '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/><w:sz w:val="19"/>')
    + "</w:styles>"
)

_XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def _esc(text: str) -> str:
    text = _XML_INVALID.sub("", text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _runs(text: str) -> str:
    """Runs for one paragraph; newlines become line breaks and tabs become tabs."""
    parts: list[str] = []
    for i, line in enumerate(text.split("\n")):
        if i:
            parts.append("<w:br/>")
        for j, piece in enumerate(line.split("\t")):
            if j:
                parts.append("<w:tab/>")
            if piece:
                parts.append(f'<w:t xml:space="preserve">{_esc(piece)}</w:t>')
    return f"<w:r>{''.join(parts)}</w:r>" if parts else ""


def _para(text: str, style: str = "") -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}{_runs(text)}</w:p>"


_FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


def _body(text: str) -> list[str]:
    out: list[str] = []
    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    para: list[str] = []

    def flush() -> None:
        if not para:
            return
        block = list(para)
        para.clear()
        while block:
            first = block[0]
            md = re.match(r"^\s*(#{1,6})\s+(.*)$", first)
            if md:
                level = min(3, len(md.group(1)))
                out.append(_para(md.group(2).strip(), f"Heading{level}"))
                block.pop(0)
                continue
            if heading_name(first) is not None and len(first.split()) <= 12 and not first.rstrip().endswith("."):
                out.append(_para(first.strip().strip("*"), "Heading1"))
                block.pop(0)
                continue
            break
        if block:
            out.append(_para("\n".join(block)))

    while i < len(lines):
        line = lines[i]
        fence = _FENCE.match(line)
        if fence:
            flush()
            mark = fence.group(1)
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(mark[0] * len(mark)):
                out.append(_para(lines[i], "Code"))
                i += 1
            i += 1
            continue
        if line.strip():
            para.append(line)
        else:
            flush()
        i += 1
    flush()
    return out or [_para("")]


def build_docx(text: str) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body>' + "".join(_body(text))
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr></w:body></w:document>"
    )
    return _zip([
        ("[Content_Types].xml", _CONTENT_TYPES.encode()),
        ("_rels/.rels", _ROOT_RELS.encode()),
        ("word/document.xml", document.encode()),
        ("word/_rels/document.xml.rels", _DOC_RELS.encode()),
        ("word/styles.xml", _STYLES.encode()),
    ])


def _zip(entries: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            info = zipfile.ZipInfo(name, _FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            z.writestr(info, data)
    return buf.getvalue()


# ---------------------------------------------------------------- reading

def _open(data: bytes) -> zipfile.ZipFile:
    if len(data) > MAX_DOCX_BYTES:
        raise DocxError(f"the file is too large (max {MAX_DOCX_BYTES // (1024 * 1024)} MB)")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise DocxError("this is not a Word (.docx) file") from None
    infos = z.infolist()
    if len(infos) > 5000 or sum(i.file_size for i in infos) > _MAX_UNCOMPRESSED:
        raise DocxError("the file is too large to open")
    if "word/document.xml" not in z.namelist():
        raise DocxError("this is not a Word (.docx) document")
    return z


def _parse(xml: bytes) -> ET.Element:
    if b"<!DOCTYPE" in xml[:2048] or b"<!ENTITY" in xml:
        raise DocxError("the document contains unsupported XML")
    return ET.fromstring(xml)


def _text_of(p: ET.Element) -> str:
    out: list[str] = []
    for el in p.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "t" and el.text:
            out.append(el.text)
        elif tag == "tab":
            out.append("\t")
        elif tag in ("br", "cr"):
            out.append("\n")
    return "".join(out)


def read_docx(data: bytes) -> str:
    """Plain text of a .docx: one paragraph per block, table rows as tab-separated lines."""
    root = _parse(_open(data).read("word/document.xml"))
    body = root.find("w:body", _NS)
    if body is None:
        return ""
    paras: list[str] = []
    for child in body:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = _text_of(child)
            style = child.find("w:pPr/w:pStyle", _NS)
            sval = style.get(f"{{{W}}}val", "") if style is not None else ""
            m = re.match(r"(?i)heading\s*([1-6])", sval)
            if m and text.strip():
                text = "#" * int(m.group(1)) + " " + text.strip()
            paras.append(text)
        elif tag == "tbl":
            rows = []
            for tr in child.iter(f"{{{W}}}tr"):
                cells = [" ".join(_text_of(p) for p in tc.iter(f"{{{W}}}p")).strip() for tc in tr.iter(f"{{{W}}}tc")]
                rows.append("\t".join(cells))
            paras.append("\n".join(rows))
    # blank paragraphs separate blocks; collapse runs of them
    text = "\n\n".join(p for p in paras if p.strip())
    return text


# ---------------------------------------------------------------- personal-metadata cleanup

_EMPTY_CORE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
    'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>'
).encode()
_EMPTY_APP = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
    'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"/>'
).encode()

_REMOVED_PARTS = (
    (re.compile(r"^docProps/custom\.xml$"), "custom document properties"),
    (re.compile(r"^docProps/thumbnail\.\w+$"), "thumbnail preview"),
    (re.compile(r"^word/people\.xml$"), "comment author accounts"),
)
_RSID_ATTR = re.compile(rb'\s+w:rsid\w*="[^"]*"')
_RSIDS_EL = re.compile(rb"<w:rsids>.*?</w:rsids>", re.DOTALL)
_DOCVARS_EL = re.compile(rb"<w:docVars>.*?</w:docVars>", re.DOTALL)
_TEMPLATE_EL = re.compile(rb"<w:attachedTemplate\b[^>]*/>")
_AUTHOR_ATTR = re.compile(rb'(\sw:author=")[^"]*(")')
_INITIALS_ATTR = re.compile(rb'(\sw:initials=")[^"]*(")')
_DATE_ATTR = re.compile(rb'\s+w:date="[^"]*"')
_REL_EL = re.compile(rb"<Relationship\b[^>]*/>")
_OVERRIDE_EL = re.compile(rb"<Override\b[^>]*/>")


def _attr(el: bytes, name: bytes) -> str:
    m = re.search(rb"\s" + name + rb'="([^"]*)"', el)
    return m.group(1).decode() if m else ""


def _rels_base(rels_name: str) -> str:
    # "word/_rels/document.xml.rels" -> "word"; "_rels/.rels" -> ""
    return posixpath.dirname(posixpath.dirname(rels_name))


def clean_docx(data: bytes) -> tuple[bytes, list[str]]:
    """Returns (cleaned file, what was removed)."""
    z = _open(data)
    names = z.namelist()
    removed: set[str] = set()
    report: list[str] = []
    for name in names:
        for pat, label in _REMOVED_PARTS:
            if pat.match(name):
                removed.add(name)
                report.append(f"Removed {label}.")
    changes: dict[str, int] = {}
    entries: list[tuple[str, bytes]] = []
    for name in names:
        if name in removed or name.endswith("/"):
            continue
        blob = z.read(name)
        if name == "docProps/core.xml":
            blob = _EMPTY_CORE
            report.append("Cleared author, editor, title, dates and revision number.")
        elif name == "docProps/app.xml":
            blob = _EMPTY_APP
            report.append("Cleared application, company, template and editing-time details.")
        elif name.endswith(".xml") and name.startswith("word/"):
            before = blob
            blob = _RSID_ATTR.sub(b"", blob)
            if name == "word/settings.xml":
                blob = _RSIDS_EL.sub(b"", blob)
                blob = _DOCVARS_EL.sub(b"", blob)
                blob = _TEMPLATE_EL.sub(b"", blob)
            blob = _AUTHOR_ATTR.sub(rb"\1Author\2", blob)
            blob = _INITIALS_ATTR.sub(rb"\1A\2", blob)
            blob = _DATE_ATTR.sub(b"", blob)
            if blob != before:
                changes[name] = 1
        elif name.endswith(".rels"):
            base = _rels_base(name)

            def keep(m: re.Match) -> bytes:
                el = m.group()
                if _attr(el, b"TargetMode") == "External":
                    return el
                target = _attr(el, b"Target")
                path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base, target))
                return b"" if path in removed else el

            blob = _REL_EL.sub(keep, blob)
        elif name == "[Content_Types].xml":
            blob = _OVERRIDE_EL.sub(lambda m: b"" if _attr(m.group(), b"PartName").lstrip("/") in removed else m.group(), blob)
        entries.append((name, blob))
    if changes:
        report.append("Removed revision-session IDs, document variables and template path; "
                      "comment and tracked-change authors renamed to \"Author\" and their dates removed.")
    entries.sort(key=lambda e: e[0] != "[Content_Types].xml")
    seen: set[str] = set()
    report = [r for r in report if not (r in seen or seen.add(r))]
    return _zip(entries), report or ["No personal information found."]
