"""Prompt panels for the integrity/ family (protocol-level honesty checks).

These tests are about what the endpoint does *around* the model rather than
the weights themselves: does it bill the tokens we actually sent, does it
honor request parameters, does it replay cached answers.

  * TOKEN_ACCOUNTING_PROMPTS — identical requests of increasing size. Same
    model + same tokenizer ⇒ `usage.prompt_tokens` must match the official
    API. A constant surplus is a hidden injected system prompt; a
    multiplicative surplus is usage inflation.
  * PARAM_PROMPTS — one probe per request parameter (max_tokens, stop,
    response_format, temperature high/low) with the parameter values carried
    in `meta`.
  * CACHE_PROMPTS — high-entropy requests at T=1 (a cache returns the same
    bytes twice) plus nonce-echo requests (a semantic/prefix cache returns
    an answer carrying a stale nonce).

Bump the matching *_PANEL_ID whenever content changes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List

_HERE = Path(__file__).resolve().parent
_LONG_CONTEXT = _HERE.parent / "long_context"
if str(_LONG_CONTEXT) not in sys.path:
    sys.path.insert(0, str(_LONG_CONTEXT))

from framework import PromptItem  # noqa: E402
from needle import generate_filler  # noqa: E402

_SYS = (
    "You are an AI coding assistant integrated into the user's editor. "
    "Answer concisely."
)


def _msgs(user: str, system: str | None = _SYS) -> tuple[dict[str, Any], ...]:
    if system is None:
        return ({"role": "user", "content": user},)
    return ({"role": "system", "content": system}, {"role": "user", "content": user})


# ---------------------------------------------------------------------------
# Token accounting
# ---------------------------------------------------------------------------

TOKEN_ACCOUNTING_PANEL_ID = "token-accounting-v1"
_TA_FILLER_SEED = 271828
_TA_LENGTHS = (0, 400, 1_500, 6_000, 24_000, 64_000)


def _ta_prompt(chars: int) -> str:
    if chars == 0:
        return "Reply with just: OK"
    code = generate_filler(chars, seed=_TA_FILLER_SEED)[:chars]
    return f"Here's a module from our repo:\n\n{code}\n\nNo changes needed yet — reply with just: OK"


TOKEN_ACCOUNTING_PROMPTS: List[PromptItem] = [
    PromptItem(f"ta_sys_{n}", _msgs(_ta_prompt(n)), {"chars": n, "system": True})
    for n in _TA_LENGTHS
] + [
    PromptItem(f"ta_nosys_{n}", _msgs(_ta_prompt(n), system=None), {"chars": n, "system": False})
    for n in (0, 1_500, 24_000)
]


# ---------------------------------------------------------------------------
# Parameter compliance
# ---------------------------------------------------------------------------

PARAM_PANEL_ID = "param-compliance-v1"

_LONG_TASK = (
    "Write a detailed, thorough explanation of how Python's garbage collector "
    "handles reference cycles, with examples."
)
_COUNT_TASK = "Count from 1 to 30, separated by commas and spaces. Output only the numbers."
_JSON_TASK = (
    "Return a JSON object describing a GitHub repository with keys "
    '"name" (string), "stars" (integer) and "topics" (array of strings). Output only JSON.'
)
_OPEN_TASK = "Suggest a name for a new CLI tool that formats SQL files. Reply with just the name."

_OUTPUT_CAP_TASK = (
    "Generate a test fixture: print the integers from 1 to 2500, one per line, "
    "with no other text. Do not abbreviate or skip any lines."
)

PARAM_PROMPTS: List[PromptItem] = [
    # Silent output cap: the honest reply is ~10k tokens and ends with
    # finish_reason=stop at 2500. A gateway that clamps max_tokens below the
    # advertised limit cuts it off early.
    PromptItem("output_cap", _msgs(_OUTPUT_CAP_TASK),
               {"probe": "output_cap", "max_tokens": 16_000, "last": 2500}),
    PromptItem("max_tokens_16", _msgs(_LONG_TASK), {"probe": "max_tokens", "max_tokens": 16}),
    PromptItem("max_tokens_64", _msgs(_LONG_TASK), {"probe": "max_tokens", "max_tokens": 64}),
    PromptItem("stop_seq", _msgs(_COUNT_TASK), {"probe": "stop", "stop": ["17"], "forbidden": "17"}),
    PromptItem("stop_word", _msgs("List the NATO phonetic alphabet from Alpha to Zulu, comma separated, nothing else."),
               {"probe": "stop", "stop": ["Hotel"], "forbidden": "Hotel"}),
    PromptItem("json_mode", _msgs(_JSON_TASK), {"probe": "json_mode"}),
    PromptItem("temp_low", _msgs(_OPEN_TASK), {"probe": "temperature", "temperature": 0.0}),
    PromptItem("temp_high", _msgs(_OPEN_TASK), {"probe": "temperature", "temperature": 1.0}),
    PromptItem("temp_low_b", _msgs("Give me one example of a variable name for a retry counter. Just the name."),
               {"probe": "temperature", "temperature": 0.0}),
    PromptItem("temp_high_b", _msgs("Give me one example of a variable name for a retry counter. Just the name."),
               {"probe": "temperature", "temperature": 1.0}),
]


# ---------------------------------------------------------------------------
# Response caching
# ---------------------------------------------------------------------------

CACHE_PANEL_ID = "response-cache-v1"

# Template for nonce prompts. The nonce is drawn fresh per call and is not
# part of the panel hash (it is a per-call stealth/measurement input, like a
# schedule seed): a provider that keys a cache on the message prefix, or on
# embedding similarity, will hand back an answer carrying an older nonce.
NONCE_TEMPLATE = (
    "Ticket {nonce}: our CI job keeps timing out on the integration step. "
    "Start your reply with the ticket id exactly as written, then give one "
    "likely cause in one sentence."
)

CACHE_PROMPTS: List[PromptItem] = [
    PromptItem("rand_token", _msgs("Generate a random 16-character alphanumeric API key for my local .env. Just the key."),
               {"probe": "entropy"}),
    PromptItem("rand_names", _msgs("Invent five random fictional company names for seed data, comma separated, nothing else."),
               {"probe": "entropy"}),
    PromptItem("rand_uuidish", _msgs("Make up a plausible-looking git commit hash (40 hex chars) for a test fixture. Just the hash."),
               {"probe": "entropy"}),
    PromptItem("rand_story", _msgs("Write a one-sentence commit message for an imaginary bugfix. Be creative."),
               {"probe": "entropy"}),
    PromptItem("nonce_echo", _msgs(NONCE_TEMPLATE), {"probe": "nonce"}),
    PromptItem("nonce_echo_code", _msgs(NONCE_TEMPLATE, system=None), {"probe": "nonce"}),
]
