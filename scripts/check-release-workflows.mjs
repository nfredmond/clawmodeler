#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const workflowChecks = [
  {
    path: ".github/workflows/ci.yml",
    required: [
      "actions/checkout@v6",
      "actions/setup-python@v6",
      "actions/setup-node@v6",
      "corepack prepare pnpm@10 --activate",
      "pnpm release:first-user-smoke",
    ],
  },
  {
    path: ".github/workflows/release.yml",
    required: [
      "actions/checkout@v6",
      "actions/setup-python@v6",
      "actions/setup-node@v6",
      "libpangoft2-1.0-0",
      "brew install pango fontconfig harfbuzz glib",
      "msys2/setup-msys2@v2",
      "mingw-w64-x86_64-pango",
      "corepack prepare pnpm@10 --activate",
      "pnpm release:sidecar-smoke",
      "pnpm release:first-user-smoke -- --binary",
      "actions/upload-artifact@v6",
      "actions/download-artifact@v7",
      "softprops/action-gh-release@v3",
      "pnpm release:assets -- --tag",
      "release-${{ github.repository }}",
    ],
  },
  {
    path: ".github/workflows/macos-arm-dmg-smoke.yml",
    required: [
      "runs-on: macos-14",
      "actions/checkout@v6",
      "actions/setup-node@v6",
      "corepack prepare pnpm@10 --activate",
      "gh release download",
      "ClawModeler_*_aarch64.dmg",
      "pnpm release:macos-dmg-smoke",
    ],
  },
];

const forbidden = [
  "actions/checkout@v4",
  "actions/setup-node@v4",
  "actions/setup-python@v5",
  "pnpm/action-setup@",
  "actions/upload-artifact@v4",
  "actions/upload-artifact@v5",
  "actions/download-artifact@v4",
  "actions/download-artifact@v5",
  "actions/download-artifact@v6",
  "softprops/action-gh-release@v2",
];

const docChecks = [
  {
    path: "docs/release.md",
    required: [
      "pnpm release:first-user-smoke",
      "pnpm release:macos-dmg-smoke",
      "Expected installer assets:",
      "Hosted macOS ARM DMG smoke:",
      "Unsigned first-run caveats:",
      "Intel Mac x86_64: no pre-built installer",
      "Linux AppImage users may need to mark the file executable",
      "WeasyPrint native runtime:",
    ],
  },
  {
    path: "scripts/README.md",
    required: [
      "pnpm release:first-user-smoke",
      "pnpm release:first-user-smoke -- --binary",
      "pnpm release:macos-dmg-smoke",
      "PDF and DOCX",
    ],
  },
];

function readRepoFile(relativePath) {
  return fs.readFileSync(path.join(repoRoot, relativePath), "utf8");
}

function assertIncludes(content, needle, filePath) {
  if (!content.includes(needle)) {
    throw new Error(`${filePath} is missing required release workflow text: ${needle}`);
  }
}

function assertExcludes(content, needle, filePath) {
  if (content.includes(needle)) {
    throw new Error(`${filePath} still contains deprecated release workflow text: ${needle}`);
  }
}

function checkFile({ path: filePath, required }) {
  const content = readRepoFile(filePath);
  for (const needle of required) {
    assertIncludes(content, needle, filePath);
  }
  return content;
}

function main() {
  const workflowContents = workflowChecks.map(checkFile);
  for (const [index, content] of workflowContents.entries()) {
    const filePath = workflowChecks[index].path;
    for (const needle of forbidden) {
      assertExcludes(content, needle, filePath);
    }
  }
  for (const check of docChecks) {
    checkFile(check);
  }
  console.log("release workflow self-test passed");
}

main();
