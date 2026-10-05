# Bobbi Brown Makeup Manual — readable HTML edition

A readable, reflowed HTML edition of the scanned *Bobbi Brown Makeup Manual*,
published with GitHub Pages and rebuilt from source with a documented pipeline.

**Read it:** https://madelynnblue.github.io/makeup-manual/

The source PDF has no text layer — all 156 pages are page images — and its
magazine-style scan layout is awkward to read on a screen. This project adds a
text layer, reassembles that text into continuous prose, and cuts the
illustrations out of the pages so they can sit beside the words that describe
them.

## What is here

| Path | Contents |
| --- | --- |
| `index.html` | The whole book: 2 parts, 12 chapters, 383 headings, ~42,000 words |
| `assets/book.css` | Reading styles: light and dark themes, mobile layout, print stylesheet |
| `assets/book.js` | Contents drawer, lightbox, chapter filter, service worker registration |
| `sw.js` | Service worker: makes the book readable offline |
| `assets/images/` | 403 illustrations extracted from the scans |
| `assets/pages/` | 156 page facsimiles of the original book |
| `source.pdf` | The original scanned PDF the edition was built from |
| `tools/` | `scan.swift` (OCR + picture detection) and `build_site.py` (assembly) |
| `build.sh` | End-to-end rebuild |

## Reading features

* **Light and dark themes**, entirely in CSS. The page follows the reader's
  operating-system colour preference through `prefers-color-scheme`, with no
  JavaScript, no toggle and nothing stored — change the system setting and an
  open page restyles itself. A host that needs to force one theme can set
  `data-theme="light"` or `data-theme="dark"` on the `<html>` element.
* **Mobile layout.** The contents and controls collapse into a drawer behind
  the header, images scale to the viewport, and touch targets meet the 44 px
  minimum.
* **Reflowed text.** Paragraphs are rebuilt from the geometry of each OCR line,
  with dictionary-checked de-hyphenation at line breaks.
* **Structure.** Chapters, parts, headings, numbered step lists and six
  reference tables were recovered from the printed layout.
* **Illustrations appear inline with the text that describes them**, placed by
  their position on the original page rather than collected at the end of it, so
  each brush, step photo or swatch sits under its own heading. Click any of them
  for a full-size view.
* **Original page facsimiles** are collapsed under each section so you can check
  the reflow against the scan. `Show original pages` opens them all for
  side-by-side comparison; `Print` leaves them out.

## Offline reading

The service worker only installs on a secure origin, so this works over
`https://` and on `localhost` — not from a `file://` path, where the browser
disables service workers. Opening the saved folder from disk still works as an
ordinary local page; it simply does not cache itself.

To inspect what has been stored, open DevTools → Application → Cache Storage and
look for `makeup-manual-v1`. Removing that entry, or clearing site data, undoes
the save. A new deployment invalidates the old cache automatically, because the
stylesheets and scripts the page requests are versioned by content hash.

## Rebuilding

Requires macOS (Apple's Vision framework does the OCR), [poppler](https://poppler.freedesktop.org),
the Xcode command line tools, and Python 3.10+:

```sh
./build.sh                       # uses ./source.pdf
./build.sh /path/to/other.pdf    # or any other scan
```

The build writes `index.html` and `assets/` in place, which is exactly what
GitHub Pages serves. Intermediate files land in `work/` (git-ignored).

## How the text was recovered

1. Each page is rendered at 200 dpi and OCR'd with `VNRecognizeTextRequest`
   (accurate level, `en-US`), recording every line's bounding box.
2. Per-page row-ink statistics segment the scan into blocks. Typographic rows
   are recognised by having many short dark runs — one per glyph stem — and
   blocks dominated by them are set aside as text.
3. Blocks that are not typographic are exported as illustration files, with
   fragments of one photograph rejoined across bright bands and near-blank
   boxes discarded.
4. OCR lines are reflowed: merged into paragraphs by leading, indentation,
   terminal punctuation and lower-case continuation, with de-hyphenation
   checked against `/usr/share/dict/web2`.
5. Headings come from line height relative to the page's median body text, plus
   width, capitalisation and punctuation. Chapter openings come from the printed
   `Chapter N` labels, with the display line beneath them as the title.
6. A review pass against the source images drove the fixes for the defects that
   mattered most: subheads glued to body text, orphaned sentence tails across
   page turns, and tables read as prose.

`tools/scan.swift` and `tools/build_site.py` are heavily commented and can be
re-run independently.

## Known limitations

* **OCR is imperfect** on roughly 10% of pages, mostly captions and credits
  where type sits on coloured photographs. The page facsimile is the authority.
* Photographs that a column of text runs across can be split into two or three
  stacked crops; all pieces are shown in page order.
* The two-column colour charts (~pages 61–72) become tables when their grid is
  legible, otherwise their cells appear as lists of colour names.
* Decorative display type on the cover and part-title spreads can be garbled.

## Contributing a change

Everything is committed as built, so a fix to the reading experience means
editing `tools/build_site.py` (content, CSS, JS) or `tools/scan.swift` (OCR and
picture detection), then running `./build.sh` and committing the regenerated
`index.html` and assets. Every push to `main` republishes the site through the
workflow in `.github/workflows/pages.yml`.

Two helpers make that a one-liner:

```sh
./tools/publish.sh "Fix the lipstick chart"   # sync the built site, commit, push
./tools/install-hooks.sh                      # once per clone: push every commit
```

`publish.sh` copies the newest build out of a sibling `bobbi_work/site`
directory when one exists, so the published page always matches the latest
build. `install-hooks.sh` adds a `post-commit` hook, so after that a plain
`git commit` is enough: the hook pushes, the workflow deploys, and a failed
push only prints a warning instead of blocking the commit.

## Rights

The text and images belong to Bobbi Brown and the original publisher; they are
reproduced here for personal reading. The extraction and presentation code is
free to reuse.
