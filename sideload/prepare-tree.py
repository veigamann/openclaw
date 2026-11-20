#!/usr/bin/env python3
"""Prepare a checked-out openclaw tree for an iOS 18, unentitled sideload build.

Idempotent: safe to run on `main` (already patched) or on the pinned pre-26.2
commit. Run from the repository root, after checkout and before xcodegen.

  1. Drop the embedded Watch app dependency so no Rust/watchOS toolchain is
     needed for an iPhone-only build.
  2. Normalise empty `dependencies:` keys, which xcodegen rejects.
  3. Make OpenClawAppGroup fall back to the bundle-id suite when the App Group
     container is unavailable (no App Groups entitlement on free Apple IDs).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()


def drop_watch_dependency() -> None:
    path = ROOT / "apps/ios/project.yml"
    src = path.read_text()
    out = src.replace("      - target: OpenClawWatchApp\n", "")
    if out != src:
        path.write_text(out)
        print("project.yml: removed embedded Watch app dependency")
    else:
        print("project.yml: Watch dependency already absent")


def normalise_empty_dependencies() -> None:
    path = ROOT / "apps/ios/project.yml"
    src = path.read_text()
    out = re.sub(
        r"\n([ \t]*)dependencies:\n([ \t]*)(?=[A-Za-z])",
        lambda m: f"\n{m.group(1)}dependencies: []\n{m.group(2)}",
        src,
    )
    if out != src:
        path.write_text(out)
        print("project.yml: normalised empty dependency lists")
    else:
        print("project.yml: no empty dependency lists")


APP_GROUP_OLD = '''    public static var identifier: String {
        let raw = Bundle.main.object(forInfoDictionaryKey: "OpenClawAppGroupIdentifier") as? String
        return raw?.trimmedNonEmpty ?? self.canonicalIdentifier
    }
'''

APP_GROUP_NEW = '''    public static var identifier: String {
        let raw = Bundle.main.object(forInfoDictionaryKey: "OpenClawAppGroupIdentifier") as? String
        let candidate = raw?.trimmedNonEmpty ?? self.canonicalIdentifier
        // Unentitled builds (a sideloaded IPA signed without the App Groups
        // capability) must not select the shared suite: UserDefaults(suiteName:)
        // still returns an object, but writes to an unowned group are dropped.
        guard
            FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: candidate) != nil
        else {
            return Bundle.main.bundleIdentifier ?? candidate
        }
        return candidate
    }
'''


def patch_app_group_fallback() -> None:
    path = ROOT / "apps/shared/OpenClawKit/Sources/OpenClawKit/OpenClawAppGroup.swift"
    src = path.read_text()
    if "containerURL(forSecurityApplicationGroupIdentifier: candidate)" in src:
        print("OpenClawAppGroup: already patched")
        return
    if APP_GROUP_OLD not in src:
        raise SystemExit("OpenClawAppGroup: identifier body not found; refusing to guess")
    path.write_text(src.replace(APP_GROUP_OLD, APP_GROUP_NEW, 1))
    print("OpenClawAppGroup: added bundle-id fallback")


def main() -> int:
    if not (ROOT / "apps/ios/project.yml").is_file():
        print("not at the repository root", file=sys.stderr)
        return 1
    drop_watch_dependency()
    normalise_empty_dependencies()
    patch_app_group_fallback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
