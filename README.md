# One request, two implementations: W2 against W2b

The OSPD register profiles the mangrove workflow twice:
- **W2**: the 2025 package, `mangrove-cwl:v0.0.1-rc7`, pinned through bblocks-eoap-cct 291a741.
- **W2b**: the step-decomposed reimplementation by GeoLabs, GeoLabs/KindGrove release v0.0.2-rc3.

Their notes say W2b was run "with the same execute inputs as `w2-pinned` for comparability", but no comparison was ever recorded. This folder does it.

Both were run back to back on 21 Nov 2026 (about 22:00 EST), with cwltool `--provenance`, on the request of their open question Q-W2:

- bbox 95.15, 15.9, 95.35, 16.1
- cloud_cover_max 20
- days_back 90

The three competency questions are answered with DGGS fingerprints (rHEALPix, level 12). The answers are written as PROV entities appended to the register's own published examples, and validated against the register's provenance schema.

## Results

| question | answer | evidence |
|---|---|---|
| Same ground? | **Yes** | Both picked scene S2C_46PGC_20261115, which covers the whole request. Ground fingerprint `c2c56c74dbdc…`, 47,350 ha, for both runs. |
| Same time? | **Same acquisition, different windows** | Both runs used the scene acquired 2026-11-15 04:23:58 UTC, and each run has a 5 kB proof that it lies inside its window. The windows themselves differ: `days_back` counts from `datetime.now()`, so two runs two minutes apart have different windows (Allen: overlaps). |
| Same computation? | **No** | The totals agree within 1%: 8.41 ha against 8.34 ha reported. The result fingerprints differ: `ba408e8a…` against `11754816…`. 312 zones differ, 4.9 ha found only by W2 and 4.5 ha only by W2b. |

Why the results differ: W2b's output grid is shifted by half a pixel. Its origin is 95.15, 16.1; W2's is 95.14995, 16.10005. Every mangrove pixel in either version has a match within two pixels (20 m) in the other. So it's the same method on a shifted grid, which a total, or a checksum, can't show.

Both versions also carry the 2025 bugs:
- the Sentinel-2 offset applied a second time;
- each 0.0001° pixel counted as 100 m², where at 16°N it is 118.4 m².

The fixed code (KindGrove main, c69b501) finds **17.0 ha** in equal-area zones on the same scene. That's about twice what either version reports.

## Found along the way

The register's W2 source no longer runs as pinned. It imports its types from `eoap/schemas` on the **main** branch. On 7 Oct 2026 a documentation change reached main and added `doc` to an enum. W2 is CWL v1.0, which doesn't allow `doc` there, so the workflow stopped validating.

We ran it with the import pinned to `a9fb94f`, which was main before that change. `fetch_sources.sh` makes that copy. W2b is CWL v1.2 and is unaffected.

The lesson: a pinned workflow that imports from a branch is not pinned.

The provenance schema moved too. On 23 Nov 2026, two days after this comparison, the base PROV schema that the register's provenance block imports (ogcincubator/bblock-prov-schema, PR #9) changed `provType` to expect `Entity`, `Activity` or `Agent`. The register's examples write `prov:Entity`, `prov:Activity` and `prov:Agent`, so they no longer validate against the schemas as published. `validate.py` pins the schemas to make the result reproducible:
- `ogcincubator/bblock-prov-schema` at 45d4e57;
- `opengeospatial/bblocks` at de8c737;
- a copy of the GeoLabs wrapper schema in `schemas/`.

## The PROV records

`results/prov/*.fingerprinted.json` contains the register's own examples (`register-examples/`, copied from bblocks-process-profiles at 79c90fb8). To each, five entities are appended, all ordinary PROV entities. The schema isn't changed.

| entity | value | derived from |
|---|---|---|
| `…:aoi:zones` | the area of interest as a zone set: dggrs, level, root | the four literal bbox entities |
| `…:window` | the resolved window, start, end and root | `days_back` |
| `…:scene:ground` | the ground the selected scene covers | the AOI zone set |
| `…:scene:acquired` | the acquisition instant, verified inside the window (proof in `results/evidence/`) | the window |
| `…:result:zones` | the mangrove mask as a zone set | (none) |

`validate.py` checks the published examples and the fingerprinted ones against `ogc.bbr.provenance.provenance`, with every schema it imports read at the commit current on 21 Nov 2026. All four are valid. The validator also rejects broken records, which was checked separately.

Run with `--live`, it validates against the schemas as published today. Then all four fail, the register's own unchanged examples included (see below).

The last block of `compare.py` answers the three questions by reading only those two JSON files.

## Rerun

You need:
- Docker;
- [uv](https://docs.astral.sh/uv/);
- a checkout of [KindGrove](https://github.com/starling-foundries/KindGrove) with `uv sync` done. Its environment provides burin-core, rasterio and the fixed workflow code.

```
./fetch_sources.sh                 # the two workflows as the register pins them
export PATH=$PWD/bin:$PATH        # cwltool 3.1.20260108082145, as in the register's run records
S=sources/bblocks-eoap-cct/_sources/cwl-to-ogcprocess/examples
cwltool --timestamps --no-match-user --provenance runs/w2/ro --outdir runs/w2/out $S/mangrove-workflow.schemas-a9fb94f.cwl#mangrove-workflow job.json > runs/w2.log 2>&1
cwltool --timestamps --enable-ext --provenance runs/steps/ro --outdir runs/steps/out sources/kindgrove-steps/mangrove-workflow-steps.cwl#mangrove-workflow-steps job.json > runs/steps.log 2>&1
export KINDGROVE=/path/to/KindGrove
(cd $KINDGROVE && uv run python -W ignore $OLDPWD/compare.py)
uv run --no-project --with jsonschema --with referencing python validate.py
```

The two runs take about 3 minutes in all. `compare.py` alone takes seconds; the output of the run reported here is in `compare_output.txt`, and its results are in `results/`.

`validate.py` needs only `results/` and `register-examples/`, so it runs on a fresh clone without rerunning anything.

Because of `days_back`, a rerun on another day picks another scene and gives different numbers. Run both workflows back to back.

## Limits, said plainly

- **Window start.** The window start is taken from cwltool's step-start timestamp, to the second. The code calls `datetime.now()` a moment later inside the container. No conclusion depends on this.
- **Placeholder type IRIs.** `entityType` values are placeholders (`urn:proposed:…`). Real IRIs need the ZoneSet type in eoap-cct and a time-window type: that's a recommendation, not something done.
- **JSON-LD.** The register's JSON-LD context doesn't define the new value fields. Schema validation passes; the RDF view would drop them.
- **Engine.** Runs used cwltool, like the register's own records, not ZOO-Project-DRU.
- **Zone sampling.** Level-12 zones (about 17 m) each sample the pixel under their centre. Zone areas are equal-area by construction, while pixel counts assume 100 m².

## Licence

Apache-2.0. `register-examples/` holds two files copied from [GeoLabs/bblocks-process-profiles](https://github.com/GeoLabs/bblocks-process-profiles) (Apache-2.0); see `register-examples/SOURCE.txt`.
