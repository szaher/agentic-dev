from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .detect import detect_repo, repo_root
from .integrations import install as install_integration, status as integration_status
from .skills import activate, context_and_recommendations, get_skill, installed_skills, load_registry, remove, skill_content


def _print_recommendations(path: str, task: str, max_skills: int, as_json: bool):
    context, recs = context_and_recommendations(path, task, max_skills)
    if as_json:
        print(json.dumps({
            "root": str(context.root),
            "facts": sorted(context.facts),
            "evidence": context.evidence,
            "recommendations": [
                {
                    "name": r.skill.name,
                    "category": r.skill.category,
                    "description": r.skill.description,
                    "score": r.score,
                    "recommended": r.recommended,
                    "reasons": r.reasons,
                }
                for r in recs
            ],
        }, indent=2))
        return context, recs

    print(f"\nRepository: {context.root.name}")
    print("Detected context:")
    for fact in sorted(context.facts):
        reasons = "; ".join(context.evidence.get(fact, []))
        print(f"  - {fact}" + (f" — {reasons}" if reasons else ""))
    if task:
        print(f"Task context: {task}")

    print("\nSkill recommendations:")
    if not recs:
        print("  No strong recommendations. Use 'agentic skills list' to browse available skills.")
        return context, recs

    for i, r in enumerate(recs, 1):
        mark = "✓" if r.recommended else " "
        why = "; ".join(r.reasons[:3]) or "general workflow skill"
        print(f"  {i:>2}. [{mark}] {r.skill.name:<32} {r.skill.description}")
        print(f"      why: {why}")
    return context, recs


def cmd_skills_suggest(args: argparse.Namespace) -> int:
    context, recs = _print_recommendations(args.path, args.task or "", args.max, args.json)
    if args.json:
        return 0

    selected = [r.skill.name for r in recs if r.recommended]
    if args.yes:
        pass
    elif args.no_prompt or not sys.stdin.isatty():
        print("\nNo skills activated. Re-run interactively, use --yes, or use 'agentic skills add <name>'.")
        return 0
    else:
        prompt = "\nSelect skills [Enter=recommended, comma-separated numbers, a=all, n=none]: "
        answer = input(prompt).strip().lower()
        if answer in {"n", "none"}:
            return 0
        if answer in {"a", "all"}:
            selected = [r.skill.name for r in recs]
        elif answer:
            chosen: list[str] = []
            for token in answer.split(","):
                token = token.strip()
                if not token:
                    continue
                try:
                    idx = int(token)
                except ValueError:
                    print(f"Invalid selection: {token}", file=sys.stderr)
                    return 2
                if idx < 1 or idx > len(recs):
                    print(f"Selection out of range: {idx}", file=sys.stderr)
                    return 2
                chosen.append(recs[idx - 1].skill.name)
            selected = chosen

    if not selected:
        print("No skills selected.")
        return 0

    paths = activate(
        context.root,
        selected,
        shared=args.shared,
        target=args.target,
        force=args.force,
    )
    print("\nActivated:")
    for p in paths:
        print(f"  ✓ {p.relative_to(context.root)}")
    if not args.shared:
        print("  Local mode: generated skill directories are excluded via .git/info/exclude.")
    return 0


def cmd_skills_list(args: argparse.Namespace) -> int:
    skills = load_registry()
    if args.json:
        print(json.dumps([s.__dict__ for s in skills], indent=2))
        return 0
    for s in skills:
        print(f"{s.name:<32} [{s.category}] {s.description}")
    return 0


def cmd_skills_explain(args: argparse.Namespace) -> int:
    try:
        s = get_skill(args.name)
    except KeyError:
        print(f"Unknown skill: {args.name}", file=sys.stderr)
        return 2
    print(f"{s.name}\n  category: {s.category}\n  {s.description}")
    if s.signals:
        print("  repo signals: " + ", ".join(s.signals))
    if s.task_keywords:
        print("  task triggers: " + ", ".join(s.task_keywords))
    if args.full:
        print("\n" + skill_content(s.name))
    return 0


def cmd_skills_add(args: argparse.Namespace) -> int:
    root = repo_root(args.path)
    try:
        paths = activate(root, args.names, shared=args.shared, target=args.target, force=args.force)
    except KeyError as e:
        print(f"Unknown skill: {e.args[0]}", file=sys.stderr)
        return 2
    for p in paths:
        print(f"✓ {p.relative_to(root)}")
    return 0


def cmd_skills_remove(args: argparse.Namespace) -> int:
    root = repo_root(args.path)
    for p in remove(root, args.names, target=args.target):
        print(f"✓ removed {p.relative_to(root)}")
    return 0


def cmd_skills_status(args: argparse.Namespace) -> int:
    root = repo_root(args.path)
    found = installed_skills(root)
    print(f"Repository: {root}")
    print("Claude: " + (", ".join(found["claude"]) or "none"))
    print("Codex:  " + (", ".join(found["codex"]) or "none"))
    print("Pi:     " + (", ".join(found["pi"]) or "none"))
    return 0


def _exec_script(name: str, argv: list[str]) -> int:
    path = shutil.which(name)
    if not path:
        print(f"{name} is not installed. Run ./install.sh from agentic-dev-env.", file=sys.stderr)
        return 2
    return subprocess.call([path, *argv])


def cmd_setup(args: argparse.Namespace) -> int:
    return _exec_script("setup-coding-agent-env.sh", args.args)


def cmd_repo_init(args: argparse.Namespace) -> int:
    argv = [args.path]
    flag_map = [
        ("check", "--check"),
        ("no_codegraph", "--no-codegraph"),
        ("no_serena", "--no-serena"),
        ("no_instructions", "--no-instructions"),
        ("no_install_language_deps", "--no-install-language-deps"),
        ("no_runtime_install", "--no-runtime-install"),
        ("install_project_deps", "--install-project-deps"),
        ("no_skills", "--no-skills"),
        ("skills_yes", "--skills-yes"),
        ("skills_shared", "--skills-shared"),
    ]
    for attr, flag in flag_map:
        if getattr(args, attr):
            argv.append(flag)
    if args.task:
        argv += ["--task", args.task]
    if args.skills_target:
        argv += ["--skills-target", args.skills_target]
    return _exec_script("saad-tool-repo-init.sh", argv)


def cmd_doctor(args: argparse.Namespace) -> int:
    tools = [
        "git", "gh", "rg", "fd", "ast-grep", "serena", "codegraph",
        "repomix", "mise", "uv", "jq", "yq", "just",
    ]
    bad = 0
    print("Agentic development environment:")
    for tool in tools:
        path = shutil.which(tool)
        if path:
            print(f"  ✓ {tool:<14} {path}")
        else:
            print(f"  ! {tool:<14} missing")
            bad += 1
    print(f"  {'✓' if shutil.which('claude') else '!'} {'claude':<14} {shutil.which('claude') or 'not installed'}")
    print(f"  {'✓' if shutil.which('codex') else '!'} {'codex':<14} {shutil.which('codex') or 'not installed'}")
    print(f"  {'✓' if shutil.which('pi') else '!'} {'pi':<14} {shutil.which('pi') or 'not installed'}")
    print("\nNative integrations:")
    for item in integration_status():
        mark = "✓" if item.configured else ("·" if not item.available else "!")
        print(f"  {mark} {item.name:<14} {item.detail}")
    return 1 if bad else 0


def cmd_integrations_status(args: argparse.Namespace) -> int:
    for item in integration_status():
        mark = "✓" if item.configured else ("·" if not item.available else "!")
        print(f"{mark} {item.name:<8} {item.detail}")
    return 0


def cmd_integrations_install(args: argparse.Namespace) -> int:
    return install_integration(args.target)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentic", description="Agentic development environment manager")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="Run the workstation bootstrap")
    setup.add_argument("args", nargs=argparse.REMAINDER)
    setup.set_defaults(func=cmd_setup)

    repo = sub.add_parser("repo", help="Repository operations")
    repo_sub = repo.add_subparsers(dest="repo_command", required=True)
    init = repo_sub.add_parser("init", help="Initialize/check a repository")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--task", default="")
    init.add_argument("--check", action="store_true")
    init.add_argument("--no-codegraph", action="store_true")
    init.add_argument("--no-serena", action="store_true")
    init.add_argument("--no-instructions", action="store_true")
    init.add_argument("--no-install-language-deps", action="store_true")
    init.add_argument("--no-runtime-install", action="store_true")
    init.add_argument("--install-project-deps", action="store_true")
    init.add_argument("--no-skills", action="store_true")
    init.add_argument("--skills-yes", action="store_true")
    init.add_argument("--skills-shared", action="store_true")
    init.add_argument("--skills-target", choices=["both", "all", "claude", "codex", "pi"], default="both")
    init.set_defaults(func=cmd_repo_init)

    skills = sub.add_parser("skills", help="Context-aware Agent Skills")
    ssub = skills.add_subparsers(dest="skills_command", required=True)

    suggest = ssub.add_parser("suggest", help="Detect repo/task context and recommend skills")
    suggest.add_argument("path", nargs="?", default=".")
    suggest.add_argument("--task", default="")
    suggest.add_argument("--max", type=int, default=6)
    suggest.add_argument("--yes", action="store_true", help="Activate recommended skills without prompting")
    suggest.add_argument("--no-prompt", action="store_true")
    suggest.add_argument("--shared", action="store_true", help="Make activated skills commit-worthy instead of local-only")
    suggest.add_argument("--target", choices=["both", "all", "claude", "codex", "pi"], default="both")
    suggest.add_argument("--force", action="store_true")
    suggest.add_argument("--json", action="store_true")
    suggest.set_defaults(func=cmd_skills_suggest)

    ls = ssub.add_parser("list", help="List available built-in skills")
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=cmd_skills_list)

    ex = ssub.add_parser("explain", help="Explain why/when a skill is useful")
    ex.add_argument("name")
    ex.add_argument("--full", action="store_true")
    ex.set_defaults(func=cmd_skills_explain)

    add = ssub.add_parser("add", help="Activate one or more named skills")
    add.add_argument("names", nargs="+")
    add.add_argument("--path", default=".")
    add.add_argument("--shared", action="store_true")
    add.add_argument("--target", choices=["both", "all", "claude", "codex", "pi"], default="both")
    add.add_argument("--force", action="store_true")
    add.set_defaults(func=cmd_skills_add)

    rm = ssub.add_parser("remove", help="Remove agentic-dev-env managed skills")
    rm.add_argument("names", nargs="+")
    rm.add_argument("--path", default=".")
    rm.add_argument("--target", choices=["both", "all", "claude", "codex", "pi"], default="both")
    rm.set_defaults(func=cmd_skills_remove)

    status = ssub.add_parser("status", help="Show active project skills")
    status.add_argument("path", nargs="?", default=".")
    status.set_defaults(func=cmd_skills_status)

    integrations = sub.add_parser("integrations", help="Native Claude/Codex/Pi integrations")
    isub = integrations.add_subparsers(dest="integrations_command", required=True)

    istatus = isub.add_parser("status", help="Show native integration status")
    istatus.set_defaults(func=cmd_integrations_status)

    iinstall = isub.add_parser("install", help="Install/configure a native integration")
    iinstall.add_argument("target", choices=["all", "claude", "codex", "pi"])
    iinstall.set_defaults(func=cmd_integrations_install)

    doctor = sub.add_parser("doctor", help="Check the workstation toolchain and integrations")
    doctor.set_defaults(func=cmd_doctor)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
