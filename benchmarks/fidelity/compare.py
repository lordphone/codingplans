#!/usr/bin/env python3
"""Compare two fidelity run artifacts (any test family).

Pure dispatch over `RunResult` JSON files: reads two `summary.json`
artifacts, picks the matching `compare_*()` function by `test_name`, and
prints the report. No HTTP, no .env required.

Usage:
  python benchmarks/fidelity/compare.py \\
      <reference>.summary.json <target>.summary.json [--out report.json]

The first argument is the reference (e.g. `glm5-official`); the second is
the target (e.g. `glm5-alibaba`). The script enforces:
  * matching test_name (otherwise hard error),
  * matching schema_version, panel_id, panel_size, prompt_hash,
    n_samples, max_tokens (otherwise hard error from the comparator).

To register a new test family, add the family's directory to sys.path
below and import its `(TEST_NAME, compare_<test>)` pair into `_DISPATCH`.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent  # benchmarks/fidelity/
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "model_identity"))
sys.path.insert(0, str(_HERE / "long_context"))

from common import read_run_result  # noqa: E402

# model_identity/
from test_arithmetic import TEST_NAME as ARITHMETIC, compare_arithmetic  # noqa: E402
from test_entropy import TEST_NAME as ENTROPY, compare_entropy  # noqa: E402
from test_rollout_prefix import TEST_NAME as ROLLOUT, compare_rollout_prefix  # noqa: E402

# long_context/
from test_needle_single import (  # noqa: E402
    TEST_NAME as NEEDLE_SINGLE,
    compare_single_needle,
)
from test_needle_multi import (  # noqa: E402
    TEST_NAME as NEEDLE_MULTI,
    compare_needle_multi,
)
from test_needle_aggregation import (  # noqa: E402
    TEST_NAME as NEEDLE_AGGREGATION,
    compare_needle_aggregation,
)

_DISPATCH = {
    ARITHMETIC: compare_arithmetic,
    ENTROPY: compare_entropy,
    ROLLOUT: compare_rollout_prefix,
    NEEDLE_SINGLE: compare_single_needle,
    NEEDLE_MULTI: compare_needle_multi,
    NEEDLE_AGGREGATION: compare_needle_aggregation,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reference", type=Path, help="reference run summary.json")
    parser.add_argument("target", type=Path, help="target run summary.json")
    parser.add_argument("--out", type=Path, default=None,
                        help="If set, also write the report JSON to this path.")
    args = parser.parse_args()

    reference = read_run_result(args.reference)
    target = read_run_result(args.target)

    if reference.test_name != target.test_name:
        print(
            f"test_name mismatch: reference={reference.test_name!r} "
            f"target={target.test_name!r}",
            file=sys.stderr,
        )
        return 2

    fn = _DISPATCH.get(reference.test_name)
    if fn is None:
        print(
            f"unknown test_name {reference.test_name!r}; "
            f"known: {sorted(_DISPATCH)}",
            file=sys.stderr,
        )
        return 2

    try:
        report = fn(reference, target)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    payload = asdict(report)
    out_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    print(out_text, end="")
    if args.out:
        args.out.write_text(out_text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    return 1 if getattr(report, "fail", False) else 0


if __name__ == "__main__":
    raise SystemExit(main())
