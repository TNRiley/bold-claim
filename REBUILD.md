# Rebuilding Bold Claim

Enough instruction to reproduce this project from scratch with a shell, Python and no other
context. It is a recipe, not a summary. Follow it in order.

---

## 1. What is being built

One self-contained HTML page that measures every type family in the Google Fonts catalogue
directly from its outlines, and shows that `font-weight` is a label rather than a quantity.

The finding it exists to show: **the faces labelled 400 run from a stroke of 10 to 487 units of a
1000-unit em, the faces labelled 700 overlap them heavily, and if you pick a bold from one family
and a regular from another, one time in eight the bold is the lighter of the two** (one in fifteen
if you restrict both to serif, sans-serif and monospace families). Underneath that sit three
supporting findings: 1,084 of the 1,950 families ship exactly one upright weight and 1,082 of them
call it 400 whatever it weighs; a family's own step from 400 to 700 multiplies its stroke by
anywhere from 1.00 to 3.43, median 1.62; and Google's own thickness bucket, which its site filters
by, correlates with the measurement at r = 0.86 but puts the lightest 400 in the whole catalogue
(Bungee Hairline, stroke 10) in bucket 7 next to Sancreek at 236.

The page draws every letter from real outlines embedded as SVG paths. It fetches nothing at
runtime except the visit counter in the breadcrumb bar.

---

## 2. Data

Three unauthenticated endpoints. No API key is needed for any of them.

### 2a. The catalogue

```
https://fonts.google.com/metadata/fonts
```

About 2.7 MB of JSON. The part that matters is `familyMetadataList`: one object per family with
`family`, `category`, `designers`, `dateAdded`, `popularity` (1 = most used), `subsets`, `axes`,
`isNoto`, and `fonts`, a dict whose keys are the weights the family publishes. **Italic keys end in
`i`** (`"400i"`), so strip those to get the upright weights. Each weight also carries Google's own
`thickness` and `width` buckets, integers 1 to 10, which the page checks against the measurement.

As of 2026-10-05: 1,950 families, 6,045 upright faces, 701 designers, added between 2010-02-19 and
2026-09-28.

### 2b. The font files

```
https://fonts.googleapis.com/css2?family=<Family>:wght@<w>;<w>&text=Hamburgenox
```

Two quirks, both essential:

- **Send a legacy User-Agent** (`Mozilla/4.0 (compatible)`). With a modern one the CSS serves
  woff2; with an old one it serves plain `.ttf`, which fontTools reads without brotli.
- **`text=` makes gstatic subset the file.** Asking for only the eleven letters needed
  (`Hamburgenox` covers H, a, m, b, u, r, g, e, n, o, x) brings each face down from roughly 120 kB
  to about 9 kB. All 6,045 faces come to 46 MB instead of well over a gigabyte, which is the whole
  reason fetching the entire catalogue is reasonable. Subsetting preserves `unitsPerEm`, advance
  widths and outlines exactly; only glyph coverage is cut.

Several families can be requested per CSS call, which cuts the number of round trips; six at a time
with eight threads fetches the catalogue in about four minutes.

Expect roughly 53 faces to fail, and do not treat it as a bug:

- 39 return no face for a weight the metadata lists, most of them **weight 1000, which the CSS API
  does not serve** (it stops at 900).
- 14 return HTTP 400 because the family has none of the requested letters at all: Noto Color Emoji,
  Noto Sans Lycian, Noto Serif Myanmar, Chenla. A font with no Latin cannot be measured here
  anyway.

A further 15 faces download but have no usable `x`, `n` or `o` outline and are skipped at the
measuring step.

### 2c. Licences

The metadata endpoint does not say which licence a family is under. `github.com/google/fonts` files
every family under `ofl/`, `apache/` or `ufl/`, so list those three trees:

```
GET https://api.github.com/repos/google/fonts/git/trees/main      -> find the sha for each directory
GET https://api.github.com/repos/google/fonts/git/trees/<sha>     -> its child directory names
```

Check the `truncated` flag; neither tree is truncated at this size. Match a family to a directory by
squashing its name to letters and digits (`Playfair Display` -> `playfairdisplay`). That matches
1,944 of 1,950. **The six that do not are all `Edu ...` families**, filed under names that do not
squash to their family name (`Edu NSW ACT Cursive` lives in `edunswactfoundation`). Every `edu*`
directory in the repo is under the OFL, so match those on the prefix rather than guessing. Result:
1,910 OFL, 35 Apache 2.0, 5 UFL.

---

## 3. Measuring

No rasteriser. Flatten each glyph outline into closed polylines, then intersect a scanline with
them and use the **nonzero winding rule** to turn the crossings into ink intervals. Normalise
everything to a 1000-unit em (`scale = 1000 / unitsPerEm`) so a 2048-upem TrueType font and a
1000-upem CFF font compare directly.

### The trap that will bite you first

A TrueType contour may consist **entirely of off-curve control points**, with every on-curve point
implied at the midpoint of consecutive controls. fontTools signals this by passing a trailing
`None` to `qCurveTo`, with no preceding `moveTo`, and the contour has to be closed by wrapping from
the last control back to the first. Get it wrong and the outline has a gap in it, the winding count
goes wrong, and a scanline reads ink where there is none. Handle it in exactly one place and use it
from every function (here, `_quad_segments` in `src/glyphmetrics.py`).

### The three measures, and why they are kept apart

| name | what it is |
|---|---|
| `othick` | the vertical stroke of the `o` bowl, measured on a horizontal scanline at the bowl's own mid-height, averaged over the left and right strokes. **The primary measure.** |
| `capstem` | the stem of the `H`, the median over nine scanlines between 0.62 and 0.90 of cap height: above the crossbar, below the serifs. **The corroborating measure.** |
| `cov` | the ink area of the `n` divided by advance x x-height. Area rather than a scanline, so it fails differently. |

They are never averaged together. Keeping them independent is what catches errors.

`othin` is the smaller of the two horizontal bands a vertical scanline through the middle of the
`o` crosses; `othick / othin` is the stroke contrast.

### Two methodological traps, with the wrong answers written down

**Do not measure the H stem at mid cap height.** The scanline lands on the crossbar, the whole
letter reads as one continuous ink interval, and the "stem" comes back as the full width of the H.
The first run of this project reported Roboto Regular's cap stem as 546 units. Scan above the
crossbar instead and require exactly two intervals.

**Do not trust a scanline across the lowercase n in a small-caps or caps-only family.** There the
`n` is a small-cap N, and a horizontal scanline can land on its diagonal. This produced a confident,
entirely false finding: that **Cinzel's 700 was lighter than its 600** (172.8 against 204.8) and
that **Alegreya Sans SC's 800 was lighter than its 700**. Both are artefacts. On `othick` and
`capstem` both families are monotonic throughout. The fix is a guard: accept a scanline only if it
sees exactly two intervals, their widths are within 2x of each other, and the left one is under
half the advance width. Apply the same guard to the H.

The general lesson, and the reason the measures are kept separate: **a second measure that
disagrees is the only thing standing between you and publishing a confident artefact.** Over 5,525
faces `capstem` correlates with `othick` at r = 0.984 and runs 1.002 times as wide; `cov`
correlates at r = 0.779. When a finding appears on one and not the others, the finding is wrong.

### Outlines for the page

Glyph `n` and `o` from every face are written out as SVG paths with their curves intact (no
flattening) on the 1000-unit em, y negated so the page can draw them in screen coordinates with the
baseline at zero. Use **relative commands with integer coordinates**: deltas are two digits far
more often than three, which halves the bytes over 6,000 faces (452 bytes for a typical `n` against
804 absolute). Round each point in absolute space first and take deltas between the rounded values,
or the path drifts.

Measurement geometry is written out too (`ogeo`, `ovgeo`, `ngeo`, `hgeo` and the two bounding
boxes), in the same coordinate system, so the page can draw the exact scanline a face was measured
on rather than an illustration of one.

---

## 4. The page

One file, roughly 3 MB, with the payload gzipped and base64'd inline and inflated by
`DecompressionStream`. Sections in order: the measuring bench (pick a family, see its real scanlines
and eleven measurements); the two distributions mirrored above and below one axis with the overlap
band shaded; the swap (two families at the same nominal weight, side by side); the bold-step
histogram and a table of the most-used families; the single-weight families and a demonstration of
synthetic emboldening against a designed bold; Google's thickness buckets as ranges; a stroke
against contrast scatter; a null result by year; and the whole catalogue as browsable cards with
each family's weight ramp drawn from its outlines.

Visual identity: a specimen book. Near-white paper, hairline rules, and one vermilion that only ever
means "this is the thing being measured". Grey is a regular, black is a bold, red is the
measurement.

All page prose that contains a figure is generated from `stats` in the payload, computed in
`src/build.py`. Nothing is typed from a note.

---

## 5. Verification table

Rebuild and check these. They catch parse errors, coordinate-system errors and scale errors
immediately.

| what | expected |
|---|---|
| Families in the catalogue | 1,950 |
| Upright faces measured | 5,977 (of 6,045 listed; 53 unfetchable, 15 unmeasurable) |
| Roboto 400, `unitsPerEm` | 2048 |
| Roboto 400, `othick` / `capstem` / `cap` / `xh` | 90.6 / 94.2 / 710.9 / 528.3 |
| Playfair Display 400, `othick` / `othin` / contrast | 97.0 / 20.0 / 4.85 |
| Bodoni Moda 400, contrast | 5.39 (a Didone should sit far above a grotesque) |
| Montserrat 400, contrast | 1.16 (a geometric sans should sit near 1) |
| Median `othick` at 400 / at 700 | 90.7 / 144.0 |
| Lightest 400 / heaviest 400 | Bungee Hairline 10.0 / Asset 486.8 |
| Lightest 700 / heaviest 700 | Chathura 37.5 / Corben 295.7 |
| Families shipping one upright weight | 1,084, of which 1,082 call it 400, and 0 have a weight axis |
| Cross-family (bold, regular) pairs inverted | 12.4%, 1 in 8. Text categories only: 6.5%, 1 in 15 |
| 400 to 700 stroke ratio: min / median / max | 1.00 (Noto Sans Kannada, Datatype) / 1.62 / 3.43 (Astloch) |
| Families with 3+ measurable weights whose ramp **reverses** | **0** |
| Families with a step that adds nothing | 3: Datatype (all nine identical), Intel One Mono (600 = 700), Noto Sans Kannada (400 = 500 = 600 = 700) |
| Google thickness bucket against measurement | r = 0.858 over 653 families, 28 overlapping bucket pairs |
| Median contrast, serif / sans-serif | 2.01 / 1.25 |
| Median x-height over cap, sans / serif / handwriting | 0.746 / 0.709 / 0.583 |
| Median stroke at 400 by year added | stays in 80.0 to 93.2 across 2010 to 2026, no trend |

If contrast comes out near 1 for Playfair Display or Bodoni Moda, the vertical scanline is wrong.
If every `othick` is roughly double or half what is expected, the `1000 / unitsPerEm` scale is
missing or applied twice. If a glyph draws upside down, the y negation was applied to the paths but
not to the geometry, or the reverse.

---

## 6. What the page must say about itself

- It is **geometry, not rendering**. Hinting, antialiasing, gamma, the size it is set at and the
  screen it is set on all change how heavy a face looks, and none of them is measured.
- **Optical size is not accounted for.** A family with an `opsz` axis is measured at its default.
- A variable family is measured at the **static instances Google serves** for the weights it lists,
  not continuously along its axis.
- The `o` can be refused: in a stencil, inline or dot-matrix face the scanline crosses more than two
  bands and the measurement is declined rather than guessed.
- Italics are excluded. The question is weight.
- **A designer who calls their one weight 400 is following the only convention available, not making
  a claim.** The page is about the number, not about anyone's drawing. Say so.
- The letterforms embedded in the page are real outlines, two glyphs per face, derived from
  OFL, Apache 2.0 and UFL fonts. They are not a font and cannot be installed as one, but they are
  derived works, so every family is credited to its designer with its licence named, and the
  licence text for each lives in its own directory at github.com/google/fonts.

---

## 7. Running it

```bash
pip install fonttools
cd projects/bold-claim/src
python fetch.py      # catalogue + licences + 6,000 subset faces into src/raw   (~4 min, 46 MB, resumable)
python measure.py    # outlines -> raw/measured.json                        (~4 min)
python build.py      # -> payload.json, and every figure the page prints
python inject.py     # -> ../index.html, then wrap_for_pages.py + add_catalog_link.py
```

`src/raw/` is gitignored; every step there refetches or recomputes. `inject.py` ends by running the
two catalog tools, so regenerating the page never silently drops the doctype wrapper or the
breadcrumb bar.
