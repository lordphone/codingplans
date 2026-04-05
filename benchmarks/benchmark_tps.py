#!/usr/bin/env python3
"""
Lightweight TPS (output tokens per second) probe for OpenAI-compatible chat APIs.

Single run (env):
  LLM_API_KEY or OPENAI_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_PROMPT, LLM_STREAM_USAGE

Matrix run (config):
  python benchmark_tps.py --config providers.json
  Copy benchmarks/providers.example.json → benchmarks/providers.json (gitignored).
  Each provider lists api_key_env (secret lives only in your environment).

Secrets file:
  Repo-root .env (same directory as web/ and benchmarks/) is loaded automatically
  when python-dotenv is installed; see .gitignore.

Load profile:
  One HTTP streaming request at a time (no parallel calls, no batch API). Matrix mode
  starts the next job as soon as the previous finishes unless you set spacing via
  sleep_between_jobs_s in config, BENCHMARK_SLEEP_BETWEEN_JOBS, or --sleep-between-jobs.

Thinking / reasoning models:
  Some APIs stream reasoning in delta.reasoning_content (or delta.reasoning). The script
  records separate timings when those fields appear. If the provider keeps reasoning
  internal (no reasoning chunks), a long ttft_s is often "silent thinking" before the
  first answer token — interpret ttft_s as time-to-first-visible-answer, not model FLOPs.
  Enable provider-specific flags via per-provider "extra_params" in the JSON config
  (e.g. enable_thinking) only if your gateway documents them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_REPO_ROOT / ".env")


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is not None and v.strip():
        return v.strip()
    return default


def _truthy(val: str | None) -> bool:
    if val is None:
        return False
    return val.lower() in ("1", "true", "yes", "on")


def _rough_output_tokens(text: str) -> int:
    """Fallback when the stream does not report usage (~0.25 tokens/char for English)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _delta_content_and_reasoning(delta: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (content_piece, reasoning_piece) from one SSE delta, if any."""
    c = delta.get("content")
    c_str = c if isinstance(c, str) and c else None
    r = delta.get("reasoning_content")
    if not isinstance(r, str) or not r:
        r = delta.get("reasoning")
        if not isinstance(r, str) or not r:
            r = None
    return c_str, r


def _delta_has_stream_signal(delta: dict[str, Any]) -> bool:
    """True if the delta carries any token-like or structural assistant signal."""
    c, r = _delta_content_and_reasoning(delta)
    if c or r:
        return True
    if delta.get("role") is not None:
        return True
    if delta.get("tool_calls"):
        return True
    if delta.get("function_call"):
        return True
    return False


@dataclass(frozen=True)
class BenchmarkJob:
    provider_id: str
    base_url: str
    api_key: str
    model: str
    prompt: str
    max_tokens: int
    timeout_s: float
    stream_usage: bool
    extra_params: dict[str, Any] | None = None


def run_benchmark(job: BenchmarkJob) -> dict[str, Any]:
    url = job.base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": job.model,
        "messages": [{"role": "user", "content": job.prompt}],
        "max_tokens": job.max_tokens,
        "stream": True,
    }
    if job.stream_usage:
        payload["stream_options"] = {"include_usage": True}
    if job.extra_params:
        payload.update(job.extra_params)
    headers = {
        "Authorization": f"Bearer {job.api_key}",
        "Content-Type": "application/json",
    }

    assembled: list[str] = []
    assembled_reasoning: list[str] = []
    usage_output: int | None = None
    t_first_chunk: float | None = None
    t_first_delta: float | None = None
    t_first_reasoning: float | None = None
    t_last_reasoning: float | None = None
    t_first_content: float | None = None
    t_last_content: float | None = None
    request_started = time.perf_counter()

    with httpx.Client(timeout=job.timeout_s) as client:
        with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data = line[6:].strip()
                elif line.startswith("data:"):
                    data = line[5:].strip()
                else:
                    continue
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                u = chunk.get("usage")
                if isinstance(u, dict) and u.get("completion_tokens") is not None:
                    try:
                        usage_output = int(u["completion_tokens"])
                    except (TypeError, ValueError):
                        pass

                choices = chunk.get("choices") or []
                if not choices:
                    continue
                now = time.perf_counter()
                if t_first_chunk is None:
                    t_first_chunk = now

                delta = (choices[0] or {}).get("delta") or {}
                if not isinstance(delta, dict):
                    delta = {}
                if _delta_has_stream_signal(delta) and t_first_delta is None:
                    t_first_delta = now

                c_piece, r_piece = _delta_content_and_reasoning(delta)
                if r_piece:
                    if t_first_reasoning is None:
                        t_first_reasoning = now
                    t_last_reasoning = now
                    assembled_reasoning.append(r_piece)
                if c_piece:
                    if t_first_content is None:
                        t_first_content = now
                    t_last_content = now
                    assembled.append(c_piece)

    if t_first_content is None or t_last_content is None:
        raise RuntimeError("No streamed content received; check model, key, and base URL.")

    text_out = "".join(assembled)
    reasoning_out = "".join(assembled_reasoning)
    thinking_streamed = bool(reasoning_out)

    out_tokens = usage_output if usage_output is not None else _rough_output_tokens(text_out)
    gen_s = max(t_last_content - t_first_content, 1e-9)
    total_s = time.perf_counter() - request_started
    tps = out_tokens / gen_s
    ttft_s = t_first_content - request_started

    result: dict[str, Any] = {
        "provider_id": job.provider_id,
        "model": job.model,
        "base_url": job.base_url.rstrip("/"),
        "output_tokens": out_tokens,
        "output_tokens_source": "usage" if usage_output is not None else "estimated",
        "ttft_s": round(ttft_s, 4),
        "generation_s": round(gen_s, 4),
        "total_request_s": round(total_s, 4),
        "output_tps": round(tps, 2),
        "perceived_output_tps": round(out_tokens / max(total_s, 1e-9), 2),
        "thinking_streamed": thinking_streamed,
        "preview": text_out[:200] + ("…" if len(text_out) > 200 else ""),
    }

    if t_first_chunk is not None:
        result["ttft_first_chunk_s"] = round(t_first_chunk - request_started, 4)
    if t_first_delta is not None:
        result["ttft_first_delta_s"] = round(t_first_delta - request_started, 4)
    if t_first_reasoning is not None:
        result["ttft_reasoning_s"] = round(t_first_reasoning - request_started, 4)
        if t_last_reasoning is not None:
            gr = max(t_last_reasoning - t_first_reasoning, 1e-9)
            result["reasoning_generation_s"] = round(gr, 4)
            r_tok = _rough_output_tokens(reasoning_out)
            result["reasoning_tokens_estimated"] = r_tok
            result["reasoning_tps_estimated"] = round(r_tok / gr, 2)
        if reasoning_out:
            result["reasoning_preview"] = reasoning_out[:200] + ("…" if len(reasoning_out) > 200 else "")

    return result


def _load_matrix_config(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Config must be a JSON object")
    providers = data.get("providers")
    if not isinstance(providers, list) or not providers:
        raise ValueError('Config must include a non-empty "providers" array')
    return data


def jobs_from_config(
    data: dict[str, Any],
    *,
    filter_providers: set[str] | None,
    filter_models: set[str] | None,
) -> tuple[list[BenchmarkJob], list[str]]:
    default_prompt = data.get("prompt") or (
        "Write a short paragraph explaining what token throughput means for LLM APIs."
    )
    default_max = int(data.get("max_tokens", 256))
    default_timeout = float(data.get("timeout_s", 120.0))
    default_stream = bool(data.get("stream_usage", False))

    jobs: list[BenchmarkJob] = []
    skipped: list[str] = []
    for p in data["providers"]:
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        base_url = p.get("base_url")
        key_env = p.get("api_key_env")
        models = p.get("models")
        if not pid or not base_url or not key_env:
            raise ValueError(f'Provider missing id, base_url, or api_key_env: {p!r}')
        if not isinstance(models, list) or not models:
            raise ValueError(f'Provider "{pid}" needs a non-empty "models" array')

        if filter_providers and str(pid) not in filter_providers:
            continue

        api_key = _env(str(key_env))
        if not api_key:
            skipped.append(f'provider "{pid}": {key_env} not set — skipped')
            continue

        prompt = str(p.get("prompt", default_prompt))
        max_tokens = int(p.get("max_tokens", default_max))
        timeout_s = float(p.get("timeout_s", default_timeout))
        stream_usage = bool(p.get("stream_usage", default_stream))
        raw_extra = p.get("extra_params")
        extra_params: dict[str, Any] | None
        if isinstance(raw_extra, dict) and raw_extra:
            extra_params = dict(raw_extra)
        else:
            extra_params = None

        for m in models:
            model_id = str(m)
            if filter_models and model_id not in filter_models:
                continue
            jobs.append(
                BenchmarkJob(
                    provider_id=str(pid),
                    base_url=str(base_url),
                    api_key=api_key,
                    model=model_id,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    timeout_s=timeout_s,
                    stream_usage=stream_usage,
                    extra_params=extra_params,
                )
            )
    return jobs, skipped


def _run_one(job: BenchmarkJob) -> dict[str, Any]:
    try:
        return run_benchmark(job)
    except httpx.HTTPStatusError as e:
        body = (e.response.text or "")[:500]
        return {
            "provider_id": job.provider_id,
            "model": job.model,
            "base_url": job.base_url.rstrip("/"),
            "error": f"HTTP {e.response.status_code}: {body}",
        }
    except Exception as e:
        return {
            "provider_id": job.provider_id,
            "model": job.model,
            "base_url": job.base_url.rstrip("/"),
            "error": str(e),
        }


def run_matrix(
    jobs: list[BenchmarkJob],
    *,
    jsonl: bool,
    stop_on_error: bool,
    sleep_between_jobs_s: float = 0.0,
) -> int:
    results: list[dict[str, Any]] = []
    exit_code = 0
    n = len(jobs)
    for i, job in enumerate(jobs):
        row = _run_one(job)
        results.append(row)
        if "error" in row:
            exit_code = 1
            if not jsonl:
                print(row["error"], file=sys.stderr)
            if stop_on_error:
                break
        if sleep_between_jobs_s > 0 and i < n - 1:
            time.sleep(sleep_between_jobs_s)
    if jsonl:
        for row in results:
            print(json.dumps(row, ensure_ascii=False))
    else:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenAI-compatible chat streaming TPS benchmark")
    parser.add_argument(
        "--config",
        "-c",
        metavar="PATH",
        help="JSON matrix config (default: BENCHMARK_CONFIG env if set)",
    )
    parser.add_argument(
        "--provider",
        "-p",
        action="append",
        dest="providers",
        metavar="ID",
        help="Only run provider id (repeatable)",
    )
    parser.add_argument(
        "--model",
        "-m",
        action="append",
        dest="models",
        metavar="NAME",
        help="Only run model name (repeatable)",
    )
    parser.add_argument("--jsonl", action="store_true", help="One JSON object per line")
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop after the first failed job (matrix mode only)",
    )
    parser.add_argument(
        "--sleep-between-jobs",
        type=float,
        default=None,
        metavar="SEC",
        help="Seconds to pause between matrix jobs (overrides config / BENCHMARK_SLEEP_BETWEEN_JOBS)",
    )
    args = parser.parse_args()
    _load_dotenv()

    config_path = args.config or _env("BENCHMARK_CONFIG")
    if config_path:
        path = Path(config_path)
        if not path.is_file():
            print(f"Config not found: {path}", file=sys.stderr)
            return 1
        try:
            data = _load_matrix_config(path)
            fp = set(args.providers) if args.providers else None
            fm = set(args.models) if args.models else None
            jobs, skipped = jobs_from_config(data, filter_providers=fp, filter_models=fm)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            print(str(e), file=sys.stderr)
            return 1
        for msg in skipped:
            print(msg, file=sys.stderr)
        if not jobs:
            print("No jobs to run (missing keys, filters, or empty models).", file=sys.stderr)
            return 1
        pause_s = float(data.get("sleep_between_jobs_s", 0.0))
        if (ev := _env("BENCHMARK_SLEEP_BETWEEN_JOBS")) is not None:
            try:
                pause_s = float(ev)
            except ValueError:
                pass
        if args.sleep_between_jobs is not None:
            pause_s = args.sleep_between_jobs
        return run_matrix(
            jobs,
            jsonl=args.jsonl,
            stop_on_error=args.stop_on_error,
            sleep_between_jobs_s=max(0.0, pause_s),
        )

    # Legacy single env run
    api_key = _env("LLM_API_KEY") or _env("OPENAI_API_KEY")
    if not api_key:
        print(
            "Single-run mode: set LLM_API_KEY or OPENAI_API_KEY, "
            "or use --config with benchmarks/providers.example.json as a template.",
            file=sys.stderr,
        )
        return 1

    base_url = _env("LLM_BASE_URL", "https://api.openai.com/v1")
    model = _env("LLM_MODEL", "gpt-4o-mini")
    prompt = _env(
        "LLM_PROMPT",
        "Write a short paragraph explaining what token throughput means for LLM APIs.",
    )
    stream_usage = _truthy(_env("LLM_STREAM_USAGE"))
    job = BenchmarkJob(
        provider_id="env",
        base_url=base_url or "https://api.openai.com/v1",
        api_key=api_key,
        model=model or "gpt-4o-mini",
        prompt=prompt,
        max_tokens=256,
        timeout_s=120.0,
        stream_usage=stream_usage,
        extra_params=None,
    )

    row = _run_one(job)
    if "error" in row:
        print(row["error"], file=sys.stderr)
        return 1
    print(json.dumps(row, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
