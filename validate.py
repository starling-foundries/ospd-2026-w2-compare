"""Validate the register's provenance examples, as published and with the fingerprint entities appended,
against the schema the register itself uses for them (ogc.bbr.provenance.provenance, GeoLabs).

The schemas are read at the commits that were current when the comparison was run (21 Nov 2026).
The base PROV schema changed upstream on 23 Nov 2026 (ogcincubator/bblock-prov-schema PR #9): `provType`
now expects `Entity`/`Activity`/`Agent` where the register's examples write `prov:Entity` etc.
`--live` validates against the schemas as published today instead.

  uv run --no-project --with jsonschema --with referencing python validate.py [--live]
"""
import json
import sys
import urllib.request
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

HERE = Path(__file__).parent
SCHEMA = "https://geolabs.github.io/bblocks-generic-provenance-profile/build/annotated/bbr/provenance/provenance/schema.json"
# The GeoLabs block is a 447-byte wrapper whose built form is not kept in git history; schemas/ holds a
# copy, identical to the one fetched on 21 Nov 2026 (its repository last changed on 23 Sep 2026).
LOCAL = {SCHEMA: HERE / "schemas" / "ogc.bbr.provenance.provenance.schema.json"}
PINS = {   # published URL prefix -> the same files at the commit current on 21 Nov 2026
    "https://ogcincubator.github.io/bblock-prov-schema/":
        "https://raw.githubusercontent.com/ogcincubator/bblock-prov-schema/45d4e57fcbb311a4335d4f1ac3c7c7b70f312e6a/",
    "https://opengeospatial.github.io/bblocks/":
        "https://raw.githubusercontent.com/opengeospatial/bblocks/de8c737fa89df06017a41d1408ae92da50c34905/",
}
LIVE = "--live" in sys.argv


def retrieve(uri):
    if not LIVE and uri in LOCAL:
        return Resource.from_contents(json.loads(LOCAL[uri].read_text()))
    if not LIVE:
        for published, pinned in PINS.items():
            if uri.startswith(published):
                uri = pinned + uri[len(published):]
    return Resource.from_contents(json.loads(urllib.request.urlopen(uri, timeout=30).read()))


validator = Draft202012Validator(retrieve(SCHEMA).contents, registry=Registry(retrieve=retrieve))
print("schemas:", "as published today" if LIVE else "pinned to 21 Nov 2026")
files = sorted((HERE / "register-examples").rglob("provenance.json")) + sorted((HERE / "results" / "prov").glob("*.json"))
for f in files:
    doc = json.loads(f.read_text())
    errors = list(validator.iter_errors(doc))
    print(f"{'valid  ' if not errors else 'INVALID'} {len(doc):3d} records  {f.relative_to(HERE)}")
    for e in errors[:3]:
        for sub in sorted(e.context, key=lambda x: len(x.path))[:3] or [e]:
            print("        ", "/".join(map(str, sub.absolute_path)), sub.message[:120])
