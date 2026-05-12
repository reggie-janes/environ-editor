"""Tests for AppController."""
import pytest
from unittest.mock import MagicMock, patch

from envedit.controllers.app_controller import AppController
from envedit.models.env_var_model import EnvVarModel
from envedit.models.path_model import PathModel


@pytest.fixture
def mock_backend():
    backend = MagicMock()
    backend.get_user_vars.return_value = {"FOO": "foo_val", "BAR": "bar_val"}
    backend.get_system_vars.return_value = {"SYS_VAR": "sys_val"}
    backend.get_user_path.return_value = ["/usr/bin", "/bin"]
    backend.get_system_path.return_value = ["/sbin"]
    backend.expand_value.side_effect = lambda v: v
    return backend


@pytest.fixture
def controller(qapp, mock_backend):
    with patch("envedit.controllers.app_controller.get_backend", return_value=mock_backend), \
         patch("envedit.controllers.app_controller.QSettings") as mock_settings:
        mock_settings.return_value.value.return_value = ""
        ctrl = AppController()
    return ctrl


# ---------------------------------------------------------------------------
# Model properties
# ---------------------------------------------------------------------------

class TestModelProperties:
    def test_user_var_model_is_env_var_model(self, controller):
        assert isinstance(controller.userVarModel, EnvVarModel)

    def test_system_var_model_is_env_var_model(self, controller):
        assert isinstance(controller.systemVarModel, EnvVarModel)

    def test_user_path_model_is_path_model(self, controller):
        assert isinstance(controller.userPathModel, PathModel)

    def test_system_path_model_is_path_model(self, controller):
        assert isinstance(controller.systemPathModel, PathModel)

    def test_user_var_model_loaded(self, controller):
        assert controller.userVarModel.rowCount() == 2

    def test_system_var_model_loaded(self, controller):
        assert controller.systemVarModel.rowCount() == 1

    def test_user_path_model_loaded(self, controller):
        assert controller.userPathModel.rowCount() == 2

    def test_system_path_model_loaded(self, controller):
        assert controller.systemPathModel.rowCount() == 1


# ---------------------------------------------------------------------------
# getDiffText
# ---------------------------------------------------------------------------

class TestGetDiffText:
    def test_diff_empty_when_no_var_changes(self, controller):
        # Var tabs return empty when no pending changes
        assert controller.getDiffText(0) == ""
        assert controller.getDiffText(2) == ""

    def test_diff_path_always_shows_entries(self, controller):
        # Path diffs show the full current list (order matters), not just deltas
        diff = controller.getDiffText(1)
        assert "/usr/bin" in diff
        assert "/bin" in diff

    def test_diff_user_vars_edit(self, controller):
        controller.userVarModel.editVariable(0, "BAR", "new_val")
        diff = controller.getDiffText(0)
        assert "BAR" in diff
        assert "new_val" in diff

    def test_diff_user_vars_delete(self, controller):
        controller.userVarModel.deleteVariable(0)
        diff = controller.getDiffText(0)
        assert "DELETE" in diff

    def test_diff_user_path(self, controller):
        controller.userPathModel.addEntry("/extra")
        diff = controller.getDiffText(1)
        assert "/extra" in diff

    def test_diff_system_vars_edit(self, controller):
        controller.systemVarModel.editVariable(0, "SYS_VAR", "new_sys")
        diff = controller.getDiffText(2)
        assert "SYS_VAR" in diff
        assert "new_sys" in diff

    def test_diff_system_path(self, controller):
        controller.systemPathModel.addEntry("/sys/extra")
        diff = controller.getDiffText(3)
        assert "/sys/extra" in diff

    def test_diff_invalid_idx_returns_empty(self, controller):
        assert controller.getDiffText(99) == ""

    def test_diff_path_includes_index(self, controller):
        diff = controller.getDiffText(1)
        assert "1." in diff  # "  1.  /usr/bin"

    def test_set_var_diff_format(self, controller):
        controller.userVarModel.editVariable(0, "BAR", "newval")
        diff = controller.getDiffText(0)
        assert "SET" in diff
        assert "=" in diff


# ---------------------------------------------------------------------------
# applyTab
# ---------------------------------------------------------------------------

class TestApplyTab:
    def test_apply_user_vars_calls_backend(self, controller, mock_backend):
        controller.userVarModel.editVariable(0, "BAR", "new_val")
        controller.applyTab(0)
        mock_backend.apply_user_vars.assert_called_once()
        call_arg = mock_backend.apply_user_vars.call_args[0][0]
        assert call_arg.get("BAR") == "new_val"

    def test_apply_user_vars_discards_pending(self, controller, mock_backend):
        controller.userVarModel.editVariable(0, "BAR", "new_val")
        controller.applyTab(0)
        assert controller.userVarModel.pendingCount == 0

    def test_apply_user_path_calls_backend(self, controller, mock_backend):
        controller.userPathModel.addEntry("/extra")
        controller.applyTab(1)
        mock_backend.apply_user_path.assert_called_once()
        args = mock_backend.apply_user_path.call_args[0][0]
        assert "/extra" in args

    def test_apply_system_vars_calls_backend(self, controller, mock_backend):
        controller.systemVarModel.editVariable(0, "SYS_VAR", "new_sys")
        controller.applyTab(2)
        mock_backend.apply_system_vars.assert_called_once()

    def test_apply_system_path_calls_backend(self, controller, mock_backend):
        controller.systemPathModel.addEntry("/sys/extra")
        controller.applyTab(3)
        mock_backend.apply_system_path.assert_called_once()

    def test_apply_emits_error_on_exception(self, controller, mock_backend, qtbot):
        mock_backend.apply_user_vars.side_effect = RuntimeError("disk full")
        controller.userVarModel.editVariable(0, "BAR", "val")
        with qtbot.waitSignal(controller.errorOccurred, timeout=500) as blocker:
            controller.applyTab(0)
        assert "disk full" in blocker.args[0]


# ---------------------------------------------------------------------------
# reloadTab
# ---------------------------------------------------------------------------

class TestReloadTab:
    def test_reload_user_vars(self, controller, mock_backend):
        mock_backend.get_user_vars.return_value = {"NEWVAR": "newval"}
        controller.reloadTab(0)
        assert controller.userVarModel.rowCount() == 1

    def test_reload_user_path(self, controller, mock_backend):
        mock_backend.get_user_path.return_value = ["/a", "/b", "/c"]
        controller.reloadTab(1)
        assert controller.userPathModel.rowCount() == 3

    def test_reload_system_vars(self, controller, mock_backend):
        mock_backend.get_system_vars.return_value = {}
        controller.reloadTab(2)
        assert controller.systemVarModel.rowCount() == 0

    def test_reload_system_path(self, controller, mock_backend):
        mock_backend.get_system_path.return_value = ["/sys/bin"]
        controller.reloadTab(3)
        assert controller.systemPathModel.rowCount() == 1


# ---------------------------------------------------------------------------
# expandValue
# ---------------------------------------------------------------------------

class TestExpandValue:
    def test_delegates_to_backend(self, controller, mock_backend):
        # side_effect takes priority over return_value; clear it first
        mock_backend.expand_value.side_effect = None
        mock_backend.expand_value.return_value = "/home/user/bin"
        result = controller.expandValue("$HOME/bin")
        assert result == "/home/user/bin"
        mock_backend.expand_value.assert_called_with("$HOME/bin")


# ---------------------------------------------------------------------------
# platformName / isElevated
# ---------------------------------------------------------------------------

class TestInfoProperties:
    def test_platform_name_is_string(self, controller):
        assert isinstance(controller.platformName, str)
        assert len(controller.platformName) > 0

    def test_is_elevated_is_bool(self, controller):
        assert isinstance(controller.isElevated, bool)

    def test_user_tabs_read_only_is_bool(self, controller):
        assert isinstance(controller.userTabsReadOnly, bool)


# ---------------------------------------------------------------------------
# applyTab guards when running elevated-via-wrapper
# ---------------------------------------------------------------------------

class TestApplyTabUserTabsLocked:
    def test_user_vars_apply_blocked_when_wrapper_elevated(self, qapp, mock_backend, qtbot):
        with patch("envedit.controllers.app_controller.get_backend", return_value=mock_backend), \
             patch("envedit.controllers.app_controller.is_elevated_via_wrapper", return_value=True), \
             patch("envedit.controllers.app_controller.QSettings") as mock_settings:
            mock_settings.return_value.value.return_value = ""
            ctrl = AppController()
            ctrl.userVarModel.editVariable(0, "BAR", "new_val")
            with qtbot.waitSignal(ctrl.errorOccurred, timeout=500) as blocker:
                ctrl.applyTab(0)
        assert "elevated" in blocker.args[0].lower()
        mock_backend.apply_user_vars.assert_not_called()

    def test_user_path_apply_blocked_when_wrapper_elevated(self, qapp, mock_backend, qtbot):
        with patch("envedit.controllers.app_controller.get_backend", return_value=mock_backend), \
             patch("envedit.controllers.app_controller.is_elevated_via_wrapper", return_value=True), \
             patch("envedit.controllers.app_controller.QSettings") as mock_settings:
            mock_settings.return_value.value.return_value = ""
            ctrl = AppController()
            ctrl.userPathModel.addEntry("/extra")
            with qtbot.waitSignal(ctrl.errorOccurred, timeout=500) as blocker:
                ctrl.applyTab(1)
        assert "elevated" in blocker.args[0].lower()
        mock_backend.apply_user_path.assert_not_called()

    def test_system_apply_not_blocked_when_wrapper_elevated(self, qapp, mock_backend):
        # System tabs are the whole reason someone would launch via sudo —
        # they must remain functional.
        with patch("envedit.controllers.app_controller.get_backend", return_value=mock_backend), \
             patch("envedit.controllers.app_controller.is_elevated_via_wrapper", return_value=True), \
             patch("envedit.controllers.app_controller.QSettings") as mock_settings:
            mock_settings.return_value.value.return_value = ""
            ctrl = AppController()
            ctrl.systemVarModel.editVariable(0, "SYS_VAR", "new_sys")
            ctrl.applyTab(2)
        mock_backend.apply_system_vars.assert_called_once()
