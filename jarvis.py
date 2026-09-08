"""JARVIS desktop orb and local command chat."""
import argparse
import json
import math
import os
import sys
from pathlib import Path

# GNOME Wayland restricts absolute positioning; use its XWayland bridge.
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PyQt5.QtCore import QPoint, QRectF, Qt, QThread, QTimer, pyqtSignal, QLockFile, QStandardPaths
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PyQt5.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from commands import CommandEngine, HELP
from groq_client import GroqClient, GroqError, RUN_ACTION_TOOL


class CommandWorker(QThread):
    completed = pyqtSignal(object)

    def __init__(self, engine, command, confirmation=False, parent=None):
        super().__init__(parent)
        self.engine, self.command, self.confirmation = engine, command, confirmation

    def run(self):
        from commands import Result
        try:
            result = (self.engine.confirm_action(self.command) if self.confirmation
                      else self.engine.execute(self.command))
        except Exception as error:
            result = Result(f"Something went wrong: {error}")
        self.completed.emit(result)


def build_system_prompt():
    return (
        "You are JARVIS, a concise, friendly desktop assistant on the user's Ubuntu computer. "
        "You can perform actions on the computer with a single tool, run_action(command). "
        "Always reply in the same language the user writes in, and keep chat replies short "
        "(1-2 sentences) unless the user asks for more detail.\n\n"
        "Call run_action with EXACTLY one command from this list whenever the user asks you "
        "to DO something on the computer:\n"
        "- open <app name>    e.g. open firefox | open code | open terminal | open calculator | open files\n"
        "- open <website>     e.g. open youtube | open github | open gmail | open example.com\n"
        "- open <folder>      e.g. open downloads | open documents | open home\n"
        "- search <query>     e.g. search python tutorial\n"
        "- search youtube for <query>\n"
        "- volume up | volume down | mute | unmute\n"
        "- lock\n"
        "- time | date\n"
        "- apps    (lists installed applications)\n"
        "- shutdown    (the app will ask the user to confirm separately; still call the tool)\n\n"
        "If the app name is unusual, still call run_action with 'open <their name>' so the "
        "local system can look it up or suggest close matches. Never invent other commands "
        "or tool names. For small talk, questions, or requests that don't require the computer, "
        "just answer naturally WITHOUT calling the tool."
    )


class LLMWorker(QThread):
    """Runs a Groq chat round; when the model requests run_action, the command
    is executed locally and the outcome is fed back for a natural reply."""

    reply = pyqtSignal(str)
    actions = pyqtSignal(list)
    need_confirm = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, client, engine, messages, model, parent=None):
        super().__init__(parent)
        self.client, self.engine = client, engine
        self.messages, self.model = messages, model

    def run(self):
        try:
            self._run()
        except Exception as error:
            self.failed.emit(f"Groq error: {error}")

    def _run(self):
        response = self.client.chat(
            self.messages, model=self.model, tools=[RUN_ACTION_TOOL], tool_choice="auto"
        )
        message = response["choices"][0]["message"]
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            self.reply.emit(message.get("content") or "Done.")
            return
        tool_messages = [message]
        outcomes = []
        for call in tool_calls:
            tool_id = call.get("id", "")
            try:
                arguments = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            command = str(arguments.get("command", "")).strip()
            if not command:
                continue
            result = self.engine.execute(command)
            if result.confirm:
                self.need_confirm.emit(result.confirm)
                self.reply.emit(result.text)
                return
            tool_messages.append({"role": "tool", "tool_call_id": tool_id, "content": result.text})
            outcomes.append((command, result.text))
        # Second round: let the model phrase a natural reply about what happened.
        try:
            final = self.client.chat(
                list(self.messages) + tool_messages, model=self.model,
                tools=[RUN_ACTION_TOOL], tool_choice="none",
            )
            text = final["choices"][0]["message"].get("content") or "Done."
        except Exception:
            text = "; ".join(outcome[1] for outcome in outcomes) or "Done."
        self.actions.emit(outcomes)
        self.reply.emit(text)


class ChatPanel(QWidget):
    def __init__(self, orb, engine, llm=None, model=None):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.orb, self.engine, self.worker = orb, engine, None
        self.llm, self.model = llm, model
        self.messages = []
        self.last_submitted = ""
        self.pending = ""
        self.setWindowTitle("JARVIS — Groq Assistant")
        self.resize(410, 510)
        self.setStyleSheet("""
            QWidget { background: #101b2c; color: #e4f6ff; font-size: 14px; }
            QLabel#heading { color: #57dfed; font-size: 20px; font-weight: bold; }
            QTextBrowser { background: #0b1321; border: 1px solid #29405a;
                           border-radius: 10px; padding: 10px; }
            QLineEdit { background: #182a40; border: 1px solid #39738c;
                        border-radius: 8px; padding: 10px; }
            QPushButton { background: #223e56; border: none; border-radius: 7px;
                          padding: 9px; color: #a8f4ff; }
            QPushButton:hover { background: #305a72; }
            QPushButton:disabled { color: #6a8295; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        header = QHBoxLayout()
        title = QLabel("◉  J A R V I S")
        title.setObjectName("heading")
        header.addWidget(title)
        header.addStretch()
        close = QPushButton("✕")
        close.setToolTip("Hide chat (Esc)")
        close.clicked.connect(self.hide)
        header.addWidget(close)
        layout.addLayout(header)
        if self.llm is not None:
            subtitle = QLabel(f"GROQ ONLINE  •  {self.model}  •  {len(self.engine.index.apps)} apps indexed")
        else:
            subtitle = QLabel("LOCAL MODE  •  no API key / network")
        subtitle.setStyleSheet("color: #91a9bd; font-size: 11px;")
        layout.addWidget(subtitle)
        self.history = QTextBrowser()
        self.history.setOpenLinks(False)
        self.history.document().setMaximumBlockCount(500)
        layout.addWidget(self.history)
        shortcuts = QHBoxLayout()
        for label, command in [("Browser", "open google"), ("Files", "open files"), ("Help", "help")]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, cmd=command: self.submit(cmd))
            shortcuts.addWidget(button)
        layout.addLayout(shortcuts)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setMaxLength(2000)
        self.input.setPlaceholderText("Try: open youtube")
        self.input.returnPressed.connect(self.submit)
        row.addWidget(self.input)
        self.send = QPushButton("Send")
        self.send.clicked.connect(lambda: self.submit())
        row.addWidget(self.send)
        layout.addLayout(row)
        self.confirm_row = QWidget()
        confirmation = QHBoxLayout(self.confirm_row)
        yes, no = QPushButton("Confirm shutdown…"), QPushButton("Cancel")
        yes.clicked.connect(self.confirm)
        no.clicked.connect(self.cancel)
        confirmation.addWidget(yes)
        confirmation.addWidget(no)
        layout.addWidget(self.confirm_row)
        self.confirm_row.hide()
        if self.llm is not None:
            welcome = ("Ready. Talk to me naturally, or try 'open firefox' / 'search cats'.\n"
                       "Drag the orb to move it; right-click it for options.")
        else:
            welcome = ("Ready. Offline local mode: type a command like 'open firefox', or 'help'.\n"
                       "Drag the orb to move it; right-click it for options.")
        self.append("Jarvis", welcome)

    def append(self, speaker, text):
        import html
        self.history.append(f'<p><b style="color:#57dfed">{html.escape(speaker)}</b><br>'
                            + html.escape(text).replace("\n", "<br>") + "</p>")
        self.history.verticalScrollBar().setValue(self.history.verticalScrollBar().maximum())

    def submit(self, text=None):
        if self.worker is not None:
            return
        text = self.input.text().strip() if text is None else text.strip()
        if not text:
            return
        self.input.clear()
        self.pending = ""
        self.confirm_row.hide()
        if text.casefold() == "clear":
            self.history.clear()
            self.messages = []
            return
        self.append("You", text)
        self.last_submitted = text
        if self.llm is not None:
            self.messages.append({"role": "user", "content": text})
            if len(self.messages) > 24:
                del self.messages[: len(self.messages) - 24]
            self.start_llm()
        else:
            self.start_worker(text)

    def _busy(self):
        self.input.setEnabled(False)
        self.send.setEnabled(False)

    def start_worker(self, command, confirmation=False):
        self._busy()
        self.worker = CommandWorker(self.engine, command, confirmation, self)
        self.worker.completed.connect(self.received)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def start_llm(self):
        self._busy()
        system = {"role": "system", "content": build_system_prompt()}
        self.worker = LLMWorker(self.llm, self.engine, [system] + self.messages, self.model, self)
        self.worker.reply.connect(self.on_llm_reply)
        self.worker.actions.connect(lambda outcomes: None)
        self.worker.need_confirm.connect(self.on_llm_confirm)
        self.worker.failed.connect(self.on_llm_failed)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def received(self, result):
        self.append("Jarvis", result.text)
        if result.confirm:
            self.pending = result.confirm
            self.confirm_row.show()

    def on_llm_reply(self, text):
        self.append("Jarvis", text)
        self.messages.append({"role": "assistant", "content": text})
        if len(self.messages) > 24:
            del self.messages[: len(self.messages) - 24]

    def on_llm_confirm(self, action):
        self.pending = action
        self.confirm_row.show()

    def on_llm_failed(self, message):
        self.append("Jarvis", f"{message} — switching to offline local mode.")
        self.llm = None
        self.start_worker(self.last_submitted)

    def finished(self):
        sender = self.sender()
        if sender is not self.worker:
            return
        self.worker.deleteLater()
        self.worker = None
        self.input.setEnabled(True)
        self.send.setEnabled(True)
        self.input.setFocus()

    def confirm(self):
        if self.pending and self.worker is None:
            action, self.pending = self.pending, ""
            self.confirm_row.hide()
            self.start_worker(action, True)

    def cancel(self):
        self.pending = ""
        self.confirm_row.hide()
        self.append("Jarvis", "Cancelled. Nothing was executed.")

    def show_near_orb(self):
        screen = self.orb.screen().availableGeometry()
        self.resize(min(410, screen.width()), min(510, screen.height()))
        x = self.orb.x() - self.width() - 12
        if x < screen.left():
            x = self.orb.x() + self.orb.width() + 12
        x = max(screen.left(), min(x, screen.right() - self.width() + 1))
        y = max(screen.top(), min(self.orb.y() - 100, screen.bottom() - self.height() + 1))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        event.ignore()
        self.hide()


class Orb(QWidget):
    def __init__(self, engine, llm=None, model=None):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("JARVIS")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(86, 86)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("JARVIS • Click to chat • Drag to move • Right-click for options")
        self.phase = 0.0
        self.floating = True
        self.dragging = False
        self.press_position = None
        self.menu_open = False
        screen = QApplication.primaryScreen().availableGeometry()
        self.anchor = QPoint(screen.right() - 112, screen.top() + screen.height() // 3)
        self.move(self.anchor)
        self.panel = ChatPanel(self, engine, llm, model)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)

    def tick(self):
        self.phase += 0.045
        self.update()
        if self.floating and self.press_position is None and not self.panel.isVisible() and not self.underMouse() and not self.menu_open:
            point = self.anchor + QPoint(round(7 * math.sin(self.phase / 3)), round(10 * math.sin(self.phase / 2)))
            self.move(self.clamp(point))

    def clamp(self, point):
        screen = QApplication.screenAt(point + QPoint(43, 43)) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        return QPoint(max(bounds.left(), min(point.x(), bounds.right() - self.width() + 1)),
                      max(bounds.top(), min(point.y(), bounds.bottom() - self.height() + 1)))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        glow = QRadialGradient(43, 43, 43)
        glow.setColorAt(0, QColor(40, 220, 245, 130))
        glow.setColorAt(0.72, QColor(40, 220, 245, 75))
        glow.setColorAt(1, QColor(40, 220, 245, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QRectF(0, 0, 86, 86))
        painter.setBrush(QColor("#0c1c30"))
        painter.setPen(QPen(QColor("#5be6ef"), 2))
        painter.drawEllipse(QRectF(13, 13, 60, 60))
        painter.setPen(QPen(QColor("#28889f"), 2))
        painter.drawArc(QRectF(20, 20, 46, 46), int(self.phase * 140), 250 * 16)
        painter.setPen(QColor("#d7fcff"))
        painter.setFont(QFont("Sans Serif", 20, QFont.Bold))
        painter.drawText(self.rect(), Qt.AlignCenter, "J")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.press_position = event.globalPos()
            self.original_position = self.pos()
            self.dragging = False

    def mouseMoveEvent(self, event):
        if self.press_position is not None:
            delta = event.globalPos() - self.press_position
            if delta.manhattanLength() > QApplication.startDragDistance():
                self.dragging = True
            if self.dragging:
                self.anchor = self.clamp(self.original_position + delta)
                self.move(self.anchor)
                if self.panel.isVisible():
                    self.panel.hide()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.press_position is not None:
            self.press_position = None
            if not self.dragging:
                self.toggle_chat()
            self.dragging = False

    def toggle_chat(self):
        if self.panel.isVisible():
            self.panel.hide()
        else:
            self.panel.show_near_orb()

    def contextMenuEvent(self, event):
        self.menu_open = True
        menu = QMenu(self)
        menu.addAction("Open / hide chat", self.toggle_chat)
        float_action = menu.addAction("Gentle floating")
        float_action.setCheckable(True)
        float_action.setChecked(self.floating)
        float_action.toggled.connect(self.set_floating)
        menu.addSeparator()
        menu.addAction("Quit JARVIS", self.quit)
        menu.exec_(event.globalPos())
        self.menu_open = False

    def set_floating(self, enabled):
        self.anchor = self.pos()
        self.floating = enabled

    def quit(self):
        if self.panel.worker is not None:
            self.panel.append("Jarvis", "Please wait for the current command to finish before quitting.")
            self.panel.show_near_orb()
            return
        QApplication.quit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true", help="Show UI briefly and exit without executing commands")
    options = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("JARVIS")
    app.setQuitOnLastWindowClosed(False)
    runtime = QStandardPaths.writableLocation(QStandardPaths.RuntimeLocation)
    lock = QLockFile(str(Path(runtime) / "jarvis-local-assistant.lock"))
    if not options.smoke_test and not lock.tryLock(100):
        print("JARVIS is already running.", flush=True)
        return 0
    engine = CommandEngine()
    llm = model = None
    if not options.smoke_test:
        try:
            client = GroqClient()
            if client.available:
                model = client.pick_model()
                llm = client
                print(f"JARVIS Groq online; model {model}.", flush=True)
        except GroqError as error:
            print(f"JARVIS Groq unavailable: {error}", flush=True)
    orb = Orb(engine, llm, model)
    orb.show()
    print(f"JARVIS ready: {len(engine.index.apps)} apps indexed; Qt platform {app.platformName()}.", flush=True)
    if options.smoke_test:
        orb.panel.show_near_orb()
        QTimer.singleShot(1500, app.quit)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())