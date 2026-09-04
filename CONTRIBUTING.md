# Contributing to Spakoi

Thank you for helping improve Spakoi.

## Before opening an issue

Search the existing issues first. For bugs, include your Linux distribution,
GNOME Shell version, installation method, and the output of:

```sh
spakoi doctor
journalctl --user -u spakoi.service --since today
```

Do not include private data from unrelated journal entries.

## Development

Spakoi requires Python 3.11+, PyGObject, and GNOME Shell 43, 49, or 50.

```sh
make test
python3 -m compileall -q spakoi
node --check extension/spakoi@victoriaappdeveloper.github.io/extension-legacy.js
node --check extension/spakoi@victoriaappdeveloper.github.io/src/controller.js
```

Keep changes focused and add tests for behavior that can be exercised outside a
live GNOME session. Test Shell, lock-screen, and GDM changes manually on every
GNOME version affected by the change.

## Pull requests

- Explain the problem and the intended behavior.
- Link related issues.
- Describe how the change was tested.
- Update the README or changelog when user-visible behavior changes.
- Keep commits free of generated files and local IDE settings.

By contributing, you agree that your contribution is licensed under
GPL-3.0-or-later.
