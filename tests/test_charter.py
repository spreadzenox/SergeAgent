#!/usr/bin/env python3
"""Charte structurelle : tailles P1, chemins policy R4, imports acycliques."""

from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.policy import load_policy  # noqa: E402

MAX_FILE_LINES = 500
POLICY_ACCESS_RE = re.compile(r"policy((?:\[['\"][^'\"]+['\"]\])+)")
SUBSCRIPT_RE = re.compile(r"\['\"]([^'\"]+)['\"]\]")


def _modules() -> dict[str, Path]:
    """Fichier .py (kit/, serge/) -> nom de module pointé."""
    found: dict[str, Path] = {}
    for base in ('kit', 'serge'):
        for path in sorted((ROOT / base).rglob('*.py')):
            rel = path.relative_to(ROOT).with_suffix('')
            parts = list(rel.parts)
            if parts[-1] == '__init__':
                parts = parts[:-1]
            found['.'.join(parts)] = path
    return found


def _local_edges(path: Path, modules: dict[str, Path]) -> set[str]:
    """Modules kit/serge importés par ce fichier (graphe acyclique P1)."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    edges: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in modules:
                    edges.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if not node.module:
                continue
            base = node.module
            if base.startswith('serge.') or base.startswith('kit.'):
                if base in modules:
                    edges.add(base)
                for alias in node.names:
                    candidate = f'{base}.{alias.name}'
                    if candidate in modules:
                        edges.add(candidate)
    return edges


class CharterTests(unittest.TestCase):
    def test_fichiers_sous_500_lignes(self) -> None:
        oversize = []
        for name, path in _modules().items():
            lines = len(path.read_text(encoding='utf-8').splitlines())
            if lines > MAX_FILE_LINES:
                oversize.append(f'{name} ({lines})')
        self.assertEqual(oversize, [])

    def test_chemins_policy_existent(self) -> None:
        policy = load_policy()
        missing = []
        for name, path in _modules().items():
            text = path.read_text(encoding='utf-8')
            for match in POLICY_ACCESS_RE.finditer(text):
                keys = SUBSCRIPT_RE.findall(match.group(1))
                node: object = policy
                for key in keys:
                    if not isinstance(node, dict) or key not in node:
                        missing.append(f'{name}: {".".join(keys)}')
                        break
                    node = node[key]
        self.assertEqual(missing, [])

    def test_collect_sans_llm(self) -> None:
        """C0 : 0 slot LLM sur documents financiers (anti-import)."""
        offenders = []
        for path in sorted((ROOT / 'serge/collect').rglob('*.py')):
            text = path.read_text(encoding='utf-8')
            for match in re.finditer(
                r'^\s*(?:from|import)\s+(\S+)', text, re.MULTILINE
            ):
                if 'llm' in match.group(1).lower():
                    offenders.append(f'{path.name}: {match.group(1)}')
        self.assertEqual(offenders, [])

    def test_graphe_imports_acyclique(self) -> None:
        modules = _modules()
        edges = {
            name: _local_edges(path, modules) - {name}
            for name, path in modules.items()
        }
        visiting: set[str] = set()
        done: set[str] = set()
        cycle: list[str] = []

        def visit(node: str, stack: list[str]) -> None:
            if node in done or cycle:
                return
            if node in visiting:
                cycle.extend([*stack, node])
                return
            visiting.add(node)
            for target in sorted(edges.get(node, ())):
                visit(target, [*stack, node])
            visiting.discard(node)
            done.add(node)

        for name in sorted(edges):
            visit(name, [])
        self.assertEqual(cycle, [])

    def test_mc_python_sans_html(self) -> None:
        patterns = [re.compile(r'<[A-Za-z]'), re.compile(r'innerHTML')]
        for path in sorted((ROOT / 'serge/mc').rglob('*.py')):
            text = path.read_text(encoding='utf-8')
            for pattern in patterns:
                self.assertIsNone(
                    pattern.search(text),
                    f'{path.name} : HTML/JS interdit (A1)',
                )

    def test_mc_innerhtml_dans_patch_uniquement(self) -> None:
        for path in sorted((ROOT / 'serge/mc/static').rglob('*.js')):
            if path.name == 'patch.js':
                continue
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('innerHTML', text, f'{path.name} (A4)')


if __name__ == '__main__':
    unittest.main()
