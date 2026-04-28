# Release Checklist

ClawModeler releases are tag-driven. Pushing a `vX.Y.Z` tag builds Linux, macOS ARM64, and Windows desktop bundles, then publishes a GitHub release when every matrix build succeeds.

Before tagging:

- Confirm all version fields match the intended tag with `pnpm release:version-check`: root `package.json`, Python package metadata, `ENGINE_VERSION`, Tauri `Cargo.toml`, `Cargo.lock`, and `tauri.conf.json`.
- Run the core checks: `python3 -m ruff check .`, `pnpm engine:test`, `pnpm engine:check`, `pnpm ui:typecheck`, `pnpm ui:test`, `pnpm ui:build`, `pnpm desktop:acceptance`, `pnpm release:first-user-smoke`, `pnpm release:workflow:test`, and `cargo test` in `desktop/src-tauri`.
- Build the sidecar with `pnpm sidecar:build`, then run `pnpm release:sidecar-smoke`.
- Run a headless dry run from `main` with the intended RC or final candidate tag in the `candidate_tag` workflow input, then keep the uploaded `release-dry-run-proof` artifact with the release notes.
- Commit the version and changelog changes, push `main`, then push the matching `vX.Y.Z` tag.

Release workflow gates:

- Release workflows are serialized with GitHub Actions concurrency so multiple pushed tags cannot publish out of order.
- Workflow actions are pinned to Node 24-backed major versions, and pnpm is enabled through Corepack instead of `pnpm/action-setup`.
- `pnpm release:workflow:test` blocks accidental rollback to Node 20-backed workflow actions or removal of the release smoke gates.
- Each matrix build smoke-tests the generated sidecar before uploading installer artifacts.
- Each matrix build runs `pnpm release:first-user-smoke` against the packaged sidecar, proving clean workspace creation, baseline execution, workspace-index refresh, QA review, CEQA Planner Pack output, portfolio refresh, and baseline-vs-alternative diff review.
- The release job validates asset names with `pnpm release:assets -- --tag "$GITHUB_REF_NAME" --dir artifacts`.
- The release job marks the GitHub release as Latest only when the tag is the highest SemVer `vX.Y.Z` tag.
- The workflow-dispatch dry-run job validates merged artifacts with `pnpm release:dry-run`, records RC/final prerelease and Latest policy, and uploads Markdown/JSON proof without creating a tag or release.

Hosted macOS ARM DMG smoke:

- Trigger `macOS ARM DMG Smoke` with `workflow_dispatch` and the release candidate tag, for example `v1.0.0-rc.3`.
- The job uses GitHub's hosted `macos-14` Apple Silicon runner, downloads `ClawModeler_<version>_aarch64.dmg` from the GitHub release, mounts it, copies `ClawModeler.app`, verifies `Info.plist`, runs `pnpm release:sidecar-smoke` against the sidecar inside the app bundle, confirms the bundled WeasyPrint runtime is present, and launches the app once with Gatekeeper quarantine cleared.
- Run the same check manually on an Apple Silicon Mac with `pnpm release:macos-dmg-smoke -- --tag vX.Y.Z-rc.N --dmg path/to/ClawModeler_<version>_aarch64.dmg`.
- This hosted check strengthens the installer gate, but it does not replace the final manual GUI gate: install the DMG, use the unsigned first-run bypass, Run Demo, regenerate DOCX and PDF, and open both outputs.
- Record the human Apple Silicon GUI result with the evidence template in [`docs/macos-arm-gui-gate.md`](macos-arm-gui-gate.md) before promoting an RC to final.

WeasyPrint native runtime:

- Linux installs the native Pango/PangoFT2 packages in the release runner and relies on the platform package dependencies at install time.
- macOS installs the Homebrew Pango/fontconfig/HarfBuzz/GLib stack, copies the dylib dependency closure into `desktop/src-tauri/binaries/weasyprint-runtime/`, rewrites Homebrew install names to local `@loader_path` references, and ad-hoc signs the copied dylibs.
- Windows uses `msys2/setup-msys2@v2` with `mingw-w64-x86_64-pango`, copies the required DLL closure into `desktop/src-tauri/binaries/weasyprint-runtime/`, and the frozen sidecar launcher points WeasyPrint at that directory before import.
- `pnpm release:sidecar-smoke` must produce valid MD, PDF, and DOCX reports from the built sidecar before release artifacts are uploaded.

Release dry run:

- Trigger `Release` with `workflow_dispatch` on `main` before publishing a tag. Enter the intended RC tag, such as `vX.Y.Z-rc.N`, or final tag, such as `vX.Y.Z`, in the required `candidate_tag` input.
- The build matrix runs and uploads installer artifacts. The publish job is skipped because the ref is not a pushed `v*` tag.
- The `dry-run-readiness` job downloads the merged artifacts and runs `pnpm release:dry-run -- --tag "$candidate_tag" --dir artifacts --out release-dry-run-proof.md --json-out release-dry-run-proof.json`.
- Download the `release-dry-run-proof` artifact and attach it to the release checklist before pushing the public tag.

Headless dry-run proof:

- Version fields match the candidate tag's base version.
- Installer asset names match the RC/final candidate tag's base version.
- RC candidates resolve to `prerelease=true` and `make_latest=false`.
- Final candidates resolve the same Latest-release policy that the tag-driven publish job will use.
- The proof confirms no Git tag is created and no GitHub release is published by the dry-run readiness job.

Remaining release-validation blockers:

| Area | Remaining blocker | Proof needed to clear |
|---|---|---|
| Linux packaging | Manual first launch has not been recorded for the AppImage execute-bit path or native `.deb` / `.rpm` installs. | Install or launch each Linux artifact from a release build, run the built-in demo, regenerate PDF and DOCX, and open both outputs. |
| macOS packaging | Hosted DMG smoke does not replace the final Apple Silicon GUI pass for the unsigned app. | Install the DMG on real Apple Silicon, use the Gatekeeper bypass, Run Demo, regenerate PDF and DOCX, and open both outputs. |
| Windows packaging | Automated sidecar smoke does not prove the unsigned SmartScreen path or GUI installer flow. | Install the setup exe or MSI on Windows 10/11, use **More info** then **Run anyway**, Run Demo, regenerate PDF and DOCX, and open both outputs. |
| Docs | Tutorial screenshot placeholders remain until final installer verification. | Capture the release page, first-run bypass dialogs, Run Demo, Results, DOCX export, and Planner Pack screens during the manual validation pass. |

Expected installer assets:

- Linux AppImage: `ClawModeler_<version>_amd64.AppImage`
- Debian / Ubuntu package: `ClawModeler_<version>_amd64.deb`
- Fedora / RHEL package: `ClawModeler-<version>-1.x86_64.rpm`
- macOS Apple Silicon dmg: `ClawModeler_<version>_aarch64.dmg`
- Windows MSI: `ClawModeler_<version>_x64_en-US.msi`
- Windows setup exe: `ClawModeler_<version>_x64-setup.exe`
- Intel Mac x86_64: no pre-built installer until a reliable Intel builder is available.

Unsigned first-run caveats:

- macOS builds are unsigned. Document the one-time Gatekeeper path: right-click `ClawModeler.app`, choose **Open**, then choose **Open** again.
- Windows builds are unsigned. Document the one-time SmartScreen path: **More info**, then **Run anyway**.
- Linux AppImage users may need to mark the file executable before first launch.

After publication:

- Verify the release page has the expected six assets: AppImage, deb, rpm, macOS ARM64 dmg, Windows MSI, and Windows setup exe.
- Verify `gh release list --limit 5` marks the newest SemVer release as Latest.
- Verify `https://github.com/nfredmond/clawmodeler/releases/latest` resolves to the newest SemVer tag.
- For free hosted Apple Silicon beyond CI, apply for MacStadium Open Source Program access and use it for the final manual macOS ARM GUI gate when approved.
