"""Tool-calling panel for `test_tool_calls.py`.

Modeled on how coding agents (Claude Code, Cline, OpenCode, Kimi CLI) talk to
a model: a fixed toolbox of file / shell / search tools with strict JSON
schemas, and conversations that are either fresh requests or mid-task turns
with prior tool results already in the history.

Each item's `meta` carries the expectation used for the absolute accuracy
score (the primary signal is still reference-vs-target agreement):

  expect      "tool"  — a tool call is the right move
              "none"  — the right move is to answer in prose
  allowed     tool names that count as a sensible call (when expect="tool")
  min_calls   minimum number of calls in one turn (parallel tool calls)

Panel design notes (Kimi K2 Vendor Verifier methodology):
  * The vendor verifier's two headline numbers are *tool-call trigger
    agreement* (does the endpoint decide to call a tool on the same requests
    the official API does) and *schema accuracy* (are the emitted arguments
    valid JSON that satisfy the tool's schema). Quantized / mis-templated
    deployments fail these long before they fail a chat benchmark.
  * We mix ~2/3 "should call" with ~1/3 "should answer" so trigger agreement
    is measured in both directions (over-calling and under-calling).
  * Every schema sets `additionalProperties: false` and has required
    fields, so sloppy argument generation is visible.

Bump TOOL_CALLS_PANEL_ID whenever tools, prompts or the sampling
temperature change.
"""

from __future__ import annotations

import json
from typing import Any, List

from framework import PromptItem

TOOL_CALLS_PANEL_ID = "tool-calls-v1"

# Vendor-recommended agentic sampling temperature for the open-weight coding
# models we audit (Kimi K2 / GLM / Qwen-coder docs all sit at 0.6–0.7).
# Part of the measurement: changing it requires a panel id bump.
TOOL_CALLS_TEMPERATURE = 0.6


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


TOOLS: tuple[dict[str, Any], ...] = (
    _fn(
        "read_file",
        "Read a text file from the workspace. Optionally restrict to a 1-based inclusive line range.",
        {
            "path": {"type": "string", "description": "Workspace-relative file path."},
            "start_line": {"type": "integer", "minimum": 1},
            "end_line": {"type": "integer", "minimum": 1},
        },
        ["path"],
    ),
    _fn(
        "write_file",
        "Create or overwrite a file with the given full contents.",
        {
            "path": {"type": "string"},
            "content": {"type": "string", "description": "Complete new file contents."},
        },
        ["path", "content"],
    ),
    _fn(
        "edit_file",
        "Replace an exact string in a file. old_string must match the file exactly once unless replace_all is true.",
        {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean"},
        },
        ["path", "old_string", "new_string"],
    ),
    _fn(
        "run_command",
        "Run a shell command in the workspace root and return stdout/stderr and the exit code.",
        {
            "command": {"type": "string"},
            "timeout_s": {"type": "integer", "minimum": 1, "maximum": 600},
        },
        ["command"],
    ),
    _fn(
        "search_code",
        "Search the workspace with a regular expression. Returns matching lines with file paths and line numbers.",
        {
            "pattern": {"type": "string", "description": "Regular expression."},
            "glob": {"type": "string", "description": "Optional file glob filter, e.g. '**/*.py'."},
            "case_sensitive": {"type": "boolean"},
        },
        ["pattern"],
    ),
    _fn(
        "list_directory",
        "List files and folders under a workspace path.",
        {
            "path": {"type": "string"},
            "depth": {"type": "integer", "minimum": 1, "maximum": 5},
        },
        ["path"],
    ),
    _fn(
        "git",
        "Run a read-only git subcommand.",
        {
            "subcommand": {"type": "string", "enum": ["status", "diff", "log", "show", "blame"]},
            "args": {"type": "array", "items": {"type": "string"}},
        },
        ["subcommand"],
    ),
)

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    t["function"]["name"]: t["function"]["parameters"] for t in TOOLS
}

_SYS = (
    "You are a coding agent working inside the user's repository. Use the "
    "provided tools to inspect and change files and to run commands. Prefer "
    "acting over asking. When the user only asks a conceptual question that "
    "does not depend on their code, answer directly without calling tools. "
    "Keep prose short."
)


def _user(text: str) -> tuple[dict[str, Any], ...]:
    return ({"role": "system", "content": _SYS}, {"role": "user", "content": text})


def _after_tool(
    user: str,
    calls: list[tuple[str, dict[str, Any], str]],
    follow_up: str | None = None,
) -> tuple[dict[str, Any], ...]:
    """Conversation where the assistant already called tools and got results.

    `calls` is [(tool_name, arguments, tool_result_text)]. Tool-call ids are
    deterministic so the panel hash is stable."""
    msgs: list[dict[str, Any]] = [
        {"role": "system", "content": _SYS},
        {"role": "user", "content": user},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": f"call_{i}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
                for i, (name, args, _) in enumerate(calls)
            ],
        },
    ]
    for i, (_, _, result) in enumerate(calls):
        msgs.append({"role": "tool", "tool_call_id": f"call_{i}", "content": result})
    if follow_up:
        msgs.append({"role": "user", "content": follow_up})
    return tuple(msgs)


def _tool(*allowed: str, min_calls: int = 1) -> dict[str, Any]:
    return {"expect": "tool", "allowed": list(allowed), "min_calls": min_calls}


_NONE = {"expect": "none", "allowed": [], "min_calls": 0}

_FAILING_TEST_OUTPUT = """\
============================= FAILURES =============================
___________________ test_parse_duration_minutes ___________________
    def test_parse_duration_minutes():
>       assert parse_duration("15m") == 900
E       AssertionError: assert 15 == 900
tests/test_timeutil.py:12: AssertionError
==================== 1 failed, 23 passed in 0.41s ===================="""

_TIMEUTIL_SRC = """\
import re

_UNITS = {"s": 1, "m": 1, "h": 3600}


def parse_duration(text: str) -> int:
    m = re.fullmatch(r"(\\d+)([smh])", text.strip())
    if not m:
        raise ValueError(f"bad duration: {text!r}")
    return int(m.group(1)) * _UNITS[m.group(2)]
"""

_PKG_JSON = """\
{
  "name": "billing-ui",
  "version": "0.4.2",
  "scripts": { "dev": "vite", "build": "vite build", "test": "vitest run", "lint": "eslint ." },
  "dependencies": { "react": "^18.3.1", "zod": "^3.23.8" },
  "devDependencies": { "vitest": "^2.1.4", "vite": "^5.4.10", "eslint": "^9.14.0" }
}"""

TOOL_CALLS_PROMPTS: List[PromptItem] = [
    # --- fresh requests that need a tool -----------------------------------
    PromptItem("read_config", _user("What port does the dev server use? It's set somewhere in config/server.yaml."),
               _tool("read_file", "search_code")),
    PromptItem("run_tests", _user("Run the test suite with pytest and tell me what fails."),
               _tool("run_command")),
    PromptItem("find_todo", _user("Find every TODO comment in the Python files."),
               _tool("search_code", "run_command")),
    PromptItem("list_src", _user("What's in the src folder? Just the top two levels."),
               _tool("list_directory", "run_command")),
    PromptItem("git_status", _user("Do I have any uncommitted changes right now?"),
               _tool("git", "run_command")),
    PromptItem("create_gitignore", _user("Create a .gitignore for a Python project: ignore __pycache__/, .venv/, *.pyc and .env."),
               _tool("write_file")),
    PromptItem("rename_symbol_find", _user("I want to rename the function `load_cfg` to `load_config` everywhere. Start by finding all usages."),
               _tool("search_code", "run_command")),
    PromptItem("install_dep", _user("Add httpx to the project — install it with pip."),
               _tool("run_command")),
    PromptItem("read_range", _user("Show me lines 40 to 80 of app/models/user.py."),
               _tool("read_file")),
    PromptItem("blame_line", _user("Who last changed line 112 of api/routes.py and in which commit?"),
               _tool("git", "run_command")),
    PromptItem("parallel_reads", _user("Open both pyproject.toml and setup.cfg so we can compare their lint settings."),
               _tool("read_file", min_calls=2)),
    PromptItem("parallel_search", _user("Search for usages of `requests.get` and, separately, `urllib.request.urlopen` across the repo."),
               _tool("search_code", "run_command", min_calls=2)),
    PromptItem("build_frontend", _user("Build the frontend in ./web with npm and tell me if it compiles."),
               _tool("run_command")),
    PromptItem("long_timeout", _user("Run the full integration test script ./scripts/integration.sh; it takes about 5 minutes."),
               _tool("run_command")),
    PromptItem("case_insensitive", _user("Search case-insensitively for 'deprecated' in all markdown files under docs/."),
               _tool("search_code", "run_command")),
    PromptItem("recent_commits", _user("Summarize the last 5 commits on this branch."),
               _tool("git", "run_command")),
    # --- mid-task turns with prior tool results ----------------------------
    PromptItem(
        "fix_after_test_failure",
        _after_tool(
            "The duration tests are failing, can you fix it?",
            [("run_command", {"command": "pytest tests/test_timeutil.py -q"}, _FAILING_TEST_OUTPUT),
             ("read_file", {"path": "src/timeutil.py"}, _TIMEUTIL_SRC)],
        ),
        _tool("edit_file", "write_file"),
    ),
    PromptItem(
        "rerun_after_fix",
        _after_tool(
            "The duration tests are failing, can you fix it?",
            [("edit_file", {"path": "src/timeutil.py", "old_string": '"m": 1', "new_string": '"m": 60'},
              "Edited src/timeutil.py (1 replacement).")],
            "Great, now verify it.",
        ),
        _tool("run_command"),
    ),
    PromptItem(
        "add_script_after_read",
        _after_tool(
            "Add a `typecheck` npm script that runs `tsc --noEmit`.",
            [("read_file", {"path": "package.json"}, _PKG_JSON)],
        ),
        _tool("edit_file", "write_file"),
    ),
    PromptItem(
        "open_hit_after_search",
        _after_tool(
            "Where is the retry logic for HTTP calls implemented?",
            [("search_code", {"pattern": "def .*retry", "glob": "**/*.py"},
              "src/net/http.py:41:def with_retry(fn, attempts=3, backoff=0.5):\n"
              "tests/test_http.py:9:def test_with_retry_gives_up():")],
            "Show me that function.",
        ),
        _tool("read_file"),
    ),
    PromptItem(
        "diagnose_command_not_found",
        _after_tool(
            "Run the linter.",
            [("run_command", {"command": "ruff check ."}, "bash: ruff: command not found\nexit code 127")],
        ),
        _tool("run_command"),
    ),
    PromptItem(
        "answer_after_read",
        _after_tool(
            "Which version of zod does the project depend on?",
            [("read_file", {"path": "package.json"}, _PKG_JSON)],
        ),
        _NONE,
    ),
    PromptItem(
        "summarize_after_test_pass",
        _after_tool(
            "Run the tests.",
            [("run_command", {"command": "pytest -q"}, "........................\n24 passed in 0.38s\nexit code 0")],
        ),
        _NONE,
    ),
    # --- conceptual questions: should answer without tools -----------------
    PromptItem("concept_gil", _user("In general, what does Python's GIL prevent? Two sentences."), _NONE),
    PromptItem("concept_rebase", _user("What's the difference between git merge and git rebase, briefly?"), _NONE),
    PromptItem("concept_regex", _user("Write a regex that matches an IPv4 address octet (0-255). Just the regex."), _NONE),
    PromptItem("concept_bigo", _user("What's the time complexity of inserting into a binary heap?"), _NONE),
    PromptItem("concept_http", _user("Is HTTP PUT idempotent? One line."), _NONE),
    PromptItem("concept_sql", _user("Write a SQL query that returns the 3 most recent orders per customer from orders(id, customer_id, created_at)."), _NONE),
    PromptItem("concept_ts", _user("In TypeScript, when should I use `unknown` instead of `any`?"), _NONE),
]
