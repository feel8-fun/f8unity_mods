from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from PySide6.QtCore import QObject, QThread, QTranslator, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import game_setup
from common import ROOT, SetupConfig, SetupError, load_setup_config


class JsonTranslator(QTranslator):
    def __init__(self, mapping: dict[str, str] | None = None):
        super().__init__()
        self._mapping = mapping or {}

    def translate(self, _context: str, source_text: str, _disambiguation: str | None = None, _n: int = -1) -> str:
        return self._mapping.get(source_text, source_text)


@dataclass(frozen=True)
class RunOptions:
    force_reinstall: bool
    skip_exporter: bool
    exporter: str
    rue: bool
    cue: bool
    config_manager: bool
    uud: bool
    offline: bool


class SetupWorker(QObject):
    succeeded = Signal(object, float)
    failed = Signal(object, float)

    def __init__(self, action: str, target: str, options: RunOptions, config: SetupConfig):
        super().__init__()
        self.action = action
        self.target = target
        self.options = options
        self.config = config

    @Slot()
    def run(self) -> None:
        started = perf_counter()
        try:
            if self.action == "detect":
                payload = game_setup.run_detect(self.target, self.config)
            elif self.action == "diagnose":
                payload = game_setup.run_diagnose(
                    target=self.target,
                    config=self.config,
                    exporter=self.options.exporter,
                    force_reinstall=self.options.force_reinstall,
                    skip_exporter=self.options.skip_exporter,
                    rue=self.options.rue,
                    cue=self.options.cue,
                    config_manager=self.options.config_manager,
                    uud=self.options.uud,
                    offline=self.options.offline,
                )
            elif self.action == "install":
                payload = game_setup.run_install(
                    target=self.target,
                    config=self.config,
                    exporter=self.options.exporter,
                    force_reinstall=self.options.force_reinstall,
                    skip_exporter=self.options.skip_exporter,
                    rue=self.options.rue,
                    cue=self.options.cue,
                    config_manager=self.options.config_manager,
                    uud=self.options.uud,
                    offline=self.options.offline,
                )
            else:
                raise ValueError(f"unsupported action: {self.action}")

            self.succeeded.emit(payload, perf_counter() - started)
        except SetupError as e:
            self.failed.emit(
                {
                    "status": "error",
                    "type": "SetupError",
                    "code": e.code,
                    "message": e.message,
                },
                perf_counter() - started,
            )
        except Exception as e:  # pragma: no cover
            self.failed.emit(
                {
                    "status": "error",
                    "type": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc(limit=20),
                },
                perf_counter() - started,
            )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(960, 680)

        self._thread: QThread | None = None
        self._worker: SetupWorker | None = None
        self._active_action = ""
        self._lang_code = "en"
        self._qt_translator: QTranslator | None = None
        self._translation_maps = self._load_translation_maps()

        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        self.target_group = QGroupBox()
        target_layout = QHBoxLayout(self.target_group)
        self.target_input = QLineEdit()
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._browse_target)
        self.path_label = QLabel()
        target_layout.addWidget(self.path_label)
        target_layout.addWidget(self.target_input, 1)
        target_layout.addWidget(self.browse_button)
        root_layout.addWidget(self.target_group)

        self.options_group = QGroupBox()
        options_layout = QGridLayout(self.options_group)
        self.force_reinstall = QCheckBox()
        self.skip_exporter = QCheckBox()
        self.exporter_select = QComboBox()
        self.exporter_label = QLabel()
        self.install_rue = QCheckBox()
        self.install_cue = QCheckBox()
        self.install_config_manager = QCheckBox()
        self.install_uud = QCheckBox()
        self.offline_mode = QCheckBox()
        options_layout.addWidget(self.force_reinstall, 0, 0)
        options_layout.addWidget(self.skip_exporter, 0, 1)
        options_layout.addWidget(self.exporter_label, 1, 0)
        options_layout.addWidget(self.exporter_select, 1, 1)
        options_layout.addWidget(self.install_rue, 2, 0)
        options_layout.addWidget(self.install_cue, 2, 1)
        options_layout.addWidget(self.install_config_manager, 3, 0)
        options_layout.addWidget(self.install_uud, 3, 1)
        options_layout.addWidget(self.offline_mode, 4, 0)
        root_layout.addWidget(self.options_group)

        actions_layout = QHBoxLayout()
        self.detect_button = QPushButton()
        self.diagnose_button = QPushButton()
        self.install_button = QPushButton()
        self.clear_button = QPushButton()
        self.language_button = QPushButton()
        self.detect_button.clicked.connect(lambda: self._start_action("detect"))
        self.diagnose_button.clicked.connect(lambda: self._start_action("diagnose"))
        self.install_button.clicked.connect(lambda: self._start_action("install"))
        self.clear_button.clicked.connect(self.output_clear)
        self.language_button.clicked.connect(self._toggle_language)
        actions_layout.addWidget(self.detect_button)
        actions_layout.addWidget(self.diagnose_button)
        actions_layout.addWidget(self.install_button)
        actions_layout.addStretch(1)
        actions_layout.addWidget(self.language_button)
        actions_layout.addWidget(self.clear_button)
        root_layout.addLayout(actions_layout)

        self.output_label = QLabel()
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        root_layout.addWidget(self.output_label)
        root_layout.addWidget(self.output, 1)

        self._apply_language(self._lang_code)
        self._append_log(self.tr("Ready"))

    def _translation_dir(self) -> Path:
        return ROOT / "tools" / "ui" / "i18n"

    def _load_translation_maps(self) -> dict[str, dict[str, str]]:
        result: dict[str, dict[str, str]] = {"en": {}, "zh": {}}
        base = self._translation_dir()
        for code, filename in (("en", "en.json"), ("zh", "zh.json")):
            path = base / filename
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            translations = payload.get("translations", {}) if isinstance(payload, dict) else {}
            if isinstance(translations, dict):
                result[code] = {str(k): str(v) for k, v in translations.items()}
        return result

    def _apply_language(self, lang_code: str) -> None:
        app = QApplication.instance()
        if app is None:
            return
        if self._qt_translator is not None:
            app.removeTranslator(self._qt_translator)
        mapping = self._translation_maps.get(lang_code, {})
        self._qt_translator = JsonTranslator(mapping)
        app.installTranslator(self._qt_translator)
        self._lang_code = lang_code
        self._retranslate_ui()

    def _toggle_language(self) -> None:
        self._apply_language("zh" if self._lang_code == "en" else "en")

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(self.tr("F8 Game Setup UI"))
        self.target_group.setTitle(self.tr("Target"))
        self.path_label.setText(self.tr("Path:"))
        self.target_input.setPlaceholderText(self.tr("Unity game .exe or folder"))
        self.browse_button.setText(self.tr("Browse"))

        self.options_group.setTitle(self.tr("Options"))
        self.force_reinstall.setText(self.tr("Force Reinstall"))
        self.skip_exporter.setText(self.tr("Skip Exporter"))
        self.exporter_label.setText(self.tr("Exporter:"))
        self.install_rue.setText(self.tr("RuntimeUnityEditor (RUE)"))
        self.install_cue.setText(self.tr("CinematicUnityExplorer (CUE)"))
        self.install_config_manager.setText(self.tr("ConfigurationManager"))
        self.install_uud.setText(self.tr("UniversalUnityDemosaics (UUD)"))
        self.offline_mode.setText(self.tr("Offline"))

        selected_exporter = str(self.exporter_select.currentData() or "auto")
        self.exporter_select.clear()
        self.exporter_select.addItem(self.tr("Auto (Profile)"), "auto")
        self.exporter_select.addItem(self.tr("Skeleton"), "skeleton")
        self.exporter_select.addItem(self.tr("Live2D"), "live2d")
        idx = max(0, self.exporter_select.findData(selected_exporter))
        self.exporter_select.setCurrentIndex(idx)

        self.detect_button.setText(self.tr("Detect"))
        self.diagnose_button.setText(self.tr("Diagnose"))
        self.install_button.setText(self.tr("Install"))
        self.clear_button.setText(self.tr("Clear Output"))
        self.language_button.setText(self.tr("Switch to English") if self._lang_code == "zh" else self.tr("Switch to Chinese"))
        self.output_label.setText(self.tr("Output"))

    def output_clear(self) -> None:
        self.output.clear()

    def _append_log(self, message: str, payload: object | None = None) -> None:
        self.output.appendPlainText(message)
        if payload is not None:
            if isinstance(payload, (dict, list)):
                text = json.dumps(payload, ensure_ascii=False, indent=2)
            else:
                text = str(payload)
            self.output.appendPlainText(text)
        self.output.appendPlainText("")

    def _browse_target(self) -> None:
        selected_file, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Select Game EXE"),
            self.target_input.text().strip(),
            self.tr("Executable (*.exe);;All files (*)"),
        )
        if selected_file:
            self.target_input.setText(selected_file)
            return

        selected_dir = QFileDialog.getExistingDirectory(
            self,
            self.tr("Select Game Folder"),
            self.target_input.text().strip(),
        )
        if selected_dir:
            self.target_input.setText(selected_dir)

    def _collect_options(self) -> RunOptions:
        return RunOptions(
            force_reinstall=self.force_reinstall.isChecked(),
            skip_exporter=self.skip_exporter.isChecked(),
            exporter=str(self.exporter_select.currentData() or "auto"),
            rue=self.install_rue.isChecked(),
            cue=self.install_cue.isChecked(),
            config_manager=self.install_config_manager.isChecked(),
            uud=self.install_uud.isChecked(),
            offline=self.offline_mode.isChecked(),
        )

    def _set_running(self, running: bool) -> None:
        self.detect_button.setEnabled(not running)
        self.diagnose_button.setEnabled(not running)
        self.install_button.setEnabled(not running)
        self.browse_button.setEnabled(not running)
        self.target_input.setEnabled(not running)
        self.exporter_select.setEnabled(not running)
        self.language_button.setEnabled(not running)

    def _start_action(self, action: str) -> None:
        try:
            if self._thread is not None:
                return

            target = self.target_input.text().strip()
            if not target:
                self._append_log(self.tr("[ui] missing target"), {"message": self.tr("Please choose target first")})
                return

            try:
                config = load_setup_config()
            except Exception as e:
                self._append_log(self.tr("[config] failed to load"), {"message": str(e)})
                return

            options = self._collect_options()
            self._active_action = action
            self._set_running(True)
            self._append_log(
                self.tr("[{action}] started").format(action=action),
                {
                    "target": target,
                    "exporter": options.exporter,
                },
            )

            thread = QThread(self)
            worker = SetupWorker(action=action, target=target, options=options, config=config)
            worker.moveToThread(thread)

            thread.started.connect(worker.run)
            worker.succeeded.connect(self._handle_worker_success)
            worker.failed.connect(self._handle_worker_error)
            worker.succeeded.connect(thread.quit)
            worker.failed.connect(thread.quit)
            worker.succeeded.connect(worker.deleteLater)
            worker.failed.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(self._on_thread_finished)

            self._thread = thread
            self._worker = worker
            thread.start()
        except Exception as e:
            self._append_log(
                self.tr("[ui] unexpected error"),
                {"type": type(e).__name__, "message": str(e), "traceback": traceback.format_exc(limit=20)},
            )
            self._set_running(False)

    def _on_success(self, action: str, payload: object, elapsed: float) -> None:
        self._append_log(self.tr("[{action}] completed in {elapsed:.2f}s").format(action=action, elapsed=elapsed), payload)

    def _on_error(self, action: str, payload: object, elapsed: float) -> None:
        self._append_log(self.tr("[{action}] failed in {elapsed:.2f}s").format(action=action, elapsed=elapsed), payload)

    @Slot(object, float)
    def _handle_worker_success(self, payload: object, elapsed: float) -> None:
        try:
            self._on_success(self._active_action or "action", payload, elapsed)
        except Exception as e:
            self._append_log(
                self.tr("[ui] unexpected error"),
                {"type": type(e).__name__, "message": str(e), "traceback": traceback.format_exc(limit=20)},
            )

    @Slot(object, float)
    def _handle_worker_error(self, payload: object, elapsed: float) -> None:
        try:
            self._on_error(self._active_action or "action", payload, elapsed)
        except Exception as e:
            self._append_log(
                self.tr("[ui] unexpected error"),
                {"type": type(e).__name__, "message": str(e), "traceback": traceback.format_exc(limit=20)},
            )

    def _on_thread_finished(self) -> None:
        self._set_running(False)
        self._thread = None
        self._worker = None
        self._active_action = ""


def main() -> int:
    def _excepthook(exc_type, exc_value, exc_tb):
        print("Unhandled exception in game_setup_ui:", file=sys.stderr)
        traceback.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
