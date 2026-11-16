"""Cited materials library for drift-diffusion (task 2.2).

WHAT THIS MODULE IS FOR
-----------------------
Every drift-diffusion material parameter comes from here, and every value
names the source it was read from. A request may override any parameter for
one part; the manifest records which values came from the library and which
were overridden.

THE RULE THAT GOVERNS THIS FILE
-------------------------------
The spec (openspec/changes/electrical-simulation/specs/electrical-materials)
says: "each SHALL be read from its cited source before it is written into the
library ... A number quoted from memory SHALL NOT ship."

That rule is enforced, not just stated. An entry whose parameters have not
been read from a source is present in this file with ``verified=False`` and
the basis "NOT YET RETRIEVED", and ``require_cited`` refuses it. The test
suite calls ``require_cited`` for every shipped material, so an unretrieved
entry is a recorded gap rather than a silent one. That test is currently an
``xfail(strict=True)``: it RUNS, FAILS, and is expected to fail, naming the
gap; it does not turn the suite red while the gap is open, and it turns the
suite red if the gap is closed without the mark being removed. A second test
pins exactly which parameters are missing. If a material below is marked
not-retrieved, fill it by retrieving the source and citing table and page,
never from memory.

WHERE THE NUMBERS COME FROM, AND HOW THEY WERE FETCHED (2026-11-09)
-------------------------------------------------------------------
Most are from Ioffe/NSM (`https://www.ioffe.ru/SVA/NSM/Semicond/<mat>/...`).

**Provenance caveat, on every value read from Ioffe:** those pages were fetched
with `curl -sS -k`, i.e. **without TLS certificate verification** (the site's
own chain is invalid; the lead confirmed the certificate is the problem, not
the network). No credentials and no cookies were sent, and no fetched content
was piped into a shell. So the numbers are what the page said, but nobody
verified that the page was the genuine ioffe.ru page and not an
interception. A reader who needs that assurance must re-fetch them with a
validating client.

**Two kinds of value, and they are not interchangeable.** `Ioffe/NSM` gives
one figure per row. Where the page labels it a bound ("<=1400") it is recorded
as a CEILING, not a typical value. Five static permittivities (Si, GaAs, InP,
SiO2, air) are from Wikipedia's 1 kHz table, a secondary source.

What is still NOT retrieved, left as NaN and refused by `require_cited`, is
listed by `gaps()`: Al2O3 and HfO2 permittivities, Au and Ag permittivities,
Si mu/tau, SiC n_i/mu/tau. Nothing here was filled from memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from dot_material import Constant

# Placeholder for a parameter that exists in the schema but has not been read
# from a source. It is never a physical value; carrying it is how a missing
# parameter stays VISIBLE instead of being filled with a plausible number.
NOT_RETRIEVED = "NOT YET RETRIEVED"


def _missing(param: str, why: str = "") -> Constant:
    """An explicitly absent, explicitly UNVERIFIED parameter (value is NaN)."""
    return Constant(
        name=param,
        value=float("nan"),
        unit=_UNIT_OF.get(param, ""),
        basis=(
            "NOT YET RETRIEVED. " + (why or "No retrieved source carries it.")
            + " This is a recorded gap, not a value."
        ),
        verified=False,
        # UNSOURCED, and not silently so: this is the strongest UNVERIFIED mark
        # available. It is refused by require_cited regardless.
        assumed=True,
        note="refused by require_cited; see the module docstring",
    )


def _refused(param: str, why: str) -> Constant:
    """A parameter that is absent on PURPOSE, because it does not exist.

    Different from ``_missing``: a gap is "nobody has read this yet" and is the
    job of a later retrieval pass; a refusal is a decision that the parameter is
    undefined for this material (a metal has no static permittivity; a lifetime
    is a property of the sample, not the material). Both carry NaN and both are
    refused by ``require_cited``, so neither can reach a solve; keeping the pair
    apart stops a refusal being reopened as a retrieval task that can never
    succeed, and refuses "no, and stop asking" the same clear way.

    DEVSIM's drift-diffusion contact models hard-code equilibrium carrier
    densities and expose no surface recombination velocity, so an empirical
    lifetime is also not load-bearing on the current path.
    """
    return Constant(
        name=param,
        value=float("nan"),
        unit=_UNIT_OF.get(param, ""),
        basis=(
            "DELIBERATELY REFUSED, not a retrieval gap. " + why
            + " This is a decision recorded in the library, not a missing value."
        ),
        verified=False,
        assumed=True,
        note="refused by require_cited and by design; see _refused in this module",
    )


#: Set once _LIBRARY exists, read back off the entries rather than hand-listed.
REFUSED: dict[str, tuple[str, ...]] = {}


#: Units, so an absent parameter is still described correctly.
_UNIT_OF = {
    "eps_s": "1", "n_i_300K": "cm^-3",
    "mu_e": "cm^2/(V s)", "mu_h": "cm^2/(V s)",
    "tau_e": "s", "tau_h": "s", "B_rad": "cm^3/s",
}

#: The parameters a semiconductor entry must carry, per the spec.
SEMICONDUCTOR_PARAMS = (
    "eps_s",          # static relative permittivity
    "n_i_300K",       # intrinsic carrier density, cm^-3
    "mu_e",           # electron mobility, cm^2/(V s)
    "mu_h",           # hole mobility, cm^2/(V s)
    "tau_e",          # electron lifetime, s
    "tau_h",          # hole lifetime, s
    "B_rad",          # radiative recombination coefficient, cm^3/s
)

#: Non-semiconductors carry only eps_s.
INSULATOR_PARAMS = ("eps_s",)
METAL_PARAMS = ("eps_s",)


@dataclass(frozen=True)
class Material:
    """One library material: its kind and its cited parameters."""

    name: str
    kind: str  # "semiconductor" | "insulator" | "metal" | "gas"
    params: dict[str, Constant]

    def __getitem__(self, key: str) -> Constant:
        return self.params[key]


# --------------------------------------------------------------- citations

# Retrieved 2026-11-09 from the Wikipedia table "Relative permittivities of
# some materials at room temperature under 1 kHz" (WebFetch). A secondary
# source: the primary each row cites is recorded with the value, so it can be
# checked. Cited as secondary rather than dressed up as a primary one.
_WIKI_PERMITTIVITY = (
    "Wikipedia, 'Relative permittivity', table 'Relative permittivities of "
    "some materials at room temperature under 1 kHz' (retrieved with WebFetch "
    "2026-11-09); row {row}. {underlying}"
)

_UNDER = {
    "silicon": "Row carries no footnote on the retrieved page.",
    "gaas": "Row cites ref. [8], Fox, Mark (2010), 'Optical Properties of Solids'.",
    "sio2": "Row cites ref. [4], Gray, Hurst, Lewis & Meyer (2009), "
            "'Analysis and Design of Analog Integrated Circuits'.",
    "air": "Row cites ref. [1]; value given 'at STP, 900 kHz'.",
}


def _eps_s(name: str, row: str, value: float, key: str) -> Constant:
    return Constant(
        name=f"{name} eps_s",
        value=value,
        unit="1",
        basis=_WIKI_PERMITTIVITY.format(row=f"'{row}'", underlying=_UNDER[key]),
        verified=True,
        note="Secondary source; the primary cited by the table is named above "
             "and was not itself retrieved.",
    )


# Ioffe/NSM. Every value below was read from the named page on 2026-11-09,
# fetched with `curl -sS -k` (NO TLS certificate verification; see the module
# docstring). The note field always says so, so no reader has to come back
# here to find out.
_IOFFE = "https://www.ioffe.ru/SVA/NSM/Semicond"

# NASA/GRC Comparison of Selected Important Semiconductor Electronic Properties
# of Major SiC Polytypes with Silicon, GaAs, and 2H-GaN. Table 5.1, explicitly
# "at 300 K", columns: Silicon | GaAs | 4H-SiC | 6H-SiC | 3C-SiC | 2H-GaN.
NASA_SIC_TABLE = (
    "NASA/GRC (nasa.gov) 'Comparison of Selected Important Semiconductor "
    "Electronic Properties of Major SiC Polytypes', Table 5.1 at 300 K"
)

#: TU Wien (Kaufmann) dissertation Table 2.3, SiC material parameters.
#: Used for 4H n_i, where the NASA table's cell is physically impossible at
#: 300 K -- see the derivation in the SiC n_i note. Its 6H n_i (1.6e-6) and
#: its hole mobility (115, agreeing with NASA) are consistent with the calc,
#: which is why the table is trusted for the one cell NASA gets wrong.
TU_WIEN_SIC_TABLE = (
    "TU Wien PhD thesis (Kaufmann), SiC material parameters, Table 2.3"
)


def _ioffe(mat: str, page: str, row: str, value: float, unit: str,
           name: str, note: str = "") -> Constant:
    return Constant(
        name=name,
        value=value,
        unit=unit,
        basis=(
            f"Ioffe/NSM {_IOFFE}/{mat}/{page}, table 'Basic Parameters at 300 K'"
            f" / section, row '{row}'. Retrieved 2026-11-09 with curl -k: TLS "
            f"certificate NOT verified (the site's chain is invalid)."
        ),
        verified=True,
        note=note or "Fetched without TLS verification; re-fetch with a "
                     "validating client if provenance must be proven.",
    )


def _cited(page: str, row: str, value: float, unit: str, name: str,
           *, note: str = "") -> Constant:
    """A parameter read from a named, retrievable page other than Ioffe/NSM.

    ``page`` must say what the document is and where it came from, ``row`` the
    exact table row it was read off, so a value moved away from its source
    shows up in a diff.
    """
    return Constant(
        name=name,
        value=value,
        unit=unit,
        basis=f"{page}, row '{row}'. Retrieved 2026-11-11 with curl.",
        verified=True,
        note=note,
    )


# --------------------------------------------------------------- library

def _semiconductor(mat: str, eps_s: Constant, *,
                   n_i: Constant | None = None,
                   mu_e: Constant | None = None,
                   mu_h: Constant | None = None,
                   tau_e: Constant | None = None,
                   tau_h: Constant | None = None,
                   B_rad: Constant | None = None,
                   gaps: dict[str, str] | None = None,
                   refused: tuple[str, ...] | None = None) -> Material:
    """A semiconductor entry; anything not supplied is an explicit gap.

    ``gaps`` says WHY a parameter is missing, per parameter, so an unretrieved
    value carries the reason it is unretrieved. ``refused`` names the parameters
    in ``gaps`` that are absent BY DECISION rather than pending retrieval, so the
    reason is recorded as a refusal and not reopened as a task that can never
    succeed (see ``_refused``).
    """
    gaps = gaps or {}
    refused = tuple(refused) if refused is not None else ()
    have = {"eps_s": eps_s, "n_i_300K": n_i, "mu_e": mu_e, "mu_h": mu_h,
            "tau_e": tau_e, "tau_h": tau_h, "B_rad": B_rad}
    params = {}
    for key in SEMICONDUCTOR_PARAMS:
        c = have.get(key)
        if c is not None:
            params[key] = c
        elif key in refused:
            params[key] = _refused(key, gaps.get(key, ""))
        else:
            params[key] = _missing(key, gaps.get(key, ""))
    return Material(name=mat, kind="semiconductor", params=params)


_LIBRARY: dict[str, Material] = {
    # --- Si. eps_s = 11.7, the primary (Ioffe/NSM, read on the page
    # 2026-11-09). The Wikipedia table's 11.68 is a secondary figure and is
    # mentioned in the note, not used as the entry.
    "Si": _semiconductor(
        "Si",
        Constant(
            name="Si eps_s", value=11.7, unit="1",
            basis=(
                f"Ioffe/NSM {_IOFFE}/Si/basic.html, table 'Basic Parameters "
                f"at 300 K', row 'Dielectric constant', value 11.7. Retrieved "
                f"2026-11-09 with curl -k: TLS certificate NOT verified (the "
                f"site's chain is invalid)."
            ),
            verified=True,
            note="Primary source. The Wikipedia permittivity table gives "
                 "11.68 (secondary, no footnote); it is recorded here as a "
                 "disagreement, not used: neither is averaged.",
        ),
        n_i=_ioffe("Si", "bandstr.html", "Intrinsic carrier concentration",
                   1e10, "cm^-3", "Si n_i",
                   note="Ioffe prints '1*10^10 cm^-3'."),
        mu_e=_ioffe("Si", "electric.html", "Mobility electrons <=1400", 1400.0,
                    "cm^2/(V s)", "Si mu_e",
                    note="A CEILING, not a typical value: the row reads "
                         "'<=1400 cm^2 V^-1 s^-1'. Doping dependence is on "
                         "the same page as curves and was not tabulated."),
        mu_h=_ioffe("Si", "electric.html", "Mobility holes <=450", 450.0,
                    "cm^2/(V s)", "Si mu_h",
                    note="A CEILING: the row reads '<=450 cm^2 V^-1 s^-1'."),
        B_rad=_ioffe("Si", "electric.html",
                     "Radiative recombination coefficient B 1.1x10^-14",
                     1.1e-14, "cm^3/s", "Si B_rad",
                     note="Table footnote gives the source as Gerlach et al. "
                          "(1972)."),
        gaps={
            # Second-source pass 2026-11-11 (TU Wien, Ayalew, node72): still
            # refused, now on evidence rather than absence. The thesis gives
            # the Scharfetter relation tau(N, T) but says "There are no
            # reliable experimental data available to extract the corresponding
            # parameters for a-SiC" and proposes borrowing Si values for SiC --
            # the borrow is in the other direction, so it supplies no Si number.
            # A second source searching for a Si lifetime number and finding
            # none is a stronger refusal than "Ioffe drew it as a figure".
            "tau_e": "Ioffe gives Si lifetimes only as a figure (tau_n vs "
                     "acceptor density, 300 K) with no tabulated value, so no "
                     "number could be read off a table.",
            "tau_h": "Same: tau_p and L_p are a figure vs donor density, no "
                     "tabulated value.",
        },
        # By decision, not pending retrieval: a lifetime is a property of the
        # sample (doping, defects, process), not of "Si". The established
        # doping-dependent models (Scharfetter) need per-part parameters that a
        # material library cannot supply, so the user supplies tau per part via
        # an override -- which resolve() records as its source.
        refused=("tau_e", "tau_h"),
    ),
    # --- GaAs
    "GaAs": _semiconductor(
        "GaAs",
        _eps_s("GaAs", "GaAs", 12.4, "gaas"),
        n_i=_ioffe("GaAs", "bandstr.html", "Intrinsic carrier concentration",
                   2.1e6, "cm^-3", "GaAs n_i"),
        mu_e=_ioffe("GaAs", "electric.html",
                    "Mobility electrons <=8500; weakly doped drift "
                    "mu_n=8000(300/T)^(2/3)", 8000.0, "cm^2/(V s)",
                    "GaAs mu_e",
                    note="Two rows disagree in kind: the basic row is a "
                         "CEILING ('<=8500'), while the weakly doped 300 K "
                         "drift mobility is a formula, mu_n = 8000(300/T)^(2/3), "
                         "i.e. 8000 at 300 K. The library uses the 300 K value "
                         "of the drift formula and does not present it as the "
                         "ceiling."),
        mu_h=_ioffe("GaAs", "electric.html", "Mobility holes <=400", 400.0,
                    "cm^2/(V s)", "GaAs mu_h",
                    note="A CEILING: '<=400 cm^2 V^-1 s^-1'."),
        tau_h=_ioffe("GaAs", "electric.html",
                     "Pure n-type: longest lifetime of holes tau_p ~3*10^-6 s",
                     3e-6, "s", "GaAs tau_h",
                     note="Ioffe's own '~' qualifier; recorded as approximate "
                          "(the page gives no tighter figure)."),
        tau_e=_ioffe("GaAs", "electric.html",
                     "Pure p-type, low injection: tau_n ~5*10^-9 s",
                     5e-9, "s", "GaAs tau_e",
                     note="Ioffe's '~' qualifier retained."),
        B_rad=_ioffe("GaAs", "optic.html",
                     "Radiative recombination coefficient 7*10^-10",
                     7e-10, "cm^3/s", "GaAs B_rad"),
        gaps={},
    ),
    # --- InP
    "InP": _semiconductor(
        "InP",
        Constant(
            name="InP eps_s", value=12.5, unit="1",
            basis=(
                "Ioffe/NSM InP/basic.html, 'Basic Parameters at 300 K', row "
                "'Dielectric constant (static)'. Original: Shmidt, Handbook "
                "Series on Semiconductor Parameters vol.1, pp.169-190 (1996). "
                "Read for task 1.9 (dot_material.py); page re-fetched "
                "2026-11-09 to confirm."
            ),
            verified=True,
        ),
        n_i=_ioffe("InP", "bandstr.html", "Intrinsic carrier concentration",
                   1.3e7, "cm^-3", "InP n_i"),
        mu_e=_ioffe("InP", "electric.html",
                    "Mobility electrons <=5400; weakly doped "
                    "mu_n=(4.2-5.4)e3*(300/T)", 5400.0, "cm^2/(V s)",
                    "InP mu_e",
                    note="A CEILING: '<=5400'. The weakly doped drift formula "
                         "on the same page gives a RANGE, "
                         "(4.2-5.4)e3 (300/T) cm^2/(V s); the ceiling is the "
                         "upper edge of it. The range is not collapsed to a "
                         "point."),
        mu_h=_ioffe("InP", "electric.html", "Mobility holes <=200", 200.0,
                    "cm^2/(V s)", "InP mu_h",
                    note="A CEILING: '<=200 cm^2 V^-1 s^-1'."),
        tau_h=_ioffe("InP", "electric.html",
                     "Pure n-type: longest lifetime of holes tau_p ~3*10^-6 s",
                     3e-6, "s", "InP tau_h", note="Ioffe's '~' qualifier."),
        tau_e=_ioffe("InP", "electric.html",
                     "Pure p-type, low injection: tau_n ~2*10^-9 s",
                     2e-9, "s", "InP tau_e", note="Ioffe's '~' qualifier."),
        B_rad=_ioffe("InP", "optic.html",
                     "Radiative recombination coefficient 1.2*10^-10",
                     1.2e-10, "cm^3/s", "InP B_rad"),
        gaps={},
    ),
    # --- SiC. Ioffe tabulates four polytypes with DIFFERENT values. The
    # library cannot carry "SiC" as if it were one material, so the 4H
    # polytype is recorded explicitly, following Ioffe's own note that the
    # 6H value is "usually used" for 4H where it has none.
    "SiC": _semiconductor(
        "SiC",
        _ioffe("SiC", "basic.html",
               "Dielectric constant (static, ordinary direction) 6H-SiC "
               "eps_0,ort ~= 9.66", 9.66, "1", "SiC (4H/6H) eps_s",
               note="POLYTYPE: Ioffe gives 3C 9.72 (Patric & Choyke 1970), "
                    "6H ordinary 9.66 / extraordinary 10.03. For 4H Ioffe says "
                    "'the value of 6H-SiC ... is usually used'. The library "
                    "records 6H ordinary 9.66; a 4H solve is on the 6H "
                    "approximation and a 3C or anisotropic solve is NOT "
                    "covered."),
        B_rad=_ioffe("SiC", "optic.html",
                     "Radiative recombination coefficient 4H-SiC "
                     "1.5*10^-12 cm^3 s^-1", 1.5e-12, "cm^3/s", "SiC (4H) B_rad",
                     note="Ioffe labels this row 'estimate' (Goldberg et al. "
                          "2001); an estimate, not a measurement."),
        # The mobilities below come from NASA/GRC's polytype comparison table,
        # which is the reason the 4H column is used rather than Ioffe's 6H
        # fallback: it states the temperature ("at 300 K") that the field name
        # asserts. n_i does NOT come from there -- its NASA cell fails the
        # 300 K arithmetic (see the note) and TU Wien supplies it instead.
        n_i=_cited(
            TU_WIEN_SIC_TABLE,
            "Table 2.3, 4H-SiC column, n_i = 5e-9 cm^-3 (table states NO "
            "temperature; see the note)",
            5e-9, "cm^-3", "SiC (4H) n_i_300K",
            note="CORRECTED 2026-11-11 from NASA's ~1e-7, which the review "
                 "rejected. "
                 "TEMPERATURE CAVEAT, from the lead's source check: TU Wien "
                 "Table 2.3 states NO temperature. The table's Eg 3.26 eV is "
                 "described there as coming from liquid-He photoluminescence "
                 "(low temperature), while this field asserts 300 K. The 5e-9 "
                 "is therefore recorded as the table's value, NOT as a verified "
                 "300 K figure -- the source does not say 300 K and this note "
                 "must not put those words in its mouth. "
                 "WHY 1e-7 IS STILL REJECTED (300 K arithmetic, so it applies "
                 "only once we assume both sources mean ~300 K): "
                 "n_i = sqrt(Nc*Nv)*exp(-Eg/2kT), Eg=3.26 eV (the library's 4H "
                 "value), T=300 K. At m*==1.0 -- an impossible maximum -- this "
                 "gives 1.04e-8 cm^-3, still 9.6x BELOW 1e-7. Over the "
                 "plausible masses m_e*=0.2-0.37, m_h*=0.4-0.82 the range is "
                 "1.56e-9 to 4.25e-9 (computed at the corners; the interior "
                 "points lie within it). That brackets TU Wien's 5e-9 and is "
                 "one to two orders below NASA's value. "
                 "TWO DIFFERENT Eg DROPS, both correct, not interchangeable: "
                 "(a) to reach 1e-7 from the table's 5e-9 at fixed masses needs "
                 "Eg lower by 2kT*ln(20) = 0.155 eV, i.e. Eg = 3.105 eV; "
                 "(b) to reach 1e-7 from the computed ceiling 1.04e-8 needs "
                 "0.117 eV, i.e. Eg = 3.143 eV. "
                 "WHY THAT IS DAMNING FOR NASA (a weaker claim than an earlier "
                 "draft made): 3.10-3.14 eV is not 6H's gap either. 6H is "
                 "~3.02 eV, so that band sits 0.12-0.16 eV BELOW 4H (3.26) and "
                 "0.08-0.12 eV ABOVE 6H -- in neither polytype's gap. The "
                 "anomaly is therefore plain MIS-SCALING, not 'NASA's cell is a "
                 "6H number', which this note claimed before the arithmetic was "
                 "redone. "
                 "TU Wien's 6H value (1.6e-6) is high by ~3-5x against the same "
                 "calc at Eg=3.02 (which gives 3.1e-7 to 6.4e-7) but the SAME "
                 "ORDER -- consistent with a fitted table, which is why its 4H "
                 "cell is trusted over NASA's on arithmetic alone."),
        mu_e=_cited(
            NASA_SIC_TABLE,
            "Electron mobility at N_D=10^16 cm^-3, 4H-SiC: parallel-to-c "
            "800, perpendicular-to-c 60",
            800.0, "cm^2/(V s)", "SiC (4H) mu_e",
            note="ANISOTROPIC source given as two numbers; the parallel-to-c "
                 "axis value 800 is recorded because the tet-mesh solves have "
                 "no c-axis convention to honour. Perpendicular is 60, a 13x "
                 "difference, so a solve whose current flows across the c-axis "
                 "is NOT covered by this entry."),
        mu_h=_cited(
            NASA_SIC_TABLE,
            "Hole mobility at N_A=10^16 cm^-3, 4H-SiC column",
            115.0, "cm^2/(V s)", "SiC (4H) mu_h",
            note="NASA gives a single value for holes (no c-axis split), and "
                 "it agrees with TU Wien Table 2.3, also 115."),
        gaps={
            "tau_e": "Neither source retrieved for SiC tabulates a carrier "
                     "lifetime: NASA Table 5.1 has no lifetime row, TU Wien "
                     "Table 2.3 omits it, and the TU Wien lifetime section "
                     "(node72) explicitly says 'There are no reliable "
                     "experimental data available to extract the "
                     "corresponding parameters for a-SiC' -- it then proposes "
                     "substituting Si lifetimes, which is an admission that no "
                     "SiC number exists to read. Ioffe SiC pages carry none "
                     "either. Remains a gap, not a plausible-looking number.",
            "tau_h": "Same as tau_e: no SiC lifetime in NASA Table 5.1, TU "
                     "Wien Table 2.3, TU Wien node72 or the fetched Ioffe SiC "
                     "pages.",
        },
        refused=("tau_e", "tau_h"),
    ),
    # --- insulators and metals: Ioffe/NSM carries semiconductors only.
    # The dielectrics path (SVA/NSM/Dielectrics/) returns 404 and the listed
    # index has no insulator entries, so these have no Ioffe source at all.
    "SiO2": Material(name="SiO2", kind="insulator",
                     params={"eps_s": _eps_s("SiO2", "Silicon dioxide", 3.9, "sio2")}),
    "Al2O3": Material(
        name="Al2O3", kind="insulator",
        params={"eps_s": _missing(
            "eps_s", "Ioffe/NSM covers semiconductors only; SVA/NSM/Dielectrics/ "
                     "returns 404. Needs a dielectric handbook.")},
    ),
    "HfO2": Material(
        name="HfO2", kind="insulator",
        params={"eps_s": _missing(
            "eps_s", "Ioffe/NSM covers semiconductors only; SVA/NSM/Dielectrics/ "
                     "returns 404. Needs a dielectric handbook.")},
    ),
    # --- metals. A metal has NO static permittivity: in an electrostatic or
    # drift-diffusion solve it is a conductor, i.e. a contact or equipotential,
    # not a dielectric. (Optical, frequency-dependent metal permittivity is a
    # separate library and out of scope.) The entries keep a kind of "metal" so
    # a caller can find them, and eps_s stays an explicit gap with that reason.
    "Au": Material(
        name="Au", kind="metal",
        params={"eps_s": _refused(
            "eps_s", "A metal has no static permittivity: in these solves gold "
                     "is a conductor (contact or equipotential), not a "
                     "dielectric. Ioffe/NSM carries semiconductors only, and no "
                     "dielectric handbook would list a static eps for a metal. "
                     "Using Au as a dielectric is refused; model it as a contact.")},
    ),
    "Ag": Material(
        name="Ag", kind="metal",
        params={"eps_s": _refused(
            "eps_s", "A metal has no static permittivity: in these solves "
                     "silver is a conductor (contact or equipotential), not a "
                     "dielectric. Same reason as Au. Using Ag as a dielectric "
                     "is refused; model it as a contact.")},
    ),
    "air": Material(
        name="air",
        kind="gas",
        params={"eps_s": _eps_s("air", "Air", 1.0, "air")},
    ),
}

#: The materials whose parameters are absent BY DECISION, not pending retrieval.
#: Read back off the entries above rather than hand-listed: a hand-typed second
#: copy is the thing that drifts from the library it describes. Each entry is a
#: decision that must survive refactors -- a later pass that "closes the gap"
#: here would have to invent a number, which is exactly what the library forbids.
REFUSED.update({
    mat.name: tuple(p for p, c in mat.params.items()
                    if c.basis.startswith("DELIBERATELY REFUSED"))
    for mat in _LIBRARY.values()
})
REFUSED = {k: v for k, v in REFUSED.items() if v}

#: The parameters that are absent because nobody has read them yet. Unlike
#: REFUSED, these are the CALLER's to supply: the quantity exists, and a
#: per-part override is exactly how a value without a library source reaches the
#: solve. Si's lifetimes used to sit here; they moved to REFUSED because the
#: sample-dependence is a material fact, not a retrieval backlog.
RETRIEVAL_GAPS: dict[str, tuple[str, ...]] = {
    "Al2O3": ("eps_s",),
    "HfO2": ("eps_s",),
}

LIBRARY_NAMES: tuple[str, ...] = tuple(_LIBRARY)


def library() -> dict[str, Material]:
    """The shipped library, by material name."""
    return dict(_LIBRARY)


def get(name: str) -> Material:
    """A library material by name, or ValueError listing the library."""
    try:
        return _LIBRARY[name]
    except KeyError:
        raise ValueError(
            f"unknown material {name!r}; library has: {', '.join(LIBRARY_NAMES)}"
        ) from None


def require_cited(materials: Iterable[str] | None = None) -> None:
    """Raise naming every parameter that has no retrieved source.

    This is the spec's "an uncited library entry is refused by its own test".
    It refuses a value that is unretrieved regardless of how plausible it
    looks, and it refuses a NaN, so a placeholder can never be mistaken for a
    number by a downstream solve.
    """
    names = list(materials) if materials is not None else list(LIBRARY_NAMES)
    bad: list[str] = []
    for name in names:
        mat = _LIBRARY[name]
        for param, c in mat.params.items():
            if not c.verified or c.value != c.value:  # NaN is never equal to itself
                bad.append(f"{name}.{param}")
    if bad:
        raise ValueError(
            "uncited parameter(s) in the materials library: "
            + ", ".join(sorted(bad))
            + ". Read each from its cited source (table and page) before it "
              "ships; do not fill from memory."
        )


def resolve(
    parts: Iterable[str],
    material_of_part: dict[str, str],
    overrides: dict[str, dict[str, float]] | None = None,
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, str]]]:
    """Resolve each part's parameters from the library, applying overrides.

    Returns ``(values, sources)`` where ``values[part][param]`` is the number
    used and ``sources[part][param]`` is ``"library: <name>"`` or
    ``"override"``. The manifest records the second, so a reader can always see
    which numbers were ours and which came from the shipped library.
    """
    overrides = overrides or {}
    values: dict[str, dict[str, float]] = {}
    sources: dict[str, dict[str, str]] = {}
    for part in parts:
        if part not in material_of_part:
            raise ValueError(f"part {part!r} has no material assigned")
        mat_name = material_of_part[part]
        mat = get(mat_name)
        vals: dict[str, float] = {}
        srcs: dict[str, str] = {}
        for param, c in mat.params.items():
            vals[param] = c.value
            srcs[param] = f"library: {mat_name}"
        # Every parameter still carrying a NaN here would go into the solve as
        # NaN, far from the part that caused it; name it now instead. This ONE
        # check covers both kinds of absence -- a retrieval gap nobody filled
        # (Al2O3.eps_s) and a refusal the caller did not override (Au.eps_s) --
        # because both are NaN by construction, and two checks for one rule is
        # how they drift apart. The reason each is absent lives in its entry.
        for param, c in mat.params.items():
            if param in overrides.get(part, {}):
                continue
            if c.value != c.value:  # NaN is never equal to itself
                kind = ("deliberately undefined for this material"
                        if param in REFUSED.get(mat_name, ())
                        else "a retrieval gap nobody has filled")
                raise ValueError(
                    f"{mat_name}.{param} is {kind} and part {part!r} does not "
                    f"override it: {c.basis}")
        for param, value in overrides.get(part, {}).items():
            vals[param] = float(value)
            srcs[param] = "override"
        values[part] = vals
        sources[part] = srcs
    return values, sources


def gaps() -> dict[str, list[str]]:
    """Materials with an unretrieved parameter, and which parameters."""
    out: dict[str, list[str]] = {}
    for name in LIBRARY_NAMES:
        bad = [p for p, c in _LIBRARY[name].params.items() if not c.verified]
        if bad:
            out[name] = bad
    return out


def report() -> str:
    """Human-readable dump: every material, parameter, value and citation."""
    out = ["Shipped materials library", "=" * 45, ""]
    for name in LIBRARY_NAMES:
        mat = _LIBRARY[name]
        out.append(f"{name} ({mat.kind})")
        for param, c in mat.params.items():
            out.append(f"    {c.cite()}")
    return "\n".join(out)
