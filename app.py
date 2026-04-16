#!/usr/bin/env python3
"""
Mac GPS Spoofer - macOS aplikace pro simulaci GPS polohy na iPhonu.

Pouziva pymobiledevice3 pro komunikaci s pripojenym iPhonem pres USB.
Vyzaduje macOS, Python 3, PyQt6 a pymobiledevice3.
"""

import math
import os
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import time

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QVBoxLayout, QWidget,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_python3():
    """Najde cestu k python3 binarce."""
    for path in [
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
    ]:
        if os.path.isfile(path):
            return path
    return sys.executable


def find_pymobiledevice3():
    """Najde cestu k pymobiledevice3 CLI."""
    for path in [
        "/opt/homebrew/bin/pymobiledevice3",
        "/usr/local/bin/pymobiledevice3",
        os.path.expanduser("~/.local/bin/pymobiledevice3"),
    ]:
        if os.path.isfile(path):
            return path
    try:
        result = subprocess.run(
            ["which", "pymobiledevice3"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "pymobiledevice3"


PYTHON3 = find_python3()
PMD3 = find_pymobiledevice3()


# ---------------------------------------------------------------------------
# Signal bridge (thread-safe Qt signals)
# ---------------------------------------------------------------------------

class StatusBridge(QObject):
    """Thread-safe bridge pro aktualizaci UI z worker threadu."""
    status_changed = pyqtSignal(str)
    device_changed = pyqtSignal(bool)


# ---------------------------------------------------------------------------
# Tunneld Manager
# ---------------------------------------------------------------------------

class TunneldManager:
    """Spravuje tunneld daemon bezici na pozadi."""

    LOG_PATH = os.path.join(tempfile.gettempdir(), "gps_spoofer_tunneld.log")

    def __init__(self, on_status=None):
        self.process = None
        self._rsd_address = None
        self._rsd_port = None
        self._lock = threading.Lock()
        self.on_status = on_status or (lambda msg: None)
        self._reader_thread = None
        self._stop_event = threading.Event()

    def start(self):
        if self.has_tunnel:
            self.on_status("tunneld uz bezi")
            return True

        self.on_status("Spoustim tunneld (bude potreba sudo heslo)...")

        try:
            # Vymazat stary log
            try:
                os.remove(self.LOG_PATH)
            except FileNotFoundError:
                pass

            # Spustit tunneld na pozadi se sudo, vystup do log souboru
            bg_cmd = (
                f"{PYTHON3} -m pymobiledevice3 remote tunneld "
                f"> {shlex.quote(self.LOG_PATH)} 2>&1 &"
            )
            cmd = [
                "osascript", "-e",
                f"do shell script {shlex.quote(bg_cmd)} "
                f"with administrator privileges",
            ]
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self._stop_event.clear()
            self._reader_thread = threading.Thread(
                target=self._read_log_file, daemon=True,
            )
            self._reader_thread.start()
            self.on_status("tunneld spusten, cekam na tunel...")
            return True
        except Exception as e:
            self.on_status(f"Chyba pri spusteni tunneld: {e}")
            return False

    def _read_log_file(self):
        """Cte log soubor tunneld a hleda RSD adresu/port."""
        rsd_pattern = re.compile(r"Created tunnel --rsd\s+(\S+)\s+(\d+)")
        read_pos = 0
        # Cekej az se log soubor objevi (max 30s)
        for _ in range(60):
            if self._stop_event.is_set():
                return
            if os.path.exists(self.LOG_PATH):
                break
            time.sleep(0.5)
        else:
            self.on_status("Chyba: tunneld log se nevytvoril")
            return

        # Cti log dokud se nenajde RSD nebo se nezastavi
        for _ in range(120):  # max 60s (120 * 0.5s)
            if self._stop_event.is_set():
                return
            try:
                with open(self.LOG_PATH, "r") as f:
                    f.seek(read_pos)
                    new_data = f.read()
                    read_pos = f.tell()
                if new_data:
                    for line in new_data.splitlines():
                        match = rsd_pattern.search(line)
                        if match:
                            addr = match.group(1)
                            port = match.group(2)
                            with self._lock:
                                self._rsd_address = addr
                                self._rsd_port = port
                            self.on_status(
                                f"Tunel pripraven: {addr}:{port}"
                            )
                            return
            except Exception:
                pass
            time.sleep(0.5)

        self.on_status("Chyba: tunneld nenasel tunel do 60s")

    def stop(self):
        self._stop_event.set()
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    self.process.kill()
                except Exception:
                    pass
            except Exception:
                pass
        kill_cmd = shlex.quote("pkill -f 'pymobiledevice3 remote tunneld'")
        try:
            subprocess.run(
                ["osascript", "-e",
                 f"do shell script {kill_cmd} with administrator privileges"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass
        self.process = None
        with self._lock:
            self._rsd_address = None
            self._rsd_port = None
        # Uklidit log
        try:
            os.remove(self.LOG_PATH)
        except Exception:
            pass

    def get_rsd(self):
        """Atomicky vrati (rsd_address, rsd_port)."""
        with self._lock:
            return self._rsd_address, self._rsd_port

    @property
    def is_running(self):
        return self.process is not None and self.process.poll() is None

    @property
    def has_tunnel(self):
        with self._lock:
            return self._rsd_address is not None and self._rsd_port is not None


# ---------------------------------------------------------------------------
# Device Detector
# ---------------------------------------------------------------------------

class DeviceDetector:

    @staticmethod
    def list_devices():
        try:
            result = subprocess.run(
                [PMD3, "usbmux", "list"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None

    @staticmethod
    def is_device_connected():
        output = DeviceDetector.list_devices()
        if output is None:
            return False
        return bool(output) and output != "[]"


# ---------------------------------------------------------------------------
# GPS Simulator
# ---------------------------------------------------------------------------

class GPSSimulator:

    def __init__(self, rsd_address, rsd_port, on_status=None):
        self.rsd_address = rsd_address
        self.rsd_port = rsd_port
        self.on_status = on_status or (lambda msg: None)
        self._process = None
        self._lock = threading.Lock()
        self._running = False

    def set_location(self, lat, lon):
        if not (math.isfinite(lat) and math.isfinite(lon)):
            self.on_status("Chyba: neplatne souradnice (NaN/Inf)")
            return False
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            self.on_status("Chyba: souradnice mimo rozsah")
            return False
        try:
            cmd = [
                PMD3, "developer", "dvt", "simulate-location", "set",
                "--rsd", self.rsd_address, self.rsd_port,
                "--", str(lat), str(lon),
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                self.on_status(f"Poloha nastavena: {lat}, {lon}")
                return True
            else:
                error = result.stderr.strip() or result.stdout.strip()
                self.on_status(f"Chyba: {error}")
                return False
        except subprocess.TimeoutExpired:
            self.on_status("Chyba: Timeout pri nastavovani polohy")
            return False
        except Exception as e:
            self.on_status(f"Chyba: {e}")
            return False

    def play_gpx(self, gpx_path):
        with self._lock:
            self._running = True
        try:
            cmd = [
                PMD3, "developer", "dvt", "simulate-location", "play",
                "--rsd", self.rsd_address, self.rsd_port,
                gpx_path,
            ]
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            self.on_status(f"Prehravani trasy: {os.path.basename(gpx_path)}")

            while True:
                with self._lock:
                    if not self._running:
                        break
                if self._process.poll() is not None:
                    break
                line = self._process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    self.on_status(f"GPX: {line}")

            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()

            with self._lock:
                if self._running:
                    self.on_status("Prehravani trasy dokonceno")
        except Exception as e:
            self.on_status(f"Chyba prehravani: {e}")
        finally:
            with self._lock:
                self._running = False
            self._process = None

    def clear_location(self):
        with self._lock:
            self._running = False
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    self._process.kill()
                except Exception:
                    pass
            except Exception:
                pass
        try:
            cmd = [
                PMD3, "developer", "dvt", "simulate-location", "clear",
                "--rsd", self.rsd_address, self.rsd_port,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                self.on_status("Simulace zastavena – skutecna poloha obnovena")
                return True
            else:
                error = result.stderr.strip() or result.stdout.strip()
                self.on_status(f"Chyba pri zastavovani: {error}")
                return False
        except subprocess.TimeoutExpired:
            self.on_status("Chyba: Timeout pri zastavovani simulace")
            return False
        except Exception as e:
            self.on_status(f"Chyba: {e}")
            return False

    @property
    def is_playing(self):
        with self._lock:
            return self._running


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

STYLESHEET = """
QMainWindow {
    background-color: #1e1e2e;
}
QWidget#central {
    background-color: #1e1e2e;
}
QLabel {
    color: #cdd6f4;
}
QLabel#title {
    font-size: 20px;
    font-weight: bold;
    color: #cdd6f4;
}
QLabel#section {
    font-size: 13px;
    font-weight: bold;
    color: #89b4fa;
    padding-top: 4px;
}
QLabel#deviceConnected {
    color: #a6e3a1;
    font-size: 12px;
}
QLabel#deviceDisconnected {
    color: #f38ba8;
    font-size: 12px;
}
QLabel#statusBar {
    background-color: #45475a;
    color: #f9e2af;
    font-size: 11px;
    padding: 6px 8px;
    border-radius: 4px;
}
QWidget#card {
    background-color: #313244;
    border-radius: 8px;
}
QLineEdit {
    background-color: #45475a;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 6px 8px;
    font-family: "Menlo", monospace;
    font-size: 12px;
    selection-background-color: #89b4fa;
}
QLineEdit:focus {
    border: 1px solid #89b4fa;
}
QPushButton {
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 12px;
    font-weight: bold;
}
QPushButton#accent {
    background-color: #89b4fa;
    color: #1e1e2e;
}
QPushButton#accent:hover {
    background-color: #74c7ec;
}
QPushButton#accent:pressed {
    background-color: #89dceb;
}
QPushButton#secondary {
    background-color: #45475a;
    color: #cdd6f4;
}
QPushButton#secondary:hover {
    background-color: #585b70;
}
QPushButton#danger {
    background-color: #f38ba8;
    color: #1e1e2e;
}
QPushButton#danger:hover {
    background-color: #eba0ac;
}
QPushButton#danger:pressed {
    background-color: #f2cdcd;
}
"""


# ---------------------------------------------------------------------------
# GUI Application
# ---------------------------------------------------------------------------

class GPSSpoofApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GPS Spoofer")
        self.setMinimumSize(500, 560)
        self.resize(520, 580)

        # Signal bridge
        self.bridge = StatusBridge()
        self.bridge.status_changed.connect(self._update_status)
        self.bridge.device_changed.connect(self._update_device_ui)

        # Stav
        self.tunneld = TunneldManager(
            on_status=lambda msg: self.bridge.status_changed.emit(msg)
        )
        self.simulator = None
        self.gpx_thread = None
        self.device_connected = False

        # Device detection guard
        self._detecting = False
        self._detect_lock = threading.Lock()

        self._build_ui()

        # Spustit tunneld pri startu
        threading.Thread(target=self._start_tunneld, daemon=True).start()

        # Periodicky kontrolovat pripojeni zarizeni
        self.device_timer = QTimer(self)
        self.device_timer.timeout.connect(self._refresh_device)
        self.device_timer.start(5000)
        self._refresh_device()

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(4)

        # --- Nadpis ---
        title = QLabel("GPS Spoofer")
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addSpacing(8)

        # --- Sekce: Zarizeni ---
        layout.addWidget(self._section_label("Zarizeni"))
        dev_card = self._card()
        dev_layout = QHBoxLayout(dev_card)
        dev_layout.setContentsMargins(12, 10, 12, 10)

        self.device_dot = QLabel("\u2b24")
        self.device_dot.setStyleSheet("color: #f38ba8; font-size: 10px;")
        self.device_dot.setFixedWidth(18)
        dev_layout.addWidget(self.device_dot)

        self.device_label = QLabel("Hledam zarizeni...")
        self.device_label.setObjectName("deviceDisconnected")
        dev_layout.addWidget(self.device_label, 1)

        refresh_btn = QPushButton("Obnovit")
        refresh_btn.setObjectName("secondary")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh_device)
        dev_layout.addWidget(refresh_btn)

        layout.addWidget(dev_card)
        layout.addSpacing(4)

        # --- Sekce: Prehrat trasu ---
        layout.addWidget(self._section_label("Prehrat trasu"))
        gpx_card = self._card()
        gpx_layout = QVBoxLayout(gpx_card)
        gpx_layout.setContentsMargins(12, 10, 12, 10)
        gpx_layout.setSpacing(8)

        file_row = QHBoxLayout()
        self.gpx_entry = QLineEdit()
        self.gpx_entry.setPlaceholderText("Cesta ke GPX souboru...")
        file_row.addWidget(self.gpx_entry, 1)

        browse_btn = QPushButton("Vybrat soubor")
        browse_btn.setObjectName("secondary")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.clicked.connect(self._browse_gpx)
        file_row.addWidget(browse_btn)
        gpx_layout.addLayout(file_row)

        play_btn = QPushButton("\u25b6  Spustit trasu")
        play_btn.setObjectName("accent")
        play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        play_btn.clicked.connect(self._play_gpx)
        gpx_layout.addWidget(play_btn)

        layout.addWidget(gpx_card)
        layout.addSpacing(4)

        # --- Sekce: Jednorazova poloha ---
        layout.addWidget(self._section_label("Jednorazova poloha"))
        loc_card = self._card()
        loc_layout = QVBoxLayout(loc_card)
        loc_layout.setContentsMargins(12, 10, 12, 10)
        loc_layout.setSpacing(8)

        coords_row = QHBoxLayout()
        lat_label = QLabel("Lat:")
        lat_label.setFixedWidth(30)
        coords_row.addWidget(lat_label)
        self.lat_entry = QLineEdit()
        self.lat_entry.setPlaceholderText("50.0880")
        coords_row.addWidget(self.lat_entry, 1)

        coords_row.addSpacing(8)
        lon_label = QLabel("Lon:")
        lon_label.setFixedWidth(30)
        coords_row.addWidget(lon_label)
        self.lon_entry = QLineEdit()
        self.lon_entry.setPlaceholderText("14.4208")
        coords_row.addWidget(self.lon_entry, 1)
        loc_layout.addLayout(coords_row)

        set_btn = QPushButton("\U0001f4cd  Nastavit polohu")
        set_btn.setObjectName("accent")
        set_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        set_btn.clicked.connect(self._set_location)
        loc_layout.addWidget(set_btn)

        layout.addWidget(loc_card)
        layout.addSpacing(4)

        # --- Sekce: Ovladani ---
        layout.addWidget(self._section_label("Ovladani"))
        ctrl_card = self._card()
        ctrl_layout = QVBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(12, 10, 12, 10)

        stop_btn = QPushButton("\u23f9  Zastavit simulaci")
        stop_btn.setObjectName("danger")
        stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        stop_btn.clicked.connect(self._stop_simulation)
        ctrl_layout.addWidget(stop_btn)

        layout.addWidget(ctrl_card)

        # --- Stavovy radek ---
        layout.addStretch(1)
        self.status_label = QLabel("Spoustim...")
        self.status_label.setObjectName("statusBar")
        layout.addWidget(self.status_label)

    # --- UI helpers ---

    @staticmethod
    def _section_label(text):
        label = QLabel(text)
        label.setObjectName("section")
        return label

    @staticmethod
    def _card():
        card = QWidget()
        card.setObjectName("card")
        return card

    # --- Akce ---

    def _start_tunneld(self):
        self.tunneld.start()

    def _refresh_device(self):
        with self._detect_lock:
            if self._detecting:
                return
            self._detecting = True
        threading.Thread(target=self._detect_device, daemon=True).start()

    def _detect_device(self):
        try:
            connected = DeviceDetector.is_device_connected()
            self.device_connected = connected
            self.bridge.device_changed.emit(connected)
        finally:
            with self._detect_lock:
                self._detecting = False

    def _update_device_ui(self, connected):
        if connected:
            self.device_dot.setStyleSheet("color: #a6e3a1; font-size: 10px;")
            self.device_label.setText("iPhone pripojen")
            self.device_label.setObjectName("deviceConnected")
        else:
            self.device_dot.setStyleSheet("color: #f38ba8; font-size: 10px;")
            self.device_label.setText("Zadny iPhone nenalezen")
            self.device_label.setObjectName("deviceDisconnected")
        self.device_label.style().unpolish(self.device_label)
        self.device_label.style().polish(self.device_label)

    def _browse_gpx(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Vyber GPX soubor", "",
            "GPX soubory (*.gpx);;Vsechny soubory (*)",
        )
        if path:
            self.gpx_entry.setText(path)

    def _ensure_simulator(self):
        if not self.tunneld.has_tunnel:
            self._update_status(
                "Tunel neni pripraven. Cekejte nebo restartujte aplikaci."
            )
            return False
        if not self.device_connected:
            self._update_status("iPhone neni pripojen.")
            return False

        rsd_addr, rsd_port = self.tunneld.get_rsd()

        if (self.simulator is not None
                and self.simulator.rsd_address == rsd_addr
                and self.simulator.rsd_port == rsd_port):
            return True

        # RSD se zmenilo nebo simulator neexistuje – vytvorit novy
        if self.simulator and self.simulator.is_playing:
            self.simulator.clear_location()
        self.simulator = GPSSimulator(
            rsd_addr, rsd_port,
            on_status=lambda msg: self.bridge.status_changed.emit(msg),
        )
        return True

    def _play_gpx(self):
        gpx_path = self.gpx_entry.text().strip()
        if not gpx_path:
            self._update_status("Zadna GPX cesta neni zadana.")
            return
        if not os.path.isfile(gpx_path):
            self._update_status("GPX soubor neexistuje.")
            return
        if not self._ensure_simulator():
            return
        if self.simulator.is_playing:
            self._update_status("Trasa uz se prehrava. Nejdriv ji zastavte.")
            return

        self.gpx_thread = threading.Thread(
            target=self.simulator.play_gpx, args=(gpx_path,), daemon=True,
        )
        self.gpx_thread.start()

    def _set_location(self):
        lat_str = self.lat_entry.text().strip()
        lon_str = self.lon_entry.text().strip()

        if not lat_str or not lon_str:
            self._update_status("Zadejte souradnice (latitude a longitude).")
            return
        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except ValueError:
            self._update_status("Neplatne souradnice – zadejte cisla.")
            return

        if not (math.isfinite(lat) and math.isfinite(lon)):
            self._update_status("Neplatne souradnice – zadejte konecna cisla.")
            return
        if not (-90 <= lat <= 90):
            self._update_status("Latitude musi byt mezi -90 a 90.")
            return
        if not (-180 <= lon <= 180):
            self._update_status("Longitude musi byt mezi -180 a 180.")
            return

        if not self._ensure_simulator():
            return

        threading.Thread(
            target=self.simulator.set_location, args=(lat, lon), daemon=True,
        ).start()

    def _stop_simulation(self):
        if not self._ensure_simulator():
            return
        threading.Thread(
            target=self.simulator.clear_location, daemon=True,
        ).start()

    def _update_status(self, msg):
        self.status_label.setText(msg)

    def closeEvent(self, event):
        self._update_status("Ukoncuji...")
        self.device_timer.stop()
        if self.simulator and self.simulator.is_playing:
            self.simulator.clear_location()
        stop_thread = threading.Thread(target=self.tunneld.stop)
        stop_thread.start()
        stop_thread.join(timeout=10)
        event.accept()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)

    window = GPSSpoofApp()
    window.show()

    sys.exit(app.exec())
