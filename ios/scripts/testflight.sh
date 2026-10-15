#!/bin/sh
# Archive The Brief and upload it to App Store Connect, where it lands in
# TestFlight once Apple finishes processing it (usually 10–30 minutes).
#
#   ios/scripts/testflight.sh            # team read from Xcode's signed-in account
#   TEAM_ID=ABCDE12345 ios/scripts/testflight.sh
#
# Needs: Xcode signed in to your Apple Developer account (Settings > Accounts),
# and an app record in App Store Connect for com.heechangkang.thebrief.
# Signing is automatic: -allowProvisioningUpdates lets Xcode create the App ID,
# certificate and profile on the first run.
set -eu
cd "$(dirname "$0")/.."

if [ -z "${TEAM_ID:-}" ]; then
  TEAM_ID=$(defaults read com.apple.dt.Xcode IDEProvisioningTeamByIdentifier 2>/dev/null \
    | sed -n 's/.*teamID = \([A-Z0-9]\{10\}\);.*/\1/p' | head -1)
fi
if [ -z "$TEAM_ID" ]; then
  echo "No team found. Sign in under Xcode > Settings > Accounts, or set TEAM_ID." >&2
  exit 1
fi

# Every upload needs a build number higher than the last; the time is one.
BUILD=${BUILD:-$(date -u +%Y%m%d%H%M)}
ARCHIVE=build/TheBrief.xcarchive
echo "Team $TEAM_ID, build $BUILD"

python3 generate_project.py >/dev/null
rm -rf "$ARCHIVE" build/export
mkdir -p build

xcodebuild -project TheBrief.xcodeproj -scheme TheBrief -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" \
  -allowProvisioningUpdates \
  DEVELOPMENT_TEAM="$TEAM_ID" CURRENT_PROJECT_VERSION="$BUILD" \
  archive > build/archive.log 2>&1 || {
    grep -E "error:|warning: .*signing" build/archive.log | head -20 >&2
    echo "Archive failed; full log in ios/build/archive.log" >&2
    exit 1
  }

cat > build/ExportOptions.plist <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>method</key><string>app-store-connect</string>
  <key>destination</key><string>upload</string>
  <key>teamID</key><string>$TEAM_ID</string>
  <key>signingStyle</key><string>automatic</string>
  <key>uploadSymbols</key><true/>
  <key>manageAppVersionAndBuildNumber</key><false/>
</dict>
</plist>
PLIST

xcodebuild -exportArchive -archivePath "$ARCHIVE" \
  -exportOptionsPlist build/ExportOptions.plist -exportPath build/export \
  -allowProvisioningUpdates

echo "Uploaded build $BUILD. It appears in App Store Connect > TestFlight after processing."
