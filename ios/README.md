# The Brief for iOS

A native SwiftUI app for the newsletters on the website. It has no web views:
lists, articles, furigana and pinyin, the language filter, search, story mode
and read-aloud are all drawn natively.

## How it gets content

The app reads the same Supabase `newsletter` table the website reads, with the
same publishable key. Row-level security limits that key to reading published
issues, but the issues sit behind the site's password and this repository is
public, so the key is not in the source: it is passed in at build time as the
`SUPABASE_PUBLISHABLE_KEY` build setting — a GitHub secret in CI, an argument to
`xcodebuild` or `ios/scripts/testflight.sh` locally — and read back from
Info.plist (`TheBrief/Data/SupabaseClient.swift`). To run from Xcode, add it
under the target's Build Settings (User-Defined) without committing it.
Reading needs no password. Generate and "Write about a company" do: they go
through the site's `/api/generate`, so the app asks for the site password once,
keeps it in the Keychain, and signs in with it whenever the site's cookie is
missing (`TheBrief/Data/GenerateClient.swift`). The site's daily cap applies.

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
team `N7DWY66V6B`), uploaded with an App Store Connect API key.

**From GitHub, no Mac needed.** `.github/workflows/ios.yml` builds the app on
GitHub's Macs on every push that touches `ios/`, and on `main` it also uploads
the build to TestFlight. It needs two repository secrets: `SUPABASE_PUBLISHABLE_KEY`
and `ASC_KEY_P8`, the contents of `AuthKey_42Z98QR7J4.p8`. To ship by hand, run the workflow from the
Actions tab.

**From a Mac:**

```sh
ASC_KEY_PATH=~/Downloads/AuthKey_42Z98QR7J4.p8 ASC_KEY_ID=42Z98QR7J4 \
ASC_ISSUER_ID=4b0444d7-b87e-4112-8b16-653ff28b5bb9 TEAM_ID=N7DWY66V6B \
  ios/scripts/testflight.sh
```

Either way it archives unsigned, signs for App Store distribution at export (an
archive signed for development would need a registered iPhone), stamps a build
number from the time, and uploads. The TestFlight group "Internal" has access
to every build, so each upload reaches its testers once Apple finishes
processing it — usually a few minutes. Internal testers must be users on the
App Store Connect team; anyone else needs an external group and Beta App Review.
