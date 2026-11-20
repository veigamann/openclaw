#!/bin/bash
# Build an UNSIGNED OpenClaw iOS .ipa targeting iOS 18 (iPhone XR / iOS 18.x).
# Run from the repository root on macOS with a full Xcode install.
#
#   SIDELOAD_BUNDLE_ID=com.seunome.openclaw bash build-unsigned-ipa.sh
#
# Output: build/OpenClaw-unsigned.ipa  -> drop it into SideStore/AltStore.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# If this script lives outside the repo, run it with the repo as CWD instead:
if [[ ! -d "$ROOT_DIR/apps/ios" ]]; then
  ROOT_DIR="$(pwd)"
fi
cd "$ROOT_DIR"
[[ -d apps/ios ]] || { echo "error: run inside the openclaw repo root" >&2; exit 1; }

APP_BUNDLE_ID="${SIDELOAD_BUNDLE_ID:-com.matheusveiga.openclaw}"
CONFIGURATION="${SIDELOAD_CONFIGURATION:-Release}"

echo "==> bundle id: $APP_BUNDLE_ID (change with SIDELOAD_BUNDLE_ID)"

# 1. Unique bundle IDs + unsigned build settings. apps/ios/Signing.xcconfig
#    #includes this file last, so these win.
cat > apps/ios/.local-signing.xcconfig <<EOF
OPENCLAW_CODE_SIGN_STYLE = Manual
OPENCLAW_CODE_SIGN_IDENTITY = "-"
OPENCLAW_DEVELOPMENT_TEAM =
OPENCLAW_APP_BUNDLE_ID = ${APP_BUNDLE_ID}
OPENCLAW_SHARE_BUNDLE_ID = ${APP_BUNDLE_ID}.share
OPENCLAW_APP_GROUP_ID = group.${APP_BUNDLE_ID}.shared
OPENCLAW_ACTIVITY_WIDGET_BUNDLE_ID = ${APP_BUNDLE_ID}.activitywidget
OPENCLAW_WATCH_APP_BUNDLE_ID = ${APP_BUNDLE_ID}.watchkitapp
OPENCLAW_APP_PROFILE =
OPENCLAW_SHARE_PROFILE =
OPENCLAW_ACTIVITY_WIDGET_PROFILE =
OPENCLAW_WATCH_APP_PROFILE =
EOF

# 2. Generated inputs the project needs (version xcconfig, swift file list,
#    mermaid bundle, test TLS identity used by the preGen hook).
bash scripts/ios-write-version-xcconfig.sh
node scripts/ios-write-swift-filelist.mjs

# 3. Lint tools are mandatory: project.yml runs swiftformat/swiftlint as
#    pre-build phases and fails if the pinned versions are missing.
if ! command -v swiftformat >/dev/null 2>&1 || ! command -v swiftlint >/dev/null 2>&1; then
  echo "==> installing pinned swiftformat/swiftlint into .build/swift-tools"
  ./scripts/install-swift-tools.sh "$ROOT_DIR/.build/swift-tools"
  export PATH="$ROOT_DIR/.build/swift-tools:$PATH"
fi

# 4. Generate the Xcode project (preGenCommand runs the mermaid + TLS scripts).
( cd apps/ios && xcodegen generate )

# 5. Unsigned release archive. No code signature, no entitlements: SideStore
#    signs on-device with your Apple ID and adds the entitlements it supports.
rm -rf build/OpenClaw.xcarchive
xcodebuild \
  -project apps/ios/OpenClaw.xcodeproj \
  -scheme OpenClaw \
  -configuration "$CONFIGURATION" \
  -destination 'generic/platform=iOS' \
  -archivePath "$ROOT_DIR/build/OpenClaw.xcarchive" \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGN_IDENTITY="" \
  archive

# 6. Package Payload/ into an .ipa
APP_PATH="$ROOT_DIR/build/OpenClaw.xcarchive/Products/Applications/OpenClaw.app"
[[ -d "$APP_PATH" ]] || { echo "error: archive has no OpenClaw.app" >&2; exit 1; }
if [[ -d "$APP_PATH/_CodeSignature" ]]; then
  echo "error: archive is signed; expected an unsigned build" >&2
  exit 1
fi

rm -rf build/Payload build/OpenClaw-unsigned.ipa
mkdir -p build/Payload
cp -R "$APP_PATH" build/Payload/
( cd build && /usr/bin/zip -qry OpenClaw-unsigned.ipa Payload )

ls -lh build/OpenClaw-unsigned.ipa
echo "==> done: $(pwd)/build/OpenClaw-unsigned.ipa"
