# JARVIS local desktop assistant

Run `/home/mvsr/jarvis/start_jarvis.sh`. Click the glowing J orb to open
the chat panel. Drag the orb to reposition it. Right-click for floating and quit
controls. Escape or the panel's close button hides chat without quitting.
The orb gently bobs around its position rather than roaming across your work.

## Commands

- `open firefox`, `open chrome`, `open code`, `open terminal`, `open calculator`
- `apps` lists launchable installed apps; use `open <app name>` to launch one.
- `open youtube`, `open github`, `open gmail`, `open example.com`
- `search Python tutorial`, `search youtube for relaxing music`
- `open downloads`, `open documents`, `open home`
- `volume up`, `volume down`, `mute`, `unmute`, `lock`, `time`, `date`
- `shutdown` requires an explicit chat button, then the system powers off
  immediately (which is itself the final confirmation); if a password/authorization
  prompt appears, it is expected and cancelling it safely aborts the shutdown.
- `help`, `clear`

Approximate application names produce suggestions, not automatic launches.
Browser and application responses acknowledge a launch request; they cannot
guarantee that the target application finished loading. Folder aliases currently
use standard English folder names under your home directory.

## Scope and safety

This is a typed, rule-based assistant, not an LLM or a voice assistant. No API
keys, new packages, or cloud processing are needed. Web requests naturally use
your internet connection and browser. Chat is held in memory, not saved to disk.
Input is never evaluated as shell commands. Only HTTP(S) URLs are supported.
Screenshot automation and global hotkeys are not implemented.

Requires the existing Python/PyQt5 environment at
`/home/mvsr/anaconda3/bin/python3`. Launches use OS desktop tools.
Uses Qt's xcb backend through XWayland on GNOME Wayland. Always-on-top behavior
is a window-manager hint; fullscreen apps and desktop policies may override it.
Transparent margins may receive mouse events; this is not a click-through overlay.
The chat stays open until you hide it, rather than dismissing on accidental focus loss.

## Login startup

The installed login entry is `/home/mvsr/.config/autostart/jarvis.desktop`.
Remove that file to disable login startup. The app-menu entry is
`/home/mvsr/.local/share/applications/jarvis.desktop`.
Quit from the orb's right-click menu before removing the project.

## Validation

```sh
cd /home/mvsr/jarvis
/home/mvsr/anaconda3/bin/python3 -m unittest discover -s tests -v
/home/mvsr/jarvis/start_jarvis.sh --smoke-test
```

Tests mock desktop actions so they don't open applications or change power state.
The smoke test briefly displays the orb and chat, then exits automatically.# jalvis
