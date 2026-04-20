# Release Checklist

ClawModeler releases are tag-driven. Pushing a `vX.Y.Z` tag builds Linux, macOS ARM64, and Windows desktop bundles, then publishes a GitHub release when every matrix build succeeds.

Before tagging:

- Confirm all version fields match the intended tag with `pnpm release:version-check`: root `package.json`, Python package metadata, `ENGINE_VERSION`, Tauri `Cargo.toml`, `Cargo.lock`, and `tauri.conf.json`.
- Run the core checks: `python3 -m ruff check .`, `pnpm engine:test`, `pnpm engine:check`, `pnpm ui:typecheck`, `pnpm ui:test`, `pnpm ui:build`, `pnpm desktop:acceptance`, and `cargo test` in `desktop/src-tauri`.
- Build the sidecar with `pnpm sidecar:build`, then run `pnpm release:sidecar-smoke`.
- Commit the version and changelog changes, push `main`, then push the matching `vX.Y.Z` tag.

Release workflow gates:

- Release workflows are serialized with GitHub Actions concurrency so multiple pushed tags cannot publish out of order.
- Each matrix build smoke-tests the generated sidecar before uploading installer artifacts.
- The release job validates asset names with `pnpm release:assets -- --tag "$GITHUB_REF_NAME" --dir artifacts`.
- The release job marks the GitHub release as Latest only when the tag is the highest SemVer `vX.Y.Z` tag.

After publication:

- Verify the release page has the expected six assets: AppImage, deb, rpm, macOS ARM64 dmg, Windows MSI, and Windows setup exe.
- Verify `gh release list --limit 5` marks the newest SemVer release as Latest.
- Verify `https://github.com/nfredmond/clawmodeler/releases/latest` resolves to the newest SemVer tag.
