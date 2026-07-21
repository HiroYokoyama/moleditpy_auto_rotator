"""
Auto Rotator Plugin for MoleditPy.
Continuously spins the 3D viewer by orbiting the camera around a chosen global
or view axis, live in the window (no file output). A small dialog controls the
rotation speed and axis and starts/stops the motion.

Source code, README, and full license (GNU GPL):
    https://github.com/HiroYokoyama/moleditpy_auto_rotator
Copyright (c) HiroYokoyama. Licensed under the GNU General Public License;
see the LICENSE file in the repository above for the full terms.
"""

# pylint: disable=too-many-instance-attributes,no-name-in-module

import math
import logging
from PyQt6.QtCore import QCoreApplication, QTimer
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                             QComboBox, QSpinBox, QPushButton, QFormLayout)
import numpy as np

logger = logging.getLogger(__name__)

# --- Plugin Metadata ---
PLUGIN_NAME = "Auto Rotator"
PLUGIN_VERSION = "1.0.0"
PLUGIN_AUTHOR = "HiroYokoyama"
PLUGIN_DESCRIPTION = "Continuously spins the 3D viewer by orbiting the camera around a chosen axis."
PLUGIN_CATEGORY = "View"
PLUGIN_TAGS = ["Visualization"]
PLUGIN_DEPENDENCIES = ["pyvista", "PyQt6", "numpy"]
PLUGIN_SUPPORTED_MOLEDITPY_VERSION = ">=3.0.0, <5.0.0"
PLUGIN_SUPPORTED_PYTHON_VERSION = ">=3.9, <3.15"
PLUGIN_SUPPORTED_OS = ["Windows", "macOS", "Linux", "WSL"]

# Timer cadence for smooth motion; the per-tick angle is derived from the
# user's speed (degrees/second) divided by this rate.
_FPS = 50
_TICK_MS = int(1000 / _FPS)


def initialize(context):
    """Register the tool in the View menu."""
    context.add_menu_action("View/Auto Rotator...", lambda: show_rotator_dialog(context))


def show_rotator_dialog(context):
    """Singleton: reuse the existing window if it is already open."""
    win = context.get_window("auto_rotator_dialog")
    if win:
        win.show()
        win.raise_()
        return

    mw = context.get_main_window()
    dialog = RotatorDialog(context, mw)
    context.register_window("auto_rotator_dialog", dialog)
    dialog.show()


class RotatorDialog(QDialog):
    """Dialog controlling live auto-rotation of the 3D viewer."""

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self.setWindowTitle("Auto Rotator")

        self.timer = QTimer(self)
        self.timer.setInterval(_TICK_MS)
        self.timer.timeout.connect(self._tick)

        self.setup_ui()

    def setup_ui(self):
        """Build the Speed + Axis controls and the Start/Stop button."""
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Axis selection (3 global + 3 view-relative), mirroring Rotation Giffer.
        self.axis_combo = QComboBox()
        self.axis_combo.addItems([
            "Z Axis (Global)",
            "X Axis (Global)",
            "Y Axis (Global)",
            "Roll (Spin around line of sight)",
            "Elevation (Pitch up/down)",
            "Azimuth (Yaw left/right)"
        ])
        form.addRow("Rotation Axis:", self.axis_combo)

        # Speed in degrees per second; negative reverses the spin direction.
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(-360, 360)
        self.speed_spin.setValue(45)
        self.speed_spin.setSuffix(" °/s")
        form.addRow("Speed:", self.speed_spin)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        self.btn_toggle = QPushButton("Start")
        self.btn_close = QPushButton("Close")
        self.btn_toggle.clicked.connect(self.toggle)
        self.btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_toggle)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def toggle(self):
        """Start or stop the rotation timer."""
        if self.timer.isActive():
            self.timer.stop()
            self.btn_toggle.setText("Start")
        else:
            self.timer.start()
            self.btn_toggle.setText("Stop")

    def _tick(self):
        """Advance the camera by one small step around the selected axis."""
        plotter = getattr(self.context, "plotter", None)
        if plotter is None:
            return

        axis_idx = self.axis_combo.currentIndex()
        step_deg = self.speed_spin.value() / _FPS
        if step_deg == 0:
            return

        self._orbit_camera(plotter, axis_idx, step_deg)

    def _orbit_camera(self, plotter, axis_idx, step_deg):
        """
        Rotate the camera incrementally by 'step_deg' degrees around the chosen
        axis, computed from the camera's current orientation each tick.
        """
        cam = plotter.camera

        fp = np.array(cam.focal_point, dtype=float)
        pos = np.array(cam.position, dtype=float)
        up = np.array(cam.up, dtype=float)

        view_vec = pos - fp

        eps = 1e-8
        view_norm = np.linalg.norm(view_vec)
        up_norm = np.linalg.norm(up)
        if view_norm < eps or up_norm < eps:
            return

        view_dir = view_vec / view_norm
        up_dir = up / up_norm
        right_dir = np.cross(up_dir, view_dir)

        if axis_idx == 0:    # Z Axis (Global)
            axis = np.array([0.0, 0.0, 1.0])
        elif axis_idx == 1:  # X Axis (Global)
            axis = np.array([1.0, 0.0, 0.0])
        elif axis_idx == 2:  # Y Axis (Global)
            axis = np.array([0.0, 1.0, 0.0])
        elif axis_idx == 3:  # Roll -> line of sight
            axis = view_dir
        elif axis_idx == 4:  # Elevation (Pitch) -> right vector
            axis = right_dir
        elif axis_idx == 5:  # Azimuth (Yaw) -> up vector
            axis = up_dir
        else:
            return

        axis_norm = np.linalg.norm(axis)
        if axis_norm < eps:
            return
        axis = axis / axis_norm

        theta = math.radians(-step_deg)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        # Rodrigues' rotation of a vector 'v' around unit axis 'k' by 'theta'.
        def rotate_vec(v, k):
            return (
                v * cos_t
                + np.cross(k, v) * sin_t
                + k * np.dot(k, v) * (1 - cos_t)
            )

        new_view_vec = rotate_vec(view_vec, axis)
        new_up = rotate_vec(up, axis)

        # Update via VTK native setters to bypass PyVista's auto-reset triggers.
        cam.SetPosition(*(fp + new_view_vec))
        cam.SetViewUp(*new_up)

        plotter.renderer.ResetCameraClippingRange()
        plotter.render()

        # Let the Cocoa backbuffer swap so the motion is visible on macOS.
        QCoreApplication.processEvents()

    def closeEvent(self, event):  # pylint: disable=invalid-name
        """Stop the timer and release the singleton slot so reopening works."""
        self.timer.stop()
        self.context.register_window("auto_rotator_dialog", None)
        super().closeEvent(event)
