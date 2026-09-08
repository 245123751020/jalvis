"""Discover launchable desktop applications without evaluating their Exec fields."""
import configparser
import difflib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class App:
    name: str
    path: Path
    desktop_id: str


def normalize(text):
    return " ".join(text.casefold().replace("-", " ").replace("_", " ").split())


class AppIndex:
    def __init__(self, directories=None):
        if directories is None:
            data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
            data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
            directories = [data_home / "applications"]
            directories += [Path(p) / "applications" for p in data_dirs.split(":") if p]
            directories.append(Path("/var/lib/snapd/desktop/applications"))
        self.apps = []
        seen = set()
        desktops = set(os.environ.get("XDG_CURRENT_DESKTOP", "").split(":"))
        for directory in directories:
            directory = Path(directory)
            for path in sorted(directory.glob("**/*.desktop")):
                desktop_id = str(path.relative_to(directory)).replace("/", "-")
                if desktop_id in seen:
                    continue
                seen.add(desktop_id)
                parser = configparser.ConfigParser(interpolation=None, strict=False)
                try:
                    parser.read(path, encoding="utf-8")
                    entry = parser["Desktop Entry"]
                    if entry.get("Type") != "Application":
                        continue
                    if any(entry.getboolean(key, fallback=False) for key in ("Hidden", "NoDisplay")):
                        continue
                    only = set(filter(None, entry.get("OnlyShowIn", "").split(";")))
                    excluded = set(filter(None, entry.get("NotShowIn", "").split(";")))
                    if (only and not desktops.intersection(only)) or desktops.intersection(excluded):
                        continue
                    if entry.get("TryExec") and not shutil.which(entry["TryExec"]):
                        continue
                    name = entry.get("Name", "").strip()
                    if name and (entry.get("Exec") or entry.getboolean("DBusActivatable", fallback=False)):
                        self.apps.append(App(name, path, desktop_id))
                except (OSError, UnicodeError, configparser.Error, ValueError, KeyError):
                    continue
        self.apps.sort(key=lambda app: app.name.casefold())

    def find(self, name):
        key = normalize(name)
        aliases = {
            "chrome": "google chrome", "vs code": "visual studio code",
            "vscode": "visual studio code", "code": "visual studio code",
            "calc": "calculator", "file manager": "files", "nautilus": "files",
            "gnome terminal": "terminal",
        }
        key = aliases.get(key, key)
        for app in self.apps:
            if key in (normalize(app.name), normalize(app.desktop_id.removesuffix(".desktop"))):
                return app
        return None

    def suggest(self, name):
        names = [app.name for app in self.apps]
        mapping = {normalize(n): n for n in names}
        matches = difflib.get_close_matches(normalize(name), list(mapping), n=4, cutoff=0.45)
        return [mapping[m] for m in matches]