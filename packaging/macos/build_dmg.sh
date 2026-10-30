#!/usr/bin/env bash
# Puppetcam.app (from pyinstaller) -> dist/Puppetcam-<version>-macos-arm64.dmg
#
# Optional environment, for a build that opens without Gatekeeper warnings:
#   MACOS_SIGN_IDENTITY   "Developer ID Application: Name (TEAMID)", in the keychain, also
#                         set when running pyinstaller
#   APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD   notarization (app-specific password)
# Without them the app is only ad-hoc signed: see "Installing" in the README.
set -euo pipefail
cd "$(dirname "$0")/../.."

VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/puppetcam/__init__.py)
APP=dist/Puppetcam.app
DMG="dist/Puppetcam-${VERSION}-macos-$(uname -m).dmg"

# pyinstaller already signed the app when MACOS_SIGN_IDENTITY was set (see puppetcam.spec).
if [[ -n "${MACOS_SIGN_IDENTITY:-}" ]]; then
  codesign --verify --deep --strict --verbose=2 "$APP"
fi

STAGE=$(mktemp -d)
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -volname "Puppetcam" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

if [[ -n "${MACOS_SIGN_IDENTITY:-}" ]]; then
  codesign --force --timestamp --sign "$MACOS_SIGN_IDENTITY" "$DMG"
fi
if [[ -n "${APPLE_ID:-}" && -n "${APPLE_TEAM_ID:-}" && -n "${APPLE_APP_PASSWORD:-}" ]]; then
  xcrun notarytool submit "$DMG" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
    --password "$APPLE_APP_PASSWORD" --wait
  xcrun stapler staple "$DMG"
fi
echo "$DMG"
