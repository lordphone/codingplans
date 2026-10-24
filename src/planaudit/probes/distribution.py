"""Sampled short-answer distributions (text only; no logprobs needed).

Detects: quantization, model swap — on endpoints that do not expose logprobs.

Each prompt asks for a short, open choice ("name an animal", "pick a number")
and is sampled many times at temperature 1. The per-prompt statistic is the
total variation between the two endpoints' empirical answer distributions;
its null distribution comes from shuffling the endpoint labels within each
prompt. Reported effect is the observed mean TV minus the mean TV under
shuffling, i.e. the part of the gap that finite sampling does not explain.
"""

from __future__ import annotations

import re

import numpy as np

from ..artifacts import Run
from ..client import Request
from . import panels
from .base import Item, Probe, Verdict, ok_rows

PROMPTS = [
    "Name an animal. Reply with one word only.",
    "Pick a random integer from 1 to 20. Reply with the number only.",
    "Pick a random integer from 1 to 100. Reply with the number only.",
    "Name a color. One word only.",
    "Name a fruit. One word only.",
    "Name a country. Reply with its name only.",
    "Give a first name for a fictional detective. One word only.",
    "Name a programming language. One word only.",
    "Pick a letter of the alphabet. Reply with the letter only.",
    "Name a musical instrument. One word only.",
    "Name a city in Europe. Reply with the name only.",
    "Name a famous scientist. Surname only.",
    "Pick a day of the week. One word only.",
    "Name a type of tree. One word only.",
    "Say a word that rhymes with 'light'. One word only.",
    "Name a vegetable. One word only.",
    "Name a sport. One word only.",
    "Name a gemstone. One word only.",
    "Pick a planet in the solar system. One word only.",
    "Name an emotion. One word only.",
    "Give a name for a pet cat. One word only.",
    "Name a kitchen utensil. One or two words only.",
    "Name a board game. Reply with its name only.",
    "Name a bird. One word only.",
    "Pick a month. One word only.",
    "Name a flower. One word only.",
    "Name a metal. One word only.",
    "Name a dance style. One or two words only.",
    "Name a mythical creature. One word only.",
    "Name a cheese. One word only.",
]

_WORD = re.compile(r"[a-z0-9]+")


def normalize(text: str, words: int = 2) -> str:
    return " ".join(_WORD.findall(text.lower())[:words]) or "<empty>"


def excess_tv(
    a: list[list[str]], b: list[list[str]], *, B: int, seed: int
) -> tuple[float, float, np.ndarray]:
    """(excess mean TV, permutation p-value, per-prompt observed TV).

    a[i], b[i] are the answers to prompt i from each side. Labels are shuffled
    within each prompt, jointly across prompts."""
    g = np.random.default_rng(seed)
    obs_tv, null_tv = [], np.zeros(B)
    for xs, ys in zip(a, b, strict=True):
        vocab = {v: k for k, v in enumerate(sorted(set(xs) | set(ys)))}
        codes = np.array([vocab[v] for v in xs + ys])
        onehot = np.eye(len(vocab))[codes]  # (n, K)
        na, n = len(xs), len(codes)
        lab = np.zeros(n)
        lab[:na] = 1
        obs_tv.append(_tv(onehot, lab[None, :], na, n - na)[0])
        perms = np.argsort(g.random((B, n)), axis=1)
        null_tv += _tv(onehot, lab[perms], na, n - na)
    obs = np.asarray(obs_tv)
    null = null_tv / len(a)
    p = float((1 + np.count_nonzero(null >= obs.mean() - 1e-12)) / (1 + B))
    return float(obs.mean() - null.mean()), p, obs


def _tv(onehot: np.ndarray, labels: np.ndarray, na: int, nb: int) -> np.ndarray:
    ca = labels @ onehot / na
    cb = (1 - labels) @ onehot / nb
    return 0.5 * np.abs(ca - cb).sum(axis=1)


class DistributionProbe(Probe):
    name = "distribution"
    title = "Answer distribution"
    detects = "quantization, model swap"
    effect_name = "excess total variation"
    default_margin = 0.05
    defaults = {"n_items": 30, "samples": 32, "temperature": 1.0, "max_tokens": 8, "seed": 1}

    def items(self) -> list[Item]:
        c = self.cfg
        out = []
        for i in range(c["n_items"]):
            prompt = PROMPTS[i % len(PROMPTS)]
            if i >= len(PROMPTS):  # extend past the base list with neutral prefixes
                lead = panels.rng(c["seed"], "dist", i).choice(["Quick:", "Be brief.", "Answer:"])
                prompt = f"{lead} {prompt}"
            req = Request(
                messages=panels.user(prompt),
                max_tokens=c["max_tokens"],
                temperature=c["temperature"],
            )
            out.append(Item(id=f"d{i:03d}", requests=[req] * c["samples"]))
        return out

    def _answers(self, run: Run, ids: list[str]) -> list[list[str]]:
        return [[normalize(x.text) for x in ok_rows(run, i)] for i in ids]

    def summarize(self, run: Run, ids: list[str] | None = None) -> dict:
        ids = self._ids(run, None, ids)
        answers = self._answers(run, ids)
        distinct = [len(set(a)) / len(a) for a in answers if a]
        return {**super().summarize(run, ids), "distinct_ratio": float(np.mean(distinct or [0]))}

    def _compare(self, ref: Run, tgt: Run, ids: list[str], *, B: int, seed: int) -> Verdict:
        a, b = self._answers(ref, ids), self._answers(tgt, ids)
        keep = [k for k in range(len(ids)) if len(a[k]) >= 4 and len(b[k]) >= 4]
        if len(keep) < 3:
            return self._empty("fewer than 3 prompts with enough samples on both sides")
        a, b = [a[k] for k in keep], [b[k] for k in keep]
        effect, p, per = excess_tv(a, b, B=B, seed=seed)
        top = sorted(zip(per, [ids[k] for k in keep], strict=True), reverse=True)[:5]
        return self.verdict(
            effect,
            p,
            len(keep),
            detail={"mean_tv": float(per.mean()), "most_different": [i for _, i in top]},
            reference=self.summarize(ref, ids),
            target=self.summarize(tgt, ids),
        )
