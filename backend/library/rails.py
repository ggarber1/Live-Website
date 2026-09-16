"""Safety rails shared by the media scanners.

A scanner treats disk as the truth and the table as a rebuildable index, so
its dangerous operation is removal. These rails keep one bad scan (an
unmounted drive, a reconfigured root) from gutting a table.
"""

# A scan may not delete more than this share of the table without
# --force-removals. Zero files found is the limiting case.
REMOVAL_LIMIT = 0.5
# Below this many rows the proportional check is a nuisance, not a guard.
REMOVAL_FLOOR = 10


class ScanAborted(RuntimeError):
    """The scan refused to act. The CLI prints the message and exits non-zero."""


def refuse_mass_removal(root, stale, indexed, found_any, table, noun, variable):
    """Raise ScanAborted if deleting `stale` would gut `table`.

    Returns normally when the removal looks like ordinary attrition.

    This is deliberately louder than the unreadable-directory case, which
    defers removal silently: there we know the walk was incomplete, so
    skipping removal is automatically right. Here the walk succeeded and the
    result merely looks destructive, which needs a human to confirm.
    """
    if not found_any:
        raise ScanAborted(
            f"found no {noun} files under {root} but {table} holds "
            f"{len(indexed)} rows; refusing to delete them. "
            "Is the drive mounted? Pass --force-removals to proceed anyway."
        )
    if len(indexed) < REMOVAL_FLOOR:
        return
    share = len(stale) / len(indexed)
    if share > REMOVAL_LIMIT:
        raise ScanAborted(
            f"scan would remove {len(stale)} of {len(indexed)} rows "
            f"({share:.0%}) under {root}; refusing. Did {variable} change, or "
            "did the drive remount under a different path? Pass "
            "--force-removals to proceed anyway."
        )
