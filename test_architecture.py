from __future__ import annotations

import ast
import unittest
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class ArchitectureTests(unittest.TestCase):
    def test_feature_modules_have_no_runtime_global_injection(self):
        offenders = []
        for path in sorted(ROOT.glob("feature_*.py")):
            source = path.read_text(encoding="utf-8")
            if "bind_app_globals" in source or "globals().update(namespace)" in source:
                offenders.append(path.name)
        self.assertEqual(offenders, [])

    def test_feature_mixin_methods_do_not_collide(self):
        owners: dict[str, list[str]] = defaultdict(list)

        for path in sorted(ROOT.glob("feature_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:
                if not isinstance(node, ast.ClassDef) or not node.name.endswith("Mixin"):
                    continue
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        owners[item.name].append(f"{path.name}:{node.name}")

        collisions = {
            name: locations
            for name, locations in owners.items()
            if len(locations) > 1
        }
        self.assertEqual(collisions, {})

    def test_app_vars_are_instance_owned(self):
        tree = ast.parse(
            (ROOT / "app.py").read_text(encoding="utf-8"),
            filename="app.py",
        )
        logger = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "LoggerApp"
        )

        class_level_vars = {
            target.id
            for node in logger.body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
            )
            if isinstance(target, ast.Name)
        }
        self.assertNotIn("_vars", class_level_vars)

    def test_all_python_sources_parse(self):
        failures = {}
        for path in sorted(ROOT.glob("*.py")):
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                failures[path.name] = str(exc)
        self.assertEqual(failures, {})


if __name__ == "__main__":
    unittest.main()
