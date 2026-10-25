"""Incremental Treeview updates for the logbook view.

Rebuilding a 20 000-row ``ttk.Treeview`` after every saved, edited or deleted
QSO costs seconds of Tk work.  ``plan_row_diff`` compares the rows currently
shown with the new rows and returns a small list of operations when the
relative order of the remaining rows is unchanged (the normal case for add,
edit, delete and status changes).  Otherwise ``None`` is returned and the
caller performs a full rebuild.

Rows are ``(iid, tag, values)`` tuples.  Inserting/updating uses direct Tcl
calls: ttk's generic option formatting dominated the per-row cost.
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

Row = tuple[str, str, tuple]
DEFAULT_MAX_OPS = 2000


def plan_row_diff(old: Sequence[Row], new: Sequence[Row], *, max_ops: int = DEFAULT_MAX_OPS) -> list[tuple] | None:
    """Return ``[("delete", iid) | ("insert", index, row) | ("update", row)]`` or ``None``.

    Applying the operations in order to a tree that shows ``old`` yields
    exactly ``new`` (same ids, order, tags and values).
    """
    old_ids = [row[0] for row in old]
    new_ids = [row[0] for row in new]
    old_set = set(old_ids)
    new_set = set(new_ids)
    if len(old_set) != len(old_ids) or len(new_set) != len(new_ids):
        return None  # duplicate ids: let the full rebuild handle them
    if [iid for iid in old_ids if iid in new_set] != [iid for iid in new_ids if iid in old_set]:
        return None  # reordered rows: full rebuild is simpler and safe
    ops: list[tuple] = [("delete", iid) for iid in old_ids if iid not in new_set]
    old_by_id = {row[0]: row for row in old}
    for index, row in enumerate(new):
        previous = old_by_id.get(row[0])
        if previous is None:
            ops.append(("insert", index, row))
        elif previous[1] != row[1] or tuple(previous[2]) != tuple(row[2]):
            ops.append(("update", row))
        if len(ops) > max_ops:
            return None
    return ops


def insert_row(tree: Any, index: Any, row: Row) -> None:
    iid, tag, values = row
    tree.tk.call(tree._w, "insert", "", index, "-id", iid, "-values", tuple(values), "-tags", (tag,))


def update_row(tree: Any, row: Row) -> None:
    iid, tag, values = row
    tree.tk.call(tree._w, "item", iid, "-values", tuple(values), "-tags", (tag,))


def apply_row_diff(tree: Any, ops: Iterable[tuple]) -> None:
    ops = list(ops)
    deletes = [op[1] for op in ops if op[0] == "delete"]
    if deletes:
        existing = [iid for iid in deletes if tree.exists(iid)]
        if existing:
            tree.delete(*existing)
    for op in ops:
        if op[0] == "insert":
            insert_row(tree, op[1], op[2])
        elif op[0] == "update":
            update_row(tree, op[1])
