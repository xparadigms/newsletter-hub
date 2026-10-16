#!/bin/sh
# Archive The Brief and upload it to App Store Connect, where it lands in
# TestFlight once Apple finishes processing it (usually 10–30 minutes).
#
#   ios/scripts/testflight.sh            # team read from Xcode's signed-in account
#   TEAM_ID=ABCDE12345 ios/scripts/testflight.sh
#
# Needs an app record in App Store Connect for com.heechangkang.thebrief, and
# either Xcode signed in to the developer account (Settings > Accounts) or an
# App Store Connect API key:
#
#   ASC_KEY_PATH=~/Downloads/AuthKey_XXXXXXXXXX.p8 ASC_KEY_ID=XXXXXXXXXX \
#   ASC_ISSUER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx TEAM_ID=N7DWY66V6B \
#     ios/scripts/testflight.sh
#
# The archive is built unsigned and signed for distribution at export: an
# archive signed for development needs a registered device, and the upload
# needs none. -allowProvisioningUpdates lets Xcode create the distribution
# certificate and profile on the first run.
set -eu
cd "$(dirname "$0")/.."

AUTH=""
if [ -n "${ASC_KEY_PATH:-}" ]; then
  AUTH="-authenticationKeyPath $ASC_KEY_PATH -authenticationKeyID $ASC_KEY_ID -authenticationKeyIssuerID $ASC_ISSUER_ID"
fi

if [ -z "${TEAM_ID:-}" ]; then
  TEAM_ID=$(defaults read com.apple.dt.Xcode IDEProvisioningTeamByIdentifier 2>/dev/null \
    | sed -n 's/.*teamID = \([A-Z0-9]\{10\}\);.*/\1/p' | head -1)
fi
if [ -z "$TEAM_ID" ]; then
  echo "No team found. Sign in under Xcode > Settings > Accounts, or set TEAM_ID." >&2
  exit 1
fi

# The database's read key is not in the source (the repository is public);
# it goes into the build here. See TheBrief/Data/SupabaseClient.swift.
if [ -z "${SUPABASE_PUBLISHABLE_KEY:-}" ]; then
  echo "Set SUPABASE_PUBLISHABLE_KEY (Supabase > Project Settings > API Keys)." >&2
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
  -allowProvisioningUpdates $AUTH \
  DEVELOPMENT_TEAM="$TEAM_ID" CURRENT_PROJECT_VERSION="$BUILD" \
  CODE_SIGNING_ALLOWED=NO SUPABASE_PUBLISHABLE_KEY="$SUPABASE_PUBLISHABLE_KEY" \
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
  -allowProvisioningUpdates $AUTH

echo "Uploaded build $BUILD. It appears in App Store Connect > TestFlight after processing."
