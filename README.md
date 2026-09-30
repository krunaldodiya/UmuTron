# Steam Library Metadata Manager

An Ubuntu desktop app in development for organizing non-Steam game metadata and manually syncing supported shortcut fields and artwork to Steam.

**Status: initial implementation, not yet a usable application.** The first commit contains the product/design specification and tested local game identity model. No Steam library writes are implemented yet.

## Planned experience

- Search by game name or Steam store ID and select a metadata match.
- Browse cover cards and edit game details, executable paths, arguments and artwork.
- Light, Dark and Follow System appearance.
- Save locally, or Save & Sync after reviewing and confirming Steam changes.
- Export/import a ZIP backup of metadata and artwork; relink moved game files.

This app does not launch games, install games, choose Proton, or modify game files. Full descriptions and release information remain visible here; Steam receives only fields its non-Steam shortcuts support.

See [product and UI design](docs/DESIGN.md) and [implementation milestones](docs/ROADMAP.md).

## Development

Python 3.12 or later. The initial domain model uses only the standard library.

```sh
python3 -m unittest discover -s tests -v
```

The planned desktop interface uses GTK 4 with libadwaita. No desktop package is available yet.
