"""``record_fields``: the six-component recorder the HLST dataset needs.

The training set is a vector field. ``frames`` gives ``|E|``, which throws away
the direction the model has to predict, so the dataset needs Ex Ey Ez Hx Hy Hz
on the whole grid at chosen steps. This file proves that seam.

The trap this file exists to avoid: a test that only checks the keys exist
passes on a recorder that writes zeros. So every assertion here is against
independently-obtained truth -- a re-run with a probe, and monotonic growth of
a driven field -- and the negative case (asked for nothing) is checked too.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "dockerfiles" / "maxwell_solver"))

fdtd = pytest.importorskip("fdtd")

SHAPE = (7, 7, 7)


def _source():
    return fdtd.Source(cell=(3, 3, 3), component="z", frequency=0.25,
                       profile="pulse", bandwidth=0.1)


def _run(**kwargs):
    return fdtd.simulate(np.ones(SHAPE, np.float32), _source(), 12,
                         boundary="metal", **kwargs)


def test_six_components_at_the_requested_steps():
    run = _run(record_fields={"steps": [3, 7], "stride": (1, 1, 1)})
    recorded = run["fields"]
    assert recorded is not None

    for family in ("E", "H"):
        # the bare axis triple, shared by both families -- which is exactly
        # why they are kept apart rather than in one dict
        assert set(recorded[family]) == {"x", "y", "z"}, (
            f"{family} must hold all three axes, got {sorted(recorded[family])}")
    assert "x" in run["fields"]["E"] and "x" in run["fields"]["H"], (
        "E and H must both survive: keying one dict on the shared axis names "
        "would let H overwrite E")

    for family in ("E", "H"):
        for axis in ("x", "y", "z"):
            values = np.asarray(recorded[family][axis])
            assert values.shape == (2, *SHAPE), (
                f"{family}{axis} wants one grid per requested step, got "
                f"{values.shape}")
            assert values.dtype == np.float32


def test_the_recorded_values_are_the_fields_that_ran():
    """Not just nonzero -- the same numbers a probe would have read.

    A recorder that sampled the wrong array, or the wrong step, would still
    produce a plausible-looking field. Two runs of the same scene differ only
    in that one records step 7 in full and the other probes that cell.
    """
    steps = [7]
    recorded = _run(record_fields={"steps": steps, "stride": (1, 1, 1)})
    probed = _run(probes=[(3, 3, 3)])

    # the driven component at the source cell is the strongest, so it is the
    # one a wrong-array bug is least likely to fake
    left = np.asarray(recorded["fields"]["E"]["z"])[0, 3, 3, 3]
    assert left != 0.0, (
        "the source drives Ez; a zero here means the recorder read an array "
        "the run never wrote")
    right = probed["traces"][0][7]
    # the probe is taken AFTER the E update of its step, the recorder too
    assert left == pytest.approx(right, rel=1e-5), (
        "the recorded Ez at the source cell must equal the probe's trace at "
        "that step")


def test_the_stride_samples_the_grid_rather_than_the_whole_of_it():
    run = _run(record_fields={"steps": [3], "stride": (2, 2, 2)})
    values = np.asarray(run["fields"]["E"]["z"])
    assert values.shape == (1, 4, 4, 4), (
        f"a stride of 2 on a {SHAPE} grid keeps 4 nodes an axis, got "
        f"{values.shape}")


def test_asking_for_no_record_changes_nothing():
    """The seam is additive: a run that does not ask pays nothing."""
    run = _run()
    assert run["fields"] is None, (
        "a caller that did not ask for a field record must get None, not an "
        "empty one it might mistake for data")


def test_a_closure_that_zeroes_the_state_is_what_the_recorder_records():
    """The seam ordering: ``closure`` runs BEFORE the recorder.

    Nothing in v1 passes ``closure``, so a recorder that captured the sample
    before the closure ran would stay green through this whole file and the
    repair tests -- and then SP-Closure would land and the training set would
    be recorded from unclosed states. Zeroing the state in a closure makes the
    order observable: whatever the recorder stored must be exactly zero.
    Both closure styles are covered, because they reach the state by
    different code paths: mutate in place and return a replacement pair.
    """
    def zero_in_place(state, dt):
        field, h_field = state
        for values in (field, h_field):
            for component in fdtd.COMPONENTS:
                values[component][...] = 0.0
        return None

    def zero_by_replacement(state, dt):
        field, h_field = state
        return ({c: np.zeros_like(v) for c, v in field.items()},
                {c: np.zeros_like(v) for c, v in h_field.items()})

    request = {"steps": [7], "stride": (1, 1, 1)}
    unclosed = _run(record_fields=request)
    assert np.any(np.asarray(unclosed["fields"]["E"]["z"]) != 0.0), (
        "the unclosed run must record a live field, or the zero below could "
        "come from a run that never drove anything")

    for closure in (zero_in_place, zero_by_replacement):
        run = _run(record_fields=request, closure=closure)
        recorded = run["fields"]
        for family in ("E", "H"):
            for axis in ("x", "y", "z"):
                values = np.asarray(recorded[family][axis])
                assert np.all(values == 0.0), (
                    f"{family}{axis} was recorded nonzero through a closure "
                    f"that zeroed the state ({closure.__name__}): the "
                    f"recorder is sampling before the closure runs")


@pytest.mark.parametrize("bad,why", [
    ({"steps": [99], "stride": (1, 1, 1)}, "outside the run"),
    ({"steps": [3, 3], "stride": (1, 1, 1)}, "repeated"),
    ({"steps": [3], "stride": (0, 1, 1)}, "whole numbers"),
])
def test_a_bad_request_is_refused_with_a_reason(bad, why):
    with pytest.raises(fdtd.FDTDError) as caught:
        _run(record_fields=bad)
    assert why in str(caught.value)


def test_the_save_schedule_travels_with_the_arrays():
    """A consumer must learn WHICH steps it got, not assume 0,1,2,...

    The record used to carry only the six arrays, so anything reading it had to
    assume the saves were consecutive from zero. That is true at stride 1 and
    start 0 and false for every other request -- and the failure is silent: a
    strided fine leg gets paired against the wrong coarse times and the pair
    looks like a physics disagreement instead of a bookkeeping one. The
    HLST coarse/fine divergence gate caught it on a stride-8 run.

    Asserted against the REQUEST rather than the default, so a recorder that
    echoes a hardcoded range cannot pass.
    """
    run = _run(record_fields={"steps": [0, 4, 8, 11], "stride": (2, 1, 3)})
    fields = run["fields"]

    assert fields["steps"] == [0, 4, 8, 11], (
        f"the schedule must report the requested steps, got "
        f"{fields.get('steps')!r}: a consumer that guesses them trains on "
        f"arrays labelled with the wrong physical times")
    assert tuple(fields["stride"]) == (2, 1, 3), (
        f"the stride must travel too, got {fields.get('stride')!r}")
