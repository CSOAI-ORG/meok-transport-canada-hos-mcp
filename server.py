#!/usr/bin/env python3
"""
MEOK Transport Canada Hours of Service + NSC Compliance MCP
============================================================

By MEOK AI Labs · https://haulage.app · MIT
<!-- mcp-name: io.github.CSOAI-ORG/meok-transport-canada-hos-mcp -->

WHAT THIS DOES
--------------
Canadian commercial trucking lives under a federal-provincial split: Transport
Canada writes the rules (SOR/2005-313 + NSC), provinces enforce. A single
out-of-service order at an Ontario MTO or Quebec SAAQ scale is enough to:
  - Drop a CVOR score (Ontario) or PEVL rating (Quebec) into intervention
  - Suspend operating privileges
  - Lock cross-border shipping (CBSA + FMCSA cross-reference)
  - Spike insurance 25-200% on next renewal
  - Force facility audit + remediation pack

This MCP gives Safety Officers, dispatch supervisors, and owner-operators the
callable toolkit to stay compliant across Canadian commercial vehicle
operations — including the Canada-only twin-cycle regime (Cycle 1 vs Cycle 2),
the South-of-60 vs North-of-60 latitude split, ELD T-T-019 certified-device
rules, and the cross-border CA↔US regime handoff:

  - SOR/2005-313 Hours of Service (south + north of 60°N split)
  - 36-hour off-duty cycle-switch (Cycle 1 ↔ Cycle 2) + carrier notification
  - ELD mandate (Transport Canada T-T-019 — third-party certified only, 1 Jan 2023)
  - NSC Standard 9 (HoS) + Standard 11 (Vehicle Maintenance) carrier rating
  - Cross-border CA↔US regime resolution (which HoS applies in which jurisdiction)
  - Provincial Ministry of Transport audit prep
    (Ontario MTO CVOR · Quebec SAAQ PEVL · BC CVSE · Alberta TS Carrier Services)

TOOLS (7)
---------
- check_canada_hos_south_60th(driver_log)        → 13/14/16/10/70-120 audit
- check_canada_hos_north_60th(driver_log)        → 15/18/80 (Arctic regime)
- check_eld_canada_mandate(vehicle_spec)         → T-T-019 certified device check
- check_cycle_switch(driver, last_switch_date)   → 36h off-duty + notification
- check_nsc_carrier_safety(operator_data)        → NSC Standard 9 rating bands
- audit_cross_border_us_canada(driver, cross)    → CA HoS vs FMCSA at the line
- prepare_carrier_audit_pack(operator_data)      → Provincial MoT evidence checklist

WHY YOU PAY
-----------
One avoided CVOR intervention (Ontario) or PEVL "conditional" rating (Quebec)
= CAD $20k-$150k saved on insurance + remediation + lost shipper contracts.
CAD $49/mo Starter is a rounding error vs the existential risk.

PRICING
-------
Free MIT self-host · CAD 49/mo Starter · CAD 149/mo Pro · CAD 999/mo Fleet.

REGULATORY BASIS
----------------
SOR/2005-313 — Commercial Vehicle Drivers Hours of Service Regulations
Canadian Council of Motor Transport Administrators (CCMTA) — NSC Standard 9 (HoS)
                                                           — NSC Standard 11 (Periodic Vehicle Inspection)
                                                           — NSC Standard 14 (Carrier Safety Rating)
Transport Canada T-T-019 — ELD Technical Standard (Canada, 1 Jan 2023 mandate)
CSA Border Carrier Initiative — cross-border CA↔US harmonisation
Provincial enforcement: Ontario MTO (CVOR), Quebec SAAQ (PEVL), BC CVSE,
                       Alberta Transportation Carrier Services
"""

from __future__ import annotations
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone, date, timedelta
from typing import Optional
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("meok-transport-canada-hos")
_HMAC_SECRET = os.environ.get("MEOK_HMAC_SECRET", "")


# ──────────────────────────────────────────────────────────────────────
# Regulatory tables — SOR/2005-313 + NSC Standard 9
# ──────────────────────────────────────────────────────────────────────

# South of 60°N rules (SOR/2005-313, Part 1)
SOUTH_60_HOS_LIMITS = {
    "max_daily_driving_hr": 13,           # 13h driving per day
    "max_daily_on_duty_hr": 14,           # 14h on-duty per day
    "max_daily_cycle_window_hr": 16,      # 16h elapsed from end of last 8h off
    "min_daily_off_duty_hr": 10,          # 10h off-duty per day (at least 8 consecutive)
    "min_consecutive_off_duty_hr": 8,     # 8 of the 10 must be consecutive
    "cycle_1_max_on_duty_hr_per_7_day": 70,   # Cycle 1: 70h / 7 days
    "cycle_2_max_on_duty_hr_per_14_day": 120, # Cycle 2: 120h / 14 days
    "cycle_2_mandatory_24h_off_after_70": True,  # 24h off before reaching 70h in Cycle 2
    "mandatory_reset_consecutive_off_hr": 24,    # 24h consecutive off-duty for reset
}

# North of 60°N rules (SOR/2005-313, Part 2 — northern operations)
NORTH_60_HOS_LIMITS = {
    "max_daily_driving_hr": 15,           # 15h driving per day (extended for Arctic)
    "max_daily_on_duty_hr": 18,           # 18h on-duty per day
    "max_daily_cycle_window_hr": 20,      # 20h elapsed window
    "min_daily_off_duty_hr": 8,           # 8h off-duty per day
    "cycle_1_max_on_duty_hr_per_7_day": 80,   # 80h / 7 days
    "cycle_2_max_on_duty_hr_per_14_day": 120, # 120h / 14 days (same as south)
    "mandatory_reset_consecutive_off_hr": 24,
}

# Cycle-switch rules (SOR/2005-313 s.32)
CYCLE_SWITCH_RULES = {
    "min_consecutive_off_duty_hr_to_switch": 36,  # 36 consecutive hours off-duty
    "must_notify_carrier": True,
    "must_record_in_log": True,
}

# ELD mandate (Transport Canada T-T-019)
ELD_CANADA_MANDATE = {
    "effective_enforcement_date": "2023-01-01",
    "device_certification": "third-party-certified-only",  # TC accreditation body
    "required_vehicles": "Commercial Motor Vehicles regulated under SOR/2005-313, "
                         "operating in extra-provincial trucking (interprovincial or international)",
    "exempt_pre_2000_model_year": True,
    "exempt_rental_under_30_days": True,
    "exempt_statutory_exempt_driver": True,  # short-radius / certain operations per s.81
    "exempt_north_of_60_limited": False,     # ELD still applies north of 60°N
}

# NSC Standard 14 carrier safety rating bands (CCMTA)
NSC_SAFETY_RATING_BANDS = {
    "EXCELLENT": "0-14 — Excellent (low risk, light-touch oversight)",
    "SATISFACTORY": "15-34 — Satisfactory (compliant, standard oversight)",
    "CONDITIONAL": "35-69 — Conditional (intervention zone — facility audit triggered)",
    "UNSATISFACTORY": "70-100 — Unsatisfactory (privilege suspension imminent)",
}

# HoS infringement severity weights (used for NSC Standard 9 carrier scoring)
HOS_INFRINGEMENT_WEIGHTS_CA = {
    "exceeded_13h_driving_south": 7,
    "exceeded_14h_on_duty_south": 5,
    "exceeded_16h_cycle_window_south": 6,
    "insufficient_10h_off_duty_south": 5,
    "insufficient_8h_consecutive_off_south": 4,
    "exceeded_70h_7_day_cycle1": 7,
    "exceeded_120h_14_day_cycle2": 7,
    "missed_24h_reset_cycle2": 5,
    "exceeded_15h_driving_north": 7,
    "exceeded_18h_on_duty_north": 5,
    "exceeded_80h_7_day_north": 7,
    "no_eld_when_required": 5,
    "non_certified_eld_device": 6,
    "cycle_switch_insufficient_36h_off": 5,
    "cycle_switch_not_notified": 3,
    "log_falsification": 10,
}

# Provincial enforcement bodies + their carrier scoring systems
PROVINCIAL_REGULATORS = {
    "ON": {
        "name": "Ontario Ministry of Transportation",
        "carrier_id_system": "CVOR (Commercial Vehicle Operator's Registration)",
        "rating_bands": ["Excellent", "Satisfactory-Unaudited", "Satisfactory",
                         "Conditional", "Unsatisfactory"],
        "intervention_threshold_pct": 70,
    },
    "QC": {
        "name": "Société de l'assurance automobile du Québec (SAAQ)",
        "carrier_id_system": "PEVL (Politique d'évaluation des propriétaires "
                             "et exploitants de véhicules lourds)",
        "rating_bands": ["Satisfactory", "Conditional", "Unsatisfactory"],
        "intervention_threshold_pct": 65,
    },
    "BC": {
        "name": "BC Commercial Vehicle Safety and Enforcement (CVSE)",
        "carrier_id_system": "National Safety Code (NSC) Number",
        "rating_bands": ["Excellent", "Satisfactory", "Conditional", "Unsatisfactory"],
        "intervention_threshold_pct": 70,
    },
    "AB": {
        "name": "Alberta Transportation — Carrier Services",
        "carrier_id_system": "Safety Fitness Certificate (SFC)",
        "rating_bands": ["Excellent", "Satisfactory", "Conditional", "Unsatisfactory"],
        "intervention_threshold_pct": 70,
    },
}


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _sign(payload: dict) -> str:
    if not _HMAC_SECRET:
        return "unsigned-no-key-configured"
    return hmac.new(
        _HMAC_SECRET.encode(),
        json.dumps(payload, sort_keys=True, default=str).encode(),
        hashlib.sha256,
    ).hexdigest()


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _attestation(payload: dict) -> dict:
    return {**payload, "ts": _ts(), "sig": _sign(payload),
            "issuer": "meok-transport-canada-hos-mcp", "version": "1.0.0"}


# ──────────────────────────────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def check_canada_hos_south_60th(
    driver_name: str = "",
    daily_segments: Optional[list] = None,
    week_starting: str = "",
    cycle: str = "cycle_1",
) -> dict:
    """Audit a driver against SOR/2005-313 South-of-60°N rules.

    Args:
      daily_segments: list of dicts per day, like
        {"date": "2026-06-02", "driving_hr": 13.5, "on_duty_hr": 14.5,
         "cycle_window_hr": 17, "off_duty_hr": 9, "consecutive_off_duty_hr": 7}
      cycle: 'cycle_1' (70h/7d) or 'cycle_2' (120h/14d)

    Returns infringement list + severity total + 24-hour reset eligibility.
    """
    daily_segments = daily_segments or []
    infringements = []

    # Cycle cumulative limit (rolling)
    cycle_on_duty = sum(d.get("on_duty_hr", d.get("driving_hr", 0)) for d in daily_segments)
    if cycle == "cycle_1":
        cycle_limit = SOUTH_60_HOS_LIMITS["cycle_1_max_on_duty_hr_per_7_day"]
        cycle_code = "exceeded_70h_7_day_cycle1"
    else:
        cycle_limit = SOUTH_60_HOS_LIMITS["cycle_2_max_on_duty_hr_per_14_day"]
        cycle_code = "exceeded_120h_14_day_cycle2"

    if cycle_on_duty > cycle_limit:
        infringements.append({
            "code": cycle_code,
            "actual_hr": round(cycle_on_duty, 2),
            "limit_hr": cycle_limit,
            "severity": HOS_INFRINGEMENT_WEIGHTS_CA[cycle_code],
        })

    # Cycle 2 mandatory 24h off after 70h
    if cycle == "cycle_2" and cycle_on_duty >= 70:
        had_24h_reset = any(d.get("consecutive_off_duty_hr", 0) >= 24 for d in daily_segments)
        if not had_24h_reset:
            infringements.append({
                "code": "missed_24h_reset_cycle2",
                "rationale": "Cycle 2 requires 24h consecutive off-duty before reaching 70h on-duty",
                "severity": HOS_INFRINGEMENT_WEIGHTS_CA["missed_24h_reset_cycle2"],
            })

    for d in daily_segments:
        dr = d.get("driving_hr", 0)
        on_duty = d.get("on_duty_hr", dr)
        cycle_window = d.get("cycle_window_hr", on_duty)
        off_duty = d.get("off_duty_hr", 24)
        consec_off = d.get("consecutive_off_duty_hr", off_duty)

        # 13h daily driving limit
        if dr > SOUTH_60_HOS_LIMITS["max_daily_driving_hr"]:
            infringements.append({
                "code": "exceeded_13h_driving_south", "date": d.get("date"),
                "actual_hr": dr,
                "severity": HOS_INFRINGEMENT_WEIGHTS_CA["exceeded_13h_driving_south"],
            })

        # 14h daily on-duty limit
        if on_duty > SOUTH_60_HOS_LIMITS["max_daily_on_duty_hr"]:
            infringements.append({
                "code": "exceeded_14h_on_duty_south", "date": d.get("date"),
                "actual_hr": on_duty,
                "severity": HOS_INFRINGEMENT_WEIGHTS_CA["exceeded_14h_on_duty_south"],
            })

        # 16h elapsed cycle window
        if cycle_window > SOUTH_60_HOS_LIMITS["max_daily_cycle_window_hr"]:
            infringements.append({
                "code": "exceeded_16h_cycle_window_south", "date": d.get("date"),
                "actual_hr": cycle_window,
                "severity": HOS_INFRINGEMENT_WEIGHTS_CA["exceeded_16h_cycle_window_south"],
            })

        # 10h total off-duty per day
        if off_duty < SOUTH_60_HOS_LIMITS["min_daily_off_duty_hr"]:
            infringements.append({
                "code": "insufficient_10h_off_duty_south", "date": d.get("date"),
                "actual_hr": off_duty,
                "severity": HOS_INFRINGEMENT_WEIGHTS_CA["insufficient_10h_off_duty_south"],
            })

        # 8h consecutive off-duty (must be 8 of the 10)
        if consec_off < SOUTH_60_HOS_LIMITS["min_consecutive_off_duty_hr"]:
            infringements.append({
                "code": "insufficient_8h_consecutive_off_south", "date": d.get("date"),
                "actual_hr": consec_off,
                "severity": HOS_INFRINGEMENT_WEIGHTS_CA["insufficient_8h_consecutive_off_south"],
            })

    # 24-hour reset eligibility
    reset_eligible = any(
        d.get("consecutive_off_duty_hr", d.get("off_duty_hr", 0))
        >= SOUTH_60_HOS_LIMITS["mandatory_reset_consecutive_off_hr"]
        for d in daily_segments
    )

    payload = {
        "tool": "check_canada_hos_south_60th",
        "driver_name": driver_name,
        "week_starting": week_starting,
        "cycle": cycle,
        "cycle_on_duty_hr": round(cycle_on_duty, 2),
        "cycle_limit_hr": cycle_limit,
        "infringement_count": len(infringements),
        "infringements": infringements,
        "severity_total": sum(i.get("severity", 0) for i in infringements),
        "reset_24h_eligible": reset_eligible,
        "regulation": "SOR/2005-313 Part 1 (South of 60°N)",
    }
    return _attestation(payload)


@mcp.tool()
def check_canada_hos_north_60th(
    driver_name: str = "",
    daily_segments: Optional[list] = None,
    week_starting: str = "",
) -> dict:
    """Audit a driver against SOR/2005-313 North-of-60°N rules
    (Yukon, NWT, Nunavut, northern BC/AB/SK/MB/ON/QC/NL).

    Args:
      daily_segments: list of dicts per day, like
        {"date": "2026-06-02", "driving_hr": 15.5, "on_duty_hr": 19,
         "off_duty_hr": 7}

    Northern rules are MORE PERMISSIVE due to extreme distances + extreme isolation
    of Arctic / sub-Arctic operations:
      - 15h driving (vs 13h south)
      - 18h on-duty (vs 14h south)
      - 80h/7d cycle (vs 70h/7d south)
      - 8h off-duty (vs 10h south)
    """
    daily_segments = daily_segments or []
    infringements = []

    cycle_on_duty = sum(d.get("on_duty_hr", d.get("driving_hr", 0)) for d in daily_segments)
    cycle_limit = NORTH_60_HOS_LIMITS["cycle_1_max_on_duty_hr_per_7_day"]
    if cycle_on_duty > cycle_limit:
        infringements.append({
            "code": "exceeded_80h_7_day_north",
            "actual_hr": round(cycle_on_duty, 2),
            "limit_hr": cycle_limit,
            "severity": HOS_INFRINGEMENT_WEIGHTS_CA["exceeded_80h_7_day_north"],
        })

    for d in daily_segments:
        dr = d.get("driving_hr", 0)
        on_duty = d.get("on_duty_hr", dr)
        off_duty = d.get("off_duty_hr", 24)

        if dr > NORTH_60_HOS_LIMITS["max_daily_driving_hr"]:
            infringements.append({
                "code": "exceeded_15h_driving_north", "date": d.get("date"),
                "actual_hr": dr,
                "severity": HOS_INFRINGEMENT_WEIGHTS_CA["exceeded_15h_driving_north"],
            })

        if on_duty > NORTH_60_HOS_LIMITS["max_daily_on_duty_hr"]:
            infringements.append({
                "code": "exceeded_18h_on_duty_north", "date": d.get("date"),
                "actual_hr": on_duty,
                "severity": HOS_INFRINGEMENT_WEIGHTS_CA["exceeded_18h_on_duty_north"],
            })

        if off_duty < NORTH_60_HOS_LIMITS["min_daily_off_duty_hr"]:
            infringements.append({
                "code": "insufficient_8h_consecutive_off_south",  # reuse code (same severity)
                "date": d.get("date"),
                "actual_hr": off_duty,
                "severity": HOS_INFRINGEMENT_WEIGHTS_CA["insufficient_8h_consecutive_off_south"],
                "note": "North-of-60 requires 8h off-duty per day",
            })

    payload = {
        "tool": "check_canada_hos_north_60th",
        "driver_name": driver_name,
        "week_starting": week_starting,
        "cycle_on_duty_hr": round(cycle_on_duty, 2),
        "cycle_limit_hr": cycle_limit,
        "infringement_count": len(infringements),
        "infringements": infringements,
        "severity_total": sum(i.get("severity", 0) for i in infringements),
        "regulation": "SOR/2005-313 Part 2 (North of 60°N — Yukon, NWT, Nunavut + northern provinces)",
        "note": "Northern rules permit longer driving / on-duty windows due to Arctic operational realities.",
    }
    return _attestation(payload)


@mcp.tool()
def check_eld_canada_mandate(
    vrn_or_vin: str = "",
    extra_provincial_operation: bool = True,
    engine_model_year: int = 2020,
    is_rental_under_30_days: bool = False,
    is_statutory_exempt: bool = False,
    eld_installed: bool = False,
    eld_make: str = "",
    eld_model: str = "",
    third_party_certified: bool = False,
    certification_body: str = "",
) -> dict:
    """Determine if a CMV requires an ELD under Transport Canada T-T-019
    (effective 1 Jan 2023 — fully enforced 1 Jan 2023, no grandfathering).

    Canada is STRICTER than the US ELD mandate in one way: only THIRD-PARTY
    CERTIFIED ELDs are accepted (self-certification, which the US allows,
    is NOT permitted in Canada).

    A vehicle requires an ELD if:
      - operating in extra-provincial trucking (interprovincial / international)
      - is a CMV regulated under SOR/2005-313

    Exemptions:
      - Engine model year pre-2000
      - Rental vehicle <30 day rental term
      - Statutory exempt driver per SOR/2005-313 s.81 (short-radius, etc.)
    """
    triggers = []
    if extra_provincial_operation:
        triggers.append("Extra-provincial CMV under SOR/2005-313")

    exemptions = []
    if engine_model_year < 2000:
        exemptions.append(f"engine model year {engine_model_year} < 2000 (pre-2000 exempt)")
    if is_rental_under_30_days:
        exemptions.append("rental vehicle under 30-day term (T-T-019 exempt)")
    if is_statutory_exempt:
        exemptions.append("statutory exempt driver per SOR/2005-313 s.81")

    eld_required = bool(triggers) and not exemptions

    # Certification status — Canada-specific: must be third-party certified
    cert_status = "NOT_REQUIRED"
    cert_advisory = ""
    if eld_required:
        if not eld_installed:
            cert_status = "MISSING"
            cert_advisory = (
                "ELD REQUIRED but NOT installed. This is a Transport Canada T-T-019 "
                "violation and an NSC Standard 9 carrier-score event. Fit a third-party "
                "certified ELD immediately. Self-certified US ELDs are NOT valid in Canada."
            )
        elif not third_party_certified:
            cert_status = "INSTALLED_BUT_NON_CERTIFIED"
            cert_advisory = (
                "ELD installed but NOT third-party certified under T-T-019. "
                "Canada does NOT accept self-certified devices. Verify certification "
                "via FPInnovations or other Transport Canada-accredited certification body."
            )
        else:
            cert_status = "CERTIFIED_OK"
            cert_advisory = (
                f"Third-party certified ELD ({eld_make} {eld_model}) by "
                f"{certification_body or 'an accredited body'} — T-T-019 compliant."
            )

    compliance_status = "COMPLIANT"
    if eld_required and cert_status in ("MISSING", "INSTALLED_BUT_NON_CERTIFIED"):
        compliance_status = "NON_COMPLIANT"
    elif eld_required and cert_status == "CERTIFIED_OK":
        compliance_status = "COMPLIANT_ELD_CERTIFIED"

    return _attestation({
        "tool": "check_eld_canada_mandate",
        "vrn_or_vin": vrn_or_vin,
        "extra_provincial_operation": extra_provincial_operation,
        "engine_model_year": engine_model_year,
        "eld_required": eld_required,
        "eld_installed": eld_installed,
        "third_party_certified": third_party_certified,
        "certification_body": certification_body,
        "certification_status": cert_status,
        "certification_advisory": cert_advisory,
        "triggers": triggers,
        "exemptions": exemptions,
        "compliance_status": compliance_status,
        "regulation": "Transport Canada T-T-019 ELD Technical Standard (effective 1 Jan 2023)",
        "note_vs_us": (
            "Canada requires THIRD-PARTY certification; US accepts self-certification. "
            "A US-only self-certified ELD is NOT valid for Canadian extra-provincial operation."
        ),
    })


@mcp.tool()
def check_cycle_switch(
    driver_name: str = "",
    from_cycle: str = "cycle_1",
    to_cycle: str = "cycle_2",
    switch_date: str = "",
    consecutive_off_duty_hr_before_switch: float = 0,
    carrier_notified: bool = False,
    recorded_in_log: bool = False,
) -> dict:
    """Verify a Cycle 1 ↔ Cycle 2 switch is legal under SOR/2005-313 s.32.

    To switch cycles a driver must:
      - take 36 consecutive hours off-duty BEFORE the switch
      - notify the carrier of the switch
      - record the switch in the daily log

    Args:
      from_cycle: 'cycle_1' or 'cycle_2'
      to_cycle: 'cycle_1' or 'cycle_2'
      consecutive_off_duty_hr_before_switch: how many consecutive hours off the
        driver took immediately before the switch
    """
    infringements = []

    if from_cycle == to_cycle:
        return _attestation({
            "tool": "check_cycle_switch",
            "driver_name": driver_name,
            "switch_valid": False,
            "rationale": "from_cycle and to_cycle are identical — no switch occurred",
            "infringements": [],
            "regulation": "SOR/2005-313 s.32",
        })

    if consecutive_off_duty_hr_before_switch < CYCLE_SWITCH_RULES["min_consecutive_off_duty_hr_to_switch"]:
        infringements.append({
            "code": "cycle_switch_insufficient_36h_off",
            "actual_hr": consecutive_off_duty_hr_before_switch,
            "required_hr": CYCLE_SWITCH_RULES["min_consecutive_off_duty_hr_to_switch"],
            "severity": HOS_INFRINGEMENT_WEIGHTS_CA["cycle_switch_insufficient_36h_off"],
        })

    if not carrier_notified:
        infringements.append({
            "code": "cycle_switch_not_notified",
            "rationale": "Driver must notify the carrier of a cycle switch",
            "severity": HOS_INFRINGEMENT_WEIGHTS_CA["cycle_switch_not_notified"],
        })

    if not recorded_in_log:
        infringements.append({
            "code": "cycle_switch_not_notified",
            "rationale": "Cycle switch must be recorded in the driver's daily log",
            "severity": HOS_INFRINGEMENT_WEIGHTS_CA["cycle_switch_not_notified"],
        })

    switch_valid = len(infringements) == 0

    return _attestation({
        "tool": "check_cycle_switch",
        "driver_name": driver_name,
        "from_cycle": from_cycle,
        "to_cycle": to_cycle,
        "switch_date": switch_date,
        "consecutive_off_duty_hr_before_switch": consecutive_off_duty_hr_before_switch,
        "carrier_notified": carrier_notified,
        "recorded_in_log": recorded_in_log,
        "switch_valid": switch_valid,
        "infringement_count": len(infringements),
        "infringements": infringements,
        "severity_total": sum(i.get("severity", 0) for i in infringements),
        "regulation": "SOR/2005-313 s.32 — cycle reset requires 36h consecutive off-duty + notification",
    })


@mcp.tool()
def check_nsc_carrier_safety(
    operator_name: str = "",
    nsc_number: str = "",
    province: str = "ON",
    cvor_or_pevl_score_pct: float = 0,
    hos_violations_12mo: int = 0,
    vehicle_oos_rate_pct: float = 0,
    driver_oos_rate_pct: float = 0,
    collision_count_12mo: int = 0,
) -> dict:
    """Compute / classify an NSC Standard 14 carrier safety rating.

    Args:
      province: 'ON' / 'QC' / 'BC' / 'AB' (others fall back to ON-style bands)
      cvor_or_pevl_score_pct: provincial carrier score (0-100)
      vehicle_oos_rate_pct: vehicle out-of-service rate at roadside inspections
      driver_oos_rate_pct: driver out-of-service rate
      collision_count_12mo: at-fault collisions in trailing 12 months
    """
    regulator = PROVINCIAL_REGULATORS.get(province.upper(),
                                          PROVINCIAL_REGULATORS["ON"])
    threshold = regulator["intervention_threshold_pct"]

    # Map score → NSC Standard 14 band (CCMTA national standard)
    if cvor_or_pevl_score_pct < 15:
        rating = "EXCELLENT"
    elif cvor_or_pevl_score_pct < 35:
        rating = "SATISFACTORY"
    elif cvor_or_pevl_score_pct < 70:
        rating = "CONDITIONAL"
    else:
        rating = "UNSATISFACTORY"

    # Risk factors
    risk_factors = []
    if vehicle_oos_rate_pct > 20:
        risk_factors.append(f"Vehicle OOS rate {vehicle_oos_rate_pct}% > 20% national average")
    if driver_oos_rate_pct > 5:
        risk_factors.append(f"Driver OOS rate {driver_oos_rate_pct}% > 5% national average")
    if hos_violations_12mo >= 5:
        risk_factors.append(f"{hos_violations_12mo} HoS violations in 12mo — NSC Standard 9 risk")
    if collision_count_12mo >= 3:
        risk_factors.append(f"{collision_count_12mo} at-fault collisions in 12mo — collision-prone")

    intervention_risk = "LOW"
    intervention_advisory = "Routine NSC oversight."
    if rating == "UNSATISFACTORY":
        intervention_risk = "CRITICAL"
        intervention_advisory = (
            f"{regulator['name']} likely to issue PRIVILEGE SUSPENSION. "
            "Open a facility audit response now + file corrective action plan."
        )
    elif rating == "CONDITIONAL" or cvor_or_pevl_score_pct >= threshold:
        intervention_risk = "HIGH"
        intervention_advisory = (
            f"{regulator['name']} likely to trigger facility audit. "
            "Get root-cause + corrective action plan filed within 30 days."
        )
    elif risk_factors:
        intervention_risk = "MEDIUM"
        intervention_advisory = (
            "Several risk factors elevated — expect increased roadside inspections."
        )

    return _attestation({
        "tool": "check_nsc_carrier_safety",
        "operator_name": operator_name,
        "nsc_number": nsc_number,
        "province": province.upper(),
        "regulator": regulator["name"],
        "carrier_id_system": regulator["carrier_id_system"],
        "carrier_score_pct": cvor_or_pevl_score_pct,
        "rating": rating,
        "rating_meaning": NSC_SAFETY_RATING_BANDS[rating],
        "intervention_threshold_pct": threshold,
        "above_intervention_threshold": cvor_or_pevl_score_pct >= threshold,
        "risk_factors": risk_factors,
        "intervention_risk": intervention_risk,
        "intervention_advisory": intervention_advisory,
        "hos_violations_12mo": hos_violations_12mo,
        "vehicle_oos_rate_pct": vehicle_oos_rate_pct,
        "driver_oos_rate_pct": driver_oos_rate_pct,
        "collision_count_12mo": collision_count_12mo,
        "regulation": "NSC Standard 9 (HoS) + Standard 14 (Carrier Safety Rating); "
                      "provincial enforcement varies by jurisdiction.",
    })


@mcp.tool()
def audit_cross_border_us_canada(
    driver_name: str = "",
    direction: str = "CA_to_US",
    home_terminal_country: str = "CA",
    operating_in_country: str = "US",
    vehicle_eld_certified_canada: bool = False,
    vehicle_eld_registered_us: bool = False,
    driver_cdl_or_class1_status: str = "valid",
    drug_alcohol_clearinghouse_query_done: bool = False,
) -> dict:
    """Resolve which HoS regime applies + which compliance gates a driver must
    clear when crossing the CA↔US border.

    Key rule: a driver must follow the rules of the jurisdiction they are
    OPERATING in, not where they are domiciled. A Canadian-domiciled driver
    running US miles is subject to FMCSA 49 CFR Part 395; a US-domiciled
    driver running Canadian miles is subject to SOR/2005-313.

    Args:
      direction: 'CA_to_US' or 'US_to_CA' or 'round_trip'
      home_terminal_country: 'CA' or 'US'
      operating_in_country: 'CA' or 'US' (the jurisdiction whose rules apply
        for the leg being audited)
    """
    operating = operating_in_country.upper()
    home = home_terminal_country.upper()

    if operating == "CA":
        applicable_regime = "SOR/2005-313 (Canada HoS) + Transport Canada T-T-019 ELD"
        regime_rules = {
            "max_daily_driving_hr": SOUTH_60_HOS_LIMITS["max_daily_driving_hr"],
            "max_daily_on_duty_hr": SOUTH_60_HOS_LIMITS["max_daily_on_duty_hr"],
            "cycle_1_70h_7d": True,
            "cycle_2_120h_14d": True,
            "eld_third_party_certified_required": True,
        }
    else:  # US
        applicable_regime = "49 CFR Part 395 (FMCSA HoS) + 49 CFR 395.8 ELD mandate"
        regime_rules = {
            "max_daily_driving_hr_property": 11,
            "max_on_duty_window_hr_property": 14,
            "max_weekly_60_7_day_or_70_8_day": True,
            "mandatory_30min_break_after_8h": True,
            "eld_fmcsa_registered_required": True,
        }

    gates = []
    blockers = []

    if operating == "CA" and not vehicle_eld_certified_canada:
        blockers.append(
            "Vehicle ELD NOT third-party certified under T-T-019 — cannot legally "
            "operate in Canada. Self-certified US ELDs are not accepted in Canada."
        )

    if operating == "US" and not vehicle_eld_registered_us:
        blockers.append(
            "Vehicle ELD NOT on FMCSA registered list — risk of out-of-service "
            "at US roadside inspection under 49 CFR 395.22."
        )

    if direction in ("CA_to_US", "round_trip") and operating == "US":
        gates.append("CBSA pre-arrival cargo manifest (eManifest / ACE)")
        gates.append("US DOT number + MC number (interstate authority)")
        gates.append("FMCSA Drug & Alcohol Clearinghouse query (pre-employment + annual limited)")
        if not drug_alcohol_clearinghouse_query_done:
            blockers.append(
                "FMCSA Drug & Alcohol Clearinghouse query NOT on file — "
                "driver cannot legally drive interstate in the US."
            )

    if direction in ("US_to_CA", "round_trip") and operating == "CA":
        gates.append("CBSA eManifest / ACI cargo report (pre-arrival)")
        gates.append("Transport Canada NSC carrier registration")
        gates.append("Provincial commercial vehicle operating authority "
                     "(CVOR-ON / PEVL-QC / NSC-Number-BC / SFC-AB)")

    if driver_cdl_or_class1_status != "valid":
        blockers.append(
            f"Driver licence status '{driver_cdl_or_class1_status}' — must be "
            "valid CDL (US) or Class 1 / equivalent (Canada) for the leg."
        )

    return _attestation({
        "tool": "audit_cross_border_us_canada",
        "driver_name": driver_name,
        "direction": direction,
        "home_terminal_country": home,
        "operating_in_country": operating,
        "applicable_regime": applicable_regime,
        "regime_rules": regime_rules,
        "gates_required": gates,
        "blockers": blockers,
        "ok_to_cross": len(blockers) == 0,
        "advisory": (
            "READY TO CROSS — all gates documented." if len(blockers) == 0 else
            f"BLOCKED — {len(blockers)} blocker(s) must be resolved before this leg."
        ),
        "regulation": "SOR/2005-313 (CA) · 49 CFR Part 395 (US) · CBSA / CBP harmonisation",
        "key_principle": (
            "Driver follows rules of the jurisdiction OPERATING in, not home-terminal."
            " Home-terminal status only matters for record-of-duty retention."
        ),
    })


@mcp.tool()
def prepare_carrier_audit_pack(
    operator_name: str = "",
    nsc_number: str = "",
    province: str = "ON",
    fleet_size: int = 0,
    expected_audit_date: str = "",
    last_audit_outcome: str = "",
) -> dict:
    """Produce the Provincial Ministry of Transport carrier audit evidence pack.

    Each province has its own evidence intake but all are anchored on NSC
    Standards 9, 11, 14. This tool produces the union checklist + flags
    province-specific add-ons:
      - ON MTO: CVOR Abstract + safety plan
      - QC SAAQ: PEVL dossier + bilingual French/English driver records
      - BC CVSE: NSC Carrier Profile + WorkSafeBC alignment
      - AB Transportation: Safety Fitness Certificate (SFC) renewal
    """
    province_u = province.upper()
    regulator = PROVINCIAL_REGULATORS.get(province_u, PROVINCIAL_REGULATORS["ON"])

    province_addons = {
        "ON": [
            "CVOR Abstract (Ontario carrier-level dump from MTO)",
            "Written Safety Plan (mandatory >25 power units in ON)",
            "Driver pool — CVOR-eligible Driver Abstracts (last 3 yrs)",
        ],
        "QC": [
            "PEVL dossier (SAAQ-issued operator file)",
            "Driver records BILINGUAL — French + English",
            "Trip inspection reports in French where applicable",
            "Mécanicien certification for in-house maintenance",
        ],
        "BC": [
            "NSC Carrier Profile (BC CVSE-issued)",
            "WorkSafeBC employer registration + clearance letter",
            "Pre-Trip Inspection (PTI) records per Motor Vehicle Act Regulation",
        ],
        "AB": [
            "Safety Fitness Certificate (SFC) — current",
            "Alberta Carrier Profile Report (CPR) from Carrier Services",
            "Insurance certificate naming Alberta Transportation as additional insured",
        ],
    }

    core_checklist = [
        "NSC carrier registration (NSC Number) + provincial operator registration",
        "Carrier Safety Plan (written) — NSC Standard 14",
        "Hours of Service records (ELD logs) per SOR/2005-313 — last 6 months",
        "Daily Inspection Reports (DIR) — NSC Standard 13 — 3-6 months back",
        "Vehicle maintenance + Periodic Mandatory Inspection (PMI) records "
        "— NSC Standard 11 — last 24 months",
        "Driver Qualification files — abstract, road test, medical (Class 1 / CDL)",
        "Driver training records — defensive driving, hazmat (if applicable)",
        "Drug & Alcohol policy + records (if cross-border US)",
        "Insurance — minimum CAD $2M general carriers (varies by cargo class)",
        "Hazmat Transportation of Dangerous Goods (TDG) registration + driver training",
        "Accident / collision register — 3 years back",
        "ELD device list with Transport Canada certification IDs (T-T-019)",
        "Cross-border manifests + eManifest/ACI records (if applicable)",
        "Cargo securement procedures per NSC Standard 10",
    ]

    automatic_fail_items = [
        "Operating commercial vehicle without valid NSC number",
        "Driver without valid Class 1 / CDL operating regulated CMV",
        "Operating vehicle declared OOS without repair documentation",
        "No ELD where T-T-019 requires one (extra-provincial CMV)",
        "Self-certified (non-third-party-certified) ELD installed",
        "Falsified or knowingly altered Hours of Service records",
        "No periodic mechanical inspection (PMI) program — NSC Standard 11 failure",
        "No insurance certificate or insurance below provincial minimum",
    ]

    pack = {
        "tool": "prepare_carrier_audit_pack",
        "operator_name": operator_name,
        "nsc_number": nsc_number,
        "province": province_u,
        "regulator": regulator["name"],
        "carrier_id_system": regulator["carrier_id_system"],
        "fleet_size": fleet_size,
        "expected_audit_date": expected_audit_date,
        "last_audit_outcome": last_audit_outcome,
        "core_evidence_checklist": core_checklist,
        "province_specific_addons": province_addons.get(province_u,
                                                       province_addons["ON"]),
        "automatic_failure_items": automatic_fail_items,
        "rating_bands_in_use": regulator["rating_bands"],
        "regulation": "NSC Standards 9, 10, 11, 13, 14 + SOR/2005-313 + Transport "
                      "Canada T-T-019; provincial enforcement per regulator above.",
        "next_action": (
            f"Build the {province_u} {regulator['carrier_id_system']} dossier matching the "
            "core + province-specific checklist. Pre-audit gap analysis recommended."
        ),
    }
    return _attestation(pack)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()


# ── MEOK monetization layer (Stripe upgrade · PAYG · pricing) ──────────
# Free tier is zero-config. Upgrade to Pro (unlimited) or pay-as-you-go per call.
import os as _meok_os
MEOK_STRIPE_UPGRADE = "https://buy.stripe.com/00wfZjcgAeUW4c5cyQ8k90K"  # Pro (unlimited)
MEOK_PAYG_KEY = _meok_os.environ.get("MEOK_PAYG_KEY", "")  # set to enable PAYG (x402 / ~GBP0.05 per call)
MEOK_PRICING = "https://meok.ai/pricing"


def meok_upsell(tier: str = "free") -> dict:
    """Monetization options for free-tier callers: Pro upgrade, PAYG, or pricing page."""
    if tier != "free":
        return {}
    return {"upgrade_url": MEOK_STRIPE_UPGRADE,
            "payg_enabled": bool(MEOK_PAYG_KEY),
            "pricing": MEOK_PRICING}
