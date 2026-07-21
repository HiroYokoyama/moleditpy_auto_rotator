"""
tests/test_auto_rotator.py
Unit tests for the auto rotator plugin.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=too-few-public-methods,protected-access,invalid-name

import importlib.util as importlib_util
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
import numpy as np


# ---------------------------------------------------------------------------
# Install Qt stubs so the plugin imports cleanly in a headless environment.
# ---------------------------------------------------------------------------
def _install_qt_stubs():
    qt_core = types.ModuleType("PyQt6.QtCore")

    class _QCoreApplication:
        @staticmethod
        def processEvents():
            pass
    qt_core.QCoreApplication = _QCoreApplication

    class _QTimer:
        def __init__(self, *args, **kwargs):
            self._active = False
            self.timeout = MagicMock()
        def setInterval(self, _ms):
            pass
        def start(self):
            self._active = True
        def stop(self):
            self._active = False
        def isActive(self):
            return self._active
    qt_core.QTimer = _QTimer

    pyqt6 = types.ModuleType("PyQt6")
    pyqt6.QtCore = qt_core
    sys.modules["PyQt6"] = pyqt6
    sys.modules["PyQt6.QtCore"] = qt_core

    qt_widgets = types.ModuleType("PyQt6.QtWidgets")

    class _QDialog:
        def __init__(self, parent=None):
            self._parent = parent
            self._window_title = ""
        def setWindowTitle(self, title):
            self._window_title = title
        def show(self):
            pass
        def close(self):
            pass
        def closeEvent(self, event):
            pass
    qt_widgets.QDialog = _QDialog

    for name in [
        "QVBoxLayout", "QHBoxLayout", "QComboBox", "QSpinBox",
        "QPushButton", "QFormLayout"
    ]:
        setattr(qt_widgets, name, lambda *args, **kwargs: MagicMock())

    pyqt6.QtWidgets = qt_widgets
    sys.modules["PyQt6.QtWidgets"] = qt_widgets


_install_qt_stubs()


def _load_module_direct(relpath, module_name):
    src = os.path.join(os.path.dirname(__file__), "..", relpath)
    src = os.path.normpath(src)
    spec = importlib_util.spec_from_file_location(module_name, src)
    mod = importlib_util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


rot_mod = _load_module_direct("auto_rotator.py", "auto_rotator_under_test")


class TestMetadata(unittest.TestCase):
    def test_metadata(self):
        self.assertEqual(rot_mod.PLUGIN_NAME, "Auto Rotator")
        self.assertEqual(rot_mod.PLUGIN_AUTHOR, "HiroYokoyama")
        self.assertEqual(rot_mod.PLUGIN_CATEGORY, "View")

    def test_version_is_semver(self):
        parts = rot_mod.PLUGIN_VERSION.split(".")
        self.assertEqual(len(parts), 3)
        self.assertTrue(all(p.isdigit() for p in parts))


class TestInitialize(unittest.TestCase):
    def test_initialize_registers_view_action(self):
        context = MagicMock()
        rot_mod.initialize(context)
        context.add_menu_action.assert_called_once()
        args, _ = context.add_menu_action.call_args
        self.assertEqual(args[0], "View/Auto Rotator...")


class TestShowRotatorDialog(unittest.TestCase):
    def test_reuses_existing_window(self):
        context = MagicMock()
        active = MagicMock()
        context.get_window.return_value = active
        rot_mod.show_rotator_dialog(context)
        context.get_window.assert_called_once_with("auto_rotator_dialog")
        active.show.assert_called_once()
        active.raise_.assert_called_once()

    @patch("auto_rotator_under_test.RotatorDialog")
    def test_creates_and_registers_new_window(self, mock_dialog_cls):
        context = MagicMock()
        context.get_window.return_value = None
        mw = MagicMock()
        context.get_main_window.return_value = mw

        rot_mod.show_rotator_dialog(context)

        mock_dialog_cls.assert_called_once_with(context, mw)
        instance = mock_dialog_cls.return_value
        context.register_window.assert_called_once_with("auto_rotator_dialog", instance)
        instance.show.assert_called_once()


class TestToggle(unittest.TestCase):
    def _make_dialog(self):
        dialog = rot_mod.RotatorDialog.__new__(rot_mod.RotatorDialog)
        from PyQt6.QtCore import QTimer  # the stub
        dialog.timer = QTimer()
        dialog.btn_toggle = MagicMock()
        return dialog

    def test_toggle_starts_then_stops(self):
        dialog = self._make_dialog()

        dialog.toggle()
        self.assertTrue(dialog.timer.isActive())
        dialog.btn_toggle.setText.assert_called_with("Stop")

        dialog.toggle()
        self.assertFalse(dialog.timer.isActive())
        dialog.btn_toggle.setText.assert_called_with("Start")


class TestTick(unittest.TestCase):
    def test_tick_scales_speed_by_fps_and_orbits(self):
        dialog = rot_mod.RotatorDialog.__new__(rot_mod.RotatorDialog)
        dialog.context = MagicMock()
        dialog.axis_combo = MagicMock()
        dialog.axis_combo.currentIndex.return_value = 2
        dialog.speed_spin = MagicMock()
        dialog.speed_spin.value.return_value = 100  # deg/s

        with patch.object(dialog, "_orbit_camera") as mock_orbit:
            dialog._tick()
            mock_orbit.assert_called_once()
            args, _ = mock_orbit.call_args
            # step_deg == speed / _FPS
            self.assertEqual(args[1], 2)  # axis_idx
            self.assertAlmostEqual(args[2], 100 / rot_mod._FPS)

    def test_tick_zero_speed_is_noop(self):
        dialog = rot_mod.RotatorDialog.__new__(rot_mod.RotatorDialog)
        dialog.context = MagicMock()
        dialog.axis_combo = MagicMock()
        dialog.axis_combo.currentIndex.return_value = 0
        dialog.speed_spin = MagicMock()
        dialog.speed_spin.value.return_value = 0

        with patch.object(dialog, "_orbit_camera") as mock_orbit:
            dialog._tick()
            mock_orbit.assert_not_called()

    def test_tick_no_plotter_is_noop(self):
        dialog = rot_mod.RotatorDialog.__new__(rot_mod.RotatorDialog)
        dialog.context = types.SimpleNamespace(plotter=None)
        dialog.axis_combo = MagicMock()
        dialog.speed_spin = MagicMock()
        with patch.object(dialog, "_orbit_camera") as mock_orbit:
            dialog._tick()
            mock_orbit.assert_not_called()


class TestOrbitCameraMath(unittest.TestCase):
    def setUp(self):
        self.plotter = MagicMock()
        self.camera = MagicMock()
        self.plotter.camera = self.camera
        self.renderer = MagicMock()
        self.plotter.renderer = self.renderer
        self.dialog = rot_mod.RotatorDialog.__new__(rot_mod.RotatorDialog)

    def test_orbit_z_axis_global_90deg(self):
        # Camera at (0,-10,0) looking at origin, up = Z. Rotate +90 deg about Z.
        self.camera.focal_point = (0.0, 0.0, 0.0)
        self.camera.position = (0.0, -10.0, 0.0)
        self.camera.up = (0.0, 0.0, 1.0)

        self.dialog._orbit_camera(self.plotter, axis_idx=0, step_deg=90)

        self.camera.SetPosition.assert_called_once()
        self.camera.SetViewUp.assert_called_once()

        # theta = -90 deg; view_vec=(0,-10,0), k=(0,0,1)
        # v_rot = (k x v) * sin(-90) = (10,0,0)*(-1) = (-10,0,0)
        pos_args = self.camera.SetPosition.call_args[0]
        up_args = self.camera.SetViewUp.call_args[0]
        self.assertTrue(np.allclose(pos_args, [-10.0, 0.0, 0.0]))
        self.assertTrue(np.allclose(up_args, [0.0, 0.0, 1.0]))
        self.renderer.ResetCameraClippingRange.assert_called_once()
        self.plotter.render.assert_called_once()

    def test_orbit_degenerate_view_returns_early(self):
        self.camera.focal_point = (1.0, 1.0, 1.0)
        self.camera.position = (1.0, 1.0, 1.0)  # zero view vector
        self.camera.up = (0.0, 0.0, 1.0)
        self.dialog._orbit_camera(self.plotter, axis_idx=0, step_deg=10)
        self.camera.SetPosition.assert_not_called()


class TestCloseEvent(unittest.TestCase):
    def test_close_stops_timer_and_unregisters(self):
        dialog = rot_mod.RotatorDialog.__new__(rot_mod.RotatorDialog)
        dialog.context = MagicMock()
        from PyQt6.QtCore import QTimer  # stub
        dialog.timer = QTimer()
        dialog.timer.start()
        event = MagicMock()

        dialog.closeEvent(event)

        self.assertFalse(dialog.timer.isActive())
        dialog.context.register_window.assert_called_once_with("auto_rotator_dialog", None)


if __name__ == "__main__":
    unittest.main()
