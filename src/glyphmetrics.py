"""Measure real letterforms: scanline ink intervals over flattened glyph outlines.

No rasteriser involved. Every number here is derived from the outline the type
designer drew, normalised to a 1000-unit em so families with different upem
(1000 for CFF, 2048 for most TrueType) are directly comparable.
"""
import math
from fontTools.pens.recordingPen import DecomposingRecordingPen


def _flatten_quad(p0, p1, p2, n=8):
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        out.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                    u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    return out


def _flatten_cubic(p0, p1, p2, p3, n=10):
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        a, b, c, d = u**3, 3 * u * u * t, 3 * u * t * t, t**3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def contours(glyphset, name):
    """Flatten one glyph (composites decomposed) into a list of closed polylines."""
    pen = DecomposingRecordingPen(glyphset)
    glyphset[name].draw(pen)
    polys, cur = [], []
    for op, args in pen.value:
        if op == "moveTo":
            if len(cur) > 2:
                polys.append(cur)
            cur = [tuple(args[0])]
        elif op == "lineTo":
            cur.append(tuple(args[0]))
        elif op == "curveTo":
            pts = [tuple(a) for a in args]
            # cubic, possibly a chain of them sharing implied points
            for i in range(0, len(pts) - 2, 2):
                cur.extend(_flatten_cubic(cur[-1], pts[i], pts[i + 1], pts[i + 2]))
        elif op == "qCurveTo":
            pts = [tuple(a) if a is not None else None for a in args]
            if pts[-1] is None:        # TrueType all-off-curve contour
                pts = pts[:-1]
                if not cur:
                    mid = ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2)
                    cur = [mid]
            # implied on-curve points sit midway between consecutive off-curves
            for i in range(len(pts) - 1):
                ctrl = pts[i]
                nxt = pts[i + 1]
                end = nxt if i == len(pts) - 2 else ((ctrl[0] + nxt[0]) / 2, (ctrl[1] + nxt[1]) / 2)
                cur.extend(_flatten_quad(cur[-1], ctrl, end))
        elif op == "closePath" or op == "endPath":
            if len(cur) > 2:
                polys.append(cur)
            cur = []
    if len(cur) > 2:
        polys.append(cur)
    return polys


def ink_spans(polys, coord, axis="y"):
    """Ink intervals where a scanline crosses the outline, by the nonzero rule.

    axis="y": horizontal scanline at y=coord, returns intervals in x.
    axis="x": vertical   scanline at x=coord, returns intervals in y.
    """
    i, j = (1, 0) if axis == "y" else (0, 1)
    xs = []
    for poly in polys:
        n = len(poly)
        for k in range(n):
            a, b = poly[k], poly[(k + 1) % n]
            a0, b0 = a[i], b[i]
            if a0 == b0:
                continue
            lo, hi = (a0, b0) if a0 < b0 else (b0, a0)
            if not (lo <= coord < hi):
                continue
            t = (coord - a0) / (b0 - a0)
            xs.append((a[j] + t * (b[j] - a[j]), 1 if b0 > a0 else -1))
    xs.sort()
    spans, wind, start = [], 0, None
    for pos, d in xs:
        prev = wind
        wind += d
        if prev == 0 and wind != 0:
            start = pos
        elif prev != 0 and wind == 0 and start is not None:
            if pos - start > 1e-9:
                spans.append((start, pos))
            start = None
    return spans


def bbox(polys):
    if not polys:
        return None
    xs = [p[0] for poly in polys for p in poly]
    ys = [p[1] for poly in polys for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def area(polys):
    """Total enclosed ink area (shoelace, absolute sum of signed contours)."""
    total = 0.0
    for poly in polys:
        s = 0.0
        n = len(poly)
        for k in range(n):
            x0, y0 = poly[k]
            x1, y1 = poly[(k + 1) % n]
            s += x0 * y1 - x1 * y0
        total += s / 2
    return abs(total)


def svg_path(polys, scale, dy=0.0, prec=1):
    """Compact SVG path, y flipped so the page can draw it in screen coords."""
    out = []
    for poly in polys:
        # drop points that add nothing at output precision
        pts, last = [], None
        for x, y in poly:
            p = (round(x * scale, prec), round(-(y * scale) + dy, prec))
            if p != last:
                pts.append(p)
                last = p
        if len(pts) < 3:
            continue
        def fmt(v):
            return ("%g" % v)
        out.append("M" + fmt(pts[0][0]) + " " + fmt(pts[0][1]) +
                   "L" + "L".join(fmt(x) + " " + fmt(y) for x, y in pts[1:]) + "Z")
    return "".join(out)


def curve_path(glyphset, name, scale, prec=0):
    """The glyph as an SVG path with its curves intact (no flattening), scaled to
    a 1000-unit em and y-flipped into screen coordinates. Short, and exact."""
    pen = DecomposingRecordingPen(glyphset)
    glyphset[name].draw(pen)
    f = ("%." + str(prec) + "f") if prec else "%.0f"

    def P(p):
        x = float(f % (p[0] * scale))
        y = float(f % (-p[1] * scale))
        return ("%g" % x) + " " + ("%g" % y)

    out, cur = [], None
    for op, args in pen.value:
        if op == "moveTo":
            cur = tuple(args[0])
            out.append("M" + P(cur))
        elif op == "lineTo":
            cur = tuple(args[0])
            out.append("L" + P(cur))
        elif op == "curveTo":
            pts = [tuple(a) for a in args]
            for i in range(0, len(pts) - 2, 2):
                out.append("C" + P(pts[i]) + " " + P(pts[i + 1]) + " " + P(pts[i + 2]))
            cur = pts[-1]
        elif op == "qCurveTo":
            pts = [tuple(a) if a is not None else None for a in args]
            if pts[-1] is None:                       # all-off-curve contour
                pts = pts[:-1]
                mid = ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2)
                if cur is None or out and out[-1].startswith("M"):
                    out[-1] = "M" + P(mid)
                cur = mid
            for i in range(len(pts) - 1):
                ctrl, nxt = pts[i], pts[i + 1]
                end = nxt if i == len(pts) - 2 else ((ctrl[0] + nxt[0]) / 2, (ctrl[1] + nxt[1]) / 2)
                out.append("Q" + P(ctrl) + " " + P(end))
                cur = end
            if len(pts) == 1:                          # single off-curve, closes to start
                out.append("Q" + P(pts[0]) + " " + P(cur))
        elif op in ("closePath", "endPath"):
            out.append("Z")
    return "".join(out)


def rel_path(glyphset, name, scale):
    """Same outline as curve_path, written with relative commands and integer
    coordinates on the 1000-unit em. Deltas are two digits far more often than
    three, which is worth about half the bytes over 6,000 faces - and the shape
    is identical, because every point is rounded in absolute space first and the
    delta is taken between rounded values, so nothing drifts."""
    pen = DecomposingRecordingPen(glyphset)
    glyphset[name].draw(pen)

    def Q(p):
        return (int(round(p[0] * scale)), int(round(-p[1] * scale)))

    out, cur = [], (0, 0)

    def emit(cmd, pts):
        nonlocal cur
        s = cmd
        for i, p in enumerate(pts):
            d = (p[0] - cur[0], p[1] - cur[1]) if cmd != "M" else p
            s += ("" if i == 0 else " ") + str(d[0]) + ("" if d[1] < 0 else ",") + str(d[1])
        # control points are relative to the START point, so cur moves only at the end
        out.append(s)
        cur = pts[-1]

    def emit_rel(cmd, pts):
        nonlocal cur
        base = cur
        s = cmd
        for i, p in enumerate(pts):
            dx, dy = p[0] - base[0], p[1] - base[1]
            s += ("" if i == 0 else " ") + str(dx) + ("" if dy < 0 else ",") + str(dy)
        out.append(s)
        cur = pts[-1]

    for op, args in pen.value:
        if op == "moveTo":
            p = Q(args[0])
            out.append("M" + str(p[0]) + ("" if p[1] < 0 else ",") + str(p[1]))
            cur = p
        elif op == "lineTo":
            emit_rel("l", [Q(args[0])])
        elif op == "curveTo":
            pts = [Q(a) for a in args]
            for i in range(0, len(pts) - 2, 2):
                emit_rel("c", [pts[i], pts[i + 1], pts[i + 2]])
        elif op == "qCurveTo":
            raw = [a for a in args]
            if raw[-1] is None:
                raw = raw[:-1]
                mid = ((raw[0][0] + raw[-1][0]) / 2, (raw[0][1] + raw[-1][1]) / 2)
                p = Q(mid)
                out.append("M" + str(p[0]) + ("" if p[1] < 0 else ",") + str(p[1]))
                cur = p
                raw = raw + [mid]
            for i in range(len(raw) - 1):
                ctrl, nxt = raw[i], raw[i + 1]
                end = nxt if i == len(raw) - 2 else ((ctrl[0] + nxt[0]) / 2, (ctrl[1] + nxt[1]) / 2)
                emit_rel("q", [Q(ctrl), Q(end)])
        elif op in ("closePath", "endPath"):
            out.append("Z")
    return "".join(out)
