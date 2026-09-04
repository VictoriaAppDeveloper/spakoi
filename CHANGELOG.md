# Changelog

All notable changes to Spakoi will be documented in this file. The project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Public repository documentation and contribution guidelines.
- Automated Python and JavaScript checks.
- Regression tests for malformed configuration and state files.

### Security

- Install GNOME Shell extension files without preserving source ownership.
- Fail closed when strict-mode configuration cannot be evaluated.
- Escape TOML strings and validate security-relevant configuration types.
- Reject malformed or timezone-naive persisted overrides.
- Harden the user service with systemd sandboxing directives.
- Prevent schedule reset from revealing manually hidden time in strict mode.
- Reject malformed states received by the GNOME Shell extension over D-Bus.
- Avoid waiting behind an unexpected owner of the daemon's D-Bus name.
- Create user configuration and state files with a private service umask.
- Route D-Bus activation through the hardened systemd user service.
- Pin third-party GitHub Actions to immutable commit SHAs.
- Add CodeQL, dependency review, Dependabot, and checksummed release artifacts.

## [0.2.0] - 2026-09-04

### Added

- GTK schedule editor with bounded time pickers.
- Per-interval Play and Stop controls.
- Protected intervals that cannot be changed while active.
- Background service and GNOME top-panel launcher.
- Clock hiding in the panel, Date Menu, lock screen, and GDM.

### Changed

- Renamed the application from TimeVeil to Spakoi.
- Translated the application interface and documentation into English.

[Unreleased]: https://github.com/VictoriaAppDeveloper/spakoi/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/VictoriaAppDeveloper/spakoi/releases/tag/v0.2.0
