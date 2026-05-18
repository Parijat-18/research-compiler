"""Eval protocol driver.

For each paper × condition: fresh repo, plugin install (B/C), compile (B/C),
launch a Claude Code session bounded by `SESSION_BUDGET`, capture transcript +
final repo.

This script orchestrates external processes; it does not perform grading.
Grading is in `eval/grader/`.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from .conditions import CONDITIONS, IMPLEMENTATION_PROMPT, SESSION_BUDGET


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)


def _install_plugin(repo: Path, plugin_dir: Path) -> None:
    # No-op in-place: Claude Code is launched with --plugin-dir.
    pass


def _compile_paper(plugin_dir: Path, repo: Path, paper_id: str, env: dict[str, str]) -> dict:
    cli = plugin_dir / "cli" / "bin" / "paper-compiler"
    out = repo / "research"
    started = time.time()
    proc = subprocess.run(
        [sys.executable, str(cli), "build", paper_id, "--out", str(out)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )
    manifest = out / "build-manifest.json"
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "duration_sec": round(time.time() - started, 1),
        "manifest": json.loads(manifest.read_text()) if manifest.exists() else None,
    }


def _launch_session(repo: Path, condition: str, plugin_dir: Path, env: dict[str, str]) -> dict:
    """Launch a Claude Code session in headless mode.

    The actual harness depends on the user's Claude Code CLI: we shell out to
    `claude` with --plugin-dir for B/C, --no-plugin for A, and a quoted prompt.
    Returns the session transcript path and exit status.
    """
    args = ["claude", "code"]
    if condition in {"B", "C"}:
        args += ["--plugin-dir", str(plugin_dir)]
    else:
        args += ["--no-plugin"]
    args += [
        "--max-tool-calls",
        str(SESSION_BUDGET["max_tool_calls"]),
        "--max-wall-minutes",
        str(SESSION_BUDGET["wall_minutes"]),
        "--prompt",
        IMPLEMENTATION_PROMPT,
    ]
    transcript = repo / "transcript.jsonl"
    args += ["--transcript", str(transcript)]
    proc = subprocess.run(args, cwd=repo, env=env, capture_output=True, text=True)
    return {
        "returncode": proc.returncode,
        "transcript": str(transcript) if transcript.exists() else None,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def _condition_env(condition: str, base_env: dict[str, str]) -> dict[str, str]:
    env = dict(base_env)
    cond = CONDITIONS[condition]
    if cond.install_plugin and not cond.enable_mcp_tools:
        env["PAPER_COMPILER_DISABLE_MCP"] = "1"
    return env


def run(args: argparse.Namespace) -> int:
    plugin_dir = Path(args.plugin_dir).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cond = CONDITIONS[args.condition]
    results: list[dict] = []

    with open(args.paper_csv) as fh:
        rows = list(csv.DictReader(fh))

    for row in rows:
        slug = row["slug"]
        paper_id = row["paper_id"]
        repo = out_dir / args.condition / slug
        repo.mkdir(parents=True, exist_ok=True)
        _git_init(repo)
        env = _condition_env(args.condition, os.environ.copy())

        compile_result = None
        if cond.install_plugin:
            _install_plugin(repo, plugin_dir)
            compile_result = _compile_paper(plugin_dir, repo, paper_id, env)
            if compile_result["returncode"] != 0:
                print(f"compile failed for {slug}: see {repo}", file=sys.stderr)

        session = _launch_session(repo, args.condition, plugin_dir, env)
        results.append(
            {
                "slug": slug,
                "paper_id": paper_id,
                "condition": args.condition,
                "repo": str(repo),
                "compile": compile_result,
                "session": session,
                "condition_meta": asdict(cond),
            }
        )

    log = out_dir / f"runlog-{args.condition}.json"
    log.write_text(json.dumps(results, indent=2, default=str))
    print(f"wrote {log}", file=sys.stderr)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="eval.protocol")
    p.add_argument("--condition", choices=["A", "B", "C"], required=True)
    p.add_argument("--paper-csv", required=True)
    p.add_argument("--plugin-dir", default="plugin-scaffold")
    p.add_argument("--out", default="runs")
    return run(p.parse_args())


if __name__ == "__main__":
    sys.exit(main())
