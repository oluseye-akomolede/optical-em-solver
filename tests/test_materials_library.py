"""Task 2.2: the materials library cites every parameter, overridable per part.

The spec's four scenarios, each as a test:

1. A library material needs no parameters from the uploader.
2. A per-part override wins and is recorded as an override.
3. An uncited library entry is refused by its own test.
4. An unknown material is refused with ValueError naming it and listing the
   library.

Scenario 3 is the one with teeth, and it is NOT tested on a synthetic bad entry.
It is run against the SHIPPED library, so it currently FAILS and names every
parameter that has not been read from a source. That failure is the delivery
state: the machinery is done, the data is not, and the suite says which data.
See the module docstring of mse_materials.py for why the retrieval came back
empty. Making this test pass by filling values from memory is the one thing the
spec forbids.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dockerfiles" / "maxwell_solver"))

import mse_materials as MM  # noqa: E402

SPEC_MATERIALS = ("Si", "GaAs", "InP", "SiC", "SiO2", "Al2O3", "HfO2", "Au", "Ag", "air")


# ---------------------------------------------------------------- inventory

def test_every_material_the_spec_names_is_in_the_library():
    assert set(SPEC_MATERIALS) <= set(MM.LIBRARY_NAMES)


def test_a_semiconductor_carries_every_parameter_the_spec_names():
    for name in SPEC_MATERIALS:
        mat = MM.get(name)
        if mat.kind == "semiconductor":
            assert set(mat.params) == set(MM.SEMICONDUCTOR_PARAMS), name
        else:
            assert set(mat.params) == {"eps_s"}, name


def test_every_parameter_carries_a_basis_and_a_status():
    for name in MM.LIBRARY_NAMES:
        for param, c in MM.get(name).params.items():
            assert c.basis, f"{name}.{param} has no basis"
            assert c.verified or c.assumed, f"{name}.{param} is neither"


# ---------------------------------------------------------------- scenario 1

def test_a_library_semiconductor_needs_nothing_from_the_uploader():
    material_of_part = {"wire": "InP"}
    values, sources = MM.resolve(["wire"], material_of_part, overrides=None)
    assert values["wire"]["eps_s"] == 12.5
    assert sources["wire"]["eps_s"] == "library: InP"
    assert set(sources["wire"].values()) == {"library: InP"}


# ---------------------------------------------------------------- scenario 2

def test_a_per_part_override_wins_and_is_recorded_as_an_override():
    material_of_part = {"wire": "InP", "oxide": "SiO2"}
    overrides = {"wire": {"eps_s": 13.0}}
    values, sources = MM.resolve(["wire", "oxide"], material_of_part, overrides)

    assert values["wire"]["eps_s"] == 13.0
    assert sources["wire"]["eps_s"] == "override"
    # the override touches ONE parameter of ONE part
    assert sources["wire"]["mu_e"] == "library: InP"
    assert sources["oxide"]["eps_s"] == "library: SiO2"
    assert values["oxide"]["eps_s"] == 3.9


def test_an_override_of_an_unretrieved_parameter_is_marked_override():
    # A user who supplies their own tau for Si should not be blocked by the
    # library not carrying one; the manifest attributes it to them.
    #
    # Si's tau_e/tau_h are REFUSED rather than merely unretrieved (a lifetime is
    # the sample's property, not the material's), which is a stronger statement
    # about the LIBRARY. It is still a parameter the CALLER may supply, so the
    # override must reach the solve: refusing the override too would turn "we
    # will not guess" into "you cannot model silicon".
    values, sources = MM.resolve(
        ["sub"], {"sub": "Si"}, {"sub": {"tau_e": 1e-5, "tau_h": 4e-6}}
    )
    assert values["sub"]["tau_e"] == 1e-5
    assert sources["sub"]["tau_e"] == "override"
    assert sources["sub"]["eps_s"] == "library: Si"


# ---------------------------------------------------------------- scenario 4

def test_an_unknown_material_is_refused_naming_it_and_listing_the_library():
    with pytest.raises(ValueError) as exc:
        MM.get("InGaAs")
    msg = str(exc.value)
    assert "'InGaAs'" in msg
    for name in MM.LIBRARY_NAMES:
        assert name in msg


def test_an_unknown_material_is_refused_through_resolve_too():
    with pytest.raises(ValueError, match="InGaAs"):
        MM.resolve(["wire"], {"wire": "InGaAs"})


def test_a_part_with_no_material_is_refused():
    with pytest.raises(ValueError, match="'wire'"):
        MM.resolve(["wire"], {})


# ---------------------------------------------------------------- scenario 3
#
# Run against the SHIPPED library. Each parameter that is unretrieved must be
# named. This test is expected to FAIL today; the assertion shape matters more
# than the outcome: it fails on the parameters, not on an exception type.

def test_require_cited_refuses_an_unretrieved_entry_by_name():
    mat = MM.Material(
        name="Unobtainium",
        kind="insulator",
        params={"eps_s": MM._missing("eps_s")},
    )
    monkey = dict(MM._LIBRARY)
    monkey["Unobtainium"] = mat
    MM._LIBRARY.clear()
    MM._LIBRARY.update(monkey)
    try:
        with pytest.raises(ValueError, match="Unobtainium.eps_s"):
            MM.require_cited(["Unobtainium"])
    finally:
        MM._LIBRARY.pop("Unobtainium", None)


@pytest.mark.xfail(
    strict=True,
    reason="8 parameters have no number in the library, so this test fails "
           "naming them, by design. They are NOT one kind of absence: "
           "6 refused on 4 materials -- Au eps_s and Ag eps_s (the library "
           "refuses to carry a static permittivity for a conductor) and Si "
           "tau_e/tau_h and SiC tau_e/tau_h (a lifetime is the sample's "
           "property, not the material's) -- plus 2 retrieval gaps on 2 "
           "materials, Al2O3 eps_s and HfO2 eps_s, which wait on a dielectric "
           "handbook (Ioffe/NSM covers semiconductors only). The distinction "
           "matters: a refusal is closed by a decision and will never be "
           "filled, a gap is waiting on retrieval and might be. "
           "test_the_gap_is_what_the_xfail_claims_it_is pins the identity and "
           "the kind of each. Remove this mark when all 8 have numbers, i.e. "
           "when require_cited() passes -- not before.",
)
def test_every_shipped_parameter_is_cited():
    MM.require_cited()


def test_the_gap_is_what_the_xfail_claims_it_is():
    # Pins the real state: these are exactly the materials with an unretrieved
    # parameter. If this changes, the xfail above must be re-examined.
    try:
        MM.require_cited()
    except ValueError as exc:
        named = str(exc)
    else:
        pytest.fail("require_cited passed: the retrieval gap has been closed; "
                    "remove the xfail on test_every_shipped_parameter_is_cited")
    # Compared against gaps() rather than a hand-typed list, so filling a
    # parameter (this commit filled 18 of them) does not need this test edited
    # to keep passing. What it pins is the IDENTITY of the gaps: an invented
    # value shows up as a parameter that left gaps() without a source, and a
    # dropped citation shows up as one that joined it.
    expected = {
        "Si": ["tau_e", "tau_h"],
        # The SiC n_i/mu_e/mu_h left this list when NASA Table 5.1 supplied
        # them. The lifetimes are here as REFUSALS, not as pending retrieval:
        # TU Wien node72 states there are no reliable data to extract the SiC
        # lifetimes and proposes borrowing Si's instead, so no source exists
        # to keep looking for. The four eps_s entries are the only two that
        # are still genuinely being looked for.
        "SiC": ["tau_e", "tau_h"],
        "Al2O3": ["eps_s"],
        "HfO2": ["eps_s"],
        "Au": ["eps_s"],
        "Ag": ["eps_s"],
    }
    assert {k: sorted(v) for k, v in MM.gaps().items()} == {k: sorted(v) for k, v in expected.items()}
    assert set(MM.gaps()) == set(expected)
    for name in expected:
        assert f"{name}." in named, f"{name} is missing from the refusal: {named}"
    for name in set(MM.LIBRARY_NAMES) - set(expected):
        assert f"{name}." not in named, f"{name} is wrongly refused: {named}"

    # The xfail reason above makes a CLAIM about how many of these are refusals
    # and how many are retrieval gaps. A reason string is prose and cannot
    # fail, so the claim is checked against the library here instead: if
    # someone moves a parameter between the two kinds, the reason goes stale
    # and this test -- not a reader -- catches it.
    refused = {
        f"{mat}.{param}"
        for mat, params in MM.REFUSED.items()
        for param in params
    }
    still_looking = {
        f"{mat}.{param}"
        for mat, params in expected.items()
        for param in params
        if f"{mat}.{param}" not in refused
    }
    assert len(refused) == 6 and len({p.split(".")[0] for p in refused}) == 4, (
        f"the xfail reason says '6 refused on 4 materials'; the library says "
        f"{len(refused)} refused on {len({p.split('.')[0] for p in refused})} "
        f"materials: {sorted(refused)}")
    assert len(still_looking) == 2 and len({p.split(".")[0] for p in still_looking}) == 2, (
        f"the xfail reason says '2 retrieval gaps on 2 materials'; the library "
        f"says {len(still_looking)}: {sorted(still_looking)}")


def test_the_retrieved_values_are_the_cited_ones():
    # The half that DID retrieve. These numbers are the test that checks a
    # sampled subset against its source, per the spec. Bulk-imported values
    # are exactly what the citation work is meant to prevent, so each is
    # written here a second time, by hand, with its Ioffe page and row.
    #
    # Static permittivity, five materials (SI, Wikipedia/Ioffe as noted).
    assert MM.get("Si")["eps_s"].value == 11.7       # Ioffe Si/basic, 11.7
    assert MM.get("GaAs")["eps_s"].value == 12.4     # Wikipedia table [Fox 2010]
    assert MM.get("SiO2")["eps_s"].value == 3.9      # Wikipedia [Gray et al. 2009]
    assert MM.get("InP")["eps_s"].value == 12.5      # Ioffe InP/basic
    assert MM.get("air")["eps_s"].value == 1.0       # Wikipedia table
    for name in ("Si", "GaAs", "InP", "SiO2", "air"):
        assert MM.get(name)["eps_s"].verified is True


def test_the_filled_values_across_kinds_are_the_ones_read_from_the_source():
    # The reviewer's finding: pinning only eps_s left n_i, mobilities,
    # lifetimes and B_rad unchecked, so GaAs n_i could be multiplied by 1000
    # with its citation intact and the suite stayed green. These span
    # n_i, mu_e, mu_h, a lifetime and B_rad across three materials.
    #
    # Each expected value is the figure read off the named Ioffe/NSM page,
    # typed here independently of the library.
    SI = "Ioffe/NSM Si/"
    GA = "Ioffe/NSM GaAs/"
    IN = "Ioffe/NSM InP/"

    cases = [
        # (material, parameter, value, page, row)
        ("Si",   "n_i_300K", 1e10,     SI + "bandstr.html", "Intrinsic carrier concentration: 1*10^10"),
        ("Si",   "mu_e",     1400.0,   SI + "electric.html", "Mobility electrons: <=1400"),
        ("Si",   "mu_h",     450.0,    SI + "electric.html", "Mobility holes: <=450"),
        ("GaAs", "n_i_300K", 2.1e6,    GA + "bandstr.html", "Intrinsic carrier concentration: 2.1*10^6"),
        ("GaAs", "mu_e",     8000.0,   GA + "electric.html", "weakly doped drift: mu_n=8000(300/T)^(2/3)"),
        ("GaAs", "mu_h",     400.0,    GA + "electric.html", "Mobility holes: <=400"),
        ("GaAs", "tau_h",    3e-6,     GA + "electric.html", "pure n-type: tau_p ~3*10^-6"),
        ("GaAs", "tau_e",    5e-9,     GA + "electric.html", "pure p-type: tau_n ~5*10^-9"),
        ("GaAs", "B_rad",    7e-10,    GA + "optic.html",    "Radiative recombination coefficient: 7*10^-10"),
        ("InP",  "n_i_300K", 1.3e7,    IN + "bandstr.html", "Intrinsic carrier concentration: 1.3*10^7"),
        ("InP",  "mu_e",     5400.0,   IN + "electric.html", "Mobility electrons: <=5400"),
        ("InP",  "mu_h",     200.0,    IN + "electric.html", "Mobility holes: <=200"),
        ("InP",  "tau_h",    3e-6,     IN + "electric.html", "pure n-type: tau_p ~3*10^-6"),
        ("InP",  "tau_e",    2e-9,     IN + "electric.html", "pure p-type: tau_n ~2*10^-9"),
        ("InP",  "B_rad",    1.2e-10,  IN + "optic.html",    "Radiative recombination coefficient: 1.2*10^-10"),
    ]
    for mat, key, expected, page, row in cases:
        got = MM.get(mat)[key]
        assert got.value == pytest.approx(expected, rel=1e-12), (
            f"{mat}.{key} = {got.value!r}, expected {expected!r} per {page} ({row})")
        assert got.verified is True, f"{mat}.{key} is not marked verified"
        # The citation must name the page and row it was read from, so a
        # value moved away from its source shows up here too.
        page_name = page.rsplit("/", 1)[-1]
        assert page_name in got.basis, f"{mat}.{key} basis does not cite {page_name}"
    # Kinds are covered, not just one material's table.
    kinds = {key for _, key, *_ in cases}
    assert {"n_i_300K", "mu_e", "mu_h", "tau_h", "B_rad"} <= kinds
    assert {"Si", "GaAs", "InP"} <= {m for m, *_ in cases}


def test_an_unretrieved_placeholder_is_nan_not_a_plausible_number():
    # A missing parameter must never look like a value.
    c = MM.get("Au")["eps_s"]
    assert c.value != c.value  # NaN
    assert c.verified is False
    assert "epsilon" not in c.basis.lower()  # it is a gap, not a source


# ---------------------------------------------------------------- report

def test_report_prints_every_parameter_with_its_status():
    text = MM.report()
    for name in MM.LIBRARY_NAMES:
        assert name in text
    assert "[cited]" in text
    # Every absent parameter is tagged ASSUMED (the strongest mark the shared
    # Constant type offers for an unsourced number) and its basis says it is
    # a gap, so a reader of the dump cannot mistake it for a measurement.
    assert "[ASSUMED]" in text
    assert "NOT YET RETRIEVED" in text
    # Counted from the library, not typed in: DERIVED, so it cannot drift from
    # the data without a failure.
    absent = sum(len(v) for v in MM.gaps().values())
    # Was 11. Filling SiC n_i_300K, mu_e and mu_h from NASA Table 5.1 removes
    # three; the two SiC lifetimes could not be filled from any source
    # retrieved and remain gaps.
    assert absent == 8
    assert text.count("[ASSUMED]") == absent
    assert text.count("[cited]") == 34 - absent


# ------------------------------------------------- scenario 3, the refusals
#
# The second-source pass (2026-11-11) closed none of the remaining gaps and
# found that four of them CANNOT be closed by retrieval: a metal has no static
# permittivity, and a lifetime is a property of the sample, not the material.
# They are recorded as decisions rather than as pending work, so the next pass
# does not reopen them and invent a number to close them.

def test_the_refusals_are_the_four_decided_ones():
    """Pins WHICH gaps are deliberate, and that they are still gaps.

    The asymmetry matters: the retrieval gaps (Al2O3, HfO2 eps_s) wait on a
    handbook and may be closed honestly later. These four may not, so an entry
    moving out of REFUSED without a new source is the bug this test catches.
    """
    assert {k: sorted(v) for k, v in MM.REFUSED.items()} == {
        "Ag": ["eps_s"],
        "Au": ["eps_s"],
        "Si": ["tau_e", "tau_h"],
        "SiC": ["tau_e", "tau_h"],
    }
    # A refusal is still refused: the number is NaN and unverified, so it can
    # never reach a solve just because the reason changed.
    for mat, params in MM.REFUSED.items():
        for param in params:
            c = MM.Material and MM._LIBRARY[mat].params[param]
            assert not c.verified
            assert c.value != c.value, f"{mat}.{param} carries a number"
            assert c.basis.startswith("DELIBERATELY REFUSED"), c.basis
    # ...and the ones waiting on a retrieval are NOT mislabelled as decisions.
    for waiting in ("Al2O3", "HfO2"):
        for c in MM._LIBRARY[waiting].params.values():
            assert not c.basis.startswith("DELIBERATELY REFUSED"), (
                f"{waiting} is a retrieval gap, not a refusal")


def test_a_metal_cannot_be_used_as_a_dielectric():
    """The refusal has to reach the solve path, not just the entry's prose.

    Au and Ag are how a user would plausibly model an electrode's surroundings;
    letting that through with NaN would put a NaN in the potential equation, or
    worse, tempt a later edit to substitute a plausible number. It is refused by
    name instead.
    """
    with pytest.raises(ValueError, match=r"Au\.eps_s"):
        MM.resolve(["plate"], {"plate": "Au"})
    with pytest.raises(ValueError, match=r"Ag\.eps_s"):
        MM.resolve(["plate"], {"plate": "Ag"})
    # A silicon part is refused for its lifetimes for the same reason: they are
    # the sample's property and must come from the caller, not the library.
    with pytest.raises(ValueError, match=r"Si\.tau_e"):
        MM.resolve(["body"], {"body": "Si"})
    # Refusing the LIBRARY value is not refusing the CALLER: a part that supplies
    # its own lifetime resolves, because a lifetime is a sample property the
    # caller knows and the library must not invent.
    values, sources = MM.resolve(
        ["body"], {"body": "Si"}, {"body": {"tau_e": 1e-5, "tau_h": 4e-6}}
    )
    assert sources["body"]["tau_e"] == "override"


def test_a_per_part_lifetime_override_closes_the_refusal():
    """The refusal names the fix: supply tau per part, and it is recorded as one.

    This is the difference between "we refused" and "you cannot use silicon".
    The override path already exists for overrides generally; what this pins is
    that the REFUSED parameter is reachable through it -- a refusal that also
    blocks the override would be a dead end, not a decision.
    """
    values, sources = MM.resolve(
        ["body"], {"body": "Si"},
        overrides={"body": {"tau_e": 1e-5, "tau_h": 4e-6}},
    )
    assert values["body"]["tau_e"] == 1e-5
    assert values["body"]["tau_h"] == 4e-6
    assert sources["body"]["tau_e"] == "override"
    assert sources["body"]["tau_h"] == "override"
    # ...and the override does not erase the refusal from the library: the next
    # caller who forgets still gets an error naming the reason.
    assert "tau_e" in MM.REFUSED["Si"]
