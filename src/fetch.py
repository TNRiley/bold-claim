"""Download one subset font file per upright face in the Google Fonts catalogue.

Two endpoints, both public and unauthenticated:

  https://fonts.google.com/metadata/fonts
      the catalogue itself - 1,950 families with designers, dateAdded,
      popularity rank, category, and Google's own coarse thickness/width buckets.

  https://fonts.googleapis.com/css2?family=<F>:wght@<w>&text=<chars>
      the CSS the browser gets. Requested with a legacy User-Agent it serves
      plain .ttf instead of woff2, and `text=` makes gstatic subset the file to
      just the characters asked for: ~9 kB a face instead of ~120 kB, which is
      what makes fetching all 6,000 faces reasonable. Subsetting preserves
      unitsPerEm, advance widths and outlines exactly - only glyph coverage is cut.

  https://api.github.com/repos/google/fonts/git/trees/<sha>
      the licence each family is published under. The metadata endpoint does not
      say, but github.com/google/fonts files every family under ofl/, apache/ or
      ufl/, so listing those three trees gives the mapping. Needed because this
      project embeds real outlines, so each family's terms have to be named.

Everything lands in raw/ and is skipped on re-runs, so this is resumable.
"""
import json, os, re, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
FACES = os.path.join(RAW, "faces")
SPECIMEN = "Hamburgenox"          # Hamburg for the specimen, e/n/o/x for the metrics
UA = {"User-Agent": "Mozilla/4.0 (compatible)"}
META_URL = "https://fonts.google.com/metadata/fonts"


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def catalogue():
    os.makedirs(RAW, exist_ok=True)
    p = os.path.join(RAW, "fonts_metadata.json")
    if not os.path.exists(p):
        with open(p, "wb") as f:
            f.write(get(META_URL))
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def slug(family):
    return re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")


def faces(meta):
    """Every upright face: (family, weight). Italics dropped - the point of the
    page is weight, and italics double the download for nothing."""
    out = []
    for fam in meta["familyMetadataList"]:
        ws = sorted(int(k) for k in fam["fonts"] if not k.endswith("i"))
        for w in ws:
            out.append((fam["family"], w))
    return out


def css_urls(batch):
    """One CSS request for several families; returns {(family, weight): url}."""
    q = []
    for family, weights in batch:
        q.append("family=" + urllib.parse.quote_plus(family) + ":wght@" +
                 ";".join(str(w) for w in weights))
    q.append("text=" + urllib.parse.quote(SPECIMEN))
    css = get("https://fonts.googleapis.com/css2?" + "&".join(q)).decode("utf-8")
    found = {}
    for block in css.split("@font-face"):
        fam = re.search(r"font-family: '([^']+)'", block)
        wt = re.search(r"font-weight: (\d+)", block)
        st = re.search(r"font-style: (\w+)", block)
        url = re.search(r"url\((\S+?)\) format\('truetype'\)", block)
        if fam and wt and url and (not st or st.group(1) == "normal"):
            found[(fam.group(1), int(wt.group(1)))] = url.group(1)
    return found


def licences():
    """family-directory -> licence, from the three licence trees in google/fonts."""
    import json as _json
    for d in ("ofl", "apache", "ufl"):
        p = os.path.join(RAW, "lic_%s.txt" % d)
        if os.path.exists(p):
            continue
        root = _json.loads(get("https://api.github.com/repos/google/fonts/git/trees/main"))
        sha = next(t["sha"] for t in root["tree"] if t["path"] == d)
        tree = _json.loads(get("https://api.github.com/repos/google/fonts/git/trees/" + sha))
        if tree.get("truncated"):
            raise SystemExit("licence tree for %s came back truncated" % d)
        with open(p, "w", encoding="utf-8", newline="
") as f:
            f.write("
".join(t["path"] for t in tree["tree"]) + "
")
        print("  licences: %s has %d families" % (d, len(tree["tree"])), flush=True)


def main():
    meta = catalogue()
    licences()
    os.makedirs(FACES, exist_ok=True)
    want = {}
    for family, w in faces(meta):
        want.setdefault(family, []).append(w)

    # which faces are still missing on disk
    todo = {f: [w for w in ws if not os.path.exists(os.path.join(FACES, f"{slug(f)}__{w}.ttf"))]
            for f, ws in want.items()}
    todo = {f: ws for f, ws in todo.items() if ws}
    print(f"{sum(len(v) for v in want.values())} upright faces in "
          f"{len(want)} families; {sum(len(v) for v in todo.values())} to fetch", flush=True)
    if not todo:
        return

    items = list(todo.items())
    batches = [items[i:i + 6] for i in range(0, len(items), 6)]
    failed, done = [], [0]

    def run(batch):
        try:
            urls = css_urls(batch)
        except Exception as e:
            failed.append((batch[0][0], "css", repr(e)))
            return
        for family, weights in batch:
            for w in weights:
                url = urls.get((family, w))
                if url is None:
                    failed.append((family, w, "no css face"))
                    continue
                dest = os.path.join(FACES, f"{slug(family)}__{w}.ttf")
                try:
                    data = get(url)
                    with open(dest, "wb") as fh:
                        fh.write(data)
                    done[0] += 1
                except Exception as e:
                    failed.append((family, w, repr(e)))
        if done[0] and done[0] % 250 < 12:
            print(f"  {done[0]} faces", flush=True)

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(run, batches))

    print(f"fetched {done[0]}, failed {len(failed)}", flush=True)
    with open(os.path.join(RAW, "fetch_failures.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(failed, f, indent=1)


if __name__ == "__main__":
    main()
