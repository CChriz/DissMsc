#!/usr/bin/env python3
"""
jw_set_personas.py — set the member personas of an installed experiment family
(rewrites <family>/leader_home/.jiuwenswarm/config/config.yaml in place).

Usage (run in WSL as cz776; restart the family's leader afterwards):

  # from a personas file (yaml list of {member_name, persona} or {member_name: persona} map)
  python3 jw_set_personas.py --family database_5 --personas-file db_personas.yaml

  # research: inject the 5 per-task researcher profiles from a MARBLE task YAML
  python3 jw_set_personas.py --family research_5 \\
      --from-marble-task MARBLE/multiagentbench/output_yaml_deepseek/task_3.yaml

  # preview without writing
  python3 jw_set_personas.py --family research_5 --from-marble-task ... --dry-run

  # target a staging dir instead of the installed root
  python3 jw_set_personas.py --family coding_3 --root ./jw_exp_homes --personas-file p.yaml

MARBLE profiles are wrapped with the harness context (spec/workspace paths + messaging
instruction) so members still know where the task and deliverable live.
"""
import argparse
import sys

import yaml

EXP_ROOT = "/srv/jwteam/exp"

WRAPPER = (
    "{profile}\n\n"
    "---\n"
    "You are {member} on a {n}-member team working the current task.\n"
    "The full task specification is at {root}/run_current/spec/spec.md and the shared "
    "workspace is {root}/run_current/workspace.\n"
    "Collaborate with your teammates via send_message and converge on the deliverable "
    "the spec requires."
)


def load_personas(args, members, family_root, n):
    data = yaml.safe_load(open(args.personas_file, encoding="utf-8"))
    if isinstance(data, dict):
        return {k: str(v) for k, v in data.items()}
    if isinstance(data, list):
        return {d["member_name"]: d["persona"] for d in data}
    raise SystemExit("personas file must be a map or a list of {member_name, persona}")


def roster_from_marble_task(task_path, family_root, max_nodes):
    """Build a full roster (resizing to the task's agent count) from a MARBLE task."""
    task = yaml.safe_load(open(task_path, encoding="utf-8"))
    agents = task.get("agents", [])
    k = len(agents)
    if k > max_nodes:
        raise SystemExit(
            f"task has {k} agents but this family provisions only {max_nodes} node "
            f"homes — pick another task or extend the family in jw_exp_homes.py")
    roster = []
    for i, a in enumerate(agents, 1):
        m = f"agent{i}"
        roster.append({
            "member_name": m,
            "display_name": f"Agent {i}",
            "role_type": "teammate",
            "persona": WRAPPER.format(profile=a.get("profile", "").strip(),
                                      member=m, n=k, root=family_root),
        })
    return roster


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True)
    ap.add_argument("--root", default=EXP_ROOT,
                    help="parent of <family>/ (default: installed root)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--personas-file")
    src.add_argument("--from-marble-task")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg_path = f"{args.root}/{args.family}/leader_home/.jiuwenswarm/config/config.yaml"
    cfg = yaml.safe_load(open(cfg_path, encoding="utf-8"))
    team = cfg["modes"]["team"]["jiuwen_team"]
    roster = team.get("predefined_members", [])
    members = [m["member_name"] for m in roster]
    family_root = f"{args.root}/{args.family}"
    # node homes provisioned for the family cap the roster size (see jw_exp_homes.py)
    max_nodes = {"research_var": 10}.get(args.family, len(roster))

    if args.from_marble_task:
        # per-task mode: RESIZE the roster to the task's agent count + inject profiles
        new_roster = roster_from_marble_task(args.from_marble_task, family_root, max_nodes)
        team["predefined_members"] = new_roster
        for m in new_roster:
            print(f"[SET] {m['member_name']}: {m['persona'][:90].replace(chr(10), ' ')}...")
        print(f"roster resized: {len(roster)} -> {len(new_roster)} members; "
              f"launch with ./launch_all.sh {len(new_roster)}")
    else:
        personas = load_personas(args, members, family_root, len(members))
        unknown = set(personas) - set(members)
        if unknown:
            raise SystemExit(
                f"personas for unknown members {sorted(unknown)}; roster is {members}")
        for m in roster:
            if m["member_name"] in personas:
                m["persona"] = personas[m["member_name"]]
        for m in roster:
            tag = "SET" if m["member_name"] in personas else "kept"
            print(f"[{tag}] {m['member_name']}: {m['persona'][:90].replace(chr(10), ' ')}...")

    if args.dry_run:
        print("(dry run — nothing written)")
        return
    yaml.safe_dump(cfg, open(cfg_path, "w", encoding="utf-8"),
                   allow_unicode=True, sort_keys=False, width=4096)
    print(f"written: {cfg_path}\nRestart the family's leader to pick up the new personas.")


if __name__ == "__main__":
    main()
