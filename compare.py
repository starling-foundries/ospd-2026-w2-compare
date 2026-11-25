"""Two implementations of the mangrove workflow, one execute request: are the runs comparable?

  W2   the 2025 package as pinned in the OSPD register (bblocks-eoap-cct 291a741, mangrove-cwl:v0.0.1-rc7)
  W2b  the 6-step reimplementation (GeoLabs/KindGrove release v0.0.2-rc3)

Both were run back to back with cwltool --provenance on the request of Q-W2 (runs/, see README.md).
This script answers the three competency questions with DGGS fingerprints, writes the answers as PROV
entities appended to the register's own published examples, and reads the answers back from those
records alone.

  cd "$KINDGROVE" && uv run python -W ignore <this folder>/compare.py
"""
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Geod, Transformer
from shapely.geometry import box, mapping, shape

import burin

HERE = Path(__file__).parent
RUNS = HERE / "runs"
OUT = HERE / "results"
CACHE = HERE / "cache"
EXAMPLES = HERE / "register-examples"      # copies of the register's _sources/<workflow>/<step>/examples
ES = "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/"
BBOX = (95.15, 15.9, 95.35, 16.1)
DAYS_BACK = 90
L = 12
DGGRS = "https://www.opengis.net/def/dggrs/OGC/1.0/rHEALPix"
ZONE_SET = "urn:proposed:eoap-cct:ZoneSet"          # drafted for bblocks-eoap-cct, not yet submitted
TIME_WINDOW = "urn:proposed:time-window"
INSTANT_IN_WINDOW = "urn:proposed:instant-in-window"
RUN_INFO = {
    "w2": dict(title="W2, 2025 package (mangrove-cwl:v0.0.1-rc7)", step="step_1", log="w2.log",
               ex="kindgrove/mangrove", prefix="urn:example:entity:mangrove"),
    "steps": dict(title="W2b, 6-step release v0.0.2-rc3", step="select_scene", log="steps.log",
                  ex="kindgrove-steps/select-scene", prefix="urn:example:entity:select-scene"),
}
GEOD = Geod(ellps="WGS84")


def say(s=""):
    print(s, flush=True)


def ha(t):
    return t.leaf_count() * burin.cell_area_m2(L) / 1e4


def tree_of(geom):
    return burin.Tree.from_geojson(json.dumps(mapping(geom)), L)


def scene_item(sid):
    p = CACHE / f"{sid}.json"
    if not p.exists():
        import urllib.request
        p.write_text(urllib.request.urlopen(ES + sid, timeout=30).read().decode())
    return json.loads(p.read_text())


def find_key(obj, key):
    """First value of `key` anywhere in a JSON document."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        obj = list(obj.values())
    if isinstance(obj, list):
        for v in obj:
            r = find_key(v, key)
            if r is not None:
                return r
    return None


def step_start(log, step):
    """When the step that resolves days_back started (cwltool --timestamps, host local time), in UTC."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", (RUNS / log).read_text())
    m = re.search(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] INFO \[step " + step + r"\] start", text)
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").astimezone(timezone.utc)


def outputs(run):
    """Scene id, reported area and mask GeoTIFF written by one run."""
    out = RUNS / run / "out"
    docs = [json.loads(p.read_text()) for p in out.rglob("*.json")]
    text = " ".join(json.dumps(d) for d in docs)
    sid = re.search(r"S2[ABC]_\d\d[A-Z]{3}_\d{8}_\d_L2A", text).group(0)
    area = next((find_key(d, "mangrove_area_ha") for d in docs if find_key(d, "mangrove_area_ha") is not None), None)
    mask = next(p for p in sorted(out.rglob("*.tif")) if "mask" in p.name.lower())
    return sid, area, mask


def zones_of_raster(path, leaves, lon, lat):
    """Zones whose nucleus falls on a mangrove pixel (value 1) of the raster, in any CRS."""
    with rasterio.open(path) as ds:
        x, y = (lon, lat) if ds.crs.to_epsg() == 4326 else Transformer.from_crs(4326, ds.crs, always_xy=True).transform(lon, lat)
        rows, cols = rasterio.transform.rowcol(ds.transform, x, y)
        rows, cols = np.asarray(rows), np.asarray(cols)
        m = ds.read(1)
        ok = (rows >= 0) & (rows < m.shape[0]) & (cols >= 0) & (cols < m.shape[1])
        hit = np.zeros(len(leaves), bool)
        hit[ok] = m[rows[ok], cols[ok]] == 1
        px = int((m == 1).sum())
        res = abs(ds.transform.a), abs(ds.transform.e)
    return burin.Tree.from_cells(leaves[hit].tolist(), L), px, res


def fixed_code_mask(sid):
    """The same scene through the fixed code (KindGrove main, c69b501): the BOA offset added back."""
    p = CACHE / f"{sid}_fixed.tif"
    if not p.exists():
        import pystac
        sys.path.insert(0, os.environ.get("KINDGROVE", str(Path.home() / "code/KindGrove")))
        import mangrove_workflow_cli as w
        data = w.download_imagery(pystac.Item.from_dict(scene_item(sid)), list(BBOX))
        m = np.asarray(w.detect_mangroves(w.calculate_indices(data))).squeeze().astype(np.uint8)
        x, y = data.x.values, data.y.values
        with rasterio.open(p, "w", driver="GTiff", height=m.shape[0], width=m.shape[1], count=1, dtype="uint8",
                           crs="EPSG:4326", transform=rasterio.Affine(0.0001, 0, x[0] - 0.00005, 0, -0.0001, y[0] + 0.00005),
                           compress="deflate") as d:
            d.write(m, 1)
    return p


def zone_set(t, with_zones=True):
    v = {"dggrs": DGGRS, "zone_level": L, "root": t.root_hex}
    if with_zones:
        v["zones"] = [int(z) for z in t.cells()]      # compact: nine full children collapse into their parent
    return v


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj, indent=1))
    return path


# ---------------------------------------------------------------- read both runs
CACHE.mkdir(exist_ok=True)
if OUT.exists():
    shutil.rmtree(OUT)
aoi = tree_of(box(*BBOX))
leaves = np.asarray(aoi.leaves(), dtype=np.uint64)
lon, lat = burin.cells_to_lonlat(leaves)
R = {}
for run, info in RUN_INFO.items():
    sid, area, mask = outputs(run)
    item = scene_item(sid)
    start = step_start(info["log"], info["step"])
    when = item["properties"]["datetime"].rstrip("Z")
    w1 = np.datetime64(start.replace(tzinfo=None))
    w0 = w1 - np.timedelta64(DAYS_BACK, "D")
    window = burin.time.tree([(w0, w1)])
    proof = window.prove_instant(when)
    zones, px, res = zones_of_raster(mask, leaves, lon, lat)
    R[run] = dict(sid=sid, area=area, mask=mask, item=item, start=start, when=when, w=(w0, w1), window=window,
                  interval=burin.time.interval(w0, w1), proof=proof, ok=window.fingerprint.check_instant(proof, when),
                  ground=tree_of(shape(item["geometry"]).intersection(box(*BBOX))), zones=zones, px=px, res=res)
a, b = R["w2"], R["steps"]

# ---------------------------------------------------------------- the three questions
say("Same request to two implementations: bbox %s, cloud_cover_max 20, days_back %d" % (list(BBOX), DAYS_BACK))
for run, r in R.items():
    say(f"  {RUN_INFO[run]['title']}: scene {r['sid']}, reported {r['area']} ha")
say()
same_ground = a["ground"].root_hex == b["ground"].root_hex
say(f"1. Same ground? {'yes' if same_ground else 'no'}")
for run, r in R.items():
    say(f"   {run:5s} scene ground {r['ground'].root_hex[:16]}…  {ha(r['ground']):,.0f} ha  "
        f"(whole request: {r['ground'].root_hex == aoi.root_hex})")

same_scene_time = a["when"] == b["when"]
allen = burin.time.allen(a["interval"], b["interval"])
say(f"2. Same time? acquisition {'identical' if same_scene_time else 'different'}; "
    f"windows {'identical' if a['window'].root_hex == b['window'].root_hex else 'not identical'}")
for run, r in R.items():
    say(f"   {run:5s} window {r['w'][0]}/{r['w'][1]}  {r['window'].root_hex[:16]}…  "
        f"scene {r['when']} inside: {r['ok']} (proof {len(json.dumps(r['proof'].to_json()))} B)")
say(f"   the two windows: Allen '{allen}', {abs((b['start'] - a['start']).total_seconds()) / 60:.0f} min apart, "
    f"because days_back is counted from datetime.now()")

fixed = fixed_code_mask(a["sid"])
fz, fpx, _ = zones_of_raster(fixed, leaves, lon, lat)
same_result = a["zones"].root_hex == b["zones"].root_hex
only_a, only_b = a["zones"].difference(b["zones"]), b["zones"].difference(a["zones"])
say(f"3. Same computation? {'yes: identical result fingerprints' if same_result else 'no'}")
for name, t, px, rep, res in (("w2", a["zones"], a["px"], a["area"], a["res"]), ("steps", b["zones"], b["px"], b["area"], b["res"]),
                              ("fixed", fz, fpx, None, (0.0001, 0.0001))):
    say(f"   {name:5s} mask {t.root_hex[:16]}…  zones {ha(t):8.2f} ha  pixels×100 m² {px / 100:8.2f} ha"
        f"  reported {rep if rep is not None else '-':>7}  grid {res[0]:g}°")
if not same_result:
    say(f"   they differ on {only_a.leaf_count() + only_b.leaf_count()} zones "
        f"({ha(only_a):.2f} ha only in w2, {ha(only_b):.2f} ha only in steps), {len(a['zones'].divergence(b['zones']))} subtrees")
px_m2 = abs(GEOD.polygon_area_perimeter([95.25, 95.2501, 95.2501, 95.25], [16.0, 16.0, 16.0001, 16.0001])[0])
say(f"   both count a 0.0001° pixel as 100 m²; here it is {px_m2:.1f} m². The fixed code finds {ha(fz):.2f} ha "
    f"on the same scene ({ha(fz) / max(ha(a['zones']), 1e-9):.2f}× the w2 zones).")

# ---------------------------------------------------------------- the answers as PROV entities
evidence = OUT / "evidence"
write(evidence / "aoi.zones.json", zone_set(aoi))
prov = {}
for run, r in R.items():
    p, ex = RUN_INFO[run]["prefix"], RUN_INFO[run]["ex"]
    base = json.loads((EXAMPLES / ex / "provenance.json").read_text())
    ids = {rec["id"] for rec in base}
    lit = [f"{p}:in:{k}" for k in ("west", "south", "east", "north")]
    assert all(i in ids for i in lit + [f"{p}:in:days_back"]), f"{ex}: the example's ids changed"
    write(evidence / f"{run}.scene-ground.zones.json", zone_set(r["ground"]))
    write(evidence / f"{run}.window-proof.json", r["proof"].to_json())  # a dict
    write(evidence / f"{run}.mask.zones.json", zone_set(r["zones"]))
    added = [
        {"id": f"{p}:aoi:zones", "provType": "prov:Entity", "entityType": ZONE_SET,
         "value": zone_set(aoi, with_zones=False), "wasDerivedFrom": lit,
         "links": [{"href": "evidence/aoi.zones.json", "rel": "describedby", "type": "application/json"}]},
        {"id": f"{p}:window", "provType": "prov:Entity", "entityType": TIME_WINDOW,
         "value": {"start": str(r["w"][0]) + "Z", "end": str(r["w"][1]) + "Z", "root": r["window"].root_hex},
         "wasDerivedFrom": [f"{p}:in:days_back"]},
        {"id": f"{p}:scene:ground", "provType": "prov:Entity", "entityType": ZONE_SET,
         "value": zone_set(r["ground"], with_zones=False), "wasDerivedFrom": [f"{p}:aoi:zones"],
         "links": [{"href": f"evidence/{run}.scene-ground.zones.json", "rel": "describedby", "type": "application/json"},
                   {"href": ES + r["sid"], "rel": "via", "type": "application/geo+json"}]},
        {"id": f"{p}:scene:acquired", "provType": "prov:Entity", "entityType": INSTANT_IN_WINDOW,
         "value": {"instant": r["when"] + "Z", "window": r["window"].root_hex, "verified": bool(r["ok"])},
         "wasDerivedFrom": [f"{p}:window"],
         "links": [{"href": f"evidence/{run}.window-proof.json", "rel": "describedby", "type": "application/json"}]},
        {"id": f"{p}:result:zones", "provType": "prov:Entity", "entityType": ZONE_SET,
         "value": zone_set(r["zones"], with_zones=False),
         "links": [{"href": f"evidence/{run}.mask.zones.json", "rel": "describedby", "type": "application/json"}]},
    ]
    prov[run] = write(OUT / "prov" / f"{ex.replace('/', '.')}.fingerprinted.json", base + added)

# ---------------------------------------------------------------- the questions, answered from the records alone
say()
say("Answered from the two PROV records alone (results/prov/*.fingerprinted.json):")
rec = {run: {x["id"].removeprefix(RUN_INFO[run]["prefix"] + ":"): x for x in json.loads(path.read_text())} for run, path in prov.items()}
g = {run: rec[run]["scene:ground"]["value"]["root"] for run in rec}
t = {run: rec[run]["scene:acquired"]["value"]["instant"] for run in rec}
z = {run: rec[run]["result:zones"]["value"]["root"] for run in rec}
v = {run: rec[run]["scene:acquired"]["value"]["verified"] for run in rec}
say(f"  same ground?       {g['w2'] == g['steps']}   ({g['w2'][:12]}… vs {g['steps'][:12]}…)")
say(f"  same acquisition?  {t['w2'] == t['steps']}   ({t['w2']} vs {t['steps']}), each proven inside its window: {all(v.values())}")
say(f"  same result?       {z['w2'] == z['steps']}   ({z['w2'][:12]}… vs {z['steps'][:12]}…)")

write(OUT / "summary.json", {
    "request": {"bbox": list(BBOX), "cloud_cover_max": 20, "days_back": DAYS_BACK},
    "runs": {run: {"title": RUN_INFO[run]["title"], "scene": r["sid"], "acquired": r["when"], "step_start_utc": r["start"].isoformat(),
                   "window": [str(r["w"][0]), str(r["w"][1])], "window_root": r["window"].root_hex, "in_window": bool(r["ok"]),
                   "ground_root": r["ground"].root_hex, "ground_ha": round(ha(r["ground"]), 2),
                   "result_root": r["zones"].root_hex, "result_zones_ha": round(ha(r["zones"]), 2),
                   "mask_pixels": r["px"], "reported_ha": r["area"]} for run, r in R.items()},
    "fixed_code": {"result_root": fz.root_hex, "result_zones_ha": round(ha(fz), 2), "mask_pixels": fpx},
    "aoi_root": aoi.root_hex, "windows_allen": str(allen), "pixel_m2_at_16N": round(px_m2, 1),
    "differing_zones": only_a.leaf_count() + only_b.leaf_count(),
})
say(f"\nwritten: {OUT.relative_to(HERE)}")
