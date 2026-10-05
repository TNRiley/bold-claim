# 🅱️ Bold Claim

**Every type family on Google Fonts, measured off its own outlines. Pick a bold and a regular from two different families and one time in eight the bold is the lighter of the two.**

→ **[Open it](https://tnriley.github.io/bold-claim/)**

font-weight: 700 is a number in your stylesheet, and it turns out not to be a quantity. All 1,950 families on Google Fonts were fetched as subset fonts and measured directly from their outlines, with no rasteriser involved: a scanline across the bowl of the o gives the stroke, another through the middle gives the thin, and cap height and x-height come from the top of the H and the x. The faces labelled Regular run from a stroke of 10 to 487 units of a 1000-unit em, the ones labelled Bold overlap them heavily, and 1,084 families ship a single weight that they all call 400 regardless of what it weighs. Pick any family and the page draws the lines it was actually measured on, swap two families at the same nominal weight and watch the stroke move, or sort the whole catalogue from hairline to slab.

## Running it

One self-contained HTML file. No build step, no server, no network access at runtime — open `index.html` in a browser, or serve the directory with any static host.

```bash
python3 -m http.server 8000   # then visit http://localhost:8000
```

## Rebuilding it from scratch

[REBUILD.md](REBUILD.md) is written for an LLM with a shell and nothing else: the data sources and their quirks, the processing decisions, the page's structure and interactions, and a table of expected values to check the result against.

## Source

The full build pipeline is in [`src/`](src/), with a README describing how to regenerate the page from scratch.

## Data

- **[Google Fonts catalogue metadata - 1,950 families with designer, category, date added, popularity rank, subsets, variable axes and Google's own thickness and width buckets, read 2026-10-05](https://fonts.google.com/metadata/fonts)** — Catalogue metadata, published openly by Google Fonts at an unauthenticated endpoint
- **[Google Fonts CSS API - 5,977 upright faces, each requested with text=Hamburgenox so that gstatic returns a subset font of only the eleven letters measured here](https://fonts.googleapis.com/css2)** — The font files themselves: SIL Open Font Licence 1.1 (1,910 families), Apache 2.0 (35), Ubuntu Font Licence 1.0 (5)
- **[google/fonts - which of the three licence directories each family is filed under](https://github.com/google/fonts)** — Repository under Apache 2.0; each family keeps its own licence, recorded per family on the page
- **[fontTools - used to read the outlines. The scanline measurement built on top of it is this project's own, in src/glyphmetrics.py](https://github.com/fonttools/fonttools)** — MIT

Every figure on the page is computed from the data shipped with it. Check the page's own methods panel for how each number is derived and where it should not be pushed.

## Built with

Python, fontTools, vanilla JS, inline SVG glyph outlines, gzipped base64 payload.

## Licence

Code is MIT (see [LICENSE](LICENSE)). Data keeps the licence of its source, listed above.

---

Part of [Quick Projects](https://github.com/TNRiley/quick-projects) — one self-contained thing, built in one session. First published 2026-10-05.
