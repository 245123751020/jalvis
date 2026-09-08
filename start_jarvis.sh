#!/bin/sh
# Explicit interpreter also works when launched outside the interactive Conda shell.
cd /home/mvsr/jarvis || exit 1
export QT_QPA_PLATFORM=xcb
exec /home/mvsr/anaconda3/bin/python3 /home/mvsr/jarvis/jarvis.py "$@"