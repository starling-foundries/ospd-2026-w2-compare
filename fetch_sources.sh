#!/bin/sh
# Fetch the two workflows exactly as the OSPD 2026 process-profiles register pins them
# (GeoLabs/bblocks-process-profiles scripts/sources.yaml), into sources/.
set -eu
cd "$(dirname "$0")"
mkdir -p sources/kindgrove-steps

# W2: the 2025 package's workflow, pinned through bblocks-eoap-cct at 291a741
if [ ! -d sources/bblocks-eoap-cct ]; then
  git clone --quiet https://github.com/GeoLabs/bblocks-eoap-cct sources/bblocks-eoap-cct
fi
git -C sources/bblocks-eoap-cct checkout --quiet 291a741c3f2b61da7607f1dbb7a777134374227d

# W2 imports its types from eoap/schemas on the main branch, which since 7 Oct 2026 no longer
# validates under CWL v1.0. Run it against main as it was before that change.
S=sources/bblocks-eoap-cct/_sources/cwl-to-ogcprocess/examples
sed 's#raw.githubusercontent.com/eoap/schemas/main/#raw.githubusercontent.com/eoap/schemas/a9fb94fab3588c6aa5b8294f20c7e88c3e450932/#g' \
  "$S/mangrove-workflow.cwl" > "$S/mangrove-workflow.schemas-a9fb94f.cwl"

# W2b: the step-decomposed reimplementation, a release asset pinned by sha256
F=sources/kindgrove-steps/mangrove-workflow-steps.cwl
curl -sSL -o "$F" https://github.com/GeoLabs/KindGrove/releases/download/v0.0.2-rc3/mangrove-workflow-steps.cwl
echo "886e1b0119955524c435d8368b5827d3ab7fcd89fbc8552292fe3184fa89bb73  $F" | shasum -a 256 -c -
