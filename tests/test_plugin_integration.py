"""
Integration tests for auto_rotator.py
Verifies the plugin contract against a stub PluginContext without Qt/PyVista,
and optionally against the real MoleditPy PluginContext when the main app is
available as a sibling checkout or via CI_MAIN_APP_SRC.
"""
import sys
import os
import types
import unittest
from unittest.mock import MagicMock


def _install_qt_stubs():
    if "PyQt6" in sys.modules and hasattr(sys.modules["PyQt6"], "__file__"):
        return  # real Qt already present

    pyqt6 = types.ModuleType("PyQt6")
    qt_core = types.ModuleType("PyQt6.QtCore")
    qt_core.QCoreApplication = MagicMock()
    qt_core.QTimer = MagicMock()

    qt_widgets = types.ModuleType("PyQt6.QtWidgets")
    for cls_name in [
        "QDialog", "QVBoxLayout", "QHBoxLayout", "QComboBox", "QSpinBox",
        "QPushButton", "QFormLayout",
    ]:
        setattr(qt_widgets, cls_name, MagicMock())

    qt_gui = types.ModuleType("PyQt6.QtGui")

    for name, mod in [
        ("PyQt6", pyqt6),
        ("PyQt6.QtCore", qt_core),
        ("PyQt6.QtWidgets", qt_widgets),
        ("PyQt6.QtGui", qt_gui),
    ]:
        sys.modules.setdefault(name, mod)


_install_qt_stubs()

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

import auto_rotator as _pkg  # noqa: E402
from auto_rotator import initialize, PLUGIN_NAME, PLUGIN_VERSION  # noqa: E402


class _StubContext:
    def __init__(self):
        self._menu_actions = []
        self._windows = {}

    def add_menu_action(self, path, callback, **kwargs):
        self._menu_actions.append((path, callback))

    def get_window(self, key):
        return self._windows.get(key)

    def register_window(self, key, win):
        self._windows[key] = win

    def get_main_window(self):
        return MagicMock()

    def show_status_message(self, msg, duration=0):
        pass

    # Rest of the standard API (unused by this plugin)
    def add_export_action(self, label, callback): pass
    def register_save_handler(self, fn): pass
    def register_load_handler(self, fn): pass
    def register_document_reset_handler(self, fn): pass
    def register_file_opener(self, ext, fn, priority=0): pass
    def register_drop_handler(self, fn, priority=0): pass
    def add_analysis_tool(self, label, fn): pass
    def add_toolbar_action(self, fn, text, icon=None, tooltip=None): pass


class TestMetadata(unittest.TestCase):
    def test_plugin_name(self):
        self.assertEqual(PLUGIN_NAME, "Auto Rotator")

    def test_plugin_version_is_semver(self):
        parts = PLUGIN_VERSION.split(".")
        self.assertEqual(len(parts), 3)
        for p in parts:
            self.assertTrue(p.isdigit(), f"Non-numeric version part: {p!r}")


class TestInitialize(unittest.TestCase):
    def setUp(self):
        self.ctx = _StubContext()
        initialize(self.ctx)

    def test_registers_one_menu_action(self):
        self.assertEqual(len(self.ctx._menu_actions), 1)

    def test_menu_action_targets_view_menu(self):
        path, _ = self.ctx._menu_actions[0]
        self.assertTrue(path.startswith("View/"))

    def test_menu_action_is_callable(self):
        _, callback = self.ctx._menu_actions[0]
        self.assertTrue(callable(callback))


class TestShowRotatorDialog(unittest.TestCase):
    def test_reuses_existing_window(self):
        ctx = _StubContext()
        fake_win = MagicMock()
        ctx._windows["auto_rotator_dialog"] = fake_win
        _pkg.show_rotator_dialog(ctx)
        fake_win.show.assert_called_once()
        fake_win.raise_.assert_called_once()


# ---------------------------------------------------------------------------
# Real PluginContext tier (local dev + CI with cloned main app)
# ---------------------------------------------------------------------------

_MAIN_APP_CANDIDATES = [
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..",
                     "python_molecular_editor", "moleditpy", "src")
    ),
    os.environ.get("CI_MAIN_APP_SRC", ""),
]
_MAIN_APP_SRC = next(
    (p for p in _MAIN_APP_CANDIDATES if p and os.path.isdir(p)),
    None,
)
HAS_MAIN_APP = _MAIN_APP_SRC is not None

try:
    import pytest
    _skipif = pytest.mark.skipif(
        not HAS_MAIN_APP,
        reason="main app not found; clone python_molecular_editor or set CI_MAIN_APP_SRC",
    )
except ImportError:
    def _skipif(cls):
        return unittest.skip("pytest not available")(cls)


@_skipif
class TestWithRealPluginContext(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAS_MAIN_APP:
            return
        import importlib.util as _ilu
        _pi_path = os.path.join(_MAIN_APP_SRC, 'moleditpy', 'plugins', 'plugin_interface.py')
        _spec = _ilu.spec_from_file_location('moleditpy.plugins.plugin_interface', _pi_path)
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        cls.PluginContext = _mod.PluginContext
        mock_manager = MagicMock()
        mock_manager.get_main_window.return_value = MagicMock()
        cls.real_ctx = cls.PluginContext(mock_manager, PLUGIN_NAME)

    def test_real_initialize_does_not_raise(self):
        try:
            initialize(self.real_ctx)
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.fail(f"initialize(real_context) raised: {e}")

    def test_real_context_has_required_methods(self):
        for method in ["add_menu_action", "get_window", "register_window", "get_main_window"]:
            self.assertTrue(
                hasattr(self.PluginContext, method),
                f"Real PluginContext missing: {method}",
            )


if __name__ == "__main__":
    unittest.main()
