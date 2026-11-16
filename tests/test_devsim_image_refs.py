"""The solver image is named ONCE, at the Harbor tag, or this file fails.

WHY THIS EXISTS (reviewer, 2026-11-13). The local `mse-solver:devsim-2.1`
image was removed for disk; the image now lives only at
`registry.example/mode-search-engine/mse-solver:devsim-2.1`. The tag
was spelled out by hand in ten places, and a fix that changed one of them
(a81c734, test_diode_physics.py) left nine behind.

The one that mattered is tests/test_axisymmetric_junction.py: it does
`pytest.importorskip("devsim")`, so with the un-pullable bare tag the
container never starts, devsim does not import, and pytest says SKIPPED.
A stale tag there produces a GREEN result that proves nothing -- the file's
own docstring says "a skip is not evidence". That is the failure this file
makes loud: a bare tag now fails collection-time here, by file and line,
instead of turning into a skip somewhere else.

WHAT IS ASSERTED
  1. No tracked file spells the bare tag `mse-solver:devsim-<v>`.
  2. The one definition, `tests/devsim_image.py`, names the Harbor registry
     and the exact tag, so a silent edit to the constant is caught here too.

A NEW image tag is a deliberate change: add it to KNOWN and update the
constant, in one commit.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONSTANT = ROOT / "tests" / "devsim_image.py"

HARBOR = "registry.example/mode-search-engine/mse-solver:devsim-2.1"

# THE PATTERN SWALLOWS THE PREFIX. The first version was
#   r"(?<![\w./-])mse-solver:devsim-[\w.]+"
# and the lookbehind is the bug the reviewer found (qitem-20261113195634): it
# rejects any `/` before the name, so a PREFIXED tag -- `docker.io/library/
# mse-solver:devsim-2.1`, `localhost:5000/...`, a wrong Harbor namespace --
# never matched at all. Not "allowed": INVISIBLE. finditer saw nothing, so the
# test had no opinion on the one misconfiguration that fails the same way the
# bare tag does, and stayed green. Measured: docker.io/library/... is NOT
# pullable, so it turns importorskip into the same silent SKIP.
#
# So the pattern now takes the whole reference, with any registry and
# namespace, and the ACCEPT rule is the exact Harbor string -- a foreign
# registry and a wrong namespace are caught by what they are, not by whether
# the regex could see them.
#
# `[\w.:/-]*` before the name: word chars, dots, colons and slashes, which is
# the whole alphabet of a registry path. Anchoring the START is what keeps a
# line like `# the tag is mse-solver:devsim-2.1` from matching only its tail --
# but it also means the character class must be allowed to run from the line
# start, which is why it covers spaces' neighbours and not spaces.
IMAGE_REF = re.compile(r"[\w.:/-]*mse-solver:devsim-[\w.]+")

# A match is an offender unless it IS the Harbor string. There is no exception
# LIST: the first version had `KNOWN = {"mse-solver:devsim-2.1"}` "for the one
# legitimate tag", which made the test allow the exact string it forbids (found
# by mutation, before the reviewer saw it). Excluding a FILE is done by path
# below, never by value -- a value-keyed exclusion cannot tell "documented
# here" from "used there".


def _tracked_text_files():
    """Every tracked file git knows about, minus the ones that cannot spell a tag.

    Tracked, not walked: a build product or a note in .git can hold the string
    without anyone ever running it, and flagging those would train the reader
    to ignore this test.
    """
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode()
        path = ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: cannot carry a runnable tag
        yield rel, text


def test_the_solver_image_tag_is_defined_once_and_at_the_harbor_path():
    assert CONSTANT.is_file(), (
        "tests/devsim_image.py is the single definition of the solver image; "
        "without it every run instruction would spell the tag out again")
    namespace = {}
    exec(compile(CONSTANT.read_text(encoding="utf-8"), str(CONSTANT), "exec"),
         namespace)
    assert namespace["DEVSIM_IMAGE"] == HARBOR


def _offending_image_refs():
    """Every image reference in a tracked file that is not the Harbor constant.

    A generator so the test body stays one assertion and the rule is testable
    on a string without a repository (see the self-check below).
    """
    # Excluded BY PATH, never by value. This file and the constant both spell
    # references out on purpose; the guard's own rules are checked separately,
    # below, on strings rather than by reading its own source.
    excluded = {CONSTANT.relative_to(ROOT).as_posix(),
                Path(__file__).relative_to(ROOT).as_posix()}
    for rel, text in _tracked_text_files():
        if rel in excluded:
            continue
        for match in IMAGE_REF.finditer(text):
            if match.group(0) != HARBOR:
                line = text.count("\n", 0, match.start()) + 1
                yield f"{rel}:{line}: {match.group(0)}"


def test_no_file_names_the_solver_image_by_anything_but_the_harbor_path():
    offenders = list(_offending_image_refs())
    assert not offenders, (
        "the solver image is named by something other than its Harbor path. "
        "A bare tag or a foreign registry pulls nothing; in a test guarded by "
        "importorskip('devsim') that failure becomes a SKIP -- green and "
        "worthless. Use DEVSIM_IMAGE from tests/devsim_image.py:\n  "
        + "\n  ".join(offenders))


@pytest.mark.parametrize("reference, rejected", [
    # The reviewer's M1-M4, verbatim, plus the two namespace/version shapes.
    ("mse-solver:devsim-2.1", True),                         # M1 bare
    ("docker.io/library/mse-solver:devsim-2.1", True),       # M3 SURVIVED before
    ("localhost:5000/mse-solver:devsim-2.1", True),          # M4 SURVIVED before
    ("registry.example/x/mse-solver:devsim-2.1", True),
    ("registry.example/mode-search-engine/mse-solver:devsim-2.2", True),
    (HARBOR, False),
])
def test_the_guard_rejects_every_image_but_the_harbor_path(reference, rejected):
    """The rule, on a string. No repository, no skip, no image needed.

    Without this, the acceptance rule is only ever exercised by whatever
    happens to be in the tree -- and both the vacuous-KNOWN bug and the
    lookbehind bug passed the whole-tree test. This one fails on either.
    """
    found = [m.group(0) for m in IMAGE_REF.finditer(f"  --entrypoint {reference} \\")]
    offenders = [f for f in found if f != HARBOR]
    assert bool(offenders) is rejected, (
        f"{reference!r} matched {found!r}, counted as "
        f"{'rejected' if offenders else 'accepted'}")


def test_the_skip_in_an_importorskip_module_cannot_come_from_a_stale_tag():
    """The specific regression the reviewer named, pinned at its file.

    test_axisymmetric_junction.py is the one file where the stale tag turned
    into a skip rather than an error. Assert its run instruction is the
    constant and not a literal.
    """
    path = ROOT / "tests" / "test_axisymmetric_junction.py"
    text = path.read_text(encoding="utf-8")
    assert "{DEVSIM_IMAGE}" in text, (
        "test_axisymmetric_junction.py must build its docker command from "
        "DEVSIM_IMAGE; a literal here is how the review's silent skip "
        "happened the first time")
