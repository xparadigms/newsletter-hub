#!/bin/sh
# Diff the app's text pipeline against the site's. Needs a samples file of
# newsletter rows (slug, section, title, series, issue_date, summary, blocks).
set -e
cd "$(dirname "$0")/.."
SDK=$(xcrun --sdk macosx --show-sdk-path)
xcrun swiftc -O -sdk "$SDK" -o /tmp/parity-swift Parity/main.swift \
  TheBrief/Model/*.swift TheBrief/Text/*.swift TheBrief/Story/StoryDeck.swift \
  TheBrief/App/Format.swift TheBrief/Data/SupabaseClient.swift
/tmp/parity-swift "$1"
