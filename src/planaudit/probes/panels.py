"""Deterministic building blocks for probe panels.

Panels are generated from a seed rather than stored, so they are cheap to
rotate (bump the seed) and never appear verbatim on the web, where a provider
could learn to recognise and special-case them.
"""

from __future__ import annotations

import random

# ~400 common English words. Filler built from them reads as plausible prose to
# a tokenizer (about 1.3 tokens per word) without containing any facts a model
# could answer from memory.
WORDS = """
the of and to in is was that for on with as by at from his her they have this which one
had not but what all were when we there can an your been has more if will would who so
no other time some could them into than then now only its people may first like over
also new after way many these two well most made should because through each just good
how before year long great little very still own where same work life back being under
know last might us never day around while place found again old another came world small
large men year house next point hand high four given those part number state number
since against water city tree river light morning evening garden window table letter
music paper market road field forest stone bridge village harbor station winter summer
autumn spring weather cloud rain wind fire metal glass wood bread coffee kitchen door
wall floor roof corner street school office library museum theater island mountain
valley lake ocean desert plain hill coast north south east west early late quiet loud
bright dark warm cold soft hard quick slow simple careful gentle sudden steady open
close carry follow bring keep leave begin finish return travel listen answer remember
forget decide notice imagine explain gather measure prepare repair arrange collect
wander settle shape signal record pattern circle square line edge center surface detail
moment season history story voice picture color sound idea reason method system question
problem result effect change choice chance balance energy motion order matter purpose
figure basket candle ladder blanket bottle button pencil ribbon saddle shovel thread
wagon anchor compass lantern needle pocket rope sail tent trail engine mirror hammer
kettle drawer cabinet curtain
""".split()

COLORS = """
amber azure crimson cobalt emerald ivory jade lilac ochre scarlet teal violet
""".split()
ANIMALS = """
badger falcon heron lynx marten otter osprey panther raven salmon stoat walrus
""".split()
TOPICS = """
volcanoes tides bees glaciers lighthouses compilers bridges tea chess bicycles libraries
satellites coral reefs maps clocks deserts recursion umbrellas violins orchards rivers
typewriters railways honey owls magnets caves kites ferries comets gardens bakeries
""".split()


def rng(seed: int, *salt: object) -> random.Random:
    return random.Random(f"{seed}:" + ":".join(map(str, salt)))


def filler(r: random.Random, n_words: int) -> str:
    """Pseudo-prose: sentences of 8–18 common words, capitalised, full stops."""
    out: list[str] = []
    left = n_words
    while left > 0:
        k = min(left, r.randint(8, 18))
        s = " ".join(r.choice(WORDS) for _ in range(k))
        out.append(s[0].upper() + s[1:] + ".")
        left -= k
    return " ".join(out)


def user(text: str, system: str | None = None) -> list[dict[str, str]]:
    msgs = [{"role": "system", "content": system}] if system else []
    return msgs + [{"role": "user", "content": text}]
