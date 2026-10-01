from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentic_dev_env.worktrees import (
    clean_worktree,
    create_worktree,
    list_worktrees,
    worktree_status,
)
import subprocess


class WorktreeTests(unittest.TestCase):
    def repo(self) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "README.md").write_text("demo\n")
        subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
        subprocess.run([
            "git", "-C", str(root),
            "-c", "user.name=Agentic Test",
            "-c", "user.email=agentic@example.invalid",
            "commit", "-qm", "init",
        ], check=True)
        return root

    def test_create_list_status_clean(self):
        root = self.repo()
        wt_root = Path(tempfile.mkdtemp())
        created = create_worktree(
            "feature-a", root,
            agent="codex", task="implement feature A",
            worktree_root=wt_root,
        )
        wt = Path(created["worktree"])
        self.assertTrue(wt.exists())
        self.assertEqual(created["branch"], "agentic/feature-a")
        self.assertTrue((wt / ".agentic/session.json").exists())

        listed = list_worktrees(root)
        matching = [x for x in listed["worktrees"] if Path(x["worktree"]) == wt]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["session"]["agent"], "codex")
        self.assertEqual(matching[0]["session"]["task"], "implement feature A")

        status = worktree_status("feature-a", root)
        self.assertFalse(status["dirty"])
        self.assertEqual(status["branch"], "agentic/feature-a")

        result = clean_worktree("feature-a", root, delete_branch=True)
        self.assertFalse(wt.exists())
        self.assertTrue(result["deleted_branch"])

    def test_dirty_worktree_requires_force(self):
        root = self.repo()
        wt_root = Path(tempfile.mkdtemp())
        created = create_worktree("dirty", root, worktree_root=wt_root)
        wt = Path(created["worktree"])
        (wt / "uncommitted.txt").write_text("dirty\n")
        with self.assertRaises(RuntimeError):
            clean_worktree("dirty", root)
        self.assertTrue(wt.exists())
        clean_worktree("dirty", root, force=True, delete_branch=True)
        self.assertFalse(wt.exists())

    def test_collision_is_rejected(self):
        root = self.repo()
        wt_root = Path(tempfile.mkdtemp())
        create_worktree("same", root, worktree_root=wt_root)
        with self.assertRaises(FileExistsError):
            create_worktree("same", root, worktree_root=wt_root)
        clean_worktree("same", root, force=True, delete_branch=True)

    def test_primary_worktree_cannot_be_cleaned(self):
        root = self.repo()
        with self.assertRaises(ValueError):
            clean_worktree(root.name, root)


if __name__ == "__main__":
    unittest.main()
