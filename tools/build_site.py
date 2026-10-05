#!/usr/bin/env python3
"""Assemble reflowed, readable HTML for the scanned Bobbi Brown Makeup Manual.

Input : build/json/NNN.json (OCR lines + detected picture regions, one per page)
Output: index.html, assets/book.css, assets/book.js, assets/layout.json
"""

from __future__ import annotations

import html
import json
import os
import re
import statistics
import sys
import unicodedata
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def _option(name: str, default: str) -> str:
    """Read --name value from argv, else the matching environment variable."""
    argv = sys.argv[1:]
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return os.environ.get(name.upper().replace("-", "_"), default)


JSON_DIR = _option("--json", os.path.join(REPO, "work", "json"))
OUT_DIR = _option("--out", REPO)

# ---------------------------------------------------------------- dictionaries
WORDS: set[str] = set()
for name in ("web2", "words"):
    path = f"/usr/share/dict/{name}"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for word in fh:
                word = word.strip().lower()
                if word:
                    WORDS.add(word)
EXTRA = {
    "bobbi", "brown", "makeup", "eyeshadow", "eyeliner", "eyelash", "eyelashes",
    "concealer", "corrector", "concealers", "correctors", "mascara", "lipstick",
    "lipsticks", "lipgloss", "blush", "bronzer", "bronzers", "shimmer", "shimmers",
    "highlighter", "highlighters", "moisturizer", "moisturizers", "sunscreen",
    "cleanser", "toner", "exfoliant", "exfoliate", "exfoliating", "toners",
    "powder", "powders", "palette", "palettes", "swatch", "swatches", "gloss",
    "glosses", "tweezers", "sharpener", "sharpeners", "spatula", "spatulas",
    "sable", "taklon", "camellia", "talc", "mica", "dimethicone", "glycerin",
    "hyaluronic", "retinol", "antioxidant", "antioxidants", "spf", "noncomedogenic",
    "tester", "testers", "gazelle", "copacetic", "brows", "brow", "lash", "lashes",
    "smoky", "smokey", "dewy", "matte", "mattefying", "mattifying", "sallow",
    "undertone", "undertones", "overtones", "complexion", "complexions",
    "contour", "contouring", "strobing", "draping", "banding", "creasing",
    "flaking", "pilling", "cakey", "patchy", "oxidize", "oxidizes", "oxidizing",
    "photoshoot", "backstage", "runway", "editorial", "editorials", "lookbook",
    "calltime", "call", "kit", "kits", "brush", "brushes", "sponge", "sponges",
    "applicator", "applicators", "q-tip", "qtip", "tissues", "towelettes",
    "backstage", "touchup", "touch-ups", "reapply", "reapplying", "blendability",
    "longwearing", "long-lasting", "waterproof", "smudgeproof", "transferproof",
}

def is_word(token: str) -> bool:
    token = token.strip().lower()
    if not token:
        return False
    if token in WORDS or token in EXTRA:
        return True
    if token.isdigit():
        return True
    return False


# ------------------------------------------------------------------- page model
BODY_MIN_WORDS = 3


class Line:
    __slots__ = ("text", "x", "y", "w", "h", "conf")

    def __init__(self, record: dict) -> None:
        self.text = unicodedata.normalize("NFKC", str(record["text"])).strip()
        self.x = float(record["x"])
        self.y = float(record["y"])
        self.w = float(record["w"])
        self.h = float(record["h"])
        self.conf = float(record.get("conf", 1.0))


def load_pages() -> list[dict]:
    pages = []
    for name in sorted(os.listdir(JSON_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(JSON_DIR, name), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        lines = [Line(r) for r in data.get("lines", [])]
        lines = [ln for ln in lines if ln.text]
        lines.sort(key=lambda ln: (round(ln.y, 4), ln.x))
        pages.append(
            {
                "page": int(data["page"]),
                "lines": lines,
                "regions": data.get("regions", []),
                "width": data.get("width", 1),
                "height": data.get("height", 1),
            }
        )
    return pages


def body_height(pages: list[dict]) -> float:
    values = []
    for page in pages:
        for ln in page["lines"]:
            if len(ln.text.split()) >= BODY_MIN_WORDS:
                values.append(ln.h)
    if not values:
        return 0.012
    return statistics.median(values)


def chapter_heading_height(pages: list[dict], default: float) -> float:
    heights = []
    for page in pages:
        for ln in page["lines"]:
            if re.match(r"^chapter\s+\d+$", ln.text, re.I):
                heights.append(ln.h)
    if heights:
        return statistics.median(heights)
    return default


def body_left_margin(pages: list[dict]) -> float:
    xs = []
    for page in pages:
        for ln in page["lines"]:
            if len(ln.text.split()) >= BODY_MIN_WORDS and ln.h < 0.02:
                xs.append(round(ln.x, 3))
    if not xs:
        return 0.02
    return Counter(xs).most_common(1)[0][0]


# --------------------------------------------------------------- line cleaning
NOISE_PATTERNS = [
    re.compile(r"^www\.", re.I),
    re.compile(r"^\.?ebook\d+", re.I),
    re.compile(r"^ebook\d+\.com$", re.I),
    re.compile(r"^\d+\s*$"),
    re.compile(r"^[\W_]+$"),
]


GARBAGE_PATTERNS = [
    re.compile(r"^photo(graph|grapher)?\s*(by|:)", re.I),
    re.compile(r"^[-\u2013]?[A-Z][a-z]+ [A-Z][a-z]+$"),      # bare "Photo Credits" style pairs
    re.compile(r"^[.\-\u2013_\u00b7*\s]{2,}$"),            # punctuation soup
    re.compile(r"(ph|photograph|photo)\s*by.*(ph|photograph|photo)\s*by", re.I),
]


def non_dictionary_ratio(text: str) -> float:
    tokens = [t.strip(".,;:!?()\u201c\u201d\"'-").lower() for t in text.split()]
    tokens = [t for t in tokens if len(t) > 2 and t.isalpha()]
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if not is_word(t)) / len(tokens)


def is_noise(text: str, conf: float = 1.0) -> bool:
    stripped = text.strip()
    if len(stripped) < 2:
        return True
    for pattern in NOISE_PATTERNS:
        if pattern.match(stripped):
            return True
    if conf < 0.45:
        return True
    words = stripped.split()
    # a short line of pure gibberish is an OCR artefact, never book text
    if len(words) <= 4 and not any(is_word(t) for t in words):
        return True
    for pattern in GARBAGE_PATTERNS:
        if pattern.match(stripped):
            return True
    if non_dictionary_ratio(stripped) >= 0.70 and len(words) <= 12:
        return True
    # fragments of photograph credits ("...aph by Walter Chin"): a mangled
    # leading token followed by a preposition and proper names
    if len(words) <= 6 and re.search(r"\bby\b", stripped):
        head = words[0].lower()
        if len(head) >= 2 and not is_word(head):
            return True
    return False


def join_hyphen(left: str, right: str) -> str:
    """Join a line ending in a hyphen with the next line."""
    stem = left.rstrip()
    hyphenated = stem.endswith("-") or stem.endswith("\u2010") or stem.endswith("\u2013")
    if not hyphenated:
        return stem + " " + right.lstrip()
    head = stem[:-1]
    tail = right.lstrip()
    # keep genuine hyphenated compounds (make-up, long-lasting)
    tail_word = re.match(r"[A-Za-z]+", tail)
    if not tail_word:
        return stem + right.lstrip()
    joined = head.rsplit(" ", 1)[-1] + tail_word.group(0)
    if is_word(joined):
        # a real word is formed by closing the hyphen: it was a line break
        return head + tail
    if is_word(head.rsplit(" ", 1)[-1]) and is_word(tail_word.group(0)) and len(tail_word.group(0)) > 3:
        return stem + tail
    return head + tail


# ------------------------------------------------------------------ class rules
RE_CHAPTER = re.compile(r"^chapter\s+(\d+)$", re.I)
RE_PART = re.compile(r"^part\s+([ivx]+)\s*:?\s*(.*)$", re.I)
RE_STEP = re.compile(r"^(\d{1,2})[.)]?\s+(?=[A-Z\"\u201c])")
RE_BULLET = re.compile(r"^[\u2022\u00b7\u25aa\u25cf\u25ab\-\u2013]\s*")
SENTENCE_END = re.compile(r'[.!?:;\"\u201d\)]\s*$')


def is_all_caps(line: Line) -> bool:
    letters = [c for c in line.text if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) >= 0.9


class Classifier:
    """Geometry-driven classifier.

    OCR bounding-box heights track font size closely enough to separate
    headings from body text, but noisy lines are inflated, so a height rule is
    always corroborated by the line's shape (short and centred/single-line).
    """

    def __init__(self, pages: list[dict]) -> None:
        ordinary = [ln.h for page in pages for ln in page["lines"] if self.is_body_candidate(ln)]
        self.body_h = statistics.median(ordinary) if ordinary else 0.0135
        self.body_x = body_left_margin(pages)
        self.heading_h = self.body_h * 1.30

    @staticmethod
    def is_body_candidate(ln: Line) -> bool:
        # long, multi-word, sentence-sized lines are certainly body text
        return ln.w >= 0.30 and len(ln.text.split()) >= 3 and ln.h < 0.030

    def kind(self, ln: Line) -> str:
        text = ln.text.strip()
        if RE_CHAPTER.match(text):
            return "chapter"
        if RE_PART.match(text):
            return "part"
        return "heading" if self.is_heading(ln) else "body"

    def is_heading(self, ln: Line) -> bool:
        text = ln.text.strip()
        words = text.split()
        full_width = ln.w >= 0.85
        has_terminal = bool(SENTENCE_END.search(text))
        if len(words) == 0:
            return False
        # internal sentence punctuation means running text, not a title
        if re.search(r",|\.\s|\?\s|!\s", text):
            return False
        if ln.h >= self.body_h * 1.70:
            return not full_width or len(words) <= 9
        if is_all_caps(ln) and len(words) <= 9 and ln.w <= 0.65:
            return True
        if ln.w <= 0.55 and len(words) <= 8 and ln.h >= self.heading_h and not has_terminal:
            return True
        return False

    def looks_like_subhead(self, previous: Block, following: Line) -> bool:
        """True when `previous` is a short label introducing `following`."""
        if previous.kind != "p":
            return False
        words = previous.text.split()
        if not words or len(words) > 6 or previous.w > 0.55:
            return False
        if SENTENCE_END.search(previous.text):
            return False
        # a clause that broke at a comma is a list item, never a subhead
        if previous.text.rstrip().endswith((",", ";", "\u2014", "\u2013")):
            return False
        if starts_list_item(previous.text) or starts_list_item(following.text):
            return False
        if not any(c.isalpha() for c in previous.text):
            return False
        if "," in previous.text:
            return False
        # the next line must read like the start of a sentence or clause
        text = following.text.strip()
        if not text or not text[0].isupper():
            return False
        return True

    def heading_level(self, ln: Line) -> int:
        ratio = ln.h / max(self.body_h, 1e-6)
        if ratio >= 1.70:
            return 2
        if ratio >= 1.42:
            return 3
        return 4


# ------------------------------------------------------------- grouping a page
class Block:
    __slots__ = ("kind", "level", "text", "y", "x", "h", "w", "step", "cells")

    def __init__(self, kind: str, text: str, ln: Line, level: int = 0) -> None:
        self.kind = kind
        self.text = text
        self.y = ln.y
        self.x = ln.x
        self.h = ln.h
        self.w = ln.w
        self.level = level
        self.step = None
        self.cells: list[str] = []


def ends_sentence(text: str) -> bool:
    return bool(SENTENCE_END.search(text.strip()))


def group_page(page: dict, clf: Classifier) -> list[Block]:
    """Merge OCR lines into paragraphs, keeping record of each line's shape."""
    blocks: list[Block] = []
    for ln in page["lines"]:
        text = ln.text.strip()
        if is_noise(text, ln.conf):
            continue
        kind = clf.kind(ln)
        if kind in ("chapter", "part", "heading"):
            blocks.append(Block(kind, text, ln, clf.heading_level(ln)))
            continue

        # a short, unpunctuated line standing alone directly above a fresh
        # sentence is a run-in subhead, not the tail of a paragraph
        if blocks and clf.looks_like_subhead(blocks[-1], ln):
            blocks[-1].kind = "heading"
            blocks[-1].level = 4

        if blocks:
            previous = blocks[-1]
            gap = ln.y - (previous.y + previous.h)
            indented = ln.x > previous.x + 0.004
            lead = max(clf.body_h, min(previous.h, clf.body_h * 1.6))
            close = gap <= lead * 1.35
            mid_sentence = not ends_sentence(previous.text) and not starts_list_item(text)
            # a line that continues in lower case cannot open a new paragraph
            continues_lower = bool(re.match(r"^[a-z(\u201c\"]", text))
            # a short, unpunctuated fragment after a finished sentence is a
            # caption or a stray label, not the tail of the paragraph
            caption_like = (
                len(text.split()) <= 6
                and ln.w <= 0.25
                and not ends_sentence(text)
                and not continues_lower
                and ends_sentence(previous.text)
            )
            # a capitalised line after a comma or dash is the next item of a
            # list, not the continuation of the clause
            new_item = (
                previous.text.rstrip().endswith((",", ";", "\u2014", "\u2013"))
                and text[:1].isupper()
            )
            if (
                previous.kind == "p"
                and not starts_list_item(text)
                and (continues_lower or not indented)
                and not caption_like
                and not new_item
                and (continues_lower or (close and mid_sentence))
            ):
                previous.text = normalise_space(join_hyphen(previous.text, text))
                previous.h = min(previous.h, ln.h)
                previous.w = max(previous.w, ln.w)
                continue
        blocks.append(Block("p", text, ln))
    blocks = detect_lists(blocks, clf)
    return detect_tables(blocks, page["lines"], clf)


def group_rows(lines: list[Line]) -> list[list[Line]]:
    """Cluster OCR lines into visual rows by vertical overlap.

    Cells of one table row are often offset by a few pixels, so rows are built
    from the tallest line seen so far and any line whose vertical span overlaps
    it is attached to the same row.
    """
    rows: list[list[Line]] = []
    for ln in sorted(lines, key=lambda item: (item.y, item.x)):
        for row in reversed(rows[-3:]):
            reference = max(row, key=lambda item: item.h)
            overlap = min(ln.y + ln.h, reference.y + reference.h) - max(ln.y, reference.y)
            if overlap > 0.5 * min(ln.h, reference.h):
                row.append(ln)
                break
        else:
            rows.append([ln])
    return rows


def plausible_table(rows: list[list[str]], clf: Classifier) -> bool:
    """Reject paragraph text that merely looks like side-by-side lines."""
    # real table cells do not overlap horizontally
    for row in rows:
        if len(row) < 2:
            continue
        if not all(len(row[index].split()) <= 8 for index in range(len(row))):
            return False
    word_counts = sorted(len(cell.split()) for row in rows for cell in row)
    if word_counts and word_counts[len(word_counts) // 2] > 5:
        return False
    short_cells = sum(1 for cell in (cell for row in rows for cell in row) if len(cell.split()) <= 3)
    total = sum(len(row) for row in rows)
    if total and short_cells / total < 0.45:
        return False
    return True


def detect_tables(blocks: list[Block], page_lines: list[Line], clf: Classifier) -> list[Block]:
    """Replace runs of multi-cell rows with a single table block."""
    rows = group_rows([ln for ln in page_lines if ln.text.strip()])
    if not rows:
        return blocks

    bands: list[tuple[float, float]] = []
    run: list[list[Line]] = []
    for row in rows:
        if len(row) >= 2:
            run.append(row)
        elif run and len(run) >= 3:
            bands.append((min(c.y for r in run for c in r), max(c.y + c.h for r in run for c in r)))
            run = []
        elif run:
            run = []
    if len(run) >= 3:
        bands.append((min(c.y for r in run for c in r), max(c.y + c.h for r in run for c in r)))
    if not bands:
        return blocks

    result: list[Block] = []
    consumed: set[int] = set()
    tables: list[Block] = []

    for top, bottom in bands:
        members = [
            index
            for index, block in enumerate(blocks)
            if index not in consumed and top - 0.012 <= block.y <= bottom + 0.012
        ]
        if len(members) < 3:
            continue
        cell_lines = sorted(
            (ln for ln in page_lines if top - 0.012 <= ln.y <= bottom + 0.012),
            key=lambda item: (item.y, item.x),
        )
        table_rows = [
            [cell.text.strip() for cell in row]
            for row in group_rows(cell_lines)
            if len(row) >= 2
        ]
        if len(table_rows) < 3:
            continue
        if not plausible_table(table_rows, clf):
            continue
        anchor = min((blocks[index] for index in members), key=lambda block: block.y)
        table = Block("table", json.dumps(table_rows), anchor, 0)
        consumed.update(members)
        tables.append(table)

    for index, block in enumerate(blocks):
        if index not in consumed:
            result.append(block)
    result.extend(tables)
    result.sort(key=lambda item: item.y)
    return result


def starts_list_item(text: str) -> bool:
    return bool(RE_STEP.match(text) or RE_BULLET.match(text))


def detect_lists(blocks: list[Block], clf: Classifier) -> list[Block]:
    """A run of short, evenly spaced, unpunctuated lines is a list."""
    result: list[Block] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if block.kind != "p":
            result.append(block)
            index += 1
            continue
        run = [block]
        cursor = index + 1
        while cursor < len(blocks):
            candidate = blocks[cursor]
            if candidate.kind != "p":
                break
            gap = candidate.y - (run[-1].y + run[-1].h)
            short = candidate.w <= 0.62 and len(candidate.text.split()) <= 14
            tight = gap <= clf.body_h * 1.75
            plain = not ends_sentence(candidate.text)
            if short and tight and plain:
                run.append(candidate)
                cursor += 1
            else:
                break
        # a run counts as a list only when the book printed markers for it, and
        # a pair of lines is only convincing when they are numbered steps
        numbered = any(RE_STEP.match(item.text) for item in run)
        bulleted = [item for item in run if RE_BULLET.match(item.text)]
        qualifies = (numbered and len(run) >= 2) or (len(bulleted) >= 3 and len(bulleted) == len(run))
        if qualifies:
            for item in run:
                item.kind = "list" if numbered else "bullet"
                item.text = RE_BULLET.sub("", RE_STEP.sub("", item.text)).strip()
            result.extend(run)
        else:
            result.append(block)
        index = cursor if qualifies else index + 1
    return result


# --------------------------------------------------------------- front matter
RE_TOC_CHAPTER = re.compile(r"^(chapter\s+\d+)\s*:?\s*(.*)$", re.I)
RE_TOC_PART = re.compile(r"^(part\s+[ivx]+)\s*:?\s*(.*)$", re.I)


def toc_entries(pages: list[dict]) -> list[dict]:
    """Read the printed contents page and keep the printed order of entries."""
    entries: list[dict] = []
    for page in pages:
        for ln in page["lines"]:
            text = ln.text.strip()
            match = RE_TOC_CHAPTER.match(text) or RE_TOC_PART.match(text)
            if match:
                entries.append(
                    {
                        "label": match.group(1).strip(),
                        "title": match.group(2).strip(" .:"),
                        "page": page["page"],
                    }
                )
    return entries


# ------------------------------------------------------------- assemble content
def page_is_empty(page: dict) -> bool:
    return len(page["lines"]) == 0


def build_structure(pages: list[dict], clf: Classifier) -> dict:
    """Locate every chapter/part opening and pair it with the printed title."""
    chapter_re = re.compile(r"^chapter\s+(\d+)\s*:?\s*(.*)$", re.I)
    part_re = re.compile(r"^part\s+([ivx]+)\s*:?\s*(.*)$", re.I)
    by_page: dict[int, list[dict]] = {}

    for page in pages:
        if page["page"] <= 3:      # skip the printed contents page itself
            continue
        lines = page["lines"]
        for index, ln in enumerate(lines):
            text = ln.text.strip()
            chapter = chapter_re.match(text)
            part = part_re.match(text)
            if not (chapter or part):
                continue
            if ln.h < clf.body_h * 1.05 and ln.w < 0.10:
                continue
            title = (chapter or part).group(2).strip(" .:")
            if not title:
                # the title is set on the following, larger line
                for follow in lines[index + 1 : index + 4]:
                    if follow.h > ln.h * 1.02 and follow.w <= 0.70:
                        title = follow.text.strip()
                        break
            # drop a duplicated "MAKEUP ARTISTRY"-style repeat of the title
            entry = {
                "kind": "chapter" if chapter else "part",
                "label": (chapter or part).group(0).strip(),
                "number": int(chapter.group(1)) if chapter else None,
                "roman": part.group(1).upper() if part else None,
                "title": title,
                "page": page["page"],
            }
            key = entry["label"].lower()
            if key not in {e["label"].lower() for e in by_page.setdefault(page["page"], [])}:
                by_page[page["page"]].append(entry)

    structure: list[dict] = []
    for page_number in sorted(by_page):
        for entry in by_page[page_number]:
            structure.append(entry)
    return {"entries": structure}


def normalise_space(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # OCR often leaves a space before punctuation
    text = re.sub(r"\s+([,.;:!?%)\u201d\u2019])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    # tighten spaced em/en dashes: "word - word" -> "word\u2014word"
    text = re.sub(r"\s*[\u2013\u2014]\s*", "\u2014", text)
    return text


def render_inline(text: str) -> str:
    return html.escape(text, quote=False)


CSS = """
/* ---------------------------------------------------------------- palette */
:root {
  color-scheme: light;
  --paper: #faf8f5;
  --panel: #f2ece4;
  --panel-strong: #ffffff;
  --ink: #1d1a18;
  --muted: #6f6459;
  --accent: #a01e52;
  --rule: #e4ddd3;
  --shadow: 0 12px 34px rgba(0, 0, 0, .22);
  --shadow-soft: 0 20px 60px rgba(0, 0, 0, .5);
  --overlay: rgba(20, 16, 14, .9);
  --art-border: rgba(0, 0, 0, .16);
}

/* The colour theme follows the reader's operating system preference. Nothing
   is stored and nothing is toggled: if the system switches, so does the page.
   An explicit data-theme attribute on <html> is still honoured for any host
   that wants to force a theme. */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --paper: #121012;
    --panel: #1a171a;
    --panel-strong: #262228;
    --ink: #ece7e3;
    --muted: #a49a92;
    --accent: #ff85ad;
    --rule: #2e282e;
    --shadow: 0 12px 34px rgba(0, 0, 0, .55);
    --shadow-soft: 0 20px 60px rgba(0, 0, 0, .6);
    --overlay: rgba(0, 0, 0, .92);
    --art-border: rgba(255, 255, 255, .22);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --paper: #121012;
  --panel: #1a171a;
  --panel-strong: #262228;
  --ink: #ece7e3;
  --muted: #a49a92;
  --accent: #ff85ad;
  --rule: #2e282e;
  --shadow: 0 12px 34px rgba(0, 0, 0, .55);
  --shadow-soft: 0 20px 60px rgba(0, 0, 0, .6);
  --overlay: rgba(0, 0, 0, .92);
  --art-border: rgba(255, 255, 255, .22);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  font-size: clamp(17px, 1.05vw + 13px, 18.5px);
  line-height: 1.62;
  text-rendering: optimizeLegibility;
}
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }

/* ---------------------------------------------------------------- layout */
.layout { display: flex; min-height: 100vh; overflow-x: clip; }
.sidebar {
  width: 300px; flex: 0 0 300px;
  background: var(--panel);
  border-right: 1px solid var(--rule);
  padding: 24px 20px 40px;
  position: sticky; top: 0; align-self: flex-start;
  height: 100vh; overflow-y: auto; overscroll-behavior: contain;
}
.sidebar-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.sidebar h1 { font-size: 21px; line-height: 1.15; margin: 0 0 2px; letter-spacing: .01em; }
.sidebar .byline { font-size: 12.5px; color: var(--muted); margin: 0 0 4px; }
.sidebar .subtitle { font-size: 12px; color: var(--muted); margin: 0 0 16px; font-style: italic; }
.toc-tools { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
button {
  font: inherit; cursor: pointer; color: inherit;
  background: var(--panel-strong); border: 1px solid var(--rule); border-radius: 999px;
  min-height: 34px; padding: 6px 12px; font-size: 12.5px;
  transition: background-color .15s ease, border-color .15s ease, color .15s ease;
}
button:hover { border-color: var(--accent); color: var(--accent); }
button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--paper); }
button[aria-pressed="true"]:hover { color: var(--paper); }
.nav-toggle { display: none; flex: 0 0 auto; }
.search {
  width: 100%; font: inherit; font-size: 16px; padding: 9px 11px; margin-bottom: 12px;
  border: 1px solid var(--rule); border-radius: 8px;
  background: var(--panel-strong); color: var(--ink);
}
.search::placeholder { color: var(--muted); }
nav.toc { font-size: 13.5px; }
nav.toc .part {
  font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--accent); margin: 18px 0 6px; font-family: system-ui, sans-serif;
}
nav.toc a {
  display: block; padding: 6px 8px; margin-left: -8px; color: var(--ink);
  text-decoration: none; border-radius: 6px; line-height: 1.3;
}
nav.toc a:hover { background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); }
nav.toc a .num { color: var(--muted); font-size: 11.5px; display: block; }

main { flex: 1 1 auto; min-width: 0; max-width: 100%; padding: 46px clamp(18px, 5vw, 72px) 120px; }
.reading { max-width: 760px; margin: 0 auto; min-width: 0; }
img, table { max-width: 100%; }

/* ------------------------------------------------------------- typography */
h2.part-title {
  font-size: 15px; letter-spacing: .18em; text-transform: uppercase;
  font-family: system-ui, sans-serif; color: var(--accent); margin: 0 0 6px;
}
.cover { margin-bottom: 40px; }
.cover img {
  width: 100%; max-width: 420px; border-radius: 6px;
  box-shadow: var(--shadow); display: block;
  border: 1px solid var(--art-border);
}
.cover h1 { font-size: clamp(28px, 5vw, 44px); line-height: 1.05; margin: 22px 0 4px; }
.cover .tagline { color: var(--muted); font-style: italic; margin: 0; }
.cover .edition { color: var(--muted); font-size: 14.5px; }
.chapter { margin-top: 68px; border-top: 1px solid var(--rule); padding-top: 26px; }
.chapter-head .kicker {
  font-family: system-ui, sans-serif; font-size: 11.5px; letter-spacing: .2em;
  text-transform: uppercase; color: var(--accent); margin: 0 0 6px;
}
.chapter-head h2 { font-size: clamp(23px, 3.4vw, 33px); line-height: 1.12; margin: 0 0 8px; }
h3 { font-size: 20px; margin: 30px 0 8px; line-height: 1.25; }
h4 { font-size: 16.5px; margin: 24px 0 6px; line-height: 1.3; font-style: italic; font-weight: 600; }
p { margin: 0 0 14px; }
blockquote {
  margin: 18px 0; padding-left: 16px; border-left: 3px solid var(--rule);
  color: var(--muted); font-style: italic;
}

/* ------------------------------------------------------------ lists/tables */
ol.steps { margin: 10px 0 20px; padding-left: 0; list-style: none; counter-reset: step; }
ol.steps li {
  counter-increment: step; position: relative; padding-left: 42px;
  margin-bottom: 12px; min-height: 26px;
}
ol.steps li::before {
  content: counter(step); position: absolute; left: 0; top: 1px;
  width: 27px; height: 27px; border-radius: 50%;
  background: var(--accent); color: var(--paper);
  font-family: system-ui, sans-serif; font-size: 13px;
  display: flex; align-items: center; justify-content: center;
}
ol.plain { margin: 6px 0 18px; padding-left: 20px; }
.table-scroll { margin: 18px 0 26px; max-width: 100%; min-width: 0; overflow-x: auto; -webkit-overflow-scrolling: touch; }
table.chart {
  width: 100%; border-collapse: collapse; margin: 0;
  font-size: 15.5px; background: var(--panel-strong);
  border: 1px solid var(--rule); border-radius: 6px;
}
table.chart th, table.chart td {
  text-align: left; padding: 7px 12px; border-bottom: 1px solid var(--rule); vertical-align: top;
}
table.chart thead th {
  font-family: system-ui, sans-serif; font-size: 11.5px; letter-spacing: .1em;
  text-transform: uppercase; color: var(--accent); background: var(--panel);
}
table.chart tbody tr:last-child td { border-bottom: 0; }

/* ----------------------------------------------------------------- images */
.figures { display: flex; flex-wrap: wrap; gap: 14px; margin: 18px 0 26px; align-items: flex-start; }
.figures figure { margin: 0; max-width: 100%; }
.figures img {
  display: block; max-width: 100%; height: auto; border-radius: 4px;
  cursor: zoom-in; background: var(--panel-strong);
  border: 1px solid var(--art-border);
}
.figures figure.pad img { border-color: var(--rule); }
.figures figcaption { font-family: system-ui, sans-serif; font-size: 11.5px; color: var(--muted); margin-top: 5px; }
.page-facsimile { margin: 22px 0 8px; }
.page-facsimile summary {
  cursor: pointer; font-family: system-ui, sans-serif; font-size: 12px; color: var(--muted);
  padding: 6px 0; min-height: 32px;
}
.page-facsimile summary:hover { color: var(--accent); }
.page-facsimile img {
  display: block; width: 100%; max-width: 900px; margin-top: 10px;
  border: 1px solid var(--art-border); border-radius: 4px;
}
/* The summary marker is removed elsewhere, so draw our own affordance. */
.page-facsimile summary { list-style: none; }
.page-facsimile summary::-webkit-details-marker { display: none; }
.page-facsimile summary::before {
  content: "▸"; display: inline-block; width: 1.1em; color: var(--accent);
  transition: transform .15s ease;
}
.page-facsimile[open] summary::before { transform: rotate(90deg); }
.page-facsimile[open] summary { color: var(--ink); }
.lightbox {
  position: fixed; inset: 0; background: var(--overlay); display: none;
  align-items: center; justify-content: center; padding: 24px; z-index: 50; cursor: zoom-out;
}
.lightbox.open { display: flex; }
.lightbox img { max-width: 96vw; max-height: 94vh; box-shadow: var(--shadow-soft); }
.backtotop {
  position: fixed; right: 20px; bottom: 20px; z-index: 40;
  background: var(--accent); color: var(--paper); border: 0;
  border-radius: 999px; min-height: 44px; padding: 10px 18px; font-size: 13px;
  box-shadow: var(--shadow); display: none;
}
.backtotop:hover { color: var(--paper); border: 0; }
.backtotop.show { display: block; }

/* ------------------------------------------------------------ touch/mobile */
@media (hover: none) {
  nav.toc a { min-height: 44px; display: flex; flex-direction: column; justify-content: center; }
}
@media (max-width: 900px) {
  .layout { display: block; }
  .sidebar {
    position: sticky; top: 0; z-index: 30;
    width: auto; height: auto; max-height: 100dvh;
    border-right: 0; border-bottom: 1px solid var(--rule);
    padding: 12px 16px;
    background: color-mix(in srgb, var(--panel) 92%, transparent);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
  }
  .sidebar-head h1 { font-size: 17px; }
  .sidebar-head h1 .sep { display: none; }
  .sidebar .byline { font-size: 12px; margin-bottom: 8px; }
  .sidebar .subtitle { display: none; }
  .nav-toggle { display: inline-flex; align-items: center; }
  .sidebar-tools { display: none; padding-top: 10px; }
  .sidebar.nav-open .sidebar-tools { display: block; }
  .toc-tools { margin-bottom: 10px; }
  main { padding: 22px 16px 96px; }
  .chapter { margin-top: 48px; padding-top: 20px; }
  table.chart { font-size: 14.5px; }
  table.chart th, table.chart td { padding: 7px 9px; }
  .figures { gap: 10px; }
  .figures img { max-width: min(100%, 88vw); }
  .lightbox { padding: 8px; }
  .backtotop { right: 14px; bottom: 14px; }
}
@media (max-width: 420px) {
  .sidebar { padding: 10px 12px; }
  .sidebar-head h1 { font-size: 16px; }
  .toc-tools button { padding: 6px 10px; }
  .figures img { max-width: 100%; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  * { transition: none !important; }
}
@media print {
  :root { color-scheme: light; }
  .sidebar, .backtotop, .lightbox, .toc-tools, .nav-toggle { display: none !important; }
  .page-facsimile { display: none !important; }
  body { background: #fff; color: #000; }
}
"""

JS = """
(function () {
  /* The colour theme is pure CSS: it follows the reader's system setting, so
     there is nothing to store and nothing to toggle here. */

  /* -------------------------------------------------------- mobile nav */
  var sidebar = document.querySelector('.sidebar');
  var navToggle = document.querySelector('[data-nav-toggle]');
  if (sidebar && navToggle) {
    var setNav = function (open) {
      sidebar.classList.toggle('nav-open', open);
      navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    };
    setNav(false);
    navToggle.addEventListener('click', function () {
      setNav(!sidebar.classList.contains('nav-open'));
    });
    sidebar.addEventListener('click', function (event) {
      if (event.target.closest('nav.toc a')) setNav(false);
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') setNav(false);
    });
  }

  /* ---------------------------------------------------------- lightbox */
  var lightbox = document.querySelector('.lightbox');
  var lightboxImg = lightbox ? lightbox.querySelector('img') : null;
  document.addEventListener('click', function (event) {
    var img = event.target.closest('.figures img, .page-facsimile img');
    if (img && lightboxImg) {
      lightboxImg.src = img.dataset.full || img.src;
      lightbox.classList.add('open');
      event.preventDefault();
      return;
    }
    if (lightbox && lightbox.classList.contains('open')) {
      lightbox.classList.remove('open');
      lightboxImg.src = '';
    }
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && lightbox) {
      lightbox.classList.remove('open');
      if (lightboxImg) lightboxImg.src = '';
    }
  });

  /* -------------------------------------------------------- back to top */
  var top = document.querySelector('.backtotop');
  if (top) {
    var onScroll = function () { top.classList.toggle('show', window.scrollY > 900); };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    top.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  /* ------------------------------------------------------------- filter */
  var search = document.querySelector('.search');
  if (search) {
    search.addEventListener('input', function () {
      var query = search.value.trim().toLowerCase();
      document.querySelectorAll('nav.toc a').forEach(function (link) {
        var match = !query || link.textContent.toLowerCase().indexOf(query) !== -1;
        link.style.display = match ? '' : 'none';
      });
    });
  }

  /* --------------------------------------------------- page facsimiles */
  var toggle = document.querySelector('[data-toggle-pages]');
  if (toggle) {
    var show = false;
    try { show = localStorage.getItem('showFacsimiles') === '1'; } catch (error) { /* ignore */ }
    var facsimiles = document.querySelectorAll('details.page-facsimile');
    var applyPages = function (on) {
      facsimiles.forEach(function (details) { details.open = on; });
      toggle.setAttribute('aria-pressed', on ? 'true' : 'false');
      toggle.textContent = on ? 'Hide original pages' : 'Show original pages';
      try { localStorage.setItem('showFacsimiles', on ? '1' : '0'); } catch (error) { /* ignore */ }
    };
    // restore the remembered state; each summary still toggles on its own
    if (show) applyPages(true);
    toggle.addEventListener('click', function () {
      var currentlyOpen = document.querySelectorAll('details.page-facsimile[open]').length;
      applyPages(currentlyOpen < facsimiles.length);
    });
  }
})();
"""


def render_blocks(blocks: list[Block], skip_labels: set[str], title: str = "") -> list[str]:
    """Render page blocks, dropping the printed "Chapter N"/repeat-title labels."""
    parts: list[str] = []
    open_list = False
    title_key = re.sub(r"[^a-z]", "", title.lower())

    def close_list() -> None:
        nonlocal open_list
        if open_list:
            parts.append("</ol>")
            open_list = False

    for block in blocks:
        # the chapter/part label is recreated by the section header
        if block.kind in ("chapter", "part"):
            continue
        if block.kind == "heading" and title_key:
            if re.sub(r"[^a-z]", "", block.text.lower()) == title_key:
                continue
        if block.kind == "heading":
            close_list()
            tag = "h3" if block.level <= 3 else "h4"
            parts.append(f"<{tag}>{render_inline(block.text)}</{tag}>")
            continue
        if block.kind == "table":
            close_list()
            try:
                rows = json.loads(block.text)
            except (ValueError, TypeError):
                rows = []
            if rows:
                head = "".join(f"<th>{render_inline(c)}</th>" for c in rows[0])
                body_rows = "".join(
                    "<tr>" + "".join(f"<td>{render_inline(c)}</td>" for c in row) + "</tr>"
                    for row in rows[1:]
                )
                parts.append(
                    f'<div class="table-scroll"><table class="chart">'
                    f'<thead><tr>{head}</tr></thead><tbody>{body_rows}</tbody></table></div>'
                )
            continue
        if block.kind in ("list", "bullet"):
            tag = "steps" if block.kind == "list" else "plain"
            if not open_list:
                parts.append(f'<ol class="{tag}">')
                open_list = True
            parts.append(f"<li>{render_inline(block.text)}</li>")
            continue
        close_list()
        parts.append(f"<p>{render_inline(block.text)}</p>")
    close_list()
    return parts


def render_figures(page: dict) -> list[str]:
    number = page["page"]
    if not page["regions"]:
        return []
    figures = []
    for region in page["regions"]:
        name = region["file"]
        display = min(int(region["px"]), 400)
        caption = "Colour swatch" if region.get("pad") else ""
        figures.append(
            '<figure class="{cls}"><img src="assets/images/{name}" '
            'data-full="assets/images/{name}" width="{w}" loading="lazy" alt="{alt}">{cap}</figure>'.format(
                cls="pad" if region.get("pad") else "",
                name=name,
                w=display,
                alt=caption or f"Illustration from page {number}",
                cap=f"<figcaption>{caption}</figcaption>" if caption else "",
            )
        )
    return ['<div class="figures">' + "".join(figures) + "</div>"]


def main() -> None:
    pages = load_pages()
    clf = Classifier(pages)
    structure = build_structure(pages, clf)
    entries = structure["entries"]

    opening_by_page: dict[int, list[dict]] = {}
    for entry in entries:
        opening_by_page.setdefault(entry["page"], []).append(entry)

    os.makedirs(os.path.join(OUT_DIR, "assets"), exist_ok=True)

    body_parts: list[str] = []
    body_parts.append('<div class="cover">')
    body_parts.append('<img src="assets/pages/page-001.jpg" alt="Cover of Bobbi Brown Makeup Manual">')
    body_parts.append("<h1>Bobbi Brown Makeup Manual</h1>")
    body_parts.append('<p class="tagline">For Everyone from Beginner to Pro</p>')
    body_parts.append(
        '<p class="edition">A readable, reflowed edition of the scanned book &middot; '
        'illustrations extracted from the original pages</p>'
    )
    body_parts.append("</div>")

    nav_parts: list[str] = []
    section_open = False
    skip_labels: set[str] = set()
    carry: Block | None = None

    for page in pages:
        number = page["page"]
        if number == 1:
            continue
        openings = opening_by_page.get(number, [])
        blocks = group_page(page, clf) if page["lines"] else []

        # a printed-contents page contributes only navigation, not reading text
        if number == 3:
            continue

        # close the previous chapter section when a new chapter starts
        starts_chapter = any(entry["kind"] == "chapter" for entry in openings)
        if starts_chapter and section_open:
            body_parts.append("</section>")
            section_open = False

        for entry in openings:
            anchor = f"page-{number}"
            skip_labels.add(entry["label"].strip().lower())
            if entry["kind"] == "part":
                label = f'Part {entry["roman"]}'
                body_parts.append(f'<h2 class="part-title" id="{anchor}">{html.escape(entry["title"] or label)}</h2>')
                nav_parts.append(
                    f'<p class="part"><span class="num">{html.escape(label)}</span>'
                    f'{html.escape(entry["title"])}</p>'
                )
            else:
                label = f'Chapter {entry["number"]}'
                body_parts.append(f'<section class="chapter" id="{anchor}">')
                body_parts.append('<div class="chapter-head">')
                body_parts.append(f'<p class="kicker">{html.escape(label)}</p>')
                if entry["title"]:
                    body_parts.append(f'<h2>{html.escape(entry["title"])}</h2>')
                body_parts.append("</div>")
                section_open = True
                nav_parts.append(
                    f'<a href="#{anchor}">{html.escape(entry["title"] or label)}'
                    f'<span class="num">{html.escape(label)}</span></a>'
                )

        # a paragraph broken by a page turn continues on the next page
        if carry is not None and blocks:
            first = blocks[0]
            if first.kind == "p" and not starts_list_item(first.text) and not ends_sentence(carry.text):
                carry.text = normalise_space(join_hyphen(carry.text, first.text))
                blocks = blocks[1:]

        page_title = ""
        for entry in openings:
            if entry["kind"] == "chapter":
                page_title = entry["title"]
        body_parts.extend(render_blocks(blocks, skip_labels, page_title))

        carry = None
        if blocks and not openings:
            last = blocks[-1]
            if last.kind == "p" and not ends_sentence(last.text):
                carry = last
        body_parts.extend(render_figures(page))
        body_parts.append(
            f'<details class="page-facsimile"><summary>Original page {number} of the scan</summary>'
            f'<img src="assets/pages/page-{number:03d}.jpg" loading="lazy" alt="Scanned page {number}"></details>'
        )

    if section_open:
        body_parts.append("</section>")

    nav_html = "\n".join(nav_parts)
    body_html = "\n".join(body_parts)

    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="description" content="A readable, reflowed HTML edition of the Bobbi Brown Makeup Manual, with the original scanned pages and illustrations.">
<meta name="theme-color" content="#f2ece4" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a171a" media="(prefers-color-scheme: dark)">
<title>Bobbi Brown Makeup Manual &mdash; readable edition</title>
<link rel="stylesheet" href="assets/book.css">
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <div class="sidebar-head">
      <div>
        <h1>Bobbi Brown<span class="sep">, </span>Makeup Manual</h1>
        <p class="byline">For Everyone from Beginner to Pro</p>
      </div>
      <button class="nav-toggle" type="button" data-nav-toggle aria-expanded="false" aria-controls="sidebar-tools">Contents</button>
    </div>
    <p class="subtitle">Readable edition &middot; text reflowed from the scanned book</p>
    <div class="sidebar-tools" id="sidebar-tools">
      <div class="toc-tools">
        <button type="button" data-toggle-pages aria-pressed="false">Show original pages</button>
        <button type="button" onclick="window.print()">Print</button>
      </div>
      <input class="search" type="search" placeholder="Filter chapters&hellip;" aria-label="Filter chapters">
      <nav class="toc">
{nav_html}
      </nav>
    </div>
  </aside>
  <main>
    <article class="reading">
{body_html}
    </article>
  </main>
</div>
<div class="lightbox"><img alt=""></div>
<button class="backtotop" type="button">Top</button>
<script src="assets/book.js"></script>
</body>
</html>
"""

    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(document)
    with open(os.path.join(OUT_DIR, "assets", "book.css"), "w", encoding="utf-8") as fh:
        fh.write(CSS)
    with open(os.path.join(OUT_DIR, "assets", "book.js"), "w", encoding="utf-8") as fh:
        fh.write(JS)

    chapters = [e for e in entries if e["kind"] == "chapter"]
    parts = [e for e in entries if e["kind"] == "part"]
    print(f"pages: {len(pages)}  body height: {clf.body_h:.4f}")
    print(f"parts: {len(parts)}  chapters: {len(chapters)}")
    for entry in entries:
        print(f'  {entry["label"]:12s} p{entry["page"]:3d}  {entry["title"]}')
    print(f"wrote {os.path.join(OUT_DIR, 'index.html')}")


if __name__ == "__main__":
    main()
