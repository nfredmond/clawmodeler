# macOS ARM GUI Gate

The hosted CI gate covers the published Apple Silicon DMG as far as GitHub's free macOS runner can support without a human desktop session:

- Download the release DMG from GitHub.
- Mount the DMG and copy `ClawModeler.app`.
- Verify bundle metadata.
- Run the bundled sidecar through the full release sidecar smoke, including PDF and DOCX export.
- Launch `ClawModeler.app` once after clearing quarantine.

Run it from GitHub Actions with the `macOS ARM DMG Smoke` workflow, or locally on an Apple Silicon Mac:

```bash
pnpm release:macos-dmg-smoke -- --tag v1.0.0-rc.3 --dmg path/to/ClawModeler_1.0.0_aarch64.dmg
```

The final release still needs a manual Apple Silicon desktop pass:

- Install the DMG.
- Use the unsigned first-launch bypass.
- Run Demo.
- Regenerate PDF.
- Regenerate DOCX.
- Open both outputs.

## Free Hosted Apple Silicon Options

Use GitHub Actions immediately for the CI smoke. It is free for public repositories and runs on hosted Apple Silicon through `macos-14`.

Apply for MacStadium Open Source Program access for a true hosted Apple Silicon Mac that can run the manual GUI gate. Suggested request text:

> ClawModeler is an Apache-2.0 local-first transportation sketch-planning desktop app for small and rural public agencies. We publish unsigned macOS Apple Silicon DMG release candidates and need periodic manual first-user validation on real Apple Silicon: install the DMG, pass the unsigned first-run prompt, run the built-in demo, regenerate PDF and DOCX reports, and open both outputs. GitHub Actions covers automated sidecar and DMG smoke tests, but it cannot replace the final manual desktop verification. We are requesting temporary or recurring Apple Silicon Mac access for release-candidate validation before final `v1.0.0` and later desktop releases.

Include these project details in the application:

- Repository: `https://github.com/nfredmond/clawmodeler`
- License: Apache-2.0
- Current release candidate: `v1.0.0-rc.3`
- Required hardware: Apple Silicon Mac with GUI access
- Expected use: release-candidate installer validation, not general development
