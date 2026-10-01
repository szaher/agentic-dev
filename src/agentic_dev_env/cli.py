from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .capabilities import disable as disable_capability, enable as enable_capability, list_capabilities, run_capability, status as capability_status, suggest_for_repo
from .detect import detect_repo, repo_root
from .integrations import install as install_integration, status as integration_status
from .inspection import doctor_document, inspect_repository
from .infrastructure import (
    cloud_identity, cloud_write, cluster_run, database_exec, database_local_list,
    database_local_show, database_local_start, database_local_stop,
    database_schema, migration_check, observability_status, status as infrastructure_status,
)
from .execution import configure as configure_execution, run as run_execution, status as execution_status
from .skills import activate, context_and_recommendations, get_skill, installed_skills, load_registry, remove, skill_content
from .trust import define_profile, document as trust_document, get_profile, set_current
from .worktrees import clean_worktree, create_worktree, list_worktrees, worktree_status
from .verification import execute as execute_verification, plan as verification_plan
from .providers import (
    add_provider, doctor as provider_doctor, installed as installed_providers,
    migrate as migrate_provider, remove_provider, update_all as update_all_providers,
    update_provider, verify_provider,
)
from .remote import add as add_remote, get as get_remote, list_profiles as list_remotes, remove as remove_remote, status as remote_status, test as test_remote


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


def cmd_repo_inspect(args: argparse.Namespace) -> int:
    document = inspect_repository(args.path, task=args.task or "")
    if args.json:
        print(json.dumps(document, indent=2, sort_keys=True))
        return 0

    repo = document["repository"]
    print(f"Repository: {repo['name']}")
    print(f"Root: {repo['root']}")
    print("Facts:")
    for fact in repo["facts"]:
        print(f"  - {fact}")
    print("Commands:")
    for kind, values in document["commands"].items():
        print(f"  {kind:<10} " + (", ".join(values) if values else "not detected"))
    recommended = [x["name"] for x in document["skills"]["recommended"] if x["recommended"]]
    print("Recommended skills: " + (", ".join(recommended) if recommended else "none"))
    enabled_caps = [name for name, item in document["capabilities"].items() if item["enabled"]]
    print("Enabled capabilities: " + (", ".join(enabled_caps) if enabled_caps else "none"))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(doctor_document(), indent=2, sort_keys=True))
        return 0

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
    print("\nOptional capabilities:")
    for name, item in capability_status().items():
        mark = "✓" if item["enabled"] else "·"
        print(f"  {mark} {name:<22} {item['provider']}")
    return 1 if bad else 0


def cmd_worktree_create(args: argparse.Namespace) -> int:
    try:
        data = create_worktree(
            args.name, args.path,
            branch=args.branch, base=args.base,
            agent=args.agent, task=args.task,
            worktree_root=args.root,
        )
    except (ValueError, FileExistsError, subprocess.CalledProcessError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(f"✓ worktree: {data['worktree']}")
        print(f"  branch: {data['branch']}")
        if data["session"].get("agent"):
            print(f"  agent: {data['session']['agent']}")
        if data["session"].get("task"):
            print(f"  task: {data['session']['task']}")
    return 0


def cmd_worktree_list(args: argparse.Namespace) -> int:
    data = list_worktrees(args.path)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0
    for item in data["worktrees"]:
        session = item.get("session") or {}
        mark = "*" if Path(item["worktree"]).resolve() == Path(data["repository"]).resolve() else " "
        dirty = " dirty" if item.get("dirty") else ""
        print(f"{mark} {item['worktree']} [{item.get('branch', 'detached')}]{dirty}")
        if session.get("agent") or session.get("task"):
            print(f"    agent={session.get('agent') or '-'} task={session.get('task') or '-'}")
    return 0


def cmd_worktree_status(args: argparse.Namespace) -> int:
    try:
        data = worktree_status(args.name, args.path)
    except KeyError as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(json.dumps(data, indent=2))
    return 0


def cmd_worktree_clean(args: argparse.Namespace) -> int:
    try:
        data = clean_worktree(
            args.name, args.path,
            force=args.force,
            delete_branch=args.delete_branch,
        )
    except (KeyError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(f"✓ removed {data['worktree']}")
        if args.delete_branch:
            print(f"  branch deleted: {data['deleted_branch']}")
    return 0


def _verification_args(args: argparse.Namespace) -> tuple[str, str | None, list[str] | None]:
    return (
        getattr(args, "path", "."),
        getattr(args, "base", None),
        getattr(args, "symbol", None),
    )


def cmd_verify_plan(args: argparse.Namespace) -> int:
    path, base, symbols = _verification_args(args)
    data = verification_plan(path, base=base, symbols=symbols)
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0
    print(f"Repository: {data['repository']}")
    print("Changed files:")
    for file in data["changed_files"]:
        print(f"  - {file}")
    print("Verification checks:")
    if not data["checks"]:
        print("  none")
    for check in data["checks"]:
        command = check.get("command") or check.get("test_file") or "-"
        print(f"  - [{check['kind']}] {command}")
        print(f"      {check['reason']}")
    if data["skipped_checks"]:
        print("Skipped:")
        for check in data["skipped_checks"]:
            print(f"  - [{check['kind']}] {check['command']} — {check['reason']}")
    return 0


def cmd_verify_run(args: argparse.Namespace) -> int:
    path, base, symbols = _verification_args(args)
    plan = verification_plan(path, base=base, symbols=symbols)
    data = execute_verification(
        plan,
        continue_on_failure=getattr(args, "continue_on_failure", False),
        backend=getattr(args, "backend", None),
        image=getattr(args, "image", None),
        network=getattr(args, "network", None),
        profile=getattr(args, "profile", None),
    )
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        for result in data["results"]:
            mark = "✓" if result.get("success") is True else ("·" if result.get("success") is None else "!")
            label = result.get("command") or result.get("test_file") or result.get("capability")
            print(f"{mark} {result['kind']}: {label}")
        print("verification: " + ("passed" if data["success"] else "failed"))
    return 0 if data["success"] else 1


def cmd_execution_status(args: argparse.Namespace) -> int:
    data = execution_status(args.path)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        selected = data["selected"]
        print(f"backend: {selected['backend']}")
        print(f"image: {selected.get('image') or '-'}")
        print(f"network: {selected.get('network') or 'none'}")
        for name, item in data["backends"].items():
            mark = "✓" if item["available"] else "·"
            print(f"{mark} {name:<14} {item.get('binary') or 'built-in'}")
    return 0


def cmd_execution_configure(args: argparse.Namespace) -> int:
    try:
        data = configure_execution(
            backend=args.backend,
            path=args.path,
            image=args.image,
            network=args.network,
            repo_scope=args.repo,
        )
    except ValueError as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2, sort_keys=True) if args.json else f"✓ {data['scope']} backend={data['backend']}")
    return 0


def cmd_execution_run(args: argparse.Namespace) -> int:
    try:
        data = run_execution(
            args.command,
            args.path,
            backend=args.backend,
            image=args.image,
            network=args.network,
            profile=args.profile,
        )
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        if data["stdout"]:
            print(data["stdout"], end="" if data["stdout"].endswith("\n") else "\n")
        if data["stderr"]:
            print(data["stderr"], file=sys.stderr, end="" if data["stderr"].endswith("\n") else "\n")
    return 0 if data["success"] else data["returncode"] or 1


def _print_json_or_summary(data: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(json.dumps(data, indent=2))
    success = data.get("success")
    return 0 if success is not False else 1


def cmd_infra_status(args: argparse.Namespace) -> int:
    return _print_json_or_summary(infrastructure_status(args.path), args.json)


def cmd_infra_database_schema(args: argparse.Namespace) -> int:
    try:
        data = database_schema(
            args.engine, path=args.path, database=args.database,
            sqlite_file=args.sqlite_file, profile=args.profile,
        )
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    return _print_json_or_summary(data, args.json)


def cmd_infra_database_exec(args: argparse.Namespace) -> int:
    try:
        data = database_exec(
            args.engine, args.query,
            path=args.path, database=args.database,
            sqlite_file=args.sqlite_file, write=args.write,
            profile=args.profile,
        )
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    return _print_json_or_summary(data, args.json)


def cmd_infra_database_migration_check(args: argparse.Namespace) -> int:
    try:
        data = migration_check(
            args.path, profile=args.profile, backend=args.backend,
        )
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    return _print_json_or_summary(data, args.json)


def cmd_infra_database_local_start(args: argparse.Namespace) -> int:
    try:
        data = database_local_start(
            args.engine, args.image,
            name=args.name, profile=args.profile,
        )
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    return _print_json_or_summary(data, args.json)


def cmd_infra_database_local_list(args: argparse.Namespace) -> int:
    return _print_json_or_summary(database_local_list(), args.json)


def cmd_infra_database_local_show(args: argparse.Namespace) -> int:
    try:
        data = database_local_show(args.name, show_secret=args.show_secret)
    except KeyError as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    return _print_json_or_summary(data, args.json)


def cmd_infra_database_local_stop(args: argparse.Namespace) -> int:
    try:
        data = database_local_stop(args.name, profile=args.profile)
    except (KeyError, RuntimeError, PermissionError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    return _print_json_or_summary(data, args.json)


def cmd_infra_cluster_run(args: argparse.Namespace) -> int:
    try:
        data = cluster_run(
            args.verb, args.args,
            tool=args.tool, context=args.context,
            namespace=args.namespace, profile=args.profile,
        )
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    return _print_json_or_summary(data, args.json)


def cmd_infra_cloud_identity(args: argparse.Namespace) -> int:
    try:
        data = cloud_identity(args.provider, profile=args.profile)
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    return _print_json_or_summary(data, args.json)


def cmd_infra_cloud_write(args: argparse.Namespace) -> int:
    try:
        data = cloud_write(args.provider, args.args, profile=args.profile)
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    return _print_json_or_summary(data, args.json)


def cmd_infra_observability_status(args: argparse.Namespace) -> int:
    try:
        data = observability_status(args.path, profile=args.profile)
    except (RuntimeError, PermissionError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    return _print_json_or_summary(data, args.json)


def cmd_integrations_status(args: argparse.Namespace) -> int:
    for item in integration_status():
        mark = "✓" if item.configured else ("·" if not item.available else "!")
        print(f"{mark} {item.name:<8} {item.detail}")
    return 0


def cmd_integrations_install(args: argparse.Namespace) -> int:
    return install_integration(args.target)


def cmd_capabilities_list(args: argparse.Namespace) -> int:
    for item in list_capabilities():
        targets = ",".join(item.targets)
        print(f"{item.name:<24} category={item.category:<10} provider={item.provider:<16} targets={targets}")
        print(f"  {item.description}")
        print(f"  permissions: {', '.join(item.required_permissions) or 'none'}")
        print(f"  risk: {item.risk}")
    return 0


def cmd_capabilities_suggest(args: argparse.Namespace) -> int:
    context, recs = suggest_for_repo(args.path, args.task or "")
    if args.json:
        print(json.dumps({
            "root": str(context.root),
            "facts": sorted(context.facts),
            "recommendations": [
                {
                    "name": r.name,
                    "provider": r.provider,
                    "description": r.description,
                    "reasons": list(r.reasons),
                    "score": r.score,
                }
                for r in recs
            ],
        }, indent=2))
        return 0
    print(f"Repository: {context.root}")
    if not recs:
        print("No optional capability strongly recommended.")
        return 0
    for r in recs:
        print(f"✓ {r.name} via {r.provider}")
        print(f"  {r.description}")
        print(f"  why: {'; '.join(r.reasons)}")
    print("\nNothing was enabled. Use 'agentic capabilities enable <name>' explicitly.")
    return 0


def cmd_capabilities_enable(args: argparse.Namespace) -> int:
    try:
        return enable_capability(
            args.name,
            target=args.target,
            mode=args.mode,
            profile=args.profile,
            path=args.path,
        )
    except (KeyError, ValueError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2


def cmd_capabilities_run(args: argparse.Namespace) -> int:
    try:
        result = run_capability(
            args.name,
            args.path,
            image=args.image,
            profile=args.profile,
        )
    except (KeyError, ValueError, RuntimeError, PermissionError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['capability']} via {result['provider']}")
        print(f"success: {result['success']}")
        if result.get("finding_count") is not None:
            print(f"findings/components: {result['finding_count']}")
        if result.get("stderr"):
            print(result["stderr"])
    return 0 if result["success"] else 1


def cmd_capabilities_disable(args: argparse.Namespace) -> int:
    try:
        return disable_capability(args.name)
    except (KeyError, ValueError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2


def cmd_trust_list(args: argparse.Namespace) -> int:
    data = trust_document(args.path)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0
    for name, item in data["profiles"].items():
        mark = "*" if item["selected"] else " "
        print(f"{mark} {name:<18} {item['description']}")
        print("    " + ", ".join(item["permissions"]))
    return 0


def cmd_trust_show(args: argparse.Namespace) -> int:
    try:
        if args.name:
            p = get_profile(args.name)
            data = {
                "name": p.name,
                "description": p.description,
                "permissions": sorted(p.permissions),
            }
        else:
            data = trust_document(args.path)
    except KeyError as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(json.dumps(data, indent=2))
    return 0


def cmd_trust_set(args: argparse.Namespace) -> int:
    try:
        set_current(args.name, root=args.path if args.repo else None)
    except KeyError as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    scope = f"repo {Path(args.path).resolve()}" if args.repo else "user"
    print(f"✓ trust profile '{args.name}' selected for {scope}")
    return 0


def cmd_trust_define(args: argparse.Namespace) -> int:
    try:
        define_profile(args.name, args.permission, args.description)
    except ValueError as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    print(f"✓ defined trust profile '{args.name}'")
    return 0


def cmd_capabilities_status(args: argparse.Namespace) -> int:
    data = capability_status()
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    for name, item in data.items():
        mark = "✓" if item["enabled"] else "·"
        detail = item["configuration"] or {}
        suffix = f" ({detail.get('target')}, {detail.get('mode')})" if detail else ""
        print(f"{mark} {name:<22} {item['provider']}{suffix}")
    return 0



def cmd_providers_list(args: argparse.Namespace) -> int:
    data = {
        "schema_version": "1",
        "document_type": "agentic.providers",
        "providers": installed_providers(),
    }
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        if not data["providers"]:
            print("No external providers installed.")
        for item in data["providers"]:
            mark = "✓" if item.get("verified") and item.get("compatible") else "!"
            source = item.get("commit_sha") or item.get("content_digest", "")[:12]
            print(f"{mark} {item['name']:<24} {item.get('version','?'):<10} {source}")
    return 0


def cmd_providers_add(args: argparse.Namespace) -> int:
    try:
        data = add_provider(
            args.source,
            ref=args.ref,
            expected_sha256=args.sha256,
            require_signed_commit=args.require_signed_commit,
        )
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2, sort_keys=True) if args.json else f"✓ installed provider {data['name']} {data['version']}")
    return 0


def cmd_providers_verify(args: argparse.Namespace) -> int:
    try:
        data = verify_provider(args.name)
    except (KeyError, ValueError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2, sort_keys=True) if args.json else (
        f"{'✓' if data['valid'] else '!'} {data['name']} " + ("verified" if data["valid"] else "; ".join(data["reasons"]))
    ))
    return 0 if data["valid"] else 1


def cmd_providers_remove(args: argparse.Namespace) -> int:
    if not args.yes:
        print("agentic: provider removal requires --yes", file=sys.stderr)
        return 2
    try:
        remove_provider(args.name)
    except KeyError as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    print(f"✓ removed provider {args.name}")
    return 0


def cmd_providers_update(args: argparse.Namespace) -> int:
    try:
        if args.name == "all":
            data = update_all_providers(yes=args.yes)
        else:
            data = [update_provider(
                args.name,
                yes=args.yes,
                require_signed_commit=args.require_signed_commit,
            )]
    except (KeyError, ValueError, RuntimeError, PermissionError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2, sort_keys=True) if args.json else "\n".join(
        f"✓ {item['name']} {item.get('previous_version','?')} -> {item['version']} changed={item.get('changed', False)}"
        for item in data
    ))
    return 0


def cmd_providers_migrate(args: argparse.Namespace) -> int:
    try:
        data = migrate_provider(args.name, yes=args.yes)
    except (KeyError, ValueError, RuntimeError, PermissionError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2, sort_keys=True) if args.json else (
        "\n".join(f"{'✓' if x['returncode'] == 0 else '!'} migration {x['version']}" for x in data)
        or "No pending migrations."
    ))
    return 0 if all(x["returncode"] == 0 for x in data) else 1


def cmd_providers_doctor(args: argparse.Namespace) -> int:
    data = provider_doctor()
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(f"platform: {data['platform']} agentic={data['agentic_version']}")
        for item in data["providers"]:
            mark = "✓" if item.get("verified") and item.get("requirements_ok") else "!"
            print(f"{mark} {item['name']:<24} version={item.get('version','?')}")
            for group, reqs in (item.get("requirements") or {}).items():
                missing = [name for name, ok in reqs.items() if not ok]
                if missing:
                    print(f"    missing {group}: {', '.join(missing)}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    try:
        data = update_all_providers(yes=args.yes)
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2, sort_keys=True) if args.json else (
        "\n".join(f"✓ provider {x['name']} changed={x.get('changed', False)}" for x in data)
        or "No external providers installed."
    ))
    return 0



def cmd_remote_list(args: argparse.Namespace) -> int:
    data = remote_status()
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(f"ssh available: {data['ssh_available']}")
        for item in data["remotes"]:
            target = f"{item.get('user')+'@' if item.get('user') else ''}{item['host']}"
            port = f":{item['port']}" if item.get("port") else ""
            print(f"- {item['name']}: {target}{port} workdir={item.get('workdir') or '-'}")
    return 0


def cmd_remote_add(args: argparse.Namespace) -> int:
    try:
        data = add_remote(
            args.name, args.host,
            user=args.user, port=args.port,
            identity_file=args.identity_file,
            workdir=args.workdir,
        )
    except ValueError as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2, sort_keys=True) if args.json else f"✓ remote {args.name} configured")
    return 0


def cmd_remote_show(args: argparse.Namespace) -> int:
    try:
        data = get_remote(args.name)
    except KeyError:
        print(f"agentic: unknown remote {args.name}", file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


def cmd_remote_remove(args: argparse.Namespace) -> int:
    try:
        remove_remote(args.name)
    except KeyError:
        print(f"agentic: unknown remote {args.name}", file=sys.stderr)
        return 2
    print(f"✓ removed remote {args.name}")
    return 0


def cmd_remote_test(args: argparse.Namespace) -> int:
    try:
        data = test_remote(args.name)
    except (KeyError, RuntimeError) as exc:
        print(f"agentic: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2, sort_keys=True) if args.json else (
        f"{'✓' if data['success'] else '!'} {args.name}: {data['host']}"
    ))
    return 0 if data["success"] else 1


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

    inspect_cmd = repo_sub.add_parser("inspect", help="Inspect repository context without modifying it")
    inspect_cmd.add_argument("path", nargs="?", default=".")
    inspect_cmd.add_argument("--task", default="")
    inspect_cmd.add_argument("--json", action="store_true")
    inspect_cmd.set_defaults(func=cmd_repo_inspect)

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

    capabilities = sub.add_parser("capabilities", help="Optional capability packs such as browser automation")
    csub = capabilities.add_subparsers(dest="capabilities_command", required=True)

    clist = csub.add_parser("list", help="List optional capabilities")
    clist.set_defaults(func=cmd_capabilities_list)

    csuggest = csub.add_parser("suggest", help="Recommend optional capabilities from repo/task context")
    csuggest.add_argument("path", nargs="?", default=".")
    csuggest.add_argument("--task", default="")
    csuggest.add_argument("--json", action="store_true")
    csuggest.set_defaults(func=cmd_capabilities_suggest)

    cenable = csub.add_parser("enable", help="Explicitly enable an optional capability")
    cenable.add_argument("name", choices=[c.name for c in list_capabilities()])
    cenable.add_argument("--target", choices=["claude", "codex", "both"], default="both")
    cenable.add_argument("--mode", choices=["isolated", "persistent", "existing-browser", "headless"], default="isolated")
    cenable.add_argument("--profile", default=None, help="Override the selected trust profile for this enable operation")
    cenable.add_argument("--path", default=".", help="Repository used for repo-scoped trust profile lookup")
    cenable.set_defaults(func=cmd_capabilities_enable)

    crun = csub.add_parser("run", help="Run a security capability and emit normalized results")
    crun.add_argument("name", choices=[c.name for c in list_capabilities() if c.category == "security"])
    crun.add_argument("path", nargs="?", default=".")
    crun.add_argument("--image", default=None, help="Container image for container-image-scan")
    crun.add_argument("--profile", default=None)
    crun.add_argument("--json", action="store_true")
    crun.set_defaults(func=cmd_capabilities_run)

    cdisable = csub.add_parser("disable", help="Disable a managed optional capability")
    cdisable.add_argument("name", choices=[c.name for c in list_capabilities()])
    cdisable.set_defaults(func=cmd_capabilities_disable)

    cstatus = csub.add_parser("status", help="Show optional capability state")
    cstatus.add_argument("--json", action="store_true")
    cstatus.set_defaults(func=cmd_capabilities_status)

    trust = sub.add_parser("trust", help="Trust and permission profiles")
    tsub = trust.add_subparsers(dest="trust_command", required=True)

    tlist = tsub.add_parser("list", help="List trust profiles")
    tlist.add_argument("--path", default=".")
    tlist.add_argument("--json", action="store_true")
    tlist.set_defaults(func=cmd_trust_list)

    tshow = tsub.add_parser("show", help="Show a trust profile or current trust document")
    tshow.add_argument("name", nargs="?", default=None)
    tshow.add_argument("--path", default=".")
    tshow.add_argument("--json", action="store_true")
    tshow.set_defaults(func=cmd_trust_show)

    tset = tsub.add_parser("set", help="Select a trust profile")
    tset.add_argument("name")
    tset.add_argument("--repo", action="store_true", help="Set for this repository instead of user default")
    tset.add_argument("--path", default=".")
    tset.set_defaults(func=cmd_trust_set)

    tdef = tsub.add_parser("define", help="Define a custom user trust profile")
    tdef.add_argument("name")
    tdef.add_argument("--permission", action="append", required=True)
    tdef.add_argument("--description", default="")
    tdef.set_defaults(func=cmd_trust_define)

    worktree = sub.add_parser("worktree", help="Isolated Git worktrees for parallel agents")
    wsub = worktree.add_subparsers(dest="worktree_command", required=True)

    wcreate = wsub.add_parser("create", help="Create an isolated agent worktree")
    wcreate.add_argument("name")
    wcreate.add_argument("--path", default=".")
    wcreate.add_argument("--branch", default=None)
    wcreate.add_argument("--base", default="HEAD")
    wcreate.add_argument("--agent", default=None)
    wcreate.add_argument("--task", default=None)
    wcreate.add_argument("--root", default=None)
    wcreate.add_argument("--json", action="store_true")
    wcreate.set_defaults(func=cmd_worktree_create)

    wlist = wsub.add_parser("list", help="List worktrees and session metadata")
    wlist.add_argument("--path", default=".")
    wlist.add_argument("--json", action="store_true")
    wlist.set_defaults(func=cmd_worktree_list)

    wstatus = wsub.add_parser("status", help="Show one worktree/session")
    wstatus.add_argument("name")
    wstatus.add_argument("--path", default=".")
    wstatus.add_argument("--json", action="store_true")
    wstatus.set_defaults(func=cmd_worktree_status)

    wclean = wsub.add_parser("clean", help="Safely remove an agent worktree")
    wclean.add_argument("name")
    wclean.add_argument("--path", default=".")
    wclean.add_argument("--force", action="store_true")
    wclean.add_argument("--delete-branch", action="store_true")
    wclean.add_argument("--json", action="store_true")
    wclean.set_defaults(func=cmd_worktree_clean)

    verify = sub.add_parser("verify", help="Plan or run change-aware verification")
    verify.add_argument("--path", default=".")
    verify.add_argument("--base", default=None)
    verify.add_argument("--symbol", action="append", default=None)
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(func=cmd_verify_plan)
    vsub = verify.add_subparsers(dest="verify_command")

    vplan = vsub.add_parser("plan", help="Create a verification plan")
    vplan.add_argument("--path", default=".")
    vplan.add_argument("--base", default=None)
    vplan.add_argument("--symbol", action="append", default=None)
    vplan.add_argument("--json", action="store_true")
    vplan.set_defaults(func=cmd_verify_plan)

    vrun = vsub.add_parser("run", help="Execute the selected verification checks")
    vrun.add_argument("--path", default=".")
    vrun.add_argument("--base", default=None)
    vrun.add_argument("--symbol", action="append", default=None)
    vrun.add_argument("--continue-on-failure", action="store_true")
    vrun.add_argument("--backend", choices=["host", "container", "devcontainer", "dagger"], default=None)
    vrun.add_argument("--image", default=None)
    vrun.add_argument("--network", choices=["none", "default"], default=None)
    vrun.add_argument("--profile", default=None)
    vrun.add_argument("--json", action="store_true")
    vrun.set_defaults(func=cmd_verify_run)

    execution = sub.add_parser("execution", help="Execution backends and sandbox configuration")
    esub = execution.add_subparsers(dest="execution_command", required=True)

    estatus = esub.add_parser("status", help="Show backend availability and selected configuration")
    estatus.add_argument("--path", default=".")
    estatus.add_argument("--json", action="store_true")
    estatus.set_defaults(func=cmd_execution_status)

    econfig = esub.add_parser("configure", help="Configure the default execution backend")
    econfig.add_argument("backend", choices=["host", "container", "devcontainer", "dagger"])
    econfig.add_argument("--path", default=".")
    econfig.add_argument("--image", default=None)
    econfig.add_argument("--network", choices=["none", "default"], default="none")
    econfig.add_argument("--repo", action="store_true")
    econfig.add_argument("--json", action="store_true")
    econfig.set_defaults(func=cmd_execution_configure)

    erun = esub.add_parser("run", help="Run one command through a selected execution backend")
    erun.add_argument("command")
    erun.add_argument("--path", default=".")
    erun.add_argument("--backend", choices=["host", "container", "devcontainer", "dagger"], default=None)
    erun.add_argument("--image", default=None)
    erun.add_argument("--network", choices=["none", "default"], default=None)
    erun.add_argument("--profile", default=None)
    erun.add_argument("--json", action="store_true")
    erun.set_defaults(func=cmd_execution_run)

    infra = sub.add_parser("infra", help="Database, cluster, cloud, and observability capability packs")
    infrasub = infra.add_subparsers(dest="infra_command", required=True)

    istatus2 = infrasub.add_parser("status", help="Inspect infrastructure tooling without remote mutation")
    istatus2.add_argument("--path", default=".")
    istatus2.add_argument("--json", action="store_true")
    istatus2.set_defaults(func=cmd_infra_status)

    db = infrasub.add_parser("database", help="Database operations")
    dbsub = db.add_subparsers(dest="database_command", required=True)

    dbschema = dbsub.add_parser("schema", help="Inspect database schema")
    dbschema.add_argument("engine", choices=["sqlite", "postgres", "mysql"])
    dbschema.add_argument("--path", default=".")
    dbschema.add_argument("--database", default=None)
    dbschema.add_argument("--sqlite-file", default=None)
    dbschema.add_argument("--profile", default=None)
    dbschema.add_argument("--json", action="store_true")
    dbschema.set_defaults(func=cmd_infra_database_schema)

    dbexec = dbsub.add_parser("exec", help="Execute read-only SQL or an explicitly marked write")
    dbexec.add_argument("engine", choices=["sqlite", "postgres", "mysql"])
    dbexec.add_argument("query")
    dbexec.add_argument("--path", default=".")
    dbexec.add_argument("--database", default=None)
    dbexec.add_argument("--sqlite-file", default=None)
    dbexec.add_argument("--write", action="store_true")
    dbexec.add_argument("--profile", default=None)
    dbexec.add_argument("--json", action="store_true")
    dbexec.set_defaults(func=cmd_infra_database_exec)

    dbmig = dbsub.add_parser("migration-check", help="Run a detected migration/schema validation")
    dbmig.add_argument("--path", default=".")
    dbmig.add_argument("--backend", choices=["host", "container", "devcontainer", "dagger"], default=None)
    dbmig.add_argument("--profile", default=None)
    dbmig.add_argument("--json", action="store_true")
    dbmig.set_defaults(func=cmd_infra_database_migration_check)

    dblocal = dbsub.add_parser("local", help="Ephemeral local database containers")
    dblsub = dblocal.add_subparsers(dest="database_local_command", required=True)

    dbstart = dblsub.add_parser("start")
    dbstart.add_argument("engine", choices=["postgres", "mysql"])
    dbstart.add_argument("--image", required=True)
    dbstart.add_argument("--name", default=None)
    dbstart.add_argument("--profile", default=None)
    dbstart.add_argument("--json", action="store_true")
    dbstart.set_defaults(func=cmd_infra_database_local_start)

    dblist = dblsub.add_parser("list")
    dblist.add_argument("--json", action="store_true")
    dblist.set_defaults(func=cmd_infra_database_local_list)

    dbshow = dblsub.add_parser("show")
    dbshow.add_argument("name")
    dbshow.add_argument("--show-secret", action="store_true")
    dbshow.add_argument("--json", action="store_true")
    dbshow.set_defaults(func=cmd_infra_database_local_show)

    dbstop = dblsub.add_parser("stop")
    dbstop.add_argument("name")
    dbstop.add_argument("--profile", default=None)
    dbstop.add_argument("--json", action="store_true")
    dbstop.set_defaults(func=cmd_infra_database_local_stop)

    cluster = infrasub.add_parser("cluster", help="Kubernetes/OpenShift operations")
    csub2 = cluster.add_subparsers(dest="cluster_command", required=True)
    crun2 = csub2.add_parser("run", help="Run a classified kubectl/oc verb")
    crun2.add_argument("--tool", choices=["auto", "kubectl", "oc"], default="auto")
    crun2.add_argument("--context", default=None)
    crun2.add_argument("--namespace", default=None)
    crun2.add_argument("--profile", default=None)
    crun2.add_argument("--json", action="store_true")
    crun2.add_argument("verb")
    crun2.add_argument("args", nargs=argparse.REMAINDER)
    crun2.set_defaults(func=cmd_infra_cluster_run)

    cloud = infrasub.add_parser("cloud", help="Cloud account metadata and explicit write commands")
    cloudsub = cloud.add_subparsers(dest="cloud_command", required=True)
    cidentity = cloudsub.add_parser("identity")
    cidentity.add_argument("provider", choices=["aws", "azure", "gcp"])
    cidentity.add_argument("--profile", default=None)
    cidentity.add_argument("--json", action="store_true")
    cidentity.set_defaults(func=cmd_infra_cloud_identity)

    cwrite = cloudsub.add_parser("write", help="Explicit cloud mutation command; requires cloud.write")
    cwrite.add_argument("provider", choices=["aws", "azure", "gcp"])
    cwrite.add_argument("--profile", default=None)
    cwrite.add_argument("--json", action="store_true")
    cwrite.add_argument("args", nargs=argparse.REMAINDER)
    cwrite.set_defaults(func=cmd_infra_cloud_write)

    obs = infrasub.add_parser("observability", help="OpenTelemetry/observability status")
    obssub = obs.add_subparsers(dest="observability_command", required=True)
    obsstatus = obssub.add_parser("status")
    obsstatus.add_argument("--path", default=".")
    obsstatus.add_argument("--profile", default=None)
    obsstatus.add_argument("--json", action="store_true")
    obsstatus.set_defaults(func=cmd_infra_observability_status)



    remote = sub.add_parser("remote", help="SSH development profiles")
    rsub = remote.add_subparsers(dest="remote_command", required=True)

    rlist = rsub.add_parser("list", help="List SSH development profiles")
    rlist.add_argument("--json", action="store_true")
    rlist.set_defaults(func=cmd_remote_list)

    radd = rsub.add_parser("add", help="Add or update an SSH development profile")
    radd.add_argument("name")
    radd.add_argument("host")
    radd.add_argument("--user", default=None)
    radd.add_argument("--port", type=int, default=None)
    radd.add_argument("--identity-file", default=None)
    radd.add_argument("--workdir", default=None)
    radd.add_argument("--json", action="store_true")
    radd.set_defaults(func=cmd_remote_add)

    rshow = rsub.add_parser("show", help="Show one SSH development profile")
    rshow.add_argument("name")
    rshow.set_defaults(func=cmd_remote_show)

    rtest = rsub.add_parser("test", help="Test a profile with non-interactive SSH")
    rtest.add_argument("name")
    rtest.add_argument("--json", action="store_true")
    rtest.set_defaults(func=cmd_remote_test)

    rremove = rsub.add_parser("remove", help="Remove an SSH development profile")
    rremove.add_argument("name")
    rremove.set_defaults(func=cmd_remote_remove)

    providers = sub.add_parser("providers", help="External skill/capability provider lifecycle")
    psub = providers.add_subparsers(dest="providers_command", required=True)

    plist = psub.add_parser("list", help="List installed external providers")
    plist.add_argument("--json", action="store_true")
    plist.set_defaults(func=cmd_providers_list)

    padd = psub.add_parser("add", help="Install a local or Git provider")
    padd.add_argument("source")
    padd.add_argument("--ref", default=None, help="Git branch/tag/ref to clone")
    padd.add_argument("--sha256", default=None, help="Expected provider tree SHA-256")
    padd.add_argument("--require-signed-commit", action="store_true")
    padd.add_argument("--json", action="store_true")
    padd.set_defaults(func=cmd_providers_add)

    pverify = psub.add_parser("verify", help="Verify installed provider content")
    pverify.add_argument("name")
    pverify.add_argument("--json", action="store_true")
    pverify.set_defaults(func=cmd_providers_verify)

    pupdate = psub.add_parser("update", help="Update one provider or all providers")
    pupdate.add_argument("name", nargs="?", default="all")
    pupdate.add_argument("--yes", action="store_true", help="Required to modify provider source")
    pupdate.add_argument("--require-signed-commit", action="store_true")
    pupdate.add_argument("--json", action="store_true")
    pupdate.set_defaults(func=cmd_providers_update)

    pmigrate = psub.add_parser("migrate", help="Run explicit provider migration hooks")
    pmigrate.add_argument("name")
    pmigrate.add_argument("--yes", action="store_true", help="Required to execute provider hooks")
    pmigrate.add_argument("--json", action="store_true")
    pmigrate.set_defaults(func=cmd_providers_migrate)

    premove = psub.add_parser("remove", help="Remove an external provider")
    premove.add_argument("name")
    premove.add_argument("--yes", action="store_true")
    premove.set_defaults(func=cmd_providers_remove)

    pdoctor = psub.add_parser("doctor", help="Check provider integrity, compatibility, and requirements")
    pdoctor.add_argument("--json", action="store_true")
    pdoctor.set_defaults(func=cmd_providers_doctor)

    update = sub.add_parser("update", help="Update installed external providers")
    update.add_argument("--yes", action="store_true", help="Required to change provider source")
    update.add_argument("--json", action="store_true")
    update.set_defaults(func=cmd_update)

    integrations = sub.add_parser("integrations", help="Native Claude/Codex/Pi integrations")
    isub = integrations.add_subparsers(dest="integrations_command", required=True)

    istatus = isub.add_parser("status", help="Show native integration status")
    istatus.set_defaults(func=cmd_integrations_status)

    iinstall = isub.add_parser("install", help="Install/configure a native integration")
    iinstall.add_argument("target", choices=["all", "claude", "codex", "pi"])
    iinstall.set_defaults(func=cmd_integrations_install)

    doctor = sub.add_parser("doctor", help="Check the workstation toolchain and integrations")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
