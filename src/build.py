#!/usr/bin/env python
"""Turn raw/measured.json plus the catalogue metadata into payload.json.

Every number the page prints is computed here, so the prose on the page is
generated from the data rather than typed from a note. If a figure in the text
is wrong, it is wrong in this file.

The primary weight measure throughout is OTHICK: the width of the vertical
stroke of the o bowl, taken at the mid-height of the bowl, in units of a
1000-unit em. See measure.py for why it, and not the stem of the n, is the one
the headline rests on.
"""
import bisect, collections, datetime, json, os, re, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
TEXT_CATS = ("Sans Serif", "Serif", "Monospace")
K = "othick"

FACE_FIELDS = ["fam", "w", "upem", "cap", "xh", "asc", "desc",
               "othick", "othin", "capstem", "stem", "counter",
               "owidth", "oheight", "advn", "cov", "colour", "setwidth",
               "ogeo", "ovgeo", "ngeo", "hgeo", "obb", "nbb"]
CATS = ["Sans Serif", "Serif", "Display", "Handwriting", "Monospace"]
LICS = ["ofl", "apache", "ufl"]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def pct(sorted_vals, p):
    return sorted_vals[int(p / 100 * (len(sorted_vals) - 1))]


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sa = sum((x - ma) ** 2 for x in a) ** .5
    sb = sum((x - mb) ** 2 for x in b) ** .5
    return round(sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb), 4)


def load():
    with open(os.path.join(RAW, "measured.json"), encoding="utf-8") as f:
        measured = json.load(f)
    with open(os.path.join(RAW, "fonts_metadata.json"), encoding="utf-8") as f:
        meta = json.load(f)
    lic = {}
    for name in LICS:
        with open(os.path.join(RAW, "lic_%s.txt" % name), encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    lic[line.strip()] = name
    return measured, meta, lic


def licence_for(family, lic):
    """google/fonts names its directories by squashing the family name down to
    letters and digits. Six Edu families are filed under names that do not
    squash to their family name -- Edu NSW ACT Cursive lives in
    edunswactfoundation -- and every edu* directory in the repo is under the OFL,
    so those are matched on that prefix rather than guessed at."""
    k = re.sub(r"[^a-z0-9]", "", family.lower())
    if k in lic:
        return lic[k]
    if k.startswith("edu"):
        return "ofl"
    return None


def assemble(measured, meta, lic):
    fams_meta = {f["family"]: f for f in meta["familyMetadataList"]}
    by_slug = collections.defaultdict(dict)
    for key, v in measured.items():
        s, w = key.rsplit("__", 1)
        by_slug[s][int(w)] = v

    designers, d_index = [], {}
    fams, faces, pn, po = [], [], [], []
    missing = []
    for name in sorted(fams_meta, key=lambda n: fams_meta[n]["popularity"]):
        fm = fams_meta[name]
        ds = []
        for d in fm["designers"]:
            if d not in d_index:
                d_index[d] = len(designers)
                designers.append(d)
            ds.append(d_index[d])
        lc = licence_for(name, lic)
        if lc is None:
            missing.append(name)
        wght = next((a for a in fm["axes"] if a["tag"] == "wght"), None)
        fi = len(fams)
        weights = {}
        for w in sorted(by_slug.get(slug(name), {})):
            v = by_slug[slug(name)][w]
            weights[w] = len(faces)
            faces.append([fi, w] + [v.get(k) for k in FACE_FIELDS[2:]])
            pn.append(v["paths"].get("n", ""))
            po.append(v["paths"].get("o", ""))
        listed = sorted(int(k) for k in fm["fonts"] if not k.endswith("i"))
        fams.append({
            "n": name, "s": slug(name), "c": CATS.index(fm["category"]), "d": ds,
            "y": fm["dateAdded"], "p": fm["popularity"],
            "l": LICS.index(lc) if lc else None,
            "nt": 1 if fm["isNoto"] else 0,
            "ax": [int(wght["min"]), int(wght["max"])] if wght else None,
            "gt": fm["fonts"].get("400", {}).get("thickness"),
            "gw": fm["fonts"].get("400", {}).get("width"),
            "it": 1 if any(k.endswith("i") for k in fm["fonts"]) else 0,
            "nl": len(listed), "ls": listed,
            "sc": len([s for s in fm["subsets"] if s != "menu"]),
            "w": weights,
        })
    if missing:
        sys.exit("no licence found for: %s" % missing)
    return fams, faces, pn, po, designers


def figures(fams, faces, designers):
    FI = {k: i for i, k in enumerate(FACE_FIELDS)}

    def fv(i, w, field=K):
        idx = fams[i]["w"].get(w)
        return faces[idx][FI[field]] if idx is not None else None

    def vals(w, field=K, only=None):
        out = []
        for i, f in enumerate(fams):
            if only and CATS[f["c"]] not in only:
                continue
            v = fv(i, w, field)
            if v:
                out.append((v, i))
        out.sort()
        return out

    def group(pairs):
        g = collections.defaultdict(list)
        for v, i in pairs:
            g[CATS[fams[i]["c"]]].append(v)
        return g

    S = {}
    S["families"] = len(fams)
    S["faces"] = len(faces)
    S["designers"] = len(designers)
    S["measuredFamilies"] = sum(1 for f in fams if f["w"])
    S["cats"] = dict(collections.Counter(CATS[f["c"]] for f in fams))
    S["lics"] = dict(collections.Counter(LICS[f["l"]] for f in fams))
    S["dateFrom"] = min(f["y"] for f in fams)
    S["dateTo"] = max(f["y"] for f in fams)
    S["noto"] = sum(f["nt"] for f in fams)
    S["variable"] = sum(1 for f in fams if f["ax"])
    S["italics"] = sum(f["it"] for f in fams)

    # --- families that ship a single weight
    one = [i for i, f in enumerate(fams) if f["nl"] == 1]
    S["oneWeight"] = len(one)
    S["oneWeightPct"] = round(100 * len(one) / len(fams), 1)
    S["oneWeightIs400"] = sum(1 for i in one if fams[i]["ls"] == [400])
    S["oneWeightVariable"] = sum(1 for i in one if fams[i]["ax"])
    S["oneWeightByCat"] = dict(collections.Counter(CATS[fams[i]["c"]] for i in one))
    S["oneWeightCatShare"] = {c: round(100 * n / S["cats"][c], 1)
                              for c, n in S["oneWeightByCat"].items()}
    S["no400"] = [[fams[i]["n"], fams[i]["ls"]] for i, f in enumerate(fams)
                  if 400 not in f["ls"]]

    # --- the spread of a nominal weight
    v400, v700 = vals(400), vals(700)
    for tag, v in (("400", v400), ("700", v700)):
        nums = [x[0] for x in v]
        S["spread" + tag] = {
            "n": len(v), "min": v[0][0], "minName": fams[v[0][1]]["n"],
            "max": v[-1][0], "maxName": fams[v[-1][1]]["n"],
            "p5": pct(nums, 5), "p25": pct(nums, 25), "med": pct(nums, 50),
            "p75": pct(nums, 75), "p95": pct(nums, 95),
        }
    med400, med700 = S["spread400"]["med"], S["spread700"]["med"]
    heavy = [i for v, i in v400 if v > med700]
    S["heavy400"] = len(heavy)
    S["heavy400pct"] = round(100 * len(heavy) / len(v400), 1)
    S["heavy400names"] = [[fams[i]["n"], fv(i, 400)] for i in heavy[-12:]][::-1]
    S["light700"] = [[fams[i]["n"], v] for v, i in v700[:10]]
    S["oneWeightHeavy"] = round(100 * sum(1 for i in one if fv(i, 400) and fv(i, 400) > med700)
                                / sum(1 for i in one if fv(i, 400)), 1)

    # --- pick a bold and a regular from two different families
    for tag, only in (("all", None), ("text", TEXT_CATS)):
        r = [v for v, _ in vals(400, only=only)]
        b = [v for v, _ in vals(700, only=only)]
        inv = sum(len(r) - bisect.bisect_right(r, bv) for bv in b)
        S["inv_" + tag] = {"bolds": len(b), "regulars": len(r), "pairs": len(b) * len(r),
                           "inverted": inv, "pct": round(100 * inv / (len(b) * len(r)), 1),
                           "oneIn": round((len(b) * len(r)) / inv)}

    # --- crossings worth naming: both families inside the 150 most popular,
    #     and in the same category, so it is not a script face against a text face
    pop = [i for i in range(len(fams)) if fams[i]["p"] <= 150]
    named = []
    for i in pop:
        bi = fv(i, 700)
        if not bi:
            continue
        for j in pop:
            rj = fv(j, 400)
            if not rj or i == j or fams[i]["c"] != fams[j]["c"]:
                continue
            if rj > bi:
                named.append([round(rj - bi, 1), fams[i]["n"], bi, fams[j]["n"], rj,
                              CATS[fams[i]["c"]]])
    named.sort(reverse=True)
    S["namedCrossings"] = [n[1:] for n in named[:16]]
    S["namedCrossingCount"] = len(named)

    # the same thing again inside the text categories, where it is less expected:
    # a display face being heavy is a design decision, a body face being heavier
    # than someone else's bold is a trap
    tpop = [i for i in range(len(fams))
            if fams[i]["p"] <= 400 and CATS[fams[i]["c"]] in TEXT_CATS]
    tnamed = []
    for i in tpop:
        bi = fv(i, 700)
        if not bi:
            continue
        for j in tpop:
            rj = fv(j, 400)
            if rj and i != j and rj > bi:
                tnamed.append([round(rj - bi, 1), fams[i]["n"], bi, fams[j]["n"], rj,
                               CATS[fams[i]["c"]], CATS[fams[j]["c"]]])
    tnamed.sort(reverse=True)
    S["textCrossings"] = [n[1:] for n in tnamed[:16]]
    S["textCrossingCount"] = len(tnamed)

    # the twenty most popular families, measured, as a table of names people know
    S["popular"] = [[f["n"], CATS[f["c"]], f["nl"], fv(i, 400), fv(i, 700),
                     round(fv(i, 700) / fv(i, 400), 2) if (fv(i, 400) and fv(i, 700)) else None]
                    for i, f in enumerate(fams) if f["p"] <= 24]

    # --- how much a family's own bold adds
    jump = sorted(((fv(i, 700) / fv(i, 400)), i) for i in range(len(fams))
                  if fv(i, 400) and fv(i, 700))
    jn = [j for j, _ in jump]
    S["jump"] = {"n": len(jump), "min": round(jump[0][0], 3), "minName": fams[jump[0][1]]["n"],
                 "max": round(jump[-1][0], 3), "maxName": fams[jump[-1][1]]["n"],
                 "p10": round(pct(jn, 10), 3), "med": round(pct(jn, 50), 3),
                 "p90": round(pct(jn, 90), 3),
                 "small": [[fams[i]["n"], round(j, 3)] for j, i in jump[:10]],
                 "large": [[fams[i]["n"], round(j, 3)] for j, i in jump[-10:]][::-1]}

    # --- steps inside a ramp that add nothing, confirmed on the second measure
    dup = []
    for i, f in enumerate(fams):
        ws = sorted(w for w in f["w"] if fv(i, w))
        for a, b in zip(ws, ws[1:]):
            if fv(i, b) <= fv(i, a):
                ca, cb = fv(i, a, "capstem"), fv(i, b, "capstem")
                dup.append([fams[i]["n"], a, b, fv(i, a), fv(i, b),
                            1 if (ca and cb and cb <= ca) else 0])
    S["dupSteps"] = dup
    S["dupFamilies"] = sorted({d[0] for d in dup})
    S["rampFamilies"] = sum(1 for i, f in enumerate(fams)
                            if len([w for w in f["w"] if fv(i, w)]) >= 3)
    S["reversals"] = sum(1 for d in dup if d[4] < d[3])

    # --- Google's own thickness bucket against the measurement
    buckets = collections.defaultdict(list)
    for i, f in enumerate(fams):
        v = fv(i, 400)
        if v and f["gt"]:
            buckets[f["gt"]].append((v, i))
    S["buckets"] = []
    for t in sorted(buckets):
        v = sorted(buckets[t])
        S["buckets"].append({"t": t, "n": len(v), "med": round(st.median([x[0] for x in v]), 1),
                             "lo": v[0][0], "loName": fams[v[0][1]]["n"],
                             "hi": v[-1][0], "hiName": fams[v[-1][1]]["n"]})
    bx = [(f["gt"], fv(i, 400)) for i, f in enumerate(fams) if f["gt"] and fv(i, 400)]
    S["bucketCorr"] = corr([a for a, _ in bx], [b for _, b in bx])
    S["bucketN"] = len(bx)
    overlap = 0
    for a in S["buckets"]:
        for b in S["buckets"]:
            if a["t"] < b["t"] and a["hi"] > b["lo"]:
                overlap += 1
    S["bucketOverlaps"] = overlap

    # --- the measures checked against each other
    trip = [(f[FI["othick"]], f[FI["capstem"]], f[FI["cov"]]) for f in faces
            if f[FI["othick"]] and f[FI["capstem"]] and f[FI["cov"]]]
    S["checkN"] = len(trip)
    S["checkCapstem"] = corr([t[0] for t in trip], [t[1] for t in trip])
    S["checkCov"] = corr([t[0] for t in trip], [t[2] for t in trip])
    S["checkRatio"] = round(st.median([t[1] / t[0] for t in trip]), 3)

    # --- secondary dimensions
    con = sorted(((fv(i, 400, "othick") / fv(i, 400, "othin")), i) for i in range(len(fams))
                 if fv(i, 400, "othick") and fv(i, 400, "othin"))
    cn = [c for c, _ in con]
    S["contrast"] = {"n": len(con), "med": round(pct(cn, 50), 2), "p95": round(pct(cn, 95), 2),
                     "min": round(con[0][0], 2), "minName": fams[con[0][1]]["n"],
                     "max": round(con[-1][0], 2), "maxName": fams[con[-1][1]]["n"],
                     "high": [[fams[i]["n"], round(c, 2)] for c, i in con[-10:]][::-1],
                     "byCat": {k2: round(st.median(v), 2) for k2, v in group(con).items()}}

    xh = sorted(((fv(i, 400, "xh") / fv(i, 400, "cap")), i) for i in range(len(fams))
                if fv(i, 400, "xh") and fv(i, 400, "cap"))
    xn = [x for x, _ in xh]
    S["xheight"] = {"n": len(xh), "med": round(pct(xn, 50), 3),
                    "min": round(xh[0][0], 3), "minName": fams[xh[0][1]]["n"],
                    "max": round(xh[-1][0], 3), "maxName": fams[xh[-1][1]]["n"],
                    "byCat": {k2: round(st.median(v), 3) for k2, v in group(xh).items()}}

    # --- did any of it move over sixteen years
    yr = collections.defaultdict(list)
    for i, f in enumerate(fams):
        v, c, x = fv(i, 400), fv(i, 400, "cap"), fv(i, 400, "xh")
        if v and c and x:
            yr[int(f["y"][:4])].append((v, x / c))
    S["byYear"] = [[y, len(yr[y]), round(st.median([a[0] for a in yr[y]]), 1),
                    round(st.median([a[1] for a in yr[y]]), 3)] for y in sorted(yr)]
    ys = [row for row in S["byYear"] if row[1] >= 20]
    S["yearStrokeRange"] = [min(r[2] for r in ys), max(r[2] for r in ys)]
    S["yearXhRange"] = [min(r[3] for r in ys), max(r[3] for r in ys)]

    # --- the page sets itself in two of these; print their own numbers
    S["selfSet"] = {}
    for i, f in enumerate(fams):
        if f["n"] in ("Space Grotesk", "IBM Plex Mono"):
            S["selfSet"][f["n"]] = {str(w): fv(i, w) for w in (400, 500, 700) if fv(i, w)}

    with open(os.path.join(RAW, "measure_skipped.json"), encoding="utf-8") as f:
        S["skipped"] = len(json.load(f))
    with open(os.path.join(RAW, "fetch_failures.json"), encoding="utf-8") as f:
        fails = json.load(f)
    S["unfetched"] = len(fails)
    S["unfetchedOver900"] = sum(1 for x in fails if isinstance(x[1], int) and x[1] > 900)
    return S


def main():
    measured, meta, lic = load()
    fams, faces, pn, po, designers = assemble(measured, meta, lic)
    S = figures(fams, faces, designers)
    payload = {
        "generated": datetime.date.today().isoformat(),
        "cats": CATS, "lics": LICS, "designers": designers,
        "faceFields": FACE_FIELDS, "fams": fams, "faces": faces,
        "pn": pn, "po": po, "stats": S,
    }
    out = os.path.join(HERE, "payload.json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, separators=(",", ":"))
    print("payload.json %.2f MB  (%d families, %d faces)"
          % (os.path.getsize(out) / 1e6, len(fams), len(faces)))
    keys = ("oneWeight", "oneWeightIs400", "oneWeightHeavy", "no400", "spread400",
            "spread700", "heavy400", "heavy400pct", "inv_all", "inv_text", "jump",
            "bucketCorr", "bucketOverlaps", "checkCapstem", "checkRatio",
            "dupFamilies", "reversals", "yearStrokeRange", "yearXhRange", "selfSet")
    print(json.dumps({k: S[k] for k in keys}, indent=1)[:3000])


if __name__ == "__main__":
    main()
