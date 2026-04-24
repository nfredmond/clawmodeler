# ClawModeler Install Profiles

Use `install-profile.sh` to install optional Python dependencies for increasingly capable local modeling profiles.

```bash
python3 -m pip install -e .
bash scripts/install-profile.sh light
bash scripts/install-profile.sh standard
bash scripts/install-profile.sh full
bash scripts/install-profile.sh gpu
bash scripts/check-packaging.sh
pnpm release:assets:test
pnpm release:latest-policy:test
pnpm release:first-user-smoke
pnpm release:workflow:test
```

Profiles:

- `light`: fast screening stack.
- `standard`: GIS, OSM routing, GTFS, plotting, and report tooling.
- `full`: simulation, optimization, matrix, and bridge tooling.
- `gpu`: full plus PyTorch and ML libraries.

System binaries such as GDAL, Java, SUMO, Pandoc, Graphviz, Docker, and local model source trees are checked by `clawmodeler-engine doctor` but are not installed by this script.

Environment overrides:

- `CLAWMODELER_TOOLBOX`: path to a custom toolbox JSON.
- `CLAWMODELER_MODEL_ROOT`: path containing local model source trees such as `sumo/`, `matsim-libs/`, `urbansim/`, `DTALite/`, and `tbest-tools/`.

Installed sidecar entry point:

```bash
clawmodeler-engine --help
```

Packaging check:

```bash
bash scripts/check-packaging.sh
```

The check runs the sidecar unit tests, builds the wheel, verifies packaged sidecar files, installs the wheel into a temporary virtual environment, and checks the installed `clawmodeler-engine` console script.

Release checks:

```bash
pnpm sidecar:build
pnpm release:sidecar-smoke
pnpm release:first-user-smoke -- --binary desktop/src-tauri/binaries/clawmodeler-engine
pnpm release:workflow:test
pnpm release:assets -- --tag vX.Y.Z --dir artifacts
```

The release sidecar smoke check runs the built desktop sidecar through version, doctor, demo workflow, tiny-fixture workflow, CEQA Planner Pack generation, and PDF and DOCX report export. `scripts/collect-weasyprint-runtime.py` prepares the ignored `desktop/src-tauri/binaries/weasyprint-runtime/` folder for macOS and Windows release builds so WeasyPrint native libraries sit beside the packaged sidecar. The first-user smoke check starts from a clean workspace and verifies the planner-facing baseline, workspace index, QA, CEQA Planner Pack, portfolio, and diff path. The release workflow self-test blocks Node 20-backed workflow actions and missing smoke gates. The asset check verifies release bundle names before GitHub release publication.
