# JARVIS desktop assistant (Groq + local)

Run `/home/mvsr/jarvis/start_jarvis.sh`. Click the glowing J orb to open
the chat panel. Drag the orb to reposition it. Right-click for floating and quit
controls. Escape or the panel's close button hides chat without quitting.
The orb gently bobs around its position rather than roaming across your work.

When a Groq API key is available the orb answers naturally (small talk, questions)
and performs desktop actions through function calling: the model picks a
`run_action` command, the local engine executes it on your machine, and the
model confirms in words. Without a key or network it still works in offline
local-command mode.

## Natural conversation (Groq)

- "hey jarvis, what time is it?" → answers and shows the time
- "open firefox" / "open youtube" / "search python tutorial, please"
- "turn the volume up", "mute", "lock the screen"
- "what apps can you open?" → calls `apps`
- any small talk works without touching the computer
- unknown app names are still passed to `open <name>` so the local index can
  suggest close matches instead of launching something wrong

The key is read from `$GROQ_API_KEY`, then `~/.config/jarvis/groq_key`
(created with permissions 600 — it is never stored in source code). The model
is auto-selected from the account's active list (default `qwen/qwen3.8-27b`).

## Offline commands

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

Chat goes to Groq's API over HTTPS while connected — do not send passwords or
secrets through the panel. Input is never evaluated as shell commands, and the
local command engine is an explicit whitelist (also enforced in offline mode).
Only HTTP(S) URLs are supported. Chat history is kept in memory, not saved to
disk, and is trimmed to the most recent 24 messages. Screenshot automation and
global hotkeys are not implemented. If Groq becomes unreachable the panel
switches to offline local mode automatically.

Requires the existing Python/PyQt5 environment at
`/home/mvsr/anaconda3/bin/python3`; the Groq client uses only the standard
library. Launches use OS desktop tools.
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
The smoke test briefly displays the orb and chat, then exits automatically.
