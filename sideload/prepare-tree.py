#!/usr/bin/env python3
"""Downgrade a checked-out openclaw tree to build for iOS 18 on the Xcode 26 SDK.

Goal: feature parity with `main` (same app, same behavior) while the deployment
target is iOS 18.0 and every iOS 26/27-only API is behind an availability check
with a working fallback.

Run from the repository root, after checkout and before `xcodegen generate`.
Idempotent: each step reports whether it applied or was already in place.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()
IOS = ROOT / "apps/ios"
PRO = IOS / "Sources/Design/OpenClawProComponents.swift"
BRAND = IOS / "Sources/Design/OpenClawBrand.swift"
CHAT = IOS / "Sources/Design/ChatProTab.swift"
PROJECT = IOS / "project.yml"
APP_GROUP = ROOT / "apps/shared/OpenClawKit/Sources/OpenClawKit/OpenClawAppGroup.swift"

applied: list[str] = []


def edit(path: Path, old: str, new: str, label: str) -> None:
    src = path.read_text()
    if new in src:
        print(f"[skip] {label}: already applied")
        return
    if src.count(old) != 1:
        raise SystemExit(f"[fail] {label}: expected 1 match in {path}, found {src.count(old)}")
    path.write_text(src.replace(old, new, 1))
    applied.append(label)
    print(f"[ok]   {label}")


def edit_regex(path: Path, pattern: str, new: str, label: str, marker: str) -> None:
    src = path.read_text()
    if marker in src:
        print(f"[skip] {label}: already applied")
        return
    out, n = re.subn(pattern, new, src, count=1, flags=re.S)
    if n != 1:
        raise SystemExit(f"[fail] {label}: pattern not found in {path}")
    path.write_text(out)
    applied.append(label)
    print(f"[ok]   {label}")


def remove_block(path: Path, pattern: str, marker: str, label: str) -> None:
    """Delete a declaration; `marker` is text that only exists while it is present."""
    src = path.read_text()
    if marker not in src:
        print(f"[skip] {label}: already applied")
        return
    out, n = re.subn(pattern, "", src, count=1, flags=re.S)
    if n != 1:
        raise SystemExit(f"[fail] {label}: pattern not found in {path}")
    path.write_text(out)
    applied.append(label)
    print(f"[ok]   {label}")



# --------------------------------------------------------------------------
# 1. project.yml: iOS 18 deployment target, no embedded Watch app
# --------------------------------------------------------------------------
def prepare_project() -> None:
    src = PROJECT.read_text()
    out = re.sub(r'(deploymentTarget:\n    iOS: )"26\.\d+"', r'\1"18.0"', src, count=1)
    out = out.replace("      - target: OpenClawWatchApp\n", "")
    out = re.sub(
        r"\n([ \t]*)dependencies:\n([ \t]*)(?=[A-Za-z])",
        lambda m: f"\n{m.group(1)}dependencies: []\n{m.group(2)}",
        out,
    )
    if out != src:
        PROJECT.write_text(out)
        applied.append("project.yml")
        print("[ok]   project.yml: iOS 18.0, no Watch target, deps normalised")
    else:
        print("[skip] project.yml: already prepared")


# --------------------------------------------------------------------------
# 2. iOS 27.1-only toolbar APIs do not exist in the Xcode 26 SDK.
#    Drop the branches; the `else` paths are the iOS 18 implementations.
# --------------------------------------------------------------------------
def strip_ios27_toolbar_api() -> None:
    remove_block(
        PRO,
        r"@available\(iOS 27\.1, \*\)\nprivate struct OpenClawVerticalToolbarGlyphScale: ViewModifier \{.*?\n\}\n\n",
        "struct OpenClawVerticalToolbarGlyphScale",
        "ProComponents: drop OpenClawVerticalToolbarGlyphScale",
    )
    remove_block(
        PRO,
        r"@available\(iOS 27\.1, \*\)\nprivate struct OpenClawToolbarHitTarget: ViewModifier \{.*?\n\}\n\n",
        "struct OpenClawToolbarHitTarget",
        "ProComponents: drop OpenClawToolbarHitTarget",
    )
    edit(
        PRO,
        """    @ViewBuilder
    func openClawToolbarGlyphScale() -> some View {
        if #available(iOS 27.1, *) {
            self.modifier(OpenClawVerticalToolbarGlyphScale())
        } else {
            self
        }
    }
""",
        """    func openClawToolbarGlyphScale() -> some View {
        self
    }
""",
        "ProComponents: openClawToolbarGlyphScale -> self",
    )
    edit(
        PRO,
        """    @ViewBuilder
    func openClawToolbarHitTarget(preservesIntrinsicWidth: Bool = false) -> some View {
        if #available(iOS 27.1, *) {
            self.modifier(OpenClawToolbarHitTarget(preservesIntrinsicWidth: preservesIntrinsicWidth))
        } else if preservesIntrinsicWidth {
            self.frame(minHeight: 44)
        } else {
            self.frame(width: 44, height: 44)
        }
    }
""",
        """    @ViewBuilder
    func openClawToolbarHitTarget(preservesIntrinsicWidth: Bool = false) -> some View {
        if preservesIntrinsicWidth {
            self.frame(minHeight: 44)
        } else {
            self.frame(width: 44, height: 44)
        }
    }
""",
        "ProComponents: openClawToolbarHitTarget -> 44pt frame",
    )
    edit(
        PRO,
        """    @ToolbarContentBuilder
    var body: some ToolbarContent {
        if #available(iOS 27.1, *) {
            self.item.axisBehavior(.verticalPreferred).visibilityPriority(.high)
        } else {
            self.item
        }
    }
""",
        """    @ToolbarContentBuilder
    var body: some ToolbarContent {
        self.item
    }
""",
        "ProComponents: sidebar toolbar item without axis behavior",
    )
    edit(
        CHAT,
        """                .toolbar {
                    if #available(iOS 27.1, *) {
                        // Custom controls must explicitly support the system's side bar.
                        self.chatToolbar.axisBehavior(.verticalPreferred)
                    } else {
                        self.chatToolbar
                    }
                }
""",
        """                .toolbar {
                    self.chatToolbar
                }
""",
        "ChatProTab: chat toolbar without axis behavior",
    )
    remove_block(
        CHAT,
        r"@available\(iOS 27\.1, \*\)\nprivate struct ChatToolbarStatusPopover<Status: View>: ViewModifier \{.*?\n\}\n",
        "struct ChatToolbarStatusPopover",
        "ChatProTab: drop ChatToolbarStatusPopover",
    )
    edit(
        CHAT,
        """    @ViewBuilder
    private var headerAgentIdentity: some View {
        if #available(iOS 27.1, *) {
            self.headerAgentIdentityButton.modifier(ChatToolbarStatusPopover(
                isExpanded: self.$isGatewayStatusManuallyExpanded,
                status: self.expandedGatewayStatusLabel))
        } else {
            self.headerAgentIdentityButton
        }
    }
""",
        """    private var headerAgentIdentity: some View {
        self.headerAgentIdentityButton
    }
""",
        "ChatProTab: header identity without status popover",
    )


# --------------------------------------------------------------------------
# 3. iOS 26-only visual APIs: keep them, add the pre-26 fallbacks back.
# --------------------------------------------------------------------------
def restore_ios26_fallbacks() -> None:
    edit(
        PRO,
        """    @ViewBuilder
    func openClawGlassButton(prominent: Bool = false, tint: Color? = nil) -> some View {
        if prominent {
            self
                .font(OpenClawType.subheadSemiBold)
                .buttonStyle(.glassProminent)
                .tint(tint ?? OpenClawBrand.accentFill)
        } else {
            self
                .font(OpenClawType.subheadSemiBold)
                .buttonStyle(.glass)
                .tint(tint)
        }
    }

    func openClawGlassSurface() -> some View {
        self.glassEffect(.regular, in: .rect(cornerRadius: OpenClawProMetric.controlRadius))
    }
""",
        """    @ViewBuilder
    func openClawGlassButton(prominent: Bool = false, tint: Color? = nil) -> some View {
        if #available(iOS 26.0, *) {
            if prominent {
                self
                    .font(OpenClawType.subheadSemiBold)
                    .buttonStyle(.glassProminent)
                    .tint(tint ?? OpenClawBrand.accentFill)
            } else {
                self
                    .font(OpenClawType.subheadSemiBold)
                    .buttonStyle(.glass)
                    .tint(tint)
            }
        } else if prominent {
            self
                .font(OpenClawType.subheadSemiBold)
                .buttonStyle(.borderedProminent)
                .tint(tint ?? OpenClawBrand.accentFill)
        } else {
            self
                .font(OpenClawType.subheadSemiBold)
                .buttonStyle(.bordered)
                .tint(tint)
        }
    }

    @ViewBuilder
    func openClawGlassSurface() -> some View {
        if #available(iOS 26.0, *) {
            self.glassEffect(.regular, in: .rect(cornerRadius: OpenClawProMetric.controlRadius))
        } else {
            self.background(
                .regularMaterial,
                in: RoundedRectangle(cornerRadius: OpenClawProMetric.controlRadius, style: .continuous))
        }
    }
""",
        "ProComponents: glass button/surface fallbacks",
    )
    edit(
        PRO,
        """    private var item: some ToolbarContent {
        ToolbarItem(placement: self.placement) {
            OpenClawSidebarControlButton(action: self.action)
        }
        // Sidebar reveal is intentionally background-free in every host;
        // suppress the toolbar's automatic glass so it cannot reappear.
        .sharedBackgroundVisibility(.hidden)
    }
""",
        """    @ToolbarContentBuilder
    private var item: some ToolbarContent {
        if #available(iOS 26.0, *) {
            ToolbarItem(placement: self.placement) {
                OpenClawSidebarControlButton(action: self.action)
            }
            // Sidebar reveal is intentionally background-free in every host;
            // suppress the toolbar's automatic glass so it cannot reappear.
            .sharedBackgroundVisibility(.hidden)
        } else {
            ToolbarItem(placement: self.placement) {
                OpenClawSidebarControlButton(action: self.action)
            }
        }
    }
""",
        "ProComponents: sidebar toolbar item glass guard",
    )
    edit(
        PRO,
        """    var body: some View {
        GlassEffectContainer(spacing: 8) {
            self.content
        }
    }
""",
        """    var body: some View {
        if #available(iOS 26.0, *) {
            GlassEffectContainer(spacing: 8) {
                self.content
            }
        } else {
            self.content
        }
    }
""",
        "ProComponents: glass container fallback",
    )
    edit(
        CHAT,
        """        ToolbarItem(placement: .topBarLeading) {
            self.headerAgentIdentity
        }
        .sharedBackgroundVisibility(.hidden)
        ToolbarItem(placement: .topBarTrailing) {
            self.chatActionsMenu
        }
        .sharedBackgroundVisibility(.hidden)
""",
        """        if #available(iOS 26.0, *) {
            ToolbarItem(placement: .topBarLeading) {
                self.headerAgentIdentity
            }
            .sharedBackgroundVisibility(.hidden)
        } else {
            ToolbarItem(placement: .topBarLeading) {
                self.headerAgentIdentity
            }
        }
        if #available(iOS 26.0, *) {
            ToolbarItem(placement: .topBarTrailing) {
                self.chatActionsMenu
            }
            .sharedBackgroundVisibility(.hidden)
        } else {
            ToolbarItem(placement: .topBarTrailing) {
                self.chatActionsMenu
            }
        }
""",
        "ChatProTab: toolbar glass guards",
    )
    edit(
        CHAT,
        """import OpenClawProtocol
import SwiftUI

struct ChatProTab: View {
""",
        """import OpenClawProtocol
import SwiftUI

private struct ChatScrollEdgeTreatment: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 26.0, *) {
            // The shared canvas supplies color for the native blur. Automatic
            // edge effects harden to black when the host inserts an opaque fill.
            content.scrollEdgeEffectStyle(.soft, for: .vertical)
        } else {
            content
        }
    }
}

struct ChatProTab: View {
""",
        "ChatProTab: scroll edge treatment fallback",
    )
    edit(
        CHAT,
        """                // The shared canvas supplies color for the native blur. Automatic
                // edge effects harden to black when the host inserts an opaque fill.
                .scrollEdgeEffectStyle(.soft, for: .vertical)
""",
        """                .modifier(ChatScrollEdgeTreatment())
""",
        "ChatProTab: use scroll edge modifier",
    )
    edit(
        BRAND,
        """    private var glass: Glass {""",
        """    @available(iOS 26.0, *)
    private var glass: Glass {""",
        "Brand: gate Glass type to iOS 26",
    )
    edit(
        BRAND,
        """    func body(content: Content) -> some View {
        content.glassEffect(self.glass, in: .capsule)
    }
""",
        """    func body(content: Content) -> some View {
        if #available(iOS 26.0, *) {
            content.glassEffect(self.glass, in: .capsule)
        } else {
            content
                .background(Capsule(style: .continuous).fill(self.fallbackFill))
                .overlay {
                    if !self.isFilled {
                        Capsule(style: .continuous)
                            .strokeBorder(Color(uiColor: .separator), lineWidth: 0.75)
                    }
                }
                .opacity(self.isPressed && self.isEnabled ? 0.82 : 1)
                .animation(.smooth(duration: 0.14), value: self.isPressed)
        }
    }
""",
        "Brand: capsule fallback",
    )
    edit(
        BRAND,
        """private struct OpenClawButtonSurfaceModifier: ViewModifier {
    let kind: OpenClawButtonSurfaceKind
    let isEnabled: Bool
""",
        """private struct OpenClawButtonSurfaceModifier: ViewModifier {
    let kind: OpenClawButtonSurfaceKind
    let isEnabled: Bool
    let isPressed: Bool
""",
        "Brand: isPressed state",
    )
    edit(
        BRAND,
        """    @available(iOS 26.0, *)
    private var glass: Glass {
        self.isFilled ? .regular.tint(OpenClawBrand.accentFill).interactive() : .regular.interactive(self.isEnabled)
    }
""",
        """    @available(iOS 26.0, *)
    private var glass: Glass {
        self.isFilled ? .regular.tint(OpenClawBrand.accentFill).interactive() : .regular.interactive(self.isEnabled)
    }

    private var fallbackFill: Color {
        self.isFilled ? OpenClawBrand.accentFill : OpenClawBrand.activationNeutralSurface
    }
""",
        "Brand: fallback fill",
    )
    edit(
        BRAND,
        """    func openClawButtonSurface(
        _ kind: OpenClawButtonSurfaceKind,
        isEnabled: Bool) -> some View
    {
        self.modifier(OpenClawButtonSurfaceModifier(kind: kind, isEnabled: isEnabled))
    }
""",
        """    func openClawButtonSurface(
        _ kind: OpenClawButtonSurfaceKind,
        isEnabled: Bool,
        isPressed: Bool) -> some View
    {
        self.modifier(OpenClawButtonSurfaceModifier(kind: kind, isEnabled: isEnabled, isPressed: isPressed))
    }
""",
        "Brand: surface modifier plumbing",
    )
    src = BRAND.read_text()
    for kind in ("prominent", "secondary"):
        src = src.replace(
            f".openClawButtonSurface(.{kind}, isEnabled: self.isEnabled)\n",
            f".openClawButtonSurface(.{kind}, isEnabled: self.isEnabled, isPressed: configuration.isPressed)\n",
        )
    BRAND.write_text(src)
    print("[ok]   Brand: button style call sites" if "configuration.isPressed)" in src else "[warn] Brand: call sites")


# --------------------------------------------------------------------------
# 4. App Group suite when the build has no App Groups entitlement
# --------------------------------------------------------------------------
def patch_app_group() -> None:
    src = APP_GROUP.read_text()
    if "containerURL(forSecurityApplicationGroupIdentifier: candidate)" in src:
        print("[skip] AppGroup: already patched")
        return
    old = """    public static var identifier: String {
        let raw = Bundle.main.object(forInfoDictionaryKey: "OpenClawAppGroupIdentifier") as? String
        return raw?.trimmedNonEmpty ?? self.canonicalIdentifier
    }
"""
    new = """    public static var identifier: String {
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
"""
    if old not in src:
        raise SystemExit("[fail] AppGroup: identifier body not found")
    APP_GROUP.write_text(src.replace(old, new, 1))
    applied.append("AppGroup")
    print("[ok]   AppGroup: bundle-id fallback")


def main() -> int:
    if not PROJECT.is_file():
        print("not at the repository root", file=sys.stderr)
        return 1
    prepare_project()
    strip_ios27_toolbar_api()
    restore_ios26_fallbacks()
    patch_app_group()
    print(f"\n{len(applied)} change(s) applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
