# src

The pipeline. Four steps, each resumable, each safe to re-run.

```bash
pip install fonttools
python fetch.py      # catalogue + licence map + ~6,000 subset font files -> src/raw  (~4 min, 46 MB)
python measure.py    # outlines -> raw/measured.json                             (~4 min)
python build.py      # -> payload.json, plus every figure the page prints
python inject.py     # -> ../index.html, then the two catalog tools
```

| file | what it does |
|---|---|
| `fetch.py` | Reads the Google Fonts metadata endpoint, lists each family's upright weights, and downloads one subset `.ttf` per face via the CSS API. Also lists the three licence directories in `google/fonts`. Skips anything already on disk. |
| `glyphmetrics.py` | The measurement itself. Flattens outlines, intersects scanlines with them under the nonzero winding rule, and writes glyphs back out as compact relative SVG paths. No fonts-specific cleverness beyond one place that handles all-off-curve TrueType contours. |
| `measure.py` | Runs the measurements over every downloaded face and records the scanline geometry alongside the numbers, so the page can draw the line a face was actually measured on. |
| `build.py` | Assembles `payload.json` and computes every statistic the page states. **If a figure on the page is wrong, it is wrong in here** - no number is typed into the HTML by hand. |
| `inject.py` | Gzips and base64s the payload into `template.html`, writes `../index.html`, then re-runs `wrap_for_pages.py` and `add_catalog_link.py`. |
| `template.html` | The page, with `__PAYLOAD__` where the payload goes. |

`src/raw/` is gitignored. It holds the catalogue JSON, the licence listings, 46 MB of subset font
files, and `measured.json`. All of it refetches or recomputes.

Two things in here are load-bearing and easy to get wrong on a rewrite; both are explained at
length in `../REBUILD.md`:

- **All-off-curve TrueType contours.** fontTools signals them with a trailing `None` to `qCurveTo`
  and no preceding `moveTo`. Mishandled, the outline has a gap and scanlines read ink where there
  is none.
- **The guard on scanline stem measurements.** Without it, a small-caps family reports a bold
  lighter than its own semibold, confidently and wrongly. `othick` and `capstem` are kept as
  separate measures precisely so that one can catch the other.
