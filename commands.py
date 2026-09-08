"""Small, explicit local command engine. User text is never shell code."""
import datetime
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus, urlsplit

from apps_index import AppIndex


HELP = """Try these commands:
• open firefox / chrome / code / terminal / calculator / files
• open youtube / github / gmail / google
• open example.com (or an https:// URL)
• search Python tutorial
• search youtube for relaxing music
• open downloads / documents / desktop / home
• apps — list available applications
• volume up / volume down / mute / unmute
• time / date / lock
• shutdown — always asks for confirmation
• help / clear

Right-click the orb to pause floating or quit. Drag it to move it.
When Groq is connected you can also just talk to me naturally.
Otherwise this offline mode understands local commands."""


@dataclass(frozen=True)
class Result:
    text: str
    confirm: str = ""


class CommandEngine:
    def __init__(self, index=None):
        self.index = index if index is not None else AppIndex()

    @staticmethod
    def _tool(name):
        # Prefer OS tools over similarly named executables from Conda.
        system = Path("/usr/bin") / name
        return str(system) if system.is_file() else shutil.which(name)

    def _launch(self, tool, args, message):
        executable = self._tool(tool)
        if not executable:
            return Result(f"{tool} isn't installed, so I can't do that here.")
        try:
            process = subprocess.Popen(
                [executable, *args], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            try:
                code = process.wait(timeout=0.4)
                if code:
                    return Result(f"The desktop rejected that request ({tool}, exit {code}).")
            except subprocess.TimeoutExpired:
                # Desktop launchers may remain alive for the application's lifetime.
                import threading
                threading.Thread(target=process.wait, daemon=True).start()
            return Result(message)
        except OSError as error:
            return Result(f"Couldn't launch it: {error}")

    def _run(self, tool, args, message, timeout=8):
        executable = self._tool(tool)
        if not executable:
            return Result(f"{tool} isn't installed, so I can't do that here.")
        try:
            result = subprocess.run([executable, *args], capture_output=True, text=True, timeout=timeout)
            if result.returncode:
                detail = result.stderr.strip()[:250] or f"exit {result.returncode}"
                return Result(f"That didn't work: {detail}")
            return Result(message)
        except (OSError, subprocess.TimeoutExpired) as error:
            return Result(f"That didn't work: {error}")

    @staticmethod
    def web_url(target):
        if any(c.isspace() or ord(c) < 32 for c in target):
            return None
        candidate = target if "://" in target else "https://" + target
        try:
            parsed = urlsplit(candidate)
            host = parsed.hostname
            _ = parsed.port
            if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
                return None
            if not re.fullmatch(r"[a-zA-Z0-9\u0080-\uffff.-]+", host):
                return None
            if "." not in host and host != "localhost":
                return None
            return candidate
        except ValueError:
            return None

    def execute(self, text):
        text = text.strip()
        if not text:
            return Result("Type a command, such as 'open youtube'.")
        if len(text) > 2000:
            return Result("Please keep commands under 2,000 characters.")
        lower = " ".join(text.casefold().split())
        if lower in ("help", "hi", "hello", "hey", "what can you do"):
            return Result(HELP)
        if lower in ("time", "what time is it"):
            return Result(datetime.datetime.now().strftime("It's %I:%M %p."))
        if lower in ("date", "today", "what is the date"):
            return Result(datetime.datetime.now().strftime("Today is %A, %d %B %Y."))
        if lower in ("apps", "list apps"):
            return Result("Available apps:\n" + "\n".join(app.name for app in self.index.apps))
        if lower in ("shutdown", "shut down", "power off"):
            return Result("Shut down this computer? Save your work first.", confirm="shutdown")
        if lower in ("lock", "lock screen"):
            return self._run("loginctl", ["lock-session"], "Screen lock requested.")
        volumes = {
            "volume up": ["set-sink-volume", "@DEFAULT_SINK@", "+5%"],
            "volume down": ["set-sink-volume", "@DEFAULT_SINK@", "-5%"],
            "mute": ["set-sink-mute", "@DEFAULT_SINK@", "1"],
            "unmute": ["set-sink-mute", "@DEFAULT_SINK@", "0"],
        }
        if lower in volumes:
            return self._run("pactl", volumes[lower], "Volume updated.")
        search = re.match(r"^(?:search|google)\s+(.+)$", text, re.I)
        if search:
            query = search.group(1).strip()
            youtube = re.match(r"youtube\s+for\s+(.+)$", query, re.I)
            base = "https://www.youtube.com/results?search_query=" if youtube else "https://www.google.com/search?q="
            query = youtube.group(1).strip() if youtube else query
            return self._launch("xdg-open", [base + quote_plus(query)], f"Browser search requested: {query}")
        opening = re.match(r"^(?:open|launch|start)\s+(.+)$", text, re.I)
        if opening:
            target = opening.group(1).strip()
            key = target.casefold()
            sites = {
                "youtube": "https://www.youtube.com", "github": "https://github.com",
                "gmail": "https://mail.google.com", "google": "https://www.google.com",
                "whatsapp": "https://web.whatsapp.com", "chatgpt": "https://chatgpt.com",
            }
            if key in sites:
                return self._launch("xdg-open", [sites[key]], f"Requested {target} in your browser.")
            folders = {"home": Path.home(), **{n.lower(): Path.home() / n for n in ("Downloads", "Documents", "Desktop", "Pictures", "Music", "Videos")}}
            if key in folders:
                if not folders[key].is_dir():
                    return Result(f"Folder not found: {folders[key]}")
                return self._launch("xdg-open", [str(folders[key])], f"Requested folder: {folders[key]}")
            app = self.index.find(target)
            if app:
                return self._launch("gio", ["launch", str(app.path)], f"Requested launch: {app.name}.")
            url = self.web_url(target)
            if url:
                return self._launch("xdg-open", [url], f"Requested {url} in your browser.")
            suggestions = self.index.suggest(target)
            suffix = " Did you mean: " + ", ".join(suggestions) + "?" if suggestions else " Type 'apps' to see what's installed."
            return Result(f"I couldn't find '{target}'." + suffix)
        if lower == "screenshot":
            return Result("Use the Print Screen key for GNOME's screenshot tool. Automatic screenshots aren't enabled in this version.")
        return Result("I don't recognize that command. Try 'open firefox', 'search cats', or 'help'.")

    def confirm_action(self, action):
        if action == "shutdown":
            return self._run("systemctl", ["poweroff"], "Powering off the system. If the system asks for confirmation, approve the system prompt (this is expected, and cancelling it safely aborts).", timeout=45)
        return Result("Unknown action; nothing was executed.")