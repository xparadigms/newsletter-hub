# The Brief for iOS

A native SwiftUI app for the newsletters on the website. It has no web views:
lists, articles, furigana and pinyin, the language filter, search, story mode
and read-aloud are all drawn natively.

## How it gets content

The app reads the same Supabase `newsletter` table the website reads, with the
same publishable key (`TheBrief/Data/SupabaseClient.swift`). That key is meant
to ship in clients: row-level security limits it to reading published issues.
The site's password gate does not apply to the app, and the app cannot press
Generate, which needs that password.

Lists and every opened issue are cached on the device, so the app opens to the
last thing it saw and opened issues read offline.

## How it matches the site

`TheBrief/Text/Annotate.swift` and `TheBrief/Story/StoryDeck.swift` are line-by-line
ports of `web/lib/text.ts` and `web/lib/story.ts`. Change one and you must change the
other. To check they still agree, dump the same issues through both and diff:

```sh
# a samples file of newsletter rows: slug, section, title, series, issue_date, summary, blocks
(cd web && npx tsx scripts/parity-dump.ts /tmp/samples.json > /tmp/ts.txt)
ios/Parity/run.sh /tmp/samples.json > /tmp/swift.txt   # on a Mac
diff /tmp/ts.txt /tmp/swift.txt
```

They produced identical output on 210 issues across all eight sections when
the port was written.

## Building

The Xcode project is generated. After adding or removing a Swift file:

```sh
python3 ios/generate_project.py
```

Open `ios/TheBrief.xcodeproj` and run the `TheBrief` scheme. iOS 17 or later.

## TestFlight

The app record is "The Brief by Heechang" (bundle ID `com.heechangkang.thebrief`,
team `N7DWY66V6B`). Builds are signed and uploaded with an App Store Connect API
key, so Xcode needs no signed-in account:

```sh
ASC_KEY_PATH=~/Downloads/AuthKey_42Z98QR7J4.p8 ASC_KEY_ID=42Z98QR7J4 \
ASC_ISSUER_ID=4b0444d7-b87e-4112-8b16-653ff28b5bb9 TEAM_ID=N7DWY66V6B \
  ios/scripts/testflight.sh
```

It archives unsigned, signs for App Store distribution at export (an archive
signed for development would need a registered iPhone), stamps a build number
from the time, and uploads. The TestFlight group "Internal" has access to every
build, so each upload reaches its testers once Apple finishes processing it —
usually a few minutes. Internal testers must be users on the App Store Connect
team; anyone else needs an external group and Beta App Review.
