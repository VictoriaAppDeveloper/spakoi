PREFIX ?= /usr
DESTDIR ?=
PYTHON ?= python3
UUID = spakoi@victoriaappdeveloper.github.io
PYTHON_SITE ?= $(shell $(PYTHON) -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
GNOME_MAJOR ?= $(shell gnome-shell --version 2>/dev/null | sed -n 's/.* \([0-9][0-9]*\)\..*/\1/p')

.PHONY: test install uninstall

test:
	$(PYTHON) -m unittest discover -s tests -v

install:
	rm -rf "$(DESTDIR)$(PYTHON_SITE)/timeveil"
	rm -rf "$(DESTDIR)$(PYTHON_SITE)/spakoi"
	rm -f "$(DESTDIR)$(PREFIX)/bin/timeveil" "$(DESTDIR)$(PREFIX)/bin/timeveil-daemon" "$(DESTDIR)$(PREFIX)/bin/timeveil-gui"
	rm -rf "$(DESTDIR)$(PREFIX)/share/gnome-shell/extensions/timeveil@example.org"
	rm -rf "$(DESTDIR)$(PREFIX)/share/gnome-shell/extensions/spakoi@example.org"
	rm -rf "$(DESTDIR)$(PREFIX)/share/gnome-shell/extensions/$(UUID)"
	rm -f "$(DESTDIR)$(PREFIX)/share/dbus-1/services/org.timeveil.TimeVeil.service"
	rm -f "$(DESTDIR)$(PREFIX)/lib/systemd/user/timeveil.service"
	rm -f "$(DESTDIR)$(PREFIX)/share/applications/org.timeveil.TimeVeil.UI.desktop"
	rm -f "$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/org.timeveil.TimeVeil.UI.svg"
	install -d "$(DESTDIR)$(PYTHON_SITE)/spakoi"
	install -m644 spakoi/*.py "$(DESTDIR)$(PYTHON_SITE)/spakoi/"
	install -Dm755 bin/spakoi "$(DESTDIR)$(PREFIX)/bin/spakoi"
	install -Dm755 bin/spakoi-daemon "$(DESTDIR)$(PREFIX)/bin/spakoi-daemon"
	install -Dm755 bin/spakoi-gui "$(DESTDIR)$(PREFIX)/bin/spakoi-gui"
	install -Dm644 extension/$(UUID)/metadata.json "$(DESTDIR)$(PREFIX)/share/gnome-shell/extensions/$(UUID)/metadata.json"
	install -d "$(DESTDIR)$(PREFIX)/share/gnome-shell/extensions/$(UUID)/src/compat"
	install -m644 extension/$(UUID)/src/*.js "$(DESTDIR)$(PREFIX)/share/gnome-shell/extensions/$(UUID)/src/"
	install -m644 extension/$(UUID)/src/compat/*.js "$(DESTDIR)$(PREFIX)/share/gnome-shell/extensions/$(UUID)/src/compat/"
	install -d "$(DESTDIR)$(PREFIX)/share/gnome-shell/extensions/$(UUID)/icons"
	install -m644 extension/$(UUID)/icons/*.svg "$(DESTDIR)$(PREFIX)/share/gnome-shell/extensions/$(UUID)/icons/"
	@if test -n "$(GNOME_MAJOR)" && test "$(GNOME_MAJOR)" -lt 45; then \
		install -Dm644 extension/$(UUID)/extension-legacy.js "$(DESTDIR)$(PREFIX)/share/gnome-shell/extensions/$(UUID)/extension.js"; \
	else \
		install -Dm644 extension/$(UUID)/extension.js "$(DESTDIR)$(PREFIX)/share/gnome-shell/extensions/$(UUID)/extension.js"; \
	fi
	install -Dm644 extension/$(UUID)/stylesheet.css "$(DESTDIR)$(PREFIX)/share/gnome-shell/extensions/$(UUID)/stylesheet.css"
	install -Dm644 dbus/org.spakoi.Spakoi.service "$(DESTDIR)$(PREFIX)/share/dbus-1/services/org.spakoi.Spakoi.service"
	install -Dm644 systemd/spakoi-user.service "$(DESTDIR)$(PREFIX)/lib/systemd/user/spakoi.service"
	rm -f "$(DESTDIR)$(PREFIX)/share/applications/org.spakoi.Spakoi.desktop"
	install -Dm644 data/org.spakoi.Spakoi.UI.desktop "$(DESTDIR)$(PREFIX)/share/applications/org.spakoi.Spakoi.UI.desktop"
	rm -f "$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/org.spakoi.Spakoi.svg"
	install -Dm644 data/org.spakoi.Spakoi.UI.svg "$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/org.spakoi.Spakoi.UI.svg"
	@if test ! -e "$(DESTDIR)/etc/spakoi/config.toml"; then \
		if test -e "$(DESTDIR)/etc/timeveil/config.toml"; then \
			install -Dm644 "$(DESTDIR)/etc/timeveil/config.toml" "$(DESTDIR)/etc/spakoi/config.toml"; \
		else \
			install -Dm644 config/config.example.toml "$(DESTDIR)/etc/spakoi/config.toml"; \
		fi; \
	fi
	@if test -z "$(DESTDIR)"; then \
		if command -v gtk-update-icon-cache >/dev/null 2>&1; then \
			gtk-update-icon-cache -q -f "$(PREFIX)/share/icons/hicolor"; \
		fi; \
		if command -v update-desktop-database >/dev/null 2>&1; then \
			update-desktop-database -q "$(PREFIX)/share/applications"; \
		fi; \
	fi

uninstall:
	rm -rf "$(DESTDIR)$(PYTHON_SITE)/spakoi"
	rm -f "$(DESTDIR)$(PREFIX)/bin/spakoi" "$(DESTDIR)$(PREFIX)/bin/spakoi-daemon" "$(DESTDIR)$(PREFIX)/bin/spakoi-gui"
	rm -f "$(DESTDIR)$(PREFIX)/share/applications/org.spakoi.Spakoi.desktop"
	rm -f "$(DESTDIR)$(PREFIX)/share/applications/org.spakoi.Spakoi.UI.desktop"
	rm -f "$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/org.spakoi.Spakoi.svg"
	rm -f "$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/org.spakoi.Spakoi.UI.svg"
	rm -rf "$(DESTDIR)$(PREFIX)/share/gnome-shell/extensions/$(UUID)"
	rm -f "$(DESTDIR)$(PREFIX)/share/dbus-1/services/org.spakoi.Spakoi.service"
	rm -f "$(DESTDIR)$(PREFIX)/lib/systemd/user/spakoi.service"
	@if test -z "$(DESTDIR)"; then \
		if command -v gtk-update-icon-cache >/dev/null 2>&1; then \
			gtk-update-icon-cache -q -f "$(PREFIX)/share/icons/hicolor"; \
		fi; \
		if command -v update-desktop-database >/dev/null 2>&1; then \
			update-desktop-database -q "$(PREFIX)/share/applications"; \
		fi; \
	fi
