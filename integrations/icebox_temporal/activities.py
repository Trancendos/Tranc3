"""Optional Temporal activity for metadata-only IceBox policy evaluation.

Deploy only as a separate worker with Temporal Python SDK and Temporal Server.
Does not connect to IceBox, send alerts, or execute files.
"""

from temporalio import activity
from src.security.ice_box.automation_policy import plan_scan


@activity.defn(name="icebox_evaluate_scan_policy")
def evaluate_scan_policy(input: dict[str, str | bool]) -> dict[str, str | bool]:
    allowed = {"verdict", "quarantined"}
    if set(input) != allowed:
        raise ValueError("Only verdict and quarantined metadata are permitted")
    if type(input["quarantined"]) is not bool or type(input["verdict"]) is not str:
        raise TypeError("Invalid metadata types")
    return plan_scan(input["verdict"], quarantined=input["quarantined"]).as_dict()
