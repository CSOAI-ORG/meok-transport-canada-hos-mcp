import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import (
    check_canada_hos_south_60th, check_canada_hos_north_60th,
    check_eld_canada_mandate, check_cycle_switch,
    check_nsc_carrier_safety, audit_cross_border_us_canada,
    prepare_carrier_audit_pack,
    SOUTH_60_HOS_LIMITS, NORTH_60_HOS_LIMITS,
    HOS_INFRINGEMENT_WEIGHTS_CA, PROVINCIAL_REGULATORS,
    NSC_SAFETY_RATING_BANDS,
)


def _call(t, **kw):
    fn = t.fn if hasattr(t, "fn") else t
    return fn(**kw)


# ──────────────────────────────────────────────────────────────────────
# check_canada_hos_south_60th — SOR/2005-313 Part 1
# ──────────────────────────────────────────────────────────────────────

def test_south_60_13h_driving_breach():
    r = _call(check_canada_hos_south_60th, driver_name="J",
              daily_segments=[{"date": "2026-06-02", "driving_hr": 13.5,
                               "on_duty_hr": 14, "cycle_window_hr": 15,
                               "off_duty_hr": 10, "consecutive_off_duty_hr": 9}])
    codes = [i["code"] for i in r["infringements"]]
    assert "exceeded_13h_driving_south" in codes


def test_south_60_14h_on_duty_breach():
    r = _call(check_canada_hos_south_60th, driver_name="J",
              daily_segments=[{"date": "2026-06-02", "driving_hr": 12,
                               "on_duty_hr": 15, "cycle_window_hr": 15,
                               "off_duty_hr": 10, "consecutive_off_duty_hr": 9}])
    assert any(i["code"] == "exceeded_14h_on_duty_south" for i in r["infringements"])


def test_south_60_16h_cycle_window_breach():
    r = _call(check_canada_hos_south_60th, driver_name="J",
              daily_segments=[{"date": "2026-06-02", "driving_hr": 12,
                               "on_duty_hr": 13, "cycle_window_hr": 17,
                               "off_duty_hr": 10, "consecutive_off_duty_hr": 9}])
    assert any(i["code"] == "exceeded_16h_cycle_window_south" for i in r["infringements"])


def test_south_60_70h_cycle1_breach():
    days = [{"date": f"2026-06-0{d+1}", "driving_hr": 11, "on_duty_hr": 11,
             "cycle_window_hr": 13, "off_duty_hr": 11,
             "consecutive_off_duty_hr": 10} for d in range(7)]
    r = _call(check_canada_hos_south_60th, driver_name="K",
              daily_segments=days, cycle="cycle_1")
    assert any(i["code"] == "exceeded_70h_7_day_cycle1" for i in r["infringements"])


def test_south_60_clean_week_no_infringements():
    r = _call(check_canada_hos_south_60th, driver_name="C",
              daily_segments=[{"date": "2026-06-02", "driving_hr": 10,
                               "on_duty_hr": 12, "cycle_window_hr": 13,
                               "off_duty_hr": 11, "consecutive_off_duty_hr": 10}])
    assert r["infringement_count"] == 0


def test_south_60_24h_reset_eligible():
    r = _call(check_canada_hos_south_60th, driver_name="R",
              daily_segments=[{"date": "2026-06-02", "driving_hr": 8,
                               "on_duty_hr": 12, "cycle_window_hr": 13,
                               "off_duty_hr": 24, "consecutive_off_duty_hr": 24}])
    assert r["reset_24h_eligible"] is True


def test_south_60_insufficient_8h_consec_off():
    r = _call(check_canada_hos_south_60th, driver_name="J",
              daily_segments=[{"date": "2026-06-02", "driving_hr": 10,
                               "on_duty_hr": 12, "cycle_window_hr": 13,
                               "off_duty_hr": 10, "consecutive_off_duty_hr": 6}])
    assert any(i["code"] == "insufficient_8h_consecutive_off_south"
               for i in r["infringements"])


# ──────────────────────────────────────────────────────────────────────
# check_canada_hos_north_60th — SOR/2005-313 Part 2
# ──────────────────────────────────────────────────────────────────────

def test_north_60_15h_driving_breach():
    r = _call(check_canada_hos_north_60th, driver_name="A",
              daily_segments=[{"date": "2026-06-02", "driving_hr": 15.5,
                               "on_duty_hr": 17, "off_duty_hr": 8}])
    assert any(i["code"] == "exceeded_15h_driving_north" for i in r["infringements"])


def test_north_60_18h_on_duty_breach():
    r = _call(check_canada_hos_north_60th, driver_name="A",
              daily_segments=[{"date": "2026-06-02", "driving_hr": 14,
                               "on_duty_hr": 19, "off_duty_hr": 8}])
    assert any(i["code"] == "exceeded_18h_on_duty_north" for i in r["infringements"])


def test_north_60_80h_cycle_breach():
    days = [{"date": f"2026-06-0{d+1}", "driving_hr": 12, "on_duty_hr": 12,
             "off_duty_hr": 10} for d in range(7)]
    r = _call(check_canada_hos_north_60th, driver_name="N",
              daily_segments=days)
    # 12*7 = 84 > 80
    assert any(i["code"] == "exceeded_80h_7_day_north" for i in r["infringements"])


def test_north_60_clean_no_infringements():
    r = _call(check_canada_hos_north_60th, driver_name="N",
              daily_segments=[{"date": "2026-06-02", "driving_hr": 14,
                               "on_duty_hr": 16, "off_duty_hr": 9}])
    assert r["infringement_count"] == 0


# ──────────────────────────────────────────────────────────────────────
# check_eld_canada_mandate — T-T-019
# ──────────────────────────────────────────────────────────────────────

def test_eld_required_extra_provincial_no_eld():
    r = _call(check_eld_canada_mandate, vrn_or_vin="ON-TRUCK1",
              extra_provincial_operation=True,
              engine_model_year=2020, eld_installed=False)
    assert r["eld_required"] is True
    assert r["certification_status"] == "MISSING"
    assert r["compliance_status"] == "NON_COMPLIANT"


def test_eld_self_certified_us_device_not_valid_in_canada():
    # The killer Canada rule — self-certified US ELDs aren't valid here
    r = _call(check_eld_canada_mandate, vrn_or_vin="QC-TRUCK1",
              extra_provincial_operation=True,
              engine_model_year=2021, eld_installed=True,
              eld_make="GenericUSCo", eld_model="X1",
              third_party_certified=False)
    assert r["certification_status"] == "INSTALLED_BUT_NON_CERTIFIED"
    assert r["compliance_status"] == "NON_COMPLIANT"
    assert "self-certified" in r["certification_advisory"].lower()


def test_eld_third_party_certified_ok():
    r = _call(check_eld_canada_mandate, vrn_or_vin="BC-TRUCK1",
              extra_provincial_operation=True,
              engine_model_year=2022, eld_installed=True,
              eld_make="Geotab", eld_model="Drive",
              third_party_certified=True,
              certification_body="FPInnovations")
    assert r["compliance_status"] == "COMPLIANT_ELD_CERTIFIED"
    assert r["certification_status"] == "CERTIFIED_OK"


def test_eld_pre_2000_engine_exempt():
    r = _call(check_eld_canada_mandate, vrn_or_vin="AB-OLD1",
              extra_provincial_operation=True,
              engine_model_year=1998, eld_installed=False)
    assert r["eld_required"] is False
    assert any("pre-2000" in e for e in r["exemptions"])


# ──────────────────────────────────────────────────────────────────────
# check_cycle_switch — SOR/2005-313 s.32
# ──────────────────────────────────────────────────────────────────────

def test_cycle_switch_valid_36h_off_notified_logged():
    r = _call(check_cycle_switch, driver_name="J",
              from_cycle="cycle_1", to_cycle="cycle_2",
              switch_date="2026-06-05",
              consecutive_off_duty_hr_before_switch=40,
              carrier_notified=True, recorded_in_log=True)
    assert r["switch_valid"] is True
    assert r["infringement_count"] == 0


def test_cycle_switch_invalid_only_24h_off():
    r = _call(check_cycle_switch, driver_name="J",
              from_cycle="cycle_1", to_cycle="cycle_2",
              consecutive_off_duty_hr_before_switch=24,
              carrier_notified=True, recorded_in_log=True)
    assert r["switch_valid"] is False
    assert any(i["code"] == "cycle_switch_insufficient_36h_off"
               for i in r["infringements"])


def test_cycle_switch_not_notified():
    r = _call(check_cycle_switch, driver_name="J",
              from_cycle="cycle_2", to_cycle="cycle_1",
              consecutive_off_duty_hr_before_switch=40,
              carrier_notified=False, recorded_in_log=True)
    assert r["switch_valid"] is False
    assert any(i["code"] == "cycle_switch_not_notified"
               for i in r["infringements"])


def test_cycle_switch_same_cycle_no_switch():
    r = _call(check_cycle_switch, driver_name="J",
              from_cycle="cycle_1", to_cycle="cycle_1",
              consecutive_off_duty_hr_before_switch=40,
              carrier_notified=True, recorded_in_log=True)
    assert r["switch_valid"] is False
    assert "identical" in r["rationale"]


# ──────────────────────────────────────────────────────────────────────
# check_nsc_carrier_safety — NSC Standard 14
# ──────────────────────────────────────────────────────────────────────

def test_nsc_excellent_rating_low_score():
    r = _call(check_nsc_carrier_safety, operator_name="GOOD",
              nsc_number="NSC-001", province="ON",
              cvor_or_pevl_score_pct=10)
    assert r["rating"] == "EXCELLENT"
    assert r["intervention_risk"] == "LOW"


def test_nsc_unsatisfactory_high_score_quebec():
    r = _call(check_nsc_carrier_safety, operator_name="BAD",
              nsc_number="NSC-002", province="QC",
              cvor_or_pevl_score_pct=85)
    assert r["rating"] == "UNSATISFACTORY"
    assert r["intervention_risk"] == "CRITICAL"
    assert "SAAQ" in r["regulator"]


def test_nsc_conditional_with_risk_factors():
    r = _call(check_nsc_carrier_safety, operator_name="MEH",
              nsc_number="NSC-003", province="BC",
              cvor_or_pevl_score_pct=50,
              vehicle_oos_rate_pct=25, hos_violations_12mo=6)
    assert r["rating"] == "CONDITIONAL"
    assert len(r["risk_factors"]) >= 2
    assert r["intervention_risk"] == "HIGH"


def test_nsc_alberta_jurisdiction():
    r = _call(check_nsc_carrier_safety, operator_name="AB",
              nsc_number="NSC-004", province="AB",
              cvor_or_pevl_score_pct=20)
    assert "Alberta" in r["regulator"]
    assert "SFC" in r["carrier_id_system"]


# ──────────────────────────────────────────────────────────────────────
# audit_cross_border_us_canada
# ──────────────────────────────────────────────────────────────────────

def test_cross_border_ca_to_us_fmcsa_regime_applies():
    r = _call(audit_cross_border_us_canada, driver_name="J",
              direction="CA_to_US", home_terminal_country="CA",
              operating_in_country="US",
              vehicle_eld_registered_us=True,
              drug_alcohol_clearinghouse_query_done=True)
    assert "FMCSA" in r["applicable_regime"]
    assert "11" in str(r["regime_rules"]["max_daily_driving_hr_property"])
    assert r["ok_to_cross"] is True


def test_cross_border_us_to_ca_t_t_019_blocker():
    # US driver with self-certified ELD entering Canada — blocked
    r = _call(audit_cross_border_us_canada, driver_name="J",
              direction="US_to_CA", home_terminal_country="US",
              operating_in_country="CA",
              vehicle_eld_certified_canada=False)
    assert "SOR/2005-313" in r["applicable_regime"]
    assert r["ok_to_cross"] is False
    assert any("third-party certified" in b.lower() for b in r["blockers"])


def test_cross_border_clearinghouse_blocker():
    r = _call(audit_cross_border_us_canada, driver_name="J",
              direction="CA_to_US", home_terminal_country="CA",
              operating_in_country="US",
              vehicle_eld_registered_us=True,
              drug_alcohol_clearinghouse_query_done=False)
    assert r["ok_to_cross"] is False
    assert any("clearinghouse" in b.lower() for b in r["blockers"])


# ──────────────────────────────────────────────────────────────────────
# prepare_carrier_audit_pack — Provincial MoT
# ──────────────────────────────────────────────────────────────────────

def test_audit_pack_ontario_cvor():
    r = _call(prepare_carrier_audit_pack, operator_name="ACME",
              nsc_number="NSC-ON-1", province="ON",
              fleet_size=30, expected_audit_date="2026-09-01")
    assert "MTO" in r["regulator"] or "Ontario" in r["regulator"]
    assert "CVOR" in r["carrier_id_system"]
    assert any("CVOR Abstract" in addon for addon in r["province_specific_addons"])
    assert len(r["core_evidence_checklist"]) >= 10


def test_audit_pack_quebec_bilingual():
    r = _call(prepare_carrier_audit_pack, operator_name="MTL",
              nsc_number="NSC-QC-1", province="QC",
              fleet_size=15)
    assert "SAAQ" in r["regulator"]
    assert "PEVL" in r["carrier_id_system"]
    assert any("BILINGUAL" in addon or "French" in addon
               for addon in r["province_specific_addons"])


def test_audit_pack_bc_worksafebc():
    r = _call(prepare_carrier_audit_pack, operator_name="BCCO",
              nsc_number="NSC-BC-1", province="BC",
              fleet_size=8)
    assert "BC" in r["regulator"] or "CVSE" in r["regulator"]
    assert any("WorkSafeBC" in addon for addon in r["province_specific_addons"])


def test_audit_pack_alberta_sfc():
    r = _call(prepare_carrier_audit_pack, operator_name="ABCO",
              nsc_number="NSC-AB-1", province="AB",
              fleet_size=22)
    assert "Alberta" in r["regulator"]
    assert any("Safety Fitness Certificate" in addon
               for addon in r["province_specific_addons"])


def test_audit_pack_automatic_failures_listed():
    r = _call(prepare_carrier_audit_pack, operator_name="X",
              nsc_number="NSC-X", province="ON")
    assert any("ELD" in f for f in r["automatic_failure_items"])
    assert any("self-certified" in f.lower() or "non-third-party" in f.lower()
               for f in r["automatic_failure_items"])


# ──────────────────────────────────────────────────────────────────────
# HMAC attestation chain
# ──────────────────────────────────────────────────────────────────────

def test_attestation_chain_present():
    r = _call(check_canada_hos_south_60th, driver_name="X",
              daily_segments=[{"date": "2026-06-02", "driving_hr": 10,
                               "on_duty_hr": 12, "cycle_window_hr": 13,
                               "off_duty_hr": 11, "consecutive_off_duty_hr": 10}])
    assert "sig" in r and "ts" in r
    assert r["issuer"] == "meok-transport-canada-hos-mcp"
    assert r["version"] == "1.0.0"


def test_attestation_signed_with_secret():
    os.environ["MEOK_HMAC_SECRET"] = "ca-test-secret"
    import importlib, server
    importlib.reload(server)
    r = _call(server.check_nsc_carrier_safety,
              operator_name="X", nsc_number="NSC-X",
              province="ON", cvor_or_pevl_score_pct=20)
    assert r["sig"] != "unsigned-no-key-configured"
    assert len(r["sig"]) == 64  # sha256 hex
    del os.environ["MEOK_HMAC_SECRET"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
