from __future__ import annotations

import json
import shutil
import sys
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Iterable

from .detect import RepoContext, detect_repo
from .providers import skill_entries as provider_skill_entries
from .metrics import record as record_metric


MANAGED_MARKER = "<!-- managed-by: agentic-dev -->"


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    category: str
    signals: tuple[str, ...]
    task_keywords: tuple[str, ...]
    priority: int = 0
    provider: str = "builtin"


@dataclass
class Recommendation:
    skill: Skill
    score: int
    reasons: list[str]
    recommended: bool = False


def skills_root():
    return resources.files("agentic_dev").joinpath("builtin_skills")


def load_registry() -> list[Skill]:
    raw = skills_root().joinpath("registry.toml").read_bytes()
    data = tomllib.loads(raw.decode())
    skills = [
        Skill(
            name=item["name"],
            description=item["description"],
            category=item["category"],
            signals=tuple(item.get("signals", [])),
            task_keywords=tuple(item.get("task_keywords", [])),
            priority=int(item.get("priority", 0)),
            provider="builtin",
        )
        for item in data["skill"]
    ]
    names = {skill.name for skill in skills}
    for item, _root, provider in provider_skill_entries():
        name = item["name"]
        if name in names:
            continue
        skills.append(Skill(
            name=name,
            description=item["description"],
            category=item["category"],
            signals=tuple(item.get("signals", [])),
            task_keywords=tuple(item.get("task_keywords", [])),
            priority=int(item.get("priority", 0)),
            provider=provider,
        ))
        names.add(name)
    return skills


def get_skill(name: str) -> Skill:
    for skill in load_registry():
        if skill.name == name:
            return skill
    raise KeyError(name)


def skill_content(name: str) -> str:
    skill = get_skill(name)
    if skill.provider == "builtin":
        return skills_root().joinpath(name, "SKILL.md").read_text()
    for item, root, provider in provider_skill_entries():
        if provider == skill.provider and item["name"] == name:
            path = root / item["path"]
            if path.is_dir():
                path = path / "SKILL.md"
            return path.read_text()
    raise KeyError(name)


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
                score += 5
                reasons.append(f"task mentions '{keyword}'")
        if reasons:
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


# Harness -> project skill directory. ``both`` means Claude + Codex (OpenCode also
# reads .claude/skills); ``all`` covers every harness.
SKILL_DIRS = {
    "claude": (".claude", "skills"),
    "codex": (".codex", "skills"),
    "pi": (".pi", "skills"),
    "opencode": (".opencode", "skills"),
}
TARGETS = ("both", "all", *SKILL_DIRS)


def skill_roots(root: Path, target: str) -> list[Path]:
    if target not in TARGETS:
        raise ValueError(f"unknown skills target {target!r}; choose one of: {', '.join(TARGETS)}")
    harnesses = {"both": ("claude", "codex"), "all": tuple(SKILL_DIRS)}.get(target, (target,))
    return [root.joinpath(*SKILL_DIRS[name]) for name in harnesses]


def activate_report(
    root: Path,
    names: Iterable[str],
    *,
    shared: bool = False,
    target: str = "both",
    force: bool = False,
) -> list[dict[str, str]]:
    """Place skills and report every (skill, harness) outcome.

    ``written`` (created or updated), ``unchanged`` (already identical), or
    ``skipped-unmanaged`` (a SKILL.md not managed by agentic-dev exists there and
    was left alone; ``force`` overrides).
    """

    harnesses = {"both": ("claude", "codex"), "all": tuple(SKILL_DIRS)}.get(target, (target,))
    roots = list(zip(harnesses, skill_roots(root, target)))
    names = list(dict.fromkeys(names))
    for name in names:
        get_skill(name)  # validate every name before any write

    outcomes: list[dict[str, str]] = []
    for name in names:
        content = skill_content(name).rstrip() + "\n\n" + MANAGED_MARKER + "\n"
        for harness, base in roots:
            dest = base / name
            skill_md = dest / "SKILL.md"
            rel = skill_md.relative_to(root).as_posix()
            if skill_md.exists() and not _managed(skill_md) and not force:
                print(f"! {skill_md} exists and is not managed by agentic-dev; skipped.", file=sys.stderr)
                outcomes.append({"skill": name, "harness": harness, "path": rel, "status": "skipped-unmanaged"})
                continue
            if skill_md.is_file() and skill_md.read_text() == content:
                status = "unchanged"
            else:
                dest.mkdir(parents=True, exist_ok=True)
                skill_md.write_text(content)
                status = "written"
            outcomes.append({"skill": name, "harness": harness, "path": rel, "status": status})
            if not shared:
                _git_exclude(root, "/" + dest.relative_to(root).as_posix() + "/")
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
    record_metric(
        "skills.activated",
        {
            "count": len(set(names)),
            "names": sorted(set(names)),
            "target": target,
            "shared": shared,
            "providers": sorted({get_skill(name).provider for name in set(names)}),
        },
        repository=root,
    )
    return outcomes


def activate(
    root: Path,
    names: Iterable[str],
    *,
    shared: bool = False,
    target: str = "both",
    force: bool = False,
) -> list[Path]:
    """Place skills; return the skill directories that are now managed copies."""

    outcomes = activate_report(root, names, shared=shared, target=target, force=force)
    return [(root / o["path"]).parent for o in outcomes if o["status"] != "skipped-unmanaged"]


def remove(root: Path, names: Iterable[str], target: str = "both") -> list[Path]:
    roots = skill_roots(root, target)

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
    found: dict[str, list[str]] = {name: [] for name in SKILL_DIRS}
    for target, parts in SKILL_DIRS.items():
        base = root.joinpath(*parts)
        if base.is_dir():
            found[target] = sorted(p.name for p in base.iterdir() if (p / "SKILL.md").exists())
    return found


def context_and_recommendations(path: str | Path, task: str = "", max_recommended: int = 6):
    context = detect_repo(path)
    return context, recommend(context, task=task, max_recommended=max_recommended)
