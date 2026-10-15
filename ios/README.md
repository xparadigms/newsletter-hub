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

One-time setup:

1. Xcode > Settings > Accounts: sign in with the Apple ID on the developer account.
2. [App Store Connect](https://appstoreconnect.apple.com/apps) > Apps > + > New App:
   platform iOS, bundle ID `com.heechangkang.thebrief` (it appears in the list once
   the first archive has registered it, or register it under Certificates,
   Identifiers & Profiles), any free name, SKU `thebrief`.

Then, for every build:

```sh
ios/scripts/testflight.sh
```

It archives with automatic signing, stamps a build number from the time, and
uploads. The build shows under TestFlight after Apple processes it, and
internal testers (you) can install it from the TestFlight app.
