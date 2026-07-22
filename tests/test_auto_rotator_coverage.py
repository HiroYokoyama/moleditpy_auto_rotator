"""
tests/test_auto_rotator_coverage.py
Additional coverage for auto_rotator.py: dialog construction/setup_ui,
and the remaining _orbit_camera axis branches (X/Y global, roll, elevation,
azimuth, invalid axis, degenerate rotation axis).
"""

# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=too-few-public-methods,protected-access,invalid-name

import importlib.util as importlib_util
import os
import sys
import types
import unittest
from unittest.mock import MagicMock
import numpy as np


# ---------------------------------------------------------------------------
# Install Qt stubs so the plugin imports cleanly in a headless environment.
# (Mirrors tests/test_auto_rotator.py's harness.)
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


rot_mod = _load_module_direct("auto_rotator.py", "auto_rotator_under_test_cov")


class TestDialogConstruction(unittest.TestCase):
    def test_init_builds_timer_and_ui(self):
        context = MagicMock()
        parent = MagicMock()

        dialog = rot_mod.RotatorDialog(context, parent)

        self.assertIs(dialog.context, context)
        self.assertIsNotNone(dialog.timer)
        dialog.timer.timeout.connect.assert_called_once_with(dialog._tick)

        # setup_ui built the axis combo, speed spin, and buttons.
        self.assertIsNotNone(dialog.axis_combo)
        self.assertIsNotNone(dialog.speed_spin)
        self.assertIsNotNone(dialog.btn_toggle)
        self.assertIsNotNone(dialog.btn_close)

        dialog.axis_combo.addItems.assert_called_once()
        items = dialog.axis_combo.addItems.call_args[0][0]
        self.assertEqual(len(items), 6)

        dialog.speed_spin.setRange.assert_called_once_with(-360, 360)
        dialog.speed_spin.setValue.assert_called_once_with(45)

        dialog.btn_toggle.clicked.connect.assert_called_once_with(dialog.toggle)
        dialog.btn_close.clicked.connect.assert_called_once_with(dialog.close)

    def test_show_rotator_dialog_creates_real_dialog(self):
        # Exercise show_rotator_dialog end-to-end (no mocked RotatorDialog),
        # which drives __init__/setup_ui through the public entry point.
        context = MagicMock()
        context.get_window.return_value = None
        mw = MagicMock()
        context.get_main_window.return_value = mw

        rot_mod.show_rotator_dialog(context)

        context.register_window.assert_called_once()
        name, dialog = context.register_window.call_args[0]
        self.assertEqual(name, "auto_rotator_dialog")
        self.assertIsInstance(dialog, rot_mod.RotatorDialog)


class TestOrbitCameraAxisBranches(unittest.TestCase):
    def setUp(self):
        self.plotter = MagicMock()
        self.camera = MagicMock()
        self.plotter.camera = self.camera
        self.renderer = MagicMock()
        self.plotter.renderer = self.renderer
        self.dialog = rot_mod.RotatorDialog.__new__(rot_mod.RotatorDialog)

    def _set_camera(self, focal_point, position, up):
        self.camera.focal_point = focal_point
        self.camera.position = position
        self.camera.up = up

    def test_orbit_x_axis_global(self):
        self._set_camera((0.0, 0.0, 0.0), (0.0, 0.0, 10.0), (0.0, 1.0, 0.0))
        self.dialog._orbit_camera(self.plotter, axis_idx=1, step_deg=90)
        self.camera.SetPosition.assert_called_once()
        self.camera.SetViewUp.assert_called_once()
        self.plotter.render.assert_called_once()

    def test_orbit_y_axis_global(self):
        self._set_camera((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 0.0, 1.0))
        self.dialog._orbit_camera(self.plotter, axis_idx=2, step_deg=45)
        self.camera.SetPosition.assert_called_once()
        self.camera.SetViewUp.assert_called_once()

    def test_orbit_roll_line_of_sight(self):
        self._set_camera((0.0, 0.0, 0.0), (0.0, -10.0, 0.0), (0.0, 0.0, 1.0))
        self.dialog._orbit_camera(self.plotter, axis_idx=3, step_deg=30)
        self.camera.SetPosition.assert_called_once()
        # Rotating around the view direction leaves the position unchanged
        # (it's on the rotation axis) but changes the up vector.
        pos_args = self.camera.SetPosition.call_args[0]
        self.assertTrue(np.allclose(pos_args, [0.0, -10.0, 0.0]))
        self.camera.SetViewUp.assert_called_once()

    def test_orbit_elevation_pitch(self):
        self._set_camera((0.0, 0.0, 0.0), (0.0, -10.0, 0.0), (0.0, 0.0, 1.0))
        self.dialog._orbit_camera(self.plotter, axis_idx=4, step_deg=15)
        self.camera.SetPosition.assert_called_once()
        self.camera.SetViewUp.assert_called_once()
        self.renderer.ResetCameraClippingRange.assert_called_once()

    def test_orbit_azimuth_yaw(self):
        self._set_camera((0.0, 0.0, 0.0), (0.0, -10.0, 0.0), (0.0, 0.0, 1.0))
        self.dialog._orbit_camera(self.plotter, axis_idx=5, step_deg=15)
        self.camera.SetPosition.assert_called_once()
        self.camera.SetViewUp.assert_called_once()

    def test_orbit_invalid_axis_returns_early(self):
        self._set_camera((0.0, 0.0, 0.0), (0.0, -10.0, 0.0), (0.0, 0.0, 1.0))
        self.dialog._orbit_camera(self.plotter, axis_idx=99, step_deg=15)
        self.camera.SetPosition.assert_not_called()
        self.camera.SetViewUp.assert_not_called()
        self.plotter.render.assert_not_called()

    def test_orbit_degenerate_axis_returns_early(self):
        # up parallel to view direction => right_dir (elevation axis) is the
        # zero vector, so axis_norm < eps and we bail before touching camera.
        self._set_camera((0.0, 0.0, 0.0), (0.0, 0.0, 10.0), (0.0, 0.0, 1.0))
        self.dialog._orbit_camera(self.plotter, axis_idx=4, step_deg=15)
        self.camera.SetPosition.assert_not_called()
        self.camera.SetViewUp.assert_not_called()
        self.plotter.render.assert_not_called()


if __name__ == "__main__":
    unittest.main()
