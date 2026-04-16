#!/usr/bin/env python3
"""
Comprehensive test suite for GPS Spoofer app.

Runs without a real iPhone, sudo privileges, or network.
All subprocess calls are mocked.
"""

import math
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, Mock, patch, PropertyMock, call

# PyQt6 requires a QApplication before any widget import
from PyQt6.QtWidgets import QApplication, QLabel, QLineEdit
from PyQt6.QtCore import Qt

_app = None


def setUpModule():
    global _app
    if QApplication.instance() is None:
        _app = QApplication([])


def tearDownModule():
    global _app
    _app = None


# Import app module (after QApplication is created)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import app as gps_app


# ===========================================================================
# 1. TestHelperFunctions
# ===========================================================================

class TestHelperFunctions(unittest.TestCase):
    """Test find_python3() and find_pymobiledevice3() path resolution."""

    @patch("app.os.path.isfile")
    def test_find_python3_homebrew(self, mock_isfile):
        """First candidate match (homebrew) is returned."""
        mock_isfile.side_effect = lambda p: p == "/opt/homebrew/bin/python3"
        result = gps_app.find_python3()
        self.assertEqual(result, "/opt/homebrew/bin/python3")

    @patch("app.os.path.isfile")
    def test_find_python3_usr_bin(self, mock_isfile):
        """Falls back to /usr/bin/python3 if homebrew missing."""
        mock_isfile.side_effect = lambda p: p == "/usr/bin/python3"
        result = gps_app.find_python3()
        self.assertEqual(result, "/usr/bin/python3")

    @patch("app.os.path.isfile", return_value=False)
    def test_find_python3_fallback_to_sys_executable(self, mock_isfile):
        """Returns sys.executable if no candidate found."""
        result = gps_app.find_python3()
        self.assertEqual(result, sys.executable)

    @patch("app.os.path.isfile")
    def test_find_pymobiledevice3_first_match(self, mock_isfile):
        mock_isfile.side_effect = (
            lambda p: p == "/opt/homebrew/bin/pymobiledevice3"
        )
        result = gps_app.find_pymobiledevice3()
        self.assertEqual(result, "/opt/homebrew/bin/pymobiledevice3")

    @patch("app.subprocess.run")
    @patch("app.os.path.isfile", return_value=False)
    def test_find_pymobiledevice3_which_fallback(self, mock_isfile, mock_run):
        """Falls back to `which` when no candidate file exists."""
        mock_run.return_value = Mock(
            returncode=0, stdout="/custom/bin/pymobiledevice3\n"
        )
        result = gps_app.find_pymobiledevice3()
        self.assertEqual(result, "/custom/bin/pymobiledevice3")

    @patch("app.subprocess.run", side_effect=Exception("no which"))
    @patch("app.os.path.isfile", return_value=False)
    def test_find_pymobiledevice3_all_fail(self, mock_isfile, mock_run):
        """Returns fallback string when nothing is found."""
        result = gps_app.find_pymobiledevice3()
        self.assertEqual(result, "pymobiledevice3")


# ===========================================================================
# 2. TestStatusBridge
# ===========================================================================

class TestStatusBridge(unittest.TestCase):

    def test_status_changed_signal(self):
        bridge = gps_app.StatusBridge()
        slot = MagicMock()
        bridge.status_changed.connect(slot)
        bridge.status_changed.emit("hello")
        slot.assert_called_once_with("hello")

    def test_device_changed_signal(self):
        bridge = gps_app.StatusBridge()
        slot = MagicMock()
        bridge.device_changed.connect(slot)
        bridge.device_changed.emit(True)
        slot.assert_called_once_with(True)


# ===========================================================================
# 3. TestTunneldManager
# ===========================================================================

class TestTunneldManager(unittest.TestCase):

    def _make_manager(self):
        status_fn = MagicMock()
        mgr = gps_app.TunneldManager(on_status=status_fn)
        return mgr, status_fn

    def test_init_defaults(self):
        mgr, _ = self._make_manager()
        self.assertIsNone(mgr.process)
        self.assertFalse(mgr.has_tunnel)
        self.assertEqual(mgr.get_rsd(), (None, None))

    @patch("app.subprocess.Popen")
    def test_start_success(self, mock_popen):
        proc = MagicMock()
        proc.poll.return_value = None
        proc.stdout = iter([])
        mock_popen.return_value = proc

        mgr, status_fn = self._make_manager()
        result = mgr.start()

        self.assertTrue(result)
        self.assertIs(mgr.process, proc)
        mock_popen.assert_called_once()

    @patch("app.subprocess.Popen")
    def test_start_already_running(self, mock_popen):
        mgr, status_fn = self._make_manager()
        mgr.process = MagicMock()
        mgr.process.poll.return_value = None  # alive

        result = mgr.start()
        self.assertTrue(result)
        mock_popen.assert_not_called()
        status_fn.assert_called_with("tunneld uz bezi")

    @patch("app.subprocess.Popen", side_effect=OSError("denied"))
    def test_start_popen_failure(self, mock_popen):
        mgr, status_fn = self._make_manager()
        result = mgr.start()

        self.assertFalse(result)
        self.assertIn("Chyba", status_fn.call_args[0][0])

    def test_read_output_parses_ipv4_rsd(self):
        mgr, status_fn = self._make_manager()
        mgr.process = MagicMock()
        mgr.process.stdout = iter([
            "Some log line\n",
            "Created tunnel --rsd 10.0.0.1 12345\n",
        ])
        mgr._stop_event = threading.Event()

        mgr._read_output()
        self.assertEqual(mgr.get_rsd(), ("10.0.0.1", "12345"))

    def test_read_output_parses_ipv6_rsd(self):
        mgr, status_fn = self._make_manager()
        mgr.process = MagicMock()
        mgr.process.stdout = iter([
            "Created tunnel --rsd fd71:abcd:1234::1 54321\n",
        ])
        mgr._stop_event = threading.Event()

        mgr._read_output()
        self.assertEqual(mgr.get_rsd(), ("fd71:abcd:1234::1", "54321"))

    def test_read_output_parses_rsd_with_extra_text(self):
        mgr, status_fn = self._make_manager()
        mgr.process = MagicMock()
        mgr.process.stdout = iter([
            "INFO: Created tunnel --rsd 192.168.1.1 8080 for device XYZ\n",
        ])
        mgr._stop_event = threading.Event()

        mgr._read_output()
        self.assertEqual(mgr.get_rsd(), ("192.168.1.1", "8080"))

    def test_read_output_ignores_unrelated_lines(self):
        mgr, _ = self._make_manager()
        mgr.process = MagicMock()
        mgr.process.stdout = iter([
            "Starting tunneld...\n",
            "Waiting for devices...\n",
        ])
        mgr._stop_event = threading.Event()

        mgr._read_output()
        self.assertEqual(mgr.get_rsd(), (None, None))

    def test_read_output_calls_on_status_on_match(self):
        mgr, status_fn = self._make_manager()
        mgr.process = MagicMock()
        mgr.process.stdout = iter([
            "Created tunnel --rsd 10.0.0.1 9999\n",
        ])
        mgr._stop_event = threading.Event()

        mgr._read_output()
        status_fn.assert_called_with("Tunel pripraven: 10.0.0.1:9999")

    def test_read_output_stops_on_stop_event(self):
        mgr, _ = self._make_manager()
        mgr.process = MagicMock()
        mgr._stop_event = threading.Event()
        mgr._stop_event.set()
        # Even with matching lines, should stop immediately
        mgr.process.stdout = iter([
            "Created tunnel --rsd 10.0.0.1 9999\n",
        ])

        mgr._read_output()
        self.assertEqual(mgr.get_rsd(), (None, None))

    def test_read_output_exception_reports_status(self):
        """After fix: exceptions are reported, not silently swallowed."""
        mgr, status_fn = self._make_manager()
        mgr.process = MagicMock()
        mgr.process.stdout = MagicMock()
        mgr.process.stdout.__iter__ = Mock(side_effect=RuntimeError("pipe broken"))
        mgr._stop_event = threading.Event()

        mgr._read_output()
        self.assertTrue(
            any("Chyba" in str(c) for c in status_fn.call_args_list)
        )

    @patch("app.subprocess.run")
    def test_stop_terminates_process(self, mock_run):
        mgr, _ = self._make_manager()
        proc = MagicMock()
        proc.poll.return_value = None  # alive
        mgr.process = proc

        mgr.stop()

        proc.terminate.assert_called_once()
        proc.wait.assert_called_once_with(timeout=5)

    @patch("app.subprocess.run")
    def test_stop_kills_if_terminate_times_out(self, mock_run):
        mgr, _ = self._make_manager()
        proc = MagicMock()
        proc.poll.return_value = None
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=5)
        mgr.process = proc

        mgr.stop()
        proc.kill.assert_called_once()

    @patch("app.subprocess.run")
    def test_stop_clears_rsd_values(self, mock_run):
        mgr, _ = self._make_manager()
        with mgr._lock:
            mgr._rsd_address = "1.2.3.4"
            mgr._rsd_port = "5555"
        mgr.process = None

        mgr.stop()
        self.assertEqual(mgr.get_rsd(), (None, None))

    @patch("app.subprocess.run")
    def test_stop_runs_pkill(self, mock_run):
        mgr, _ = self._make_manager()
        mgr.process = None
        mgr.stop()

        # Should call subprocess.run with osascript pkill
        self.assertTrue(mock_run.called)
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[0], "osascript")

    @patch("app.subprocess.run", side_effect=Exception("pkill failed"))
    def test_stop_handles_pkill_failure(self, mock_run):
        mgr, _ = self._make_manager()
        mgr.process = None
        # Should not raise
        mgr.stop()

    def test_is_running_true(self):
        mgr, _ = self._make_manager()
        mgr.process = MagicMock()
        mgr.process.poll.return_value = None
        self.assertTrue(mgr.is_running)

    def test_is_running_false_no_process(self):
        mgr, _ = self._make_manager()
        mgr.process = None
        self.assertFalse(mgr.is_running)

    def test_is_running_false_process_exited(self):
        mgr, _ = self._make_manager()
        mgr.process = MagicMock()
        mgr.process.poll.return_value = 0
        self.assertFalse(mgr.is_running)

    def test_has_tunnel_true(self):
        mgr, _ = self._make_manager()
        with mgr._lock:
            mgr._rsd_address = "10.0.0.1"
            mgr._rsd_port = "12345"
        self.assertTrue(mgr.has_tunnel)

    def test_has_tunnel_false_partial(self):
        mgr, _ = self._make_manager()
        with mgr._lock:
            mgr._rsd_address = "10.0.0.1"
            mgr._rsd_port = None
        self.assertFalse(mgr.has_tunnel)

    def test_get_rsd_atomicity(self):
        """get_rsd() returns both values atomically."""
        mgr, _ = self._make_manager()
        with mgr._lock:
            mgr._rsd_address = "1.2.3.4"
            mgr._rsd_port = "5678"
        addr, port = mgr.get_rsd()
        self.assertEqual(addr, "1.2.3.4")
        self.assertEqual(port, "5678")

    def test_thread_safety_rsd_access(self):
        """Concurrent reads/writes don't corrupt RSD values."""
        mgr, _ = self._make_manager()
        errors = []

        def writer():
            for i in range(200):
                with mgr._lock:
                    mgr._rsd_address = f"addr_{i}"
                    mgr._rsd_port = str(i)

        def reader():
            for _ in range(200):
                addr, port = mgr.get_rsd()
                if addr is not None and port is not None:
                    # Port string should match the index in the address
                    idx = addr.split("_")[1] if "_" in addr else None
                    if idx is not None and idx != port:
                        errors.append(f"Mismatch: {addr} vs {port}")

        threads = [threading.Thread(target=writer),
                    threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        self.assertEqual(errors, [])


# ===========================================================================
# 4. TestDeviceDetector
# ===========================================================================

class TestDeviceDetector(unittest.TestCase):

    @patch("app.subprocess.run")
    def test_list_devices_success(self, mock_run):
        mock_run.return_value = Mock(
            returncode=0,
            stdout='[{"DeviceName": "iPhone"}]',
        )
        result = gps_app.DeviceDetector.list_devices()
        self.assertEqual(result, '[{"DeviceName": "iPhone"}]')

    @patch("app.subprocess.run")
    def test_list_devices_nonzero_returncode(self, mock_run):
        mock_run.return_value = Mock(returncode=1, stdout="error")
        result = gps_app.DeviceDetector.list_devices()
        self.assertIsNone(result)

    @patch("app.subprocess.run",
           side_effect=subprocess.TimeoutExpired(cmd="x", timeout=10))
    def test_list_devices_timeout(self, mock_run):
        result = gps_app.DeviceDetector.list_devices()
        self.assertIsNone(result)

    @patch("app.subprocess.run", side_effect=OSError("no binary"))
    def test_list_devices_oserror(self, mock_run):
        result = gps_app.DeviceDetector.list_devices()
        self.assertIsNone(result)

    @patch.object(gps_app.DeviceDetector, "list_devices",
                  return_value='[{"DeviceName": "iPhone"}]')
    def test_is_connected_true(self, mock_list):
        self.assertTrue(gps_app.DeviceDetector.is_device_connected())

    @patch.object(gps_app.DeviceDetector, "list_devices", return_value="")
    def test_is_connected_false_empty(self, mock_list):
        self.assertFalse(gps_app.DeviceDetector.is_device_connected())

    @patch.object(gps_app.DeviceDetector, "list_devices", return_value="[]")
    def test_is_connected_false_empty_list(self, mock_list):
        self.assertFalse(gps_app.DeviceDetector.is_device_connected())

    @patch.object(gps_app.DeviceDetector, "list_devices", return_value=None)
    def test_is_connected_false_none(self, mock_list):
        self.assertFalse(gps_app.DeviceDetector.is_device_connected())

    @patch.object(gps_app.DeviceDetector, "list_devices",
                  return_value='[{"DeviceName": "iPhone", "UDID": "abc123"}]')
    def test_is_connected_with_json(self, mock_list):
        self.assertTrue(gps_app.DeviceDetector.is_device_connected())

    @patch("app.subprocess.run")
    def test_list_devices_whitespace_output(self, mock_run):
        """Whitespace-only output should be treated as no devices."""
        mock_run.return_value = Mock(returncode=0, stdout="  \n  ")
        result = gps_app.DeviceDetector.list_devices()
        # list_devices returns stripped output
        self.assertEqual(result, "")


# ===========================================================================
# 5. TestGPSSimulator
# ===========================================================================

class TestGPSSimulator(unittest.TestCase):

    def _make_sim(self):
        status_fn = MagicMock()
        sim = gps_app.GPSSimulator("10.0.0.1", "12345", on_status=status_fn)
        return sim, status_fn

    def test_init(self):
        sim, _ = self._make_sim()
        self.assertEqual(sim.rsd_address, "10.0.0.1")
        self.assertEqual(sim.rsd_port, "12345")
        self.assertFalse(sim.is_playing)

    # --- set_location ---

    @patch("app.subprocess.run")
    def test_set_location_success(self, mock_run):
        mock_run.return_value = Mock(returncode=0)
        sim, status_fn = self._make_sim()
        result = sim.set_location(50.0, 14.0)
        self.assertTrue(result)
        status_fn.assert_called_with("Poloha nastavena: 50.0, 14.0")

    @patch("app.subprocess.run")
    def test_set_location_failure(self, mock_run):
        mock_run.return_value = Mock(
            returncode=1, stderr="device error", stdout=""
        )
        sim, status_fn = self._make_sim()
        result = sim.set_location(50.0, 14.0)
        self.assertFalse(result)

    @patch("app.subprocess.run",
           side_effect=subprocess.TimeoutExpired(cmd="x", timeout=15))
    def test_set_location_timeout(self, mock_run):
        sim, status_fn = self._make_sim()
        result = sim.set_location(50.0, 14.0)
        self.assertFalse(result)
        self.assertIn("Timeout", status_fn.call_args[0][0])

    @patch("app.subprocess.run", side_effect=OSError("no binary"))
    def test_set_location_exception(self, mock_run):
        sim, status_fn = self._make_sim()
        result = sim.set_location(50.0, 14.0)
        self.assertFalse(result)

    def test_set_location_validates_nan(self):
        sim, status_fn = self._make_sim()
        result = sim.set_location(float("nan"), 14.0)
        self.assertFalse(result)
        self.assertIn("NaN", status_fn.call_args[0][0])

    def test_set_location_validates_inf(self):
        sim, status_fn = self._make_sim()
        result = sim.set_location(float("inf"), 14.0)
        self.assertFalse(result)

    def test_set_location_validates_range_lat(self):
        sim, status_fn = self._make_sim()
        result = sim.set_location(91.0, 14.0)
        self.assertFalse(result)
        self.assertIn("rozsah", status_fn.call_args[0][0])

    def test_set_location_validates_range_lon(self):
        sim, status_fn = self._make_sim()
        result = sim.set_location(50.0, 181.0)
        self.assertFalse(result)

    @patch("app.subprocess.run")
    def test_set_location_command_structure(self, mock_run):
        """Verify exact subprocess command arguments."""
        mock_run.return_value = Mock(returncode=0)
        sim, _ = self._make_sim()
        sim.set_location(50.5, -14.3)

        cmd = mock_run.call_args[0][0]
        self.assertIn("simulate-location", cmd)
        self.assertIn("set", cmd)
        self.assertIn("--rsd", cmd)
        self.assertIn("10.0.0.1", cmd)
        self.assertIn("12345", cmd)
        self.assertIn("--", cmd)
        self.assertIn("50.5", cmd)
        self.assertIn("-14.3", cmd)

    @patch("app.subprocess.run")
    def test_set_location_boundary_valid(self, mock_run):
        """Boundary values lat=90, lon=180 should pass."""
        mock_run.return_value = Mock(returncode=0)
        sim, _ = self._make_sim()
        self.assertTrue(sim.set_location(90.0, 180.0))
        self.assertTrue(sim.set_location(-90.0, -180.0))

    # --- play_gpx ---

    @patch("app.subprocess.Popen")
    def test_play_gpx_success(self, mock_popen):
        proc = MagicMock()
        proc.poll.side_effect = [None, None, 0]
        proc.stdout.readline.side_effect = ["line1\n", "line2\n", ""]
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        sim, status_fn = self._make_sim()
        sim.play_gpx("/path/to/file.gpx")

        self.assertFalse(sim.is_playing)
        # Should have reported lines
        calls = [c[0][0] for c in status_fn.call_args_list]
        self.assertTrue(any("GPX: line1" in c for c in calls))

    @patch("app.subprocess.Popen")
    def test_play_gpx_stopped_by_clear(self, mock_popen):
        """Playback stops when _running is set to False."""
        proc = MagicMock()
        proc.poll.return_value = None

        call_count = [0]

        def readline_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return "line1\n"
            # After first line, simulate stop
            with sim._lock:
                sim._running = False
            return "line2\n"

        proc.stdout.readline = readline_side_effect
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        sim, status_fn = self._make_sim()
        sim.play_gpx("/path/to/file.gpx")
        self.assertFalse(sim.is_playing)

    @patch("app.subprocess.Popen")
    def test_play_gpx_process_dies(self, mock_popen):
        """Playback exits when process dies."""
        proc = MagicMock()
        proc.poll.return_value = 1  # Process already exited
        proc.stdout.readline.return_value = ""
        proc.wait.return_value = 1
        mock_popen.return_value = proc

        sim, _ = self._make_sim()
        sim.play_gpx("/path/to/file.gpx")
        self.assertFalse(sim.is_playing)

    @patch("app.subprocess.Popen", side_effect=OSError("no binary"))
    def test_play_gpx_exception(self, mock_popen):
        sim, status_fn = self._make_sim()
        sim.play_gpx("/path/to/file.gpx")
        self.assertFalse(sim.is_playing)
        calls = [c[0][0] for c in status_fn.call_args_list]
        self.assertTrue(any("Chyba" in c for c in calls))

    @patch("app.subprocess.Popen")
    def test_play_gpx_sets_running_flag(self, mock_popen):
        """is_playing is True during playback."""
        started = threading.Event()
        proceed = threading.Event()

        proc = MagicMock()
        proc.poll.return_value = None

        def readline():
            started.set()
            proceed.wait(timeout=2)
            return ""

        proc.stdout.readline = readline
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        sim, _ = self._make_sim()
        t = threading.Thread(target=sim.play_gpx, args=("/file.gpx",))
        t.start()

        started.wait(timeout=2)
        self.assertTrue(sim.is_playing)

        proceed.set()
        t.join(timeout=2)
        self.assertFalse(sim.is_playing)

    # --- clear_location ---

    @patch("app.subprocess.run")
    def test_clear_location_success(self, mock_run):
        mock_run.return_value = Mock(returncode=0)
        sim, status_fn = self._make_sim()
        result = sim.clear_location()
        self.assertTrue(result)
        self.assertIn("zastavena", status_fn.call_args[0][0])

    @patch("app.subprocess.run")
    def test_clear_location_failure(self, mock_run):
        mock_run.return_value = Mock(
            returncode=1, stderr="error", stdout=""
        )
        sim, _ = self._make_sim()
        self.assertFalse(sim.clear_location())

    @patch("app.subprocess.run",
           side_effect=subprocess.TimeoutExpired(cmd="x", timeout=15))
    def test_clear_location_timeout(self, mock_run):
        """After fix: TimeoutExpired shows correct message."""
        sim, status_fn = self._make_sim()
        result = sim.clear_location()
        self.assertFalse(result)
        self.assertIn("Timeout", status_fn.call_args[0][0])

    @patch("app.subprocess.run")
    def test_clear_location_terminates_playing(self, mock_run):
        mock_run.return_value = Mock(returncode=0)
        sim, _ = self._make_sim()
        proc = MagicMock()
        proc.poll.return_value = None  # alive
        sim._process = proc

        sim.clear_location()
        proc.terminate.assert_called_once()

    @patch("app.subprocess.run")
    def test_clear_location_kills_if_terminate_fails(self, mock_run):
        mock_run.return_value = Mock(returncode=0)
        sim, _ = self._make_sim()
        proc = MagicMock()
        proc.poll.return_value = None
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=5)
        sim._process = proc

        sim.clear_location()
        proc.kill.assert_called_once()

    @patch("app.subprocess.run")
    def test_clear_sets_running_false(self, mock_run):
        mock_run.return_value = Mock(returncode=0)
        sim, _ = self._make_sim()
        with sim._lock:
            sim._running = True
        sim.clear_location()
        self.assertFalse(sim.is_playing)

    @patch("app.subprocess.run")
    def test_clear_when_not_playing(self, mock_run):
        """Clear works even when nothing is playing."""
        mock_run.return_value = Mock(returncode=0)
        sim, _ = self._make_sim()
        self.assertTrue(sim.clear_location())

    def test_is_playing_property(self):
        sim, _ = self._make_sim()
        self.assertFalse(sim.is_playing)
        with sim._lock:
            sim._running = True
        self.assertTrue(sim.is_playing)

    def test_thread_safety_running_flag(self):
        """Concurrent writes to _running don't corrupt state."""
        sim, _ = self._make_sim()
        errors = []

        def toggler():
            for _ in range(500):
                with sim._lock:
                    sim._running = True
                with sim._lock:
                    sim._running = False

        threads = [threading.Thread(target=toggler) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        # Final state should be False (all togglers end with False)
        self.assertFalse(sim.is_playing)


# ===========================================================================
# 6. TestGPSSpoofAppCreation
# ===========================================================================

class TestGPSSpoofAppCreation(unittest.TestCase):
    """Test GUI window creation and widget existence."""

    @classmethod
    def setUpClass(cls):
        cls.patcher_tunneld = patch.object(
            gps_app.TunneldManager, "start", return_value=True
        )
        cls.patcher_device = patch.object(
            gps_app.DeviceDetector, "is_device_connected", return_value=False
        )
        cls.patcher_tunneld.start()
        cls.patcher_device.start()
        cls.window = gps_app.GPSSpoofApp()

    @classmethod
    def tearDownClass(cls):
        cls.window.device_timer.stop()
        cls.window.close()
        cls.patcher_tunneld.stop()
        cls.patcher_device.stop()

    def test_window_title(self):
        self.assertEqual(self.window.windowTitle(), "GPS Spoofer")

    def test_window_minimum_size(self):
        self.assertGreaterEqual(self.window.minimumWidth(), 500)
        self.assertGreaterEqual(self.window.minimumHeight(), 560)

    def test_central_widget_exists(self):
        self.assertIsNotNone(self.window.centralWidget())

    def test_lat_entry_exists(self):
        self.assertIsInstance(self.window.lat_entry, QLineEdit)

    def test_lon_entry_exists(self):
        self.assertIsInstance(self.window.lon_entry, QLineEdit)

    def test_gpx_entry_exists(self):
        self.assertIsInstance(self.window.gpx_entry, QLineEdit)

    def test_status_label_exists(self):
        self.assertIsInstance(self.window.status_label, QLabel)

    def test_device_label_exists(self):
        self.assertIsInstance(self.window.device_label, QLabel)

    def test_device_dot_exists(self):
        self.assertIsInstance(self.window.device_dot, QLabel)

    def test_bridge_signals_exist(self):
        self.assertIsNotNone(self.window.bridge.status_changed)
        self.assertIsNotNone(self.window.bridge.device_changed)

    def test_device_timer_running(self):
        self.assertTrue(self.window.device_timer.isActive())


# ===========================================================================
# 7. TestGPSSpoofAppInputValidation
# ===========================================================================

class TestGPSSpoofAppInputValidation(unittest.TestCase):
    """Test input validation in the GUI."""

    @classmethod
    def setUpClass(cls):
        cls.patcher_tunneld = patch.object(
            gps_app.TunneldManager, "start", return_value=True
        )
        cls.patcher_device = patch.object(
            gps_app.DeviceDetector, "is_device_connected", return_value=False
        )
        cls.patcher_tunneld.start()
        cls.patcher_device.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher_tunneld.stop()
        cls.patcher_device.stop()

    def setUp(self):
        self.window = gps_app.GPSSpoofApp()

    def tearDown(self):
        self.window.device_timer.stop()
        self.window.close()

    def _set_coords(self, lat, lon):
        self.window.lat_entry.setText(str(lat))
        self.window.lon_entry.setText(str(lon))

    def test_set_location_empty_lat(self):
        self.window.lat_entry.setText("")
        self.window.lon_entry.setText("14.0")
        self.window._set_location()
        self.assertIn("Zadejte", self.window.status_label.text())

    def test_set_location_empty_lon(self):
        self.window.lat_entry.setText("50.0")
        self.window.lon_entry.setText("")
        self.window._set_location()
        self.assertIn("Zadejte", self.window.status_label.text())

    def test_set_location_non_numeric_lat(self):
        self._set_coords("abc", "14.0")
        self.window._set_location()
        self.assertIn("Neplatne", self.window.status_label.text())

    def test_set_location_non_numeric_lon(self):
        self._set_coords("50.0", "xyz")
        self.window._set_location()
        self.assertIn("Neplatne", self.window.status_label.text())

    def test_set_location_lat_too_high(self):
        self._set_coords("91", "14.0")
        self.window._set_location()
        self.assertIn("Latitude", self.window.status_label.text())

    def test_set_location_lat_too_low(self):
        self._set_coords("-91", "14.0")
        self.window._set_location()
        self.assertIn("Latitude", self.window.status_label.text())

    def test_set_location_lon_too_high(self):
        self._set_coords("50.0", "181")
        self.window._set_location()
        self.assertIn("Longitude", self.window.status_label.text())

    def test_set_location_lon_too_low(self):
        self._set_coords("50.0", "-181")
        self.window._set_location()
        self.assertIn("Longitude", self.window.status_label.text())

    def test_set_location_nan(self):
        self._set_coords("nan", "14.0")
        self.window._set_location()
        self.assertIn("konecna", self.window.status_label.text())

    def test_set_location_inf(self):
        self._set_coords("inf", "14.0")
        self.window._set_location()
        self.assertIn("konecna", self.window.status_label.text())

    def test_set_location_negative_inf(self):
        self._set_coords("-inf", "14.0")
        self.window._set_location()
        self.assertIn("konecna", self.window.status_label.text())

    def test_set_location_boundary_valid(self):
        """lat=90, lon=180 passes validation (fails at _ensure_simulator)."""
        self._set_coords("90", "180")
        self.window._set_location()
        # Should pass validation, fail at tunnel check
        status = self.window.status_label.text()
        self.assertNotIn("Latitude", status)
        self.assertNotIn("Longitude", status)
        self.assertNotIn("konecna", status)

    def test_set_location_boundary_negative_valid(self):
        self._set_coords("-90", "-180")
        self.window._set_location()
        status = self.window.status_label.text()
        self.assertNotIn("Latitude", status)
        self.assertNotIn("Longitude", status)

    def test_play_gpx_empty_path(self):
        self.window.gpx_entry.setText("")
        self.window._play_gpx()
        self.assertIn("Zadna", self.window.status_label.text())

    def test_play_gpx_nonexistent_file(self):
        self.window.gpx_entry.setText("/nonexistent/path/file.gpx")
        self.window._play_gpx()
        self.assertIn("neexistuje", self.window.status_label.text())

    def test_set_location_no_tunnel(self):
        """Without tunnel, _ensure_simulator fails."""
        self._set_coords("50.0", "14.0")
        self.window._set_location()
        self.assertIn("Tunel", self.window.status_label.text())

    def test_play_gpx_no_tunnel(self):
        """Without tunnel, _ensure_simulator fails."""
        # Create a temp GPX so file check passes
        with tempfile.NamedTemporaryFile(suffix=".gpx", delete=False) as f:
            f.write(b"<gpx></gpx>")
            gpx_path = f.name
        try:
            self.window.gpx_entry.setText(gpx_path)
            self.window._play_gpx()
            self.assertIn("Tunel", self.window.status_label.text())
        finally:
            os.unlink(gpx_path)


# ===========================================================================
# 8. TestGPSSpoofAppActions
# ===========================================================================

class TestGPSSpoofAppActions(unittest.TestCase):
    """Test button handlers and simulator interactions."""

    @classmethod
    def setUpClass(cls):
        cls.patcher_tunneld = patch.object(
            gps_app.TunneldManager, "start", return_value=True
        )
        cls.patcher_device = patch.object(
            gps_app.DeviceDetector, "is_device_connected", return_value=False
        )
        cls.patcher_tunneld.start()
        cls.patcher_device.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher_tunneld.stop()
        cls.patcher_device.stop()

    def setUp(self):
        self.window = gps_app.GPSSpoofApp()

    def tearDown(self):
        self.window.device_timer.stop()
        self.window.close()

    def _setup_ready_state(self):
        """Set up window so tunnel and device are ready."""
        with self.window.tunneld._lock:
            self.window.tunneld._rsd_address = "10.0.0.1"
            self.window.tunneld._rsd_port = "12345"
        self.window.device_connected = True

    def test_ensure_simulator_creates_instance(self):
        self._setup_ready_state()
        result = self.window._ensure_simulator()
        self.assertTrue(result)
        self.assertIsNotNone(self.window.simulator)

    def test_ensure_simulator_reuses_instance(self):
        """Same RSD values -> same simulator object."""
        self._setup_ready_state()
        self.window._ensure_simulator()
        sim1 = self.window.simulator
        self.window._ensure_simulator()
        sim2 = self.window.simulator
        self.assertIs(sim1, sim2)

    def test_ensure_simulator_replaces_on_rsd_change(self):
        """Changed RSD -> new simulator, old one cleaned up."""
        self._setup_ready_state()
        self.window._ensure_simulator()
        sim1 = self.window.simulator

        # Change RSD
        with self.window.tunneld._lock:
            self.window.tunneld._rsd_address = "10.0.0.2"
            self.window.tunneld._rsd_port = "54321"
        self.window._ensure_simulator()
        sim2 = self.window.simulator

        self.assertIsNot(sim1, sim2)
        self.assertEqual(sim2.rsd_address, "10.0.0.2")

    @patch("app.subprocess.run")
    def test_set_location_calls_simulator(self, mock_run):
        mock_run.return_value = Mock(returncode=0)
        self._setup_ready_state()
        self.window.lat_entry.setText("50.0")
        self.window.lon_entry.setText("14.0")
        self.window._set_location()
        # Give thread time to run
        time.sleep(0.2)
        mock_run.assert_called()

    @patch("app.subprocess.Popen")
    def test_play_gpx_calls_simulator(self, mock_popen):
        proc = MagicMock()
        proc.poll.return_value = 0
        proc.stdout.readline.return_value = ""
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        self._setup_ready_state()
        with tempfile.NamedTemporaryFile(suffix=".gpx", delete=False) as f:
            f.write(b"<gpx></gpx>")
            gpx_path = f.name
        try:
            self.window.gpx_entry.setText(gpx_path)
            self.window._play_gpx()
            time.sleep(0.2)
            mock_popen.assert_called()
        finally:
            os.unlink(gpx_path)

    def test_play_gpx_rejects_while_playing(self):
        self._setup_ready_state()
        self.window._ensure_simulator()
        with self.window.simulator._lock:
            self.window.simulator._running = True
        with tempfile.NamedTemporaryFile(suffix=".gpx", delete=False) as f:
            f.write(b"<gpx></gpx>")
            gpx_path = f.name
        try:
            self.window.gpx_entry.setText(gpx_path)
            self.window._play_gpx()
            self.assertIn("prehrava", self.window.status_label.text())
        finally:
            os.unlink(gpx_path)

    @patch("app.subprocess.run")
    def test_stop_calls_clear(self, mock_run):
        mock_run.return_value = Mock(returncode=0)
        self._setup_ready_state()
        self.window._stop_simulation()
        time.sleep(0.2)
        mock_run.assert_called()

    def test_stop_no_tunnel_shows_error(self):
        # No tunnel set up
        self.window._stop_simulation()
        self.assertIn("Tunel", self.window.status_label.text())

    def test_update_device_ui_connected(self):
        self.window._update_device_ui(True)
        self.assertEqual(self.window.device_label.text(), "iPhone pripojen")
        self.assertIn("#a6e3a1", self.window.device_dot.styleSheet())

    def test_update_device_ui_disconnected(self):
        self.window._update_device_ui(False)
        self.assertEqual(
            self.window.device_label.text(), "Zadny iPhone nenalezen"
        )
        self.assertIn("#f38ba8", self.window.device_dot.styleSheet())

    def test_update_status(self):
        self.window._update_status("test message")
        self.assertEqual(self.window.status_label.text(), "test message")

    @patch("app.QFileDialog.getOpenFileName",
           return_value=("/tmp/test.gpx", ""))
    def test_browse_gpx_sets_path(self, mock_dialog):
        self.window._browse_gpx()
        self.assertEqual(self.window.gpx_entry.text(), "/tmp/test.gpx")

    @patch("app.QFileDialog.getOpenFileName", return_value=("", ""))
    def test_browse_gpx_cancelled(self, mock_dialog):
        self.window.gpx_entry.setText("original")
        self.window._browse_gpx()
        self.assertEqual(self.window.gpx_entry.text(), "original")

    @patch.object(gps_app.TunneldManager, "stop")
    def test_close_event_stops_timer(self, mock_stop):
        self.window.close()
        self.assertFalse(self.window.device_timer.isActive())

    @patch.object(gps_app.TunneldManager, "stop")
    def test_close_event_stops_tunneld(self, mock_stop):
        self.window.close()
        mock_stop.assert_called_once()


# ===========================================================================
# 9. TestIntegrationFlows
# ===========================================================================

class TestIntegrationFlows(unittest.TestCase):
    """Integration-style tests for full user flows."""

    @classmethod
    def setUpClass(cls):
        cls.patcher_tunneld = patch.object(
            gps_app.TunneldManager, "start", return_value=True
        )
        cls.patcher_device = patch.object(
            gps_app.DeviceDetector, "is_device_connected", return_value=False
        )
        cls.patcher_tunneld.start()
        cls.patcher_device.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher_tunneld.stop()
        cls.patcher_device.stop()

    def setUp(self):
        self.window = gps_app.GPSSpoofApp()

    def tearDown(self):
        self.window.device_timer.stop()
        self.window.close()

    @patch("app.subprocess.run")
    def test_full_flow_set_location(self, mock_run):
        """Full flow: tunnel ready -> device detected -> set location."""
        mock_run.return_value = Mock(returncode=0)

        # Simulate tunnel ready
        with self.window.tunneld._lock:
            self.window.tunneld._rsd_address = "10.0.0.1"
            self.window.tunneld._rsd_port = "12345"
        self.window.device_connected = True

        # Set location
        self.window.lat_entry.setText("50.088")
        self.window.lon_entry.setText("14.421")
        self.window._set_location()
        time.sleep(0.3)

        # Verify subprocess was called with correct coords
        self.assertTrue(mock_run.called)
        cmd = mock_run.call_args[0][0]
        self.assertIn("50.088", cmd)
        self.assertIn("14.421", cmd)

    def test_error_flow_no_tunnel_then_set(self):
        """No tunnel -> set location -> proper error."""
        self.window.lat_entry.setText("50.0")
        self.window.lon_entry.setText("14.0")
        self.window._set_location()
        self.assertIn("Tunel", self.window.status_label.text())

    def test_error_flow_no_device_then_play(self):
        """Tunnel OK but no device -> play GPX -> error."""
        with self.window.tunneld._lock:
            self.window.tunneld._rsd_address = "10.0.0.1"
            self.window.tunneld._rsd_port = "12345"
        self.window.device_connected = False

        with tempfile.NamedTemporaryFile(suffix=".gpx", delete=False) as f:
            f.write(b"<gpx></gpx>")
            gpx_path = f.name
        try:
            self.window.gpx_entry.setText(gpx_path)
            self.window._play_gpx()
            self.assertIn("iPhone", self.window.status_label.text())
        finally:
            os.unlink(gpx_path)

    def test_tunnel_dies_mid_session(self):
        """Tunnel process exits -> is_running returns False."""
        with self.window.tunneld._lock:
            self.window.tunneld._rsd_address = "10.0.0.1"
            self.window.tunneld._rsd_port = "12345"
        proc = MagicMock()
        proc.poll.return_value = 1  # exited
        self.window.tunneld.process = proc
        self.assertFalse(self.window.tunneld.is_running)

    def test_restart_after_tunnel_death(self):
        """After tunnel dies, start() creates a new process."""
        # Temporarily unpatch TunneldManager.start for this test
        self.patcher_tunneld.stop()
        try:
            with patch("app.subprocess.Popen") as mock_popen:
                proc = MagicMock()
                proc.poll.return_value = None
                proc.stdout = iter([])
                mock_popen.return_value = proc

                mgr = gps_app.TunneldManager(on_status=MagicMock())
                mgr.process = MagicMock()
                mgr.process.poll.return_value = 1  # dead
                result = mgr.start()
                self.assertTrue(result)
                mock_popen.assert_called_once()
        finally:
            self.patcher_tunneld.start()

    @patch("app.subprocess.run")
    def test_full_flow_play_and_stop(self, mock_run):
        """Play GPX -> stop simulation."""
        mock_run.return_value = Mock(returncode=0)

        with self.window.tunneld._lock:
            self.window.tunneld._rsd_address = "10.0.0.1"
            self.window.tunneld._rsd_port = "12345"
        self.window.device_connected = True

        # Ensure simulator exists
        self.window._ensure_simulator()
        # Simulate that playback is running
        with self.window.simulator._lock:
            self.window.simulator._running = True

        # Stop simulation
        self.window._stop_simulation()
        time.sleep(0.3)
        # clear_location should have been called
        self.assertTrue(mock_run.called)


# ===========================================================================
# 10. TestEdgeCases
# ===========================================================================

class TestEdgeCases(unittest.TestCase):
    """Edge case and stress tests."""

    @classmethod
    def setUpClass(cls):
        cls.patcher_tunneld = patch.object(
            gps_app.TunneldManager, "start", return_value=True
        )
        cls.patcher_device = patch.object(
            gps_app.DeviceDetector, "is_device_connected", return_value=False
        )
        cls.patcher_tunneld.start()
        cls.patcher_device.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher_tunneld.stop()
        cls.patcher_device.stop()

    def setUp(self):
        self.window = gps_app.GPSSpoofApp()

    def tearDown(self):
        self.window.device_timer.stop()
        self.window.close()

    @patch("app.subprocess.run")
    def test_rapid_set_location(self, mock_run):
        """Calling _set_location 10 times rapidly doesn't crash."""
        mock_run.return_value = Mock(returncode=0)
        with self.window.tunneld._lock:
            self.window.tunneld._rsd_address = "10.0.0.1"
            self.window.tunneld._rsd_port = "12345"
        self.window.device_connected = True

        for i in range(10):
            self.window.lat_entry.setText(str(50.0 + i * 0.001))
            self.window.lon_entry.setText("14.0")
            self.window._set_location()

        time.sleep(0.5)
        # Should not have crashed; all calls should complete

    def test_concurrent_detect_device(self):
        """Multiple _refresh_device calls don't pile up threads."""
        call_count = [0]
        original_detect = self.window._detect_device

        def counting_detect():
            call_count[0] += 1
            time.sleep(0.1)  # Simulate slow detection
            with self.window._detect_lock:
                self.window._detecting = False

        with patch.object(self.window, "_detect_device", counting_detect):
            # Reset guard
            with self.window._detect_lock:
                self.window._detecting = False

            # Call refresh 5 times quickly
            for _ in range(5):
                self.window._refresh_device()

            time.sleep(0.5)
            # Due to guard, should be less than 5 actual detections
            self.assertLess(call_count[0], 5)

    def test_very_long_gpx_path(self):
        """1000-char path doesn't crash, shows file-not-found."""
        long_path = "/tmp/" + "a" * 990 + ".gpx"
        self.window.gpx_entry.setText(long_path)
        self.window._play_gpx()
        self.assertIn("neexistuje", self.window.status_label.text())

    def test_unicode_gpx_path(self):
        """Unicode characters in path are handled."""
        self.window.gpx_entry.setText("/tmp/trasa-cesky/pruvod\u010de.gpx")
        self.window._play_gpx()
        self.assertIn("neexistuje", self.window.status_label.text())

    def test_rsd_port_out_of_range(self):
        """Port 99999 is extracted by parser (validation elsewhere)."""
        mgr = gps_app.TunneldManager()
        mgr.process = MagicMock()
        mgr.process.stdout = iter([
            "Created tunnel --rsd 10.0.0.1 99999\n",
        ])
        mgr._stop_event = threading.Event()
        mgr._read_output()
        self.assertEqual(mgr.get_rsd(), ("10.0.0.1", "99999"))

    def test_rsd_port_zero(self):
        """Port 0 is extracted."""
        mgr = gps_app.TunneldManager()
        mgr.process = MagicMock()
        mgr.process.stdout = iter(["Created tunnel --rsd 10.0.0.1 0\n"])
        mgr._stop_event = threading.Event()
        mgr._read_output()
        self.assertEqual(mgr.get_rsd(), ("10.0.0.1", "0"))

    def test_set_location_many_decimals(self):
        """Many decimal places pass validation."""
        with self.window.tunneld._lock:
            self.window.tunneld._rsd_address = "10.0.0.1"
            self.window.tunneld._rsd_port = "12345"
        self.window.device_connected = True

        self.window.lat_entry.setText("50.123456789012345")
        self.window.lon_entry.setText("14.987654321098765")
        # Should pass validation (fails at subprocess, but that's mocked away)
        # We just verify no crash or validation error
        with patch("app.subprocess.run", return_value=Mock(returncode=0)):
            self.window._set_location()
            time.sleep(0.2)
            status = self.window.status_label.text()
            self.assertNotIn("Neplatne", status)
            self.assertNotIn("Latitude", status)

    @patch("app.subprocess.run")
    def test_play_gpx_while_location_set(self, mock_run):
        """Set location then play GPX -> same simulator reused."""
        mock_run.return_value = Mock(returncode=0)
        with self.window.tunneld._lock:
            self.window.tunneld._rsd_address = "10.0.0.1"
            self.window.tunneld._rsd_port = "12345"
        self.window.device_connected = True

        self.window._ensure_simulator()
        sim_ref = self.window.simulator

        # Calling ensure again with same RSD reuses
        self.window._ensure_simulator()
        self.assertIs(self.window.simulator, sim_ref)

    def test_empty_tunneld_output(self):
        """Tunneld producing no output leaves RSD as None."""
        mgr = gps_app.TunneldManager()
        mgr.process = MagicMock()
        mgr.process.stdout = iter([])
        mgr._stop_event = threading.Event()
        mgr._read_output()
        self.assertEqual(mgr.get_rsd(), (None, None))


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    unittest.main()
