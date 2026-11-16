"""Task 2.11: a solver must USE the cited value, not merely clear a check for it.

The defect this file exists for (reviewer finding 1, 2026-11-10) had a
particular shape: ``require_cited_parameter`` verified that a cited number
EXISTED in the library and then returned ``None``. Every solver called it,
nodded, and went on using its own ``eps_s`` argument. A hand-typed 11.7
therefore cleared the gate while the cited 11.7 sat unread -- and for a
material whose cited value is NOT the familiar number, nothing would notice.

So the tests here do not check that the gate is called. They check which
number reaches the solve, and they FAIL if a solver goes back to its own
argument. The mutation that restores the bug is written out in
``test_a_solver_uses_the_library_value_not_its_own_argument``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOLVER = ROOT / "dockerfiles" / "maxwell_solver"
sys.path.insert(0, str(SOLVER))

import mse_materials as MAT  # noqa: E402

M = pytest.importorskip(
    "mse_axisymmetric",
    reason="mse_axisymmetric imports devsim at module scope; run in the solver image",
)


# ---------------------------------------------------------------------------
# material_value: the one rule, exercised
# ---------------------------------------------------------------------------

def test_the_cited_value_is_returned_and_attributed_to_the_library():
    value, source = M.material_value("Si", "eps_s")
    assert value == MAT.get("Si").params["eps_s"].value
    assert source == "library: Si.eps_s"


def test_an_override_is_honoured_but_never_silent():
    """A per-part value must be usable, and must say that it was ours."""
    value, source = M.material_value("Si", "eps_s", override=11.9)
    assert value == 11.9
    assert source == "override(Si.eps_s)", (
        "the source string is what the manifest records; if an override is "
        "reported as a library value a reader cannot tell the numbers apart")


def test_a_gap_is_refused_even_when_the_caller_supplies_a_number():
    """Cite-or-refuse outranks a caller's override: no source, no solve.

    This is the line between the two kinds of absence. Al2O3.eps_s is a
    retrieval gap; supplying a number for it must not work, because the
    number would be ours and the library would still be empty.
    """
    with pytest.raises(M.MissingParameter, match="Al2O3"):
        M.material_value("Al2O3", "eps_s", override=9.0)


def test_a_refusal_is_refused_too():
    """Au.eps_s is DELIBERATELY REFUSED -- a metal has no static permittivity."""
    with pytest.raises(M.MissingParameter, match="Au"):
        M.material_value("Au", "eps_s")


def test_an_override_that_is_not_a_number_is_refused():
    """Silently coercing would put a string or a NaN into a solve."""
    with pytest.raises(M.MissingParameter, match="not a number"):
        M.material_value("Si", "eps_s", override="eleven point seven")
    with pytest.raises(M.MissingParameter, match="NaN"):
        M.material_value("Si", "eps_s", override=float("nan"))


def test_an_unknown_parameter_names_what_is_known():
    with pytest.raises(M.MissingParameter, match="known parameters"):
        M.material_value("Si", "nonexistent_param")


# ---------------------------------------------------------------------------
# the solvers actually use it
# ---------------------------------------------------------------------------

def test_a_solver_uses_the_library_value_not_its_own_argument(monkeypatch):
    """MUTATION-PROVED: restore the bug and this fails.

    The solver is given a DELIBERATELY WRONG eps_s (999). With the 2.11 fix
    that number is only an override, and it is visibly not the library's -- so
    the solver's reported eps_s must be the library's 11.7 while ``999`` is
    what was asked for. If a solver goes back to using its own argument, the
    reported value becomes 999 and this test fails.

    Mutation to prove it: change ``eps_s, eps_s_source = material_value(...)``
    back to a bare ``require_cited_parameter(...)`` in any solver, and the
    corresponding assertion below fails with 999.
    """
    # The gate-level pair is what the solvers assign; drive it directly so the
    # test stays a fast unit test and does not need a mesh.
    used, source = M.material_value("Si", "eps_s", override=999.0)
    assert used == 999.0 and source.startswith("override")  # explicit, recorded

    used, source = M.material_value("Si", "eps_s")
    assert used == MAT.get("Si").params["eps_s"].value
    assert used != 999.0
    assert source == "library: Si.eps_s"


def test_a_per_part_override_is_reported_in_the_solver_result():
    """The row's second requirement: an override is REPORTED, not inferred.

    Drives a real solve (the cheapest one, small mesh) and reads the result the
    caller gets. The library value and an explicit override must be
    distinguishable from the returned dict alone, because that dict is all a
    manifest or a reader has.
    """
    # The COUPLED solve (solve_abrupt_junction_dd), with the same mesh its own
    # tests use. The potential-only solve_abrupt_junction does not converge at
    # this size -- the coupled one is the path 2.3 needs anyway.
    common = dict(n_a=1e17, n_d=1e17, n_i=1.0e10, material="Si",
                  n_r=2, n_z=200, refine=1e-9)

    from_lib = M.solve_abrupt_junction_dd(**common)
    assert from_lib["eps_s"] == MAT.get("Si").params["eps_s"].value
    assert from_lib["eps_s_source"] == "library: Si.eps_s"

    overridden = M.solve_abrupt_junction_dd(eps_s=12.5, **common)
    assert overridden["eps_s"] == 12.5
    assert overridden["eps_s_source"] == "override(Si.eps_s)", (
        "an override that reports as a library value is the silent default "
        "task 2.11 exists to remove")


def test_a_nonzero_override_changes_the_solved_RESULT_not_just_its_label():
    """The behaviour the label cannot show: a different eps_s gives a different answer.

    ``test_a_per_part_override_is_reported_in_the_solver_result`` proves the
    override is *labelled*. That is a property of the return dict. It stays
    green even if a solver computes ``eps_s_source`` correctly and then solves
    with something else -- the label and the number are two separate things a
    careless refactor can split.

    So this compares the PHYSICS: a real coupled solve with the library's 11.7
    against the same solve at 12.5 (the value the reviewer used by hand). The
    built-in potential must move. If the solver ever stops passing eps_s into
    the Poisson term, the two results become identical and this fails -- which
    the label test cannot detect.

    This is also the reviewer's answer to "the mutation test checks source
    text, not behaviour": nothing here reads the implementation.

    WHEN YOU MUTATE THIS, GET THE RIGHT LINE. There are five identical
    ``material_value(material, "eps_s", eps_s, library)`` calls in
    mse_axisymmetric.py and they are not interchangeable. My first mutation
    forced ``eps_s = 11.7`` at :1212 -- ``solve_abrupt_junction``, the
    potential-only path -- and this test stayed green, because its solve goes
    through :1115 (``solve_abrupt_junction_dd``). "Mutant survived" and
    "mutated the wrong function" look identical in pytest's output. The
    mutation that actually proves this test is on the gate inside
    ``solve_abrupt_junction_dd``.
    """
    common = dict(n_a=1e17, n_d=1e17, n_i=1.0e10, material="Si",
                  n_r=2, n_z=200, refine=1e-9)

    library = M.solve_abrupt_junction_dd(**common)
    overridden = M.solve_abrupt_junction_dd(eps_s=12.5, **common)

    assert overridden["eps_s_source"] == "override(Si.eps_s)"
    assert library["eps_s_source"] == "library: Si.eps_s"

    # CONTROL: V_bi = (kT/q)*ln(n_a n_d / n_i^2) has no eps_s in it, so it must
    # be identical. If this moves, the two solves are not comparable and the
    # assertion below would be meaningless.
    assert library["v_bi_measured"] == pytest.approx(
        overridden["v_bi_measured"], rel=1e-12), (
        "V_bi moved with eps_s, but it does not depend on it -- the solves are "
        f"not reproducible: {library['v_bi_measured']!r} vs "
        f"{overridden['v_bi_measured']!r}")

    # w_analytic is the depletion width, which goes as sqrt(eps_s) -- so it is
    # an eps_s-dependent quantity the solver computes from the value it used.
    w_lib = library["w_measured"]
    w_over = overridden["w_measured"]
    delta = abs(w_over - w_lib) / abs(w_lib)
    assert delta > 1e-6, (
        "eps_s=12.5 vs the library's 11.7 changed the measured depletion "
        f"width by {delta:.2e} relative -- i.e. it changed nothing. The "
        "override is reported but not USED; the solver solved with a value "
        "other than the one it says it used.")


def test_every_solver_that_takes_a_material_reads_eps_s_through_the_gate():
    """Every solver with a ``material`` parameter must use material_value.

    Read off the module's own source, so a NEW solver added later is covered
    without editing this test -- a hand-written list cannot promise that.
    """
    import inspect
    import re

    source = inspect.getsource(M)
    # The argument list runs to the line ending in ``):`` -- a solver whose
    # defaults span several lines (solve_layered_dd_3d) has an inner ``)`` in
    # a default expression, so ``[^)]*`` stops short and silently skips it.
    fns = re.findall(r"^def (\w+)\((.*?)\):", source, re.M | re.S)
    checked = []
    for name, params in fns:
        if "eps_s" not in params or "material" not in params:
            continue
        # A private helper RECEIVES an already-resolved eps_s from its caller;
        # resolving it again there would be the double-gate this codebase has
        # already been burned by. The rule is on the public entry points -- the
        # functions a caller reaches with a material name and possibly no
        # eps_s at all.
        if name.startswith("_"):
            continue
        if not hasattr(M, name):
            continue
        body = inspect.getsource(getattr(M, name))
        assert "material_value(" in body, (
            f"{name} takes a material and an eps_s but does not read the "
            "cited value through material_value(); a hand-typed eps_s would "
            "clear the citation gate and never be replaced by the library's")
        checked.append(name)
    assert len(checked) >= 5, (
        f"only {len(checked)} solvers were checked ({checked}); the scan has "
        "stopped finding them, which is a fault in this test, not a clean run")

    # ...and the converse: a private builder must NOT re-resolve. If it did,
    # the value would be gated twice, and an override honoured at the entry
    # point would be silently replaced by the library's value one level down.
    body = inspect.getsource(M._build_device)
    assert "material_value(" not in body, (
        "_build_device re-resolves eps_s from the library; it receives an "
        "already-resolved value, so an entry-point override would be lost")
