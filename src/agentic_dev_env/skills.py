from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Iterable

from .detect import RepoContext, detect_repo


MANAGED_MARKER = "<!-- managed-by: agentic-dev-env -->"


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    category: str
    signals: tuple[str, ...]
    task_keywords: tuple[str, ...]
    priority: int = 0


@dataclass
class Recommendation:
    skill: Skill
    score: int
    reasons: list[str]
    recommended: bool = False


def skills_root():
    return resources.files("agentic_dev_env").joinpath("builtin_skills")


def load_registry() -> list[Skill]:
    raw = skills_root().joinpath("registry.toml").read_bytes()
    data = tomllib.loads(raw.decode())
    return [
        Skill(
            name=item["name"],
            description=item["description"],
            category=item["category"],
            signals=tuple(item.get("signals", [])),
            task_keywords=tuple(item.get("task_keywords", [])),
            priority=int(item.get("priority", 0)),
        )
        for item in data["skill"]
    ]


def get_skill(name: str) -> Skill:
    for skill in load_registry():
        if skill.name == name:
            return skill
    raise KeyError(name)


def skill_content(name: str) -> str:
    return skills_root().joinpath(name, "SKILL.md").read_text()


def recommend(context: RepoContext, task: str = "", max_recommended: int = 6) -> list[Recommendation]:
    task_l = task.lower().strip()
    result: list[Recommendation] = []
    for skill in load_registry():
        reasons: list[str] = []
        score = skill.priority
        for signal in skill.signals:
            if signal in context.facts:
                score += 5
                ev = context.evidence.get(signal, [])
                reasons.append(ev[0] if ev else signal)
        for keyword in skill.task_keywords:
            if task_l and keyword.lower() in task_l:
                score += 4
                reasons.append(f"task mentions '{keyword}'")
        if score > skill.priority or skill.priority > 0:
            result.append(Recommendation(skill=skill, score=score, reasons=reasons))

    result.sort(key=lambda r: (-r.score, -r.skill.priority, r.skill.name))
    eligible = [r for r in result if r.score >= 5]
    for r in eligible[: max(1, min(max_recommended, 7))]:
        r.recommended = True
    return result


def _git_exclude(root: Path, entry: str) -> None:
    import subprocess

    try:
        git_path = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-path", "info/exclude"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:
        return
    p = Path(git_path)
    if not p.is_absolute():
        p = root / p
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = p.read_text().splitlines() if p.exists() else []
    if entry not in existing:
        with p.open("a") as f:
            if existing and existing[-1] != "":
                f.write("\n")
            f.write(entry + "\n")


def _managed(path: Path) -> bool:
    try:
        return MANAGED_MARKER in path.read_text(errors="ignore")
    except OSError:
        return False


def activate(
    root: Path,
    names: Iterable[str],
    *,
    shared: bool = False,
    target: str = "both",
    force: bool = False,
) -> list[Path]:
    roots: list[Path] = []
    if target in {"both", "claude"}:
        roots.append(root / ".claude" / "skills")
    if target in {"both", "codex"}:
        roots.append(root / ".agents" / "skills")

    installed: list[Path] = []
    for name in names:
        get_skill(name)  # validate before writes
        content = skill_content(name)
        for base in roots:
            dest = base / name
            skill_md = dest / "SKILL.md"
            if skill_md.exists() and not _managed(skill_md) and not force:
                print(f"! {skill_md} exists and is not managed by agentic-dev-env; skipped.", file=sys.stderr)
                continue
            dest.mkdir(parents=True, exist_ok=True)
            skill_md.write_text(content.rstrip() + "\n\n" + MANAGED_MARKER + "\n")
            installed.append(dest)
            if not shared:
                rel = "/" + dest.relative_to(root).as_posix() + "/"
                _git_exclude(root, rel)

    state_dir = root / ".agentic"
    state_dir.mkdir(exist_ok=True)
    state = {
        "skills": sorted(set(names)),
        "mode": "shared" if shared else "local",
        "target": target,
    }
    (state_dir / "skills.json").write_text(json.dumps(state, indent=2) + "\n")
    if not shared:
        _git_exclude(root, "/.agentic/")
    return installed


def remove(root: Path, names: Iterable[str], target: str = "both") -> list[Path]:
    roots: list[Path] = []
    if target in {"both", "claude"}:
        roots.append(root / ".claude" / "skills")
    if target in {"both", "codex"}:
        roots.append(root / ".agents" / "skills")

    removed: list[Path] = []
    for name in names:
        for base in roots:
            dest = base / name
            skill_md = dest / "SKILL.md"
            if skill_md.exists():
                if not _managed(skill_md):
                    print(f"! Refusing to remove unmanaged skill: {dest}", file=sys.stderr)
                    continue
                shutil.rmtree(dest)
                removed.append(dest)
    return removed


def installed_skills(root: Path) -> dict[str, list[str]]:
    found = {"claude": [], "codex": []}
    for target, base in [
        ("claude", root / ".claude" / "skills"),
        ("codex", root / ".agents" / "skills"),
    ]:
        if base.is_dir():
            found[target] = sorted(p.name for p in base.iterdir() if (p / "SKILL.md").exists())
    return found


def context_and_recommendations(path: str | Path, task: str = "", max_recommended: int = 6):
    context = detect_repo(path)
    return context, recommend(context, task=task, max_recommended=max_recommended)
