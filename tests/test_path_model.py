"""Tests for PathModel."""
import os
import pytest
from PySide6.QtCore import QModelIndex, Qt

from envedit.models.path_model import PathModel, _status


# ---------------------------------------------------------------------------
# _status helper
# ---------------------------------------------------------------------------

class TestStatusHelper:
    def test_existing_dir(self, tmp_path):
        assert _status(str(tmp_path)) == "✅"

    def test_symlink(self, tmp_path):
        target = tmp_path / "real_dir"
        target.mkdir()
        link = tmp_path / "link"
        link.symlink_to(target)
        assert _status(str(link)) == "🔗"

    def test_missing_path(self, tmp_path):
        assert _status(str(tmp_path / "nonexistent")) == "⚠"

    def test_file_not_dir(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        assert _status(str(f)) == "⚠"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def model(qapp):
    return PathModel()


@pytest.fixture
def populated_model(qapp):
    m = PathModel()
    m.loadData(["/usr/bin", "/bin", "/usr/local/bin"])
    return m


# ---------------------------------------------------------------------------
# loadData / rowCount / roleNames
# ---------------------------------------------------------------------------

class TestLoadData:
    def test_row_count_matches_list_length(self, model):
        model.loadData(["/a", "/b", "/c"])
        assert model.rowCount() == 3

    def test_empty_load_clears_rows(self, model):
        model.loadData(["/a"])
        model.loadData([])
        assert model.rowCount() == 0

    def test_load_clears_dirty_flag(self, model):
        model.loadData(["/a"])
        model.addEntry("/b")
        model.loadData(["/a"])
        assert model.pendingCount == 0

    def test_preserves_order(self, model):
        entries = ["/z", "/a", "/m"]
        model.loadData(entries)
        result = [model.data(model.index(i), PathModel.PathRole) for i in range(3)]
        assert result == entries

    def test_role_names_present(self, model):
        roles = model.roleNames()
        assert b"path" in roles.values()
        assert b"expanded" in roles.values()
        assert b"status" in roles.values()
        assert b"isPending" in roles.values()
        assert b"isDuplicate" in roles.values()


# ---------------------------------------------------------------------------
# data()
# ---------------------------------------------------------------------------

class TestData:
    def test_invalid_index_returns_none(self, populated_model):
        assert populated_model.data(QModelIndex(), PathModel.PathRole) is None

    def test_out_of_range_index_returns_none(self, populated_model):
        idx = populated_model.index(999)
        assert populated_model.data(idx, PathModel.PathRole) is None

    def test_path_role(self, populated_model):
        idx = populated_model.index(0)
        assert populated_model.data(idx, PathModel.PathRole) == "/usr/bin"

    def test_is_pending_false_for_unmodified(self, populated_model):
        idx = populated_model.index(0)
        assert populated_model.data(idx, PathModel.PendingRole) is False

    def test_is_duplicate_false_for_unique(self, populated_model):
        idx = populated_model.index(0)
        assert populated_model.data(idx, PathModel.DuplicateRole) is False

    def test_expanded_role_calls_expand_fn(self, qapp):
        m = PathModel(expand_fn=lambda v: v.upper())
        m.loadData(["/usr/bin"])
        idx = m.index(0)
        assert m.data(idx, PathModel.ExpandedRole) == "/USR/BIN"


# ---------------------------------------------------------------------------
# addEntry
# ---------------------------------------------------------------------------

class TestAddEntry:
    def test_add_increases_row_count(self, populated_model):
        before = populated_model.rowCount()
        populated_model.addEntry("/new/path")
        assert populated_model.rowCount() == before + 1

    def test_add_marks_dirty(self, populated_model):
        populated_model.addEntry("/new/path")
        assert populated_model.pendingCount == 1

    def test_new_entry_has_is_pending_true(self, populated_model):
        populated_model.addEntry("/new/path")
        idx = populated_model.index(populated_model.rowCount() - 1)
        assert populated_model.data(idx, PathModel.PendingRole) is True

    def test_empty_path_is_noop(self, populated_model):
        before = populated_model.rowCount()
        populated_model.addEntry("")
        assert populated_model.rowCount() == before
        assert populated_model.pendingCount == 0

    def test_whitespace_path_is_noop(self, populated_model):
        before = populated_model.rowCount()
        populated_model.addEntry("   ")
        assert populated_model.rowCount() == before

    def test_get_entries_includes_new(self, populated_model):
        populated_model.addEntry("/extra")
        assert "/extra" in populated_model.getEntries()


# ---------------------------------------------------------------------------
# editEntry
# ---------------------------------------------------------------------------

class TestEditEntry:
    def test_edit_changes_path(self, populated_model):
        populated_model.editEntry(0, "/changed")
        assert populated_model.getEntries()[0] == "/changed"

    def test_edit_marks_dirty(self, populated_model):
        populated_model.editEntry(0, "/changed")
        assert populated_model.pendingCount == 1

    def test_edit_to_same_value_is_noop(self, populated_model):
        populated_model.editEntry(0, "/usr/bin")
        assert populated_model.pendingCount == 0

    def test_edit_out_of_range_is_noop(self, populated_model):
        populated_model.editEntry(999, "/changed")
        assert populated_model.pendingCount == 0

    def test_edit_marks_row_as_pending(self, populated_model):
        populated_model.editEntry(0, "/changed")
        idx = populated_model.index(0)
        assert populated_model.data(idx, PathModel.PendingRole) is True

    def test_revert_edit_clears_pending(self, populated_model):
        populated_model.editEntry(0, "/changed")
        populated_model.editEntry(0, "/usr/bin")
        idx = populated_model.index(0)
        assert populated_model.data(idx, PathModel.PendingRole) is False


# ---------------------------------------------------------------------------
# deleteEntry
# ---------------------------------------------------------------------------

class TestDeleteEntry:
    def test_delete_decreases_row_count(self, populated_model):
        before = populated_model.rowCount()
        populated_model.deleteEntry(0)
        assert populated_model.rowCount() == before - 1

    def test_delete_marks_dirty(self, populated_model):
        populated_model.deleteEntry(0)
        assert populated_model.pendingCount == 1

    def test_deleted_entry_removed_from_get_entries(self, populated_model):
        populated_model.deleteEntry(0)
        assert "/usr/bin" not in populated_model.getEntries()

    def test_delete_out_of_range_is_noop(self, populated_model):
        before = populated_model.rowCount()
        populated_model.deleteEntry(999)
        assert populated_model.rowCount() == before

    def test_delete_negative_index_is_noop(self, populated_model):
        before = populated_model.rowCount()
        populated_model.deleteEntry(-1)
        assert populated_model.rowCount() == before


# ---------------------------------------------------------------------------
# moveUp / moveDown
# ---------------------------------------------------------------------------

class TestMove:
    def test_move_up(self, populated_model):
        populated_model.moveUp(1)
        entries = populated_model.getEntries()
        assert entries[0] == "/bin"
        assert entries[1] == "/usr/bin"

    def test_move_up_first_is_noop(self, populated_model):
        original = populated_model.getEntries()
        populated_model.moveUp(0)
        assert populated_model.getEntries() == original

    def test_move_down(self, populated_model):
        populated_model.moveDown(0)
        entries = populated_model.getEntries()
        assert entries[0] == "/bin"
        assert entries[1] == "/usr/bin"

    def test_move_down_last_is_noop(self, populated_model):
        original = populated_model.getEntries()
        populated_model.moveDown(populated_model.rowCount() - 1)
        assert populated_model.getEntries() == original

    def test_move_marks_dirty(self, populated_model):
        populated_model.moveUp(1)
        assert populated_model.pendingCount == 1

    def test_move_out_of_range_is_noop(self, populated_model):
        original = populated_model.getEntries()
        populated_model.moveUp(999)
        assert populated_model.getEntries() == original


# ---------------------------------------------------------------------------
# moveEntry
# ---------------------------------------------------------------------------

class TestMoveEntry:
    def test_move_entry_forward(self, populated_model):
        populated_model.moveEntry(0, 2)
        entries = populated_model.getEntries()
        assert entries[2] == "/usr/bin"

    def test_move_entry_backward(self, populated_model):
        populated_model.moveEntry(2, 0)
        entries = populated_model.getEntries()
        assert entries[0] == "/usr/local/bin"

    def test_move_entry_same_index_noop(self, populated_model):
        original = populated_model.getEntries()
        populated_model.moveEntry(1, 1)
        assert populated_model.getEntries() == original

    def test_move_entry_out_of_range_is_noop(self, populated_model):
        original = populated_model.getEntries()
        populated_model.moveEntry(0, 999)
        assert populated_model.getEntries() == original


# ---------------------------------------------------------------------------
# removeDuplicates
# ---------------------------------------------------------------------------

class TestRemoveDuplicates:
    def test_removes_duplicate_paths(self, qapp):
        m = PathModel()
        m.loadData(["/usr/bin", "/bin", "/usr/bin"])
        m.removeDuplicates()
        assert m.rowCount() == 2
        assert m.getEntries() == ["/usr/bin", "/bin"]

    def test_no_duplicates_is_noop(self, populated_model):
        before = populated_model.rowCount()
        populated_model.removeDuplicates()
        assert populated_model.rowCount() == before
        assert populated_model.pendingCount == 0

    def test_duplicate_flag_before_remove(self, qapp):
        m = PathModel()
        m.loadData(["/usr/bin", "/bin", "/usr/bin"])
        idx = m.index(0)
        assert m.data(idx, PathModel.DuplicateRole) is True

    def test_keeps_first_occurrence(self, qapp):
        m = PathModel()
        m.loadData(["/usr/bin", "/bin", "/usr/bin"])
        m.removeDuplicates()
        assert m.getEntries()[0] == "/usr/bin"

    def test_marks_dirty_when_duplicates_removed(self, qapp):
        m = PathModel()
        m.loadData(["/usr/bin", "/bin", "/usr/bin"])
        m.removeDuplicates()
        assert m.pendingCount == 1


# ---------------------------------------------------------------------------
# setFilter
# ---------------------------------------------------------------------------

class TestFilter:
    def test_filter_by_path_fragment(self, populated_model):
        populated_model.setFilter("local")
        assert populated_model.rowCount() == 1
        idx = populated_model.index(0)
        assert populated_model.data(idx, PathModel.PathRole) == "/usr/local/bin"

    def test_filter_case_insensitive(self, populated_model):
        populated_model.setFilter("USR")
        assert populated_model.rowCount() == 2

    def test_filter_no_match(self, populated_model):
        populated_model.setFilter("zzznomatch")
        assert populated_model.rowCount() == 0

    def test_clear_filter_restores_all(self, populated_model):
        populated_model.setFilter("local")
        populated_model.setFilter("")
        assert populated_model.rowCount() == 3

    def test_filter_does_not_affect_pending_count(self, populated_model):
        populated_model.addEntry("/extra")
        populated_model.setFilter("zzznomatch")
        assert populated_model.pendingCount == 1


# ---------------------------------------------------------------------------
# discardChanges
# ---------------------------------------------------------------------------

class TestDiscardChanges:
    def test_discard_clears_dirty(self, populated_model):
        populated_model.addEntry("/new")
        populated_model.discardChanges()
        assert populated_model.pendingCount == 0

    def test_discard_removes_added_entries(self, populated_model):
        before = populated_model.rowCount()
        populated_model.addEntry("/new")
        populated_model.discardChanges()
        assert populated_model.rowCount() == before

    def test_discard_reverts_edits(self, populated_model):
        populated_model.editEntry(0, "/changed")
        populated_model.discardChanges()
        assert populated_model.getEntries()[0] == "/usr/bin"

    def test_discard_restores_deleted_entries(self, populated_model):
        before = populated_model.rowCount()
        populated_model.deleteEntry(0)
        populated_model.discardChanges()
        assert populated_model.rowCount() == before

    def test_discard_restores_original_order(self, populated_model):
        original = populated_model.getEntries()
        populated_model.moveUp(1)
        populated_model.discardChanges()
        assert populated_model.getEntries() == original


# ---------------------------------------------------------------------------
# getEntries / pendingCount signal
# ---------------------------------------------------------------------------

class TestGetEntries:
    def test_returns_all_paths_in_order(self, populated_model):
        assert populated_model.getEntries() == ["/usr/bin", "/bin", "/usr/local/bin"]

    def test_reflects_edits(self, populated_model):
        populated_model.editEntry(0, "/edited")
        assert populated_model.getEntries()[0] == "/edited"


class TestPendingCountSignal:
    def test_signal_emitted_on_add(self, populated_model, qtbot):
        with qtbot.waitSignal(populated_model.pendingCountChanged, timeout=500):
            populated_model.addEntry("/new")

    def test_signal_emitted_on_delete(self, populated_model, qtbot):
        with qtbot.waitSignal(populated_model.pendingCountChanged, timeout=500):
            populated_model.deleteEntry(0)

    def test_signal_emitted_on_discard(self, populated_model, qtbot):
        populated_model.addEntry("/new")
        with qtbot.waitSignal(populated_model.pendingCountChanged, timeout=500):
            populated_model.discardChanges()
