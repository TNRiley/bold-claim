"""Measure every downloaded face; write raw/measured.json.

Nothing here trusts a font's declared metrics. Cap height is the top of its H,
x-height the top of its x, and stroke weight comes from scanlines laid across
the real letterforms. Everything is normalised to a 1000-unit em.

Three weight measures are taken, deliberately:

  othick   the vertical stroke of the o bowl, at the bowl's own mid-height.
           The primary measure. Present in every Latin font, unaffected by
           serifs, and in a small-caps font it simply measures the small-cap O,
           which carries the same design weight.
  capstem  the stem of the H, taken as the median over nine scanlines between
           0.62 and 0.90 of cap height - above the crossbar, below the serifs.
           The corroborating measure; it agrees with othick at r = 0.96.
  stem     the stem of the lowercase n. Kept, but NOT used as the headline,
           because in a small-caps or caps-only family the n is a small-cap N
           and a scanline across it can land on the diagonal. Guarded below so
           that a diagonal hit is rejected rather than reported.

The guard matters: before it existed, Cinzel and Alegreya Sans SC appeared to
have a bold LIGHTER than their semibold. Both were artefacts of the n measure on
small caps; othick and capstem were monotonic throughout.
"""
import json, os, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fontTools.ttLib import TTFont
import glyphmetrics as gm

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
FACES = os.path.join(RAW, "faces")
WORD = "Hamburg"        # the word whose typographic colour is measured
DRAW = "no"             # the glyphs whose outlines are shipped to the page


def lin(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def guarded_stem(polys, ys, adv):
    """Median width of the left ink interval over scanlines that see exactly two
    intervals of comparable width. Rejects diagonals and bowl hits.

    Returns (width, geometry) where geometry is the one scanline closest to that
    median, as [y, x_left, x_right] -- so the page can draw the line it was
    actually measured on rather than an illustration of one."""
    vals = []
    for y in ys:
        sp = gm.ink_spans(polys, y)
        if len(sp) != 2:
            continue
        a, b = sp[0][1] - sp[0][0], sp[1][1] - sp[1][0]
        if a <= 0 or b <= 0 or max(a, b) / min(a, b) > 2.0 or a > 0.5 * adv:
            continue
        vals.append((a, y, sp[0][0], sp[0][1]))
    if len(vals) < 3:
        return None, None
    med = statistics.median(v[0] for v in vals)
    best = min(vals, key=lambda v: abs(v[0] - med))
    return med, [best[1], best[2], best[3]]


def measure_face(path):
    f = TTFont(path, fontNumber=0, lazy=True)
    upem = f["head"].unitsPerEm
    s = 1000.0 / upem
    gs = f.getGlyphSet()
    cmap = f.getBestCmap()
    hmtx = f["hmtx"]

    def gname(ch):
        return cmap.get(ord(ch))

    def polys(ch):
        n = gname(ch)
        if not n:
            return None
        try:
            return gm.contours(gs, n) or None
        except Exception:
            return None

    H, x, n_, o, b, g = (polys(c) for c in "Hxnobg")
    if not (n_ and o and x):
        return None

    out = {"upem": upem}
    xh = gm.bbox(x)[3] * s
    out["xh"] = round(xh, 1)

    # Geometry is stored in the coordinates the page draws in: x scaled to the
    # 1000 em, y scaled AND negated, baseline at zero, so it lines up with the
    # outlines that rel_path writes. X and Y are therefore converted separately.
    def X(v):
        return round(v * s, 1)

    def Y(v):
        return round(-v * s, 1)

    def box(bb):
        return [X(bb[0]), Y(bb[3]), X(bb[2]), Y(bb[1])]

    if H:
        hb = gm.bbox(H)
        out["cap"] = round(hb[3] * s, 1)
        st, geo = guarded_stem(H, lin(hb[3] * 0.62, hb[3] * 0.90, 9), hmtx[gname("H")][0])
        if st:
            out["capstem"] = round(st * s, 1)
            out["hgeo"] = [Y(geo[0]), X(geo[1]), X(geo[2])]
    if b:
        out["asc"] = round(gm.bbox(b)[3] * s, 1)
    if g:
        out["desc"] = round(gm.bbox(g)[1] * s, 1)

    nb = gm.bbox(n_)
    advn_raw = hmtx[gname("n")][0]
    st, geo = guarded_stem(n_, lin(nb[3] * 0.30, nb[3] * 0.70, 11), advn_raw)
    if st:
        out["stem"] = round(st * s, 1)
        out["ngeo"] = [Y(geo[0]), X(geo[1]), X(geo[2])]
    out["nbb"] = box(nb)

    ob = gm.bbox(o)
    oy, ox = (ob[1] + ob[3]) / 2, (ob[0] + ob[2]) / 2
    hsp = gm.ink_spans(o, oy, "y")
    vsp = gm.ink_spans(o, ox, "x")
    if len(hsp) == 2:
        out["othick"] = round(((hsp[0][1] - hsp[0][0]) + (hsp[1][1] - hsp[1][0])) / 2 * s, 1)
        out["counter"] = round((hsp[1][0] - hsp[0][1]) * s, 1)
        out["ogeo"] = [Y(oy), X(hsp[0][0]), X(hsp[0][1]), X(hsp[1][0]), X(hsp[1][1])]
    if len(vsp) == 2:
        out["othin"] = round(min(vsp[0][1] - vsp[0][0], vsp[1][1] - vsp[1][0]) * s, 1)
        out["ovgeo"] = [X(ox), Y(vsp[1][1]), Y(vsp[1][0]), Y(vsp[0][1]), Y(vsp[0][0])]
    out["owidth"] = round((ob[2] - ob[0]) * s, 1)
    out["oheight"] = round((ob[3] - ob[1]) * s, 1)
    out["obb"] = box(ob)

    advn = advn_raw * s
    out["advn"] = round(advn, 1)
    if advn > 0 and xh > 0:
        out["cov"] = round(gm.area(n_) * s * s / (advn * xh), 4)

    # typographic colour: ink of the word as actually set, over the band it occupies
    ink = adv = 0.0
    for ch in WORD:
        p = polys(ch)
        if p is None:
            ink = None
            break
        ink += gm.area(p) * s * s
        adv += hmtx[gname(ch)][0] * s
    if ink is not None and adv > 0 and out.get("cap"):
        out["colour"] = round(ink / (adv * out["cap"]), 4)
        out["setwidth"] = round(adv, 1)

    paths = {}
    for ch in DRAW:
        nm = gname(ch)
        if nm:
            try:
                paths[ch] = gm.rel_path(gs, nm, s)
            except Exception:
                pass
    out["paths"] = paths
    return out


def main():
    files = sorted(os.listdir(FACES))
    res, bad = {}, []
    for i, fn in enumerate(files):
        try:
            m = measure_face(os.path.join(FACES, fn))
            if m is None:
                bad.append((fn[:-4], "no x/n/o outline"))
            else:
                res[fn[:-4]] = m
        except Exception as e:
            bad.append((fn[:-4], f"{type(e).__name__}: {e}"))
        if i % 1000 == 0:
            print(f"  {i}/{len(files)}", flush=True)
    print(f"measured {len(res)}, skipped {len(bad)}", flush=True)
    for p, d in (("measured.json", res), ("measure_skipped.json", bad)):
        with open(os.path.join(RAW, p), "w", encoding="utf-8", newline="\n") as f:
            json.dump(d, f, separators=(",", ":"))


if __name__ == "__main__":
    main()
