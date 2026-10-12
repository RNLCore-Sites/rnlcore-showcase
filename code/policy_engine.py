# Excerpt from RNLCore Control-Plane (private repo), lightly trimmed for the showcase.
# app/policy.py + app/policy_mapping.py + app/entitlement_transitions.py + app/device_identity.py
#
# The whole system rests on these few functions: given a device ID, decide
# exactly what network access it gets. Anything unknown resolves to LOCKED.

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

NORMAL_CHECKIN_SECONDS = 300   # healthy devices check in every 5 minutes
LOCKED_CHECKIN_SECONDS = 15    # locked devices check in fast so they recover quickly


# --- Device identity ---------------------------------------------------------

DEVICE_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def is_valid_device_id(device_id: str | None) -> bool:
    if not isinstance(device_id, str):
        return False
    return bool(DEVICE_ID_PATTERN.fullmatch(device_id))


# --- Billing standing -> entitlement ----------------------------------------

def entitlement_from_standing(billing_status: str, financing_status: str) -> str:
    """
    Pure deterministic entitlement transition logic.

      - billing late/materially_delinquent -> locked_billing
      - financing at risk                   -> wired_only
      - otherwise                           -> active

    Fail-closed on unknown standing.
    """
    try:
        b = BillingStatus(billing_status)
        f = FinancingStatus(financing_status)
    except Exception:
        return "locked_billing"

    if b in (BillingStatus.late, BillingStatus.materially_delinquent):
        return "locked_billing"

    if f == FinancingStatus.financed_at_risk:
        return "wired_only"

    return "active"


# --- Entitlement -> enforcement ---------------------------------------------

@dataclass
class EnforcementDecision:
    locked: bool
    allow_wired: bool
    allow_cellular: bool
    reason: str


def enforcement_from_entitlement(entitlement_state: str) -> EnforcementDecision:
    """Canonical enforcement mapping from persisted entitlement_state. Fail-closed on unknown values."""
    state = (entitlement_state or "").strip().lower()

    if state == "active":
        return EnforcementDecision(locked=False, allow_wired=True, allow_cellular=True,
                                   reason="Entitlement active")

    if state == "locked_billing":
        return EnforcementDecision(locked=True, allow_wired=False, allow_cellular=False,
                                   reason="Entitlement locked_billing")

    if state in {"locked_financing", "wired_only"}:
        # A payment problem removes the paid backup path,
        # but never breaks the customer's normal internet.
        return EnforcementDecision(locked=False, allow_wired=True, allow_cellular=False,
                                   reason="Entitlement financing gated (wired only)")

    return EnforcementDecision(locked=True, allow_wired=False, allow_cellular=False,
                               reason="Unknown entitlement_state (fail-closed)")


# --- The policy every device receives on check-in ----------------------------

def policy_for_checkin(device_id: str) -> dict[str, Any]:
    """Canonical enforcement source: account.entitlement_state (fail-closed)."""
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.device_id == device_id).one_or_none()
        if device is None:
            return _locked_policy(device_id, "Unknown device")

        if device.locked or not device.account_id:
            return _locked_policy(device_id, "Device is unbound or locked")

        account = db.query(Account).filter(Account.account_id == device.account_id).one_or_none()
        if account is None:
            return _locked_policy(device_id, "Unknown account")

        ent = (account.entitlement_state or "").strip()
        if not ent:
            return _locked_policy(device_id, "Missing entitlement_state (fail-closed)")

        decision = enforcement_from_entitlement(ent)

        return {
            "device_id": device_id,
            "server_time_utc": _utc_iso_z(),
            "allowed": not decision.locked,
            "allow_wired": decision.allow_wired,
            "allow_cellular": decision.allow_cellular,
            "captive_portal": decision.locked,
            "policy_version": "v1",
            "message": decision.reason,
            "checkin_interval_seconds": LOCKED_CHECKIN_SECONDS if decision.locked else NORMAL_CHECKIN_SECONDS,
            "fail_closed": True,
            "locked": decision.locked,
        }
    except Exception:
        return _locked_policy(device_id, "Policy evaluation error")
    finally:
        db.close()


def _locked_policy(device_id: str, message: str) -> dict[str, Any]:
    return {
        "device_id": device_id,
        "server_time_utc": _utc_iso_z(),
        "allowed": False,
        "allow_wired": False,
        "allow_cellular": False,
        "captive_portal": True,
        "policy_version": "v1",
        "message": message,
        "checkin_interval_seconds": LOCKED_CHECKIN_SECONDS,
        "fail_closed": True,
        "locked": True,
    }


def _utc_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# --- The device-facing endpoint (app/main.py) --------------------------------

@app.post("/v1/device/checkin")
def device_checkin(payload: CheckinRequest):
    if not is_valid_device_id(payload.device_id):
        raise HTTPException(status_code=400, detail="Invalid device_id")
    return policy_for_checkin(payload.device_id)
