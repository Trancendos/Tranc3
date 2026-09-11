"""The Immune System — the estate's own defence against what it takes in.

The user's framing, which this package implements literally: GitHub Actions are
white blood cells, the repository is the body, and every commit is food, an
experience, or an object taken in. Some of it carries defects. The point of the
immune system is not to stop the body eating -- a body that eats nothing does
not grow -- it is to let the body keep taking things in and keep developing,
while catching what would do harm.

Four layers, matching the biology and the code:

    innate      src/immune/sensors.py   fast, generic, always on. Fires on
                                        shapes, not on specific known attacks.
                                        Every one reports whether it could
                                        actually SEE, because a sensor that
                                        cannot see reports the same 'clean' as
                                        a healthy body.
    circulation src/immune/sarif.py     one bloodstream. Every sensor's output
                                        normalised to SARIF 2.1.0 so the estate
                                        can be read in one language.
    memory      src/immune/memory.py    what was met before and how it was
                                        adjudicated -- with an expiry, because
                                        a decision nobody revisits is scar
                                        tissue, not memory. Detects its own
                                        autoimmunity: a rule attacking healthy
                                        tissue across many files.
    vitals      src/immune/grade.py     the health check. A grade computed from
                                        what the sensors saw, and -- the part
                                        that matters -- the DELTA against the
                                        baseline, because absolute health says
                                        less than the direction of travel.

Zero-cost and vendor-independent by construction. It replaces what Microsoft
Security DevOps, AWS IAM Access Analyzer and CodeFactor were each doing a piece
of, on tooling this estate already owns, with no account to hold and no tenant
to onboard. See docs/governance/IMMUNE-SYSTEM.md for what each vendor taught
and where this goes further.
"""

from src.immune.memory import Adjudication, apply_memory, load_adjudications
from src.immune.sarif import Finding, MergedReport, merge
from src.immune.sensors import Outcome, Sensor, SensorResult, load_manifest, run_sensor

__all__ = [
    "Adjudication",
    "Finding",
    "MergedReport",
    "Outcome",
    "Sensor",
    "SensorResult",
    "apply_memory",
    "load_adjudications",
    "load_manifest",
    "merge",
    "run_sensor",
]
