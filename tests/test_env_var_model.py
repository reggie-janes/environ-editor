"""Tests for EnvVarModel."""
import pytest
from PySide6.QtCore import QModelIndex, Qt

from envedit.models.env_var_model import EnvVarModel


@pytest.fixture
def model(qapp):
    return EnvVarModel()


@pytest.fixture
def populated_model(qapp):
    m = EnvVarModel()
    m.loadData({"ALPHA": "aval", "BETA": "bval", "GAMMA": "gval"})
    return m


# ---------------------------------------------------------------------------
# loadData / rowCount / roleNames
# ---------------------------------------------------------------------------

class TestLoadData:
    def test_empty_load_clears_rows(self, model):
        model.loadData({"A": "1"})
        model.loadData({})
        assert model.rowCount() == 0

    def test_row_count_matches_dict_size(self, model):
        model.loadData({"X": "1", "Y": "2", "Z": "3"})
        assert model.rowCount() == 3

    def test_rows_sorted_alphabetically(self, model):
        model.loadData({"ZZZ": "z", "AAA": "a", "MMM": "m"})
        names = [model.data(model.index(i), EnvVarModel.NameRole) for i in range(3)]
        assert names == ["AAA", "MMM", "ZZZ"]

    def test_load_clears_pending_changes(self, model):
        model.loadData({"A": "1"})
        model.editVariable(0, "A", "changed")
        model.loadData({"A": "1"})
        assert model.pendingCount == 0

    def test_role_names_present(self, model):
        roles = model.roleNames()
        assert b"name" in roles.values()
        assert b"value" in roles.values()
        assert b"isPending" in roles.values()
        assert b"isDeleted" in roles.values()
        assert b"expanded" in roles.values()


# ---------------------------------------------------------------------------
# data()
# ---------------------------------------------------------------------------

class TestData:
    def test_invalid_index_returns_none(self, populated_model):
        assert populated_model.data(QModelIndex(), EnvVarModel.NameRole) is None

    def test_out_of_range_index_returns_none(self, populated_model):
        idx = populated_model.index(999)
        assert populated_model.data(idx, EnvVarModel.NameRole) is None

    def test_name_role(self, populated_model):
        idx = populated_model.index(0)
        assert populated_model.data(idx, EnvVarModel.NameRole) == "ALPHA"

    def test_value_role(self, populated_model):
        idx = populated_model.index(0)
        assert populated_model.data(idx, EnvVarModel.ValueRole) == "aval"

    def test_is_pending_false_for_unmodified(self, populated_model):
        idx = populated_model.index(0)
        assert populated_model.data(idx, EnvVarModel.PendingRole) is False

    def test_is_deleted_false_for_normal_row(self, populated_model):
        idx = populated_model.index(0)
        assert populated_model.data(idx, EnvVarModel.DeletedRole) is False

    def test_expanded_role_calls_expand_fn(self, qapp):
        m = EnvVarModel(expand_fn=lambda v: v.upper())
        m.loadData({"FOO": "bar"})
        idx = m.index(0)
        assert m.data(idx, EnvVarModel.ExpandedRole) == "BAR"


# ---------------------------------------------------------------------------
# editVariable
# ---------------------------------------------------------------------------

class TestEditVariable:
    def test_edit_value(self, populated_model):
        populated_model.editVariable(0, "ALPHA", "new_aval")
        assert populated_model.pendingCount == 1

    def test_edit_shows_pending_value(self, populated_model):
        populated_model.editVariable(0, "ALPHA", "new_aval")
        idx = populated_model.index(0)
        assert populated_model.data(idx, EnvVarModel.ValueRole) == "new_aval"

    def test_edit_to_original_value_clears_pending(self, populated_model):
        populated_model.editVariable(0, "ALPHA", "changed")
        populated_model.editVariable(0, "ALPHA", "aval")
        assert populated_model.pendingCount == 0

    def test_edit_marks_row_as_pending(self, populated_model):
        populated_model.editVariable(0, "ALPHA", "changed")
        idx = populated_model.index(0)
        assert populated_model.data(idx, EnvVarModel.PendingRole) is True

    def test_rename_variable(self, populated_model):
        populated_model.editVariable(0, "ALPHA_RENAMED", "aval")
        assert populated_model.pendingCount == 2  # delete old + add new

    def test_rename_marks_old_as_deleted(self, populated_model):
        populated_model.editVariable(0, "ALPHA_RENAMED", "aval")
        pending = populated_model.getPendingChanges()
        assert pending.get("ALPHA") is None  # None = delete

    def test_rename_to_existing_name_is_rejected(self, populated_model, qtbot):
        # ALPHA exists at index 0, BETA at index 1. Renaming ALPHA to BETA
        # would silently clobber BETA's value — refuse and emit an error.
        with qtbot.waitSignal(populated_model.errorOccurred, timeout=500):
            populated_model.editVariable(0, "BETA", "aval")
        assert populated_model.pendingCount == 0
        # BETA's original value must not have been touched.
        beta_row = next(r for r in populated_model._rows if r["name"] == "BETA")
        assert beta_row["value"] == "bval"

    def test_out_of_range_edit_is_noop(self, populated_model):
        populated_model.editVariable(999, "X", "val")
        assert populated_model.pendingCount == 0

    def test_negative_index_is_noop(self, populated_model):
        populated_model.editVariable(-1, "X", "val")
        assert populated_model.pendingCount == 0


# ---------------------------------------------------------------------------
# deleteVariable
# ---------------------------------------------------------------------------

class TestDeleteVariable:
    def test_delete_marks_row_as_deleted(self, populated_model):
        populated_model.deleteVariable(0)
        idx = populated_model.index(0)
        assert populated_model.data(idx, EnvVarModel.DeletedRole) is True

    def test_delete_increments_pending_count(self, populated_model):
        populated_model.deleteVariable(0)
        assert populated_model.pendingCount == 1

    def test_delete_appears_in_pending_changes_as_none(self, populated_model):
        populated_model.deleteVariable(0)
        pending = populated_model.getPendingChanges()
        assert pending.get("ALPHA") is None

    def test_delete_out_of_range_is_noop(self, populated_model):
        populated_model.deleteVariable(999)
        assert populated_model.pendingCount == 0


# ---------------------------------------------------------------------------
# addVariable
# ---------------------------------------------------------------------------

class TestAddVariable:
    def test_add_new_variable_increases_row_count(self, populated_model):
        before = populated_model.rowCount()
        populated_model.addVariable("NEWVAR", "newval")
        assert populated_model.rowCount() == before + 1

    def test_add_new_variable_pending(self, populated_model):
        populated_model.addVariable("NEWVAR", "newval")
        assert populated_model.pendingCount == 1

    def test_add_new_variable_reports_is_new(self, populated_model):
        # Newly added variables report isNew so the table highlights them
        # distinctly from edited variables.
        populated_model.addVariable("NEWVAR", "newval")
        row = next(
            i for i in range(populated_model.rowCount())
            if populated_model.data(populated_model.index(i), EnvVarModel.NameRole) == "NEWVAR"
        )
        idx = populated_model.index(row)
        assert populated_model.data(idx, EnvVarModel.NewRole) is True
        assert populated_model.data(idx, EnvVarModel.PendingRole) is True

    def test_edited_existing_variable_is_not_new(self, populated_model):
        populated_model.editVariable(0, "ALPHA", "changed")
        idx = populated_model.index(0)
        assert populated_model.data(idx, EnvVarModel.NewRole) is False
        assert populated_model.data(idx, EnvVarModel.PendingRole) is True

    def test_add_existing_variable_replaces_and_notifies(self, populated_model, qtbot):
        # Issue 014: collisions used to silently overwrite the existing row.
        # New behaviour: the value is replaced (preserving the convenience of
        # treating "Add" as upsert) but an informational message tells the
        # user that an existing variable was replaced rather than created.
        infos = []
        populated_model.infoOccurred.connect(infos.append)
        with qtbot.waitSignal(populated_model.infoOccurred, timeout=500):
            populated_model.addVariable("ALPHA", "updated")
        assert populated_model.pendingCount == 1
        pending = populated_model.getPendingChanges()
        assert pending["ALPHA"] == "updated"
        assert "replaced" in infos[0]

    def test_add_existing_variable_same_value_reports_no_change(self, populated_model, qtbot):
        infos = []
        populated_model.infoOccurred.connect(infos.append)
        with qtbot.waitSignal(populated_model.infoOccurred, timeout=500):
            populated_model.addVariable("ALPHA", "aval")  # same as original
        assert populated_model.pendingCount == 0
        assert "nothing changed" in infos[0].lower()

    def test_add_empty_name_is_noop(self, populated_model):
        before = populated_model.rowCount()
        populated_model.addVariable("", "value")
        assert populated_model.rowCount() == before
        assert populated_model.pendingCount == 0

    def test_add_whitespace_name_is_noop(self, populated_model):
        before = populated_model.rowCount()
        populated_model.addVariable("   ", "value")
        assert populated_model.rowCount() == before

    def test_added_variable_sorted_into_correct_position(self, populated_model):
        populated_model.addVariable("DELTA", "dval")
        names = [populated_model.data(populated_model.index(i), EnvVarModel.NameRole)
                 for i in range(populated_model.rowCount())]
        assert names == sorted(names, key=str.lower)


# ---------------------------------------------------------------------------
# discardChanges
# ---------------------------------------------------------------------------

class TestDiscardChanges:
    def test_discard_clears_pending_count(self, populated_model):
        populated_model.editVariable(0, "ALPHA", "changed")
        populated_model.discardChanges()
        assert populated_model.pendingCount == 0

    def test_discard_restores_original_value(self, populated_model):
        populated_model.editVariable(0, "ALPHA", "changed")
        populated_model.discardChanges()
        idx = populated_model.index(0)
        assert populated_model.data(idx, EnvVarModel.ValueRole) == "aval"

    def test_discard_removes_added_variables(self, populated_model):
        before = populated_model.rowCount()
        populated_model.addVariable("NEWVAR", "val")
        populated_model.discardChanges()
        assert populated_model.rowCount() == before

    def test_discard_undeletes_rows(self, populated_model):
        populated_model.deleteVariable(0)
        populated_model.discardChanges()
        idx = populated_model.index(0)
        assert populated_model.data(idx, EnvVarModel.DeletedRole) is False


# ---------------------------------------------------------------------------
# setFilter
# ---------------------------------------------------------------------------

class TestFilter:
    def test_filter_by_name(self, populated_model):
        populated_model.setFilter("alpha")
        assert populated_model.rowCount() == 1
        idx = populated_model.index(0)
        assert populated_model.data(idx, EnvVarModel.NameRole) == "ALPHA"

    def test_filter_by_value(self, populated_model):
        populated_model.setFilter("bval")
        assert populated_model.rowCount() == 1
        idx = populated_model.index(0)
        assert populated_model.data(idx, EnvVarModel.NameRole) == "BETA"

    def test_filter_case_insensitive(self, populated_model):
        populated_model.setFilter("ALPHA")
        assert populated_model.rowCount() == 1

    def test_filter_no_match(self, populated_model):
        populated_model.setFilter("zzznomatch")
        assert populated_model.rowCount() == 0

    def test_clear_filter_restores_all_rows(self, populated_model):
        populated_model.setFilter("alpha")
        populated_model.setFilter("")
        assert populated_model.rowCount() == 3

    def test_filter_does_not_affect_pending_changes(self, populated_model):
        populated_model.editVariable(0, "ALPHA", "changed")
        populated_model.setFilter("beta")
        assert populated_model.pendingCount == 1

    def test_filter_matches_pending_value(self, populated_model):
        populated_model.editVariable(0, "ALPHA", "unique_pending")
        populated_model.setFilter("unique_pending")
        assert populated_model.rowCount() == 1
        assert populated_model.data(populated_model.index(0), EnvVarModel.NameRole) == "ALPHA"

    def test_filter_matches_expanded_value(self, qapp):
        model = EnvVarModel(expand_fn=lambda v: v.replace("$TOKEN", "/resolved/path"))
        model.loadData({"FOO": "$TOKEN/extra"})
        model.setFilter("/resolved")  # only in expanded value — should match
        assert model.rowCount() == 1
        model.setFilter("token")    # in raw value — should also match
        assert model.rowCount() == 1
        model.setFilter("nomatch")
        assert model.rowCount() == 0


# ---------------------------------------------------------------------------
# getPendingChanges
# ---------------------------------------------------------------------------

class TestGetPendingChanges:
    def test_empty_on_fresh_load(self, populated_model):
        assert populated_model.getPendingChanges() == {}

    def test_returns_copy(self, populated_model):
        changes = populated_model.getPendingChanges()
        changes["INJECTED"] = "should not affect model"
        assert "INJECTED" not in populated_model.getPendingChanges()

    def test_reflects_multiple_edits(self, populated_model):
        populated_model.editVariable(0, "ALPHA", "new1")
        populated_model.editVariable(1, "BETA", "new2")
        pending = populated_model.getPendingChanges()
        assert pending["ALPHA"] == "new1"
        assert pending["BETA"] == "new2"


# ---------------------------------------------------------------------------
# getDiffOperations
# ---------------------------------------------------------------------------

class TestGetDiffOperations:
    def test_empty_when_no_changes(self, populated_model):
        assert populated_model.getDiffOperations() == []

    def test_edit_op_carries_old_and_new_value(self, populated_model):
        populated_model.editVariable(0, "ALPHA", "new")
        ops = populated_model.getDiffOperations()
        assert ops == [
            {"op": "edit", "name": "ALPHA", "old_value": "aval", "new_value": "new"}
        ]

    def test_remove_op_carries_old_value(self, populated_model):
        populated_model.deleteVariable(0)
        ops = populated_model.getDiffOperations()
        assert ops == [
            {"op": "remove", "name": "ALPHA", "old_value": "aval"}
        ]

    def test_add_op_for_new_variable(self, populated_model):
        populated_model.addVariable("DELTA", "dval")
        ops = populated_model.getDiffOperations()
        assert ops == [
            {"op": "add", "name": "DELTA", "new_value": "dval"}
        ]

    def test_mixed_ops_sorted_case_insensitive(self, populated_model):
        populated_model.editVariable(0, "ALPHA", "a2")
        populated_model.deleteVariable(2)        # GAMMA
        populated_model.addVariable("zeta", "z")
        names = [op["name"] for op in populated_model.getDiffOperations()]
        assert names == ["ALPHA", "GAMMA", "zeta"]

    def test_rename_emits_add_and_remove(self, populated_model):
        # Rename ALPHA → ALPHA2 — implemented as delete + add at the model
        # layer, so the diff surfaces both ops.
        populated_model.editVariable(0, "ALPHA2", "aval")
        kinds = {op["op"] for op in populated_model.getDiffOperations()}
        assert kinds == {"add", "remove"}


# ---------------------------------------------------------------------------
# pendingCountChanged signal
# ---------------------------------------------------------------------------

class TestPendingCountSignal:
    def test_signal_emitted_on_edit(self, populated_model, qtbot):
        with qtbot.waitSignal(populated_model.pendingCountChanged, timeout=500):
            populated_model.editVariable(0, "ALPHA", "changed")

    def test_signal_emitted_on_delete(self, populated_model, qtbot):
        with qtbot.waitSignal(populated_model.pendingCountChanged, timeout=500):
            populated_model.deleteVariable(0)

    def test_signal_emitted_on_discard(self, populated_model, qtbot):
        populated_model.editVariable(0, "ALPHA", "changed")
        with qtbot.waitSignal(populated_model.pendingCountChanged, timeout=500):
            populated_model.discardChanges()
