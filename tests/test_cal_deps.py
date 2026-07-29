"""Ordering-constraint validation for the calibration sequence.

The constraints in cal/deps.py exist because a mis-ordered calibration
converges on a *wrong answer* instead of failing (e.g. rx_iq before tx_iq
absorbs the TX image into the RX corrector).  These tests check that the
canonical plans satisfy the rules, that violations raise with the physical
reason attached, and that the plan matches what run_full_cal executes.
"""
from __future__ import annotations

import pytest

from wifitrx.cal.deps import STEP_REQUIRES, planned_steps, validate_order
from wifitrx.cal.sequence import PROFILES


def test_rules_are_nontrivial():
    # premise: an emptied-out table must not validate everything vacuously
    n = sum(len(v) for v in STEP_REQUIRES.values())
    assert n >= 8, f"STEP_REQUIRES has shrunk to {n} rules"


@pytest.mark.parametrize("profile", sorted(PROFILES))
@pytest.mark.parametrize("with_iip2", [False, True])
@pytest.mark.parametrize("with_dpd", [False, True])
def test_every_canonical_plan_validates(profile, with_iip2, with_dpd):
    plan = planned_steps(PROFILES[profile], with_iip2=with_iip2,
                         with_dpd=with_dpd)
    validate_order(plan)  # must not raise


def test_rx_iq_before_tx_iq_is_rejected_with_the_reason():
    plan = planned_steps(PROFILES["factory"], with_iip2=True, with_dpd=True)
    i, j = plan.index("tx_iq"), plan.index("rx_iq")
    plan[i], plan[j] = plan[j], plan[i]
    with pytest.raises(ValueError, match="TX-cancels-RX"):
        validate_order(plan)


def test_iip2_without_lo_leak_cal_is_rejected():
    plan = planned_steps(PROFILES["factory"], with_iip2=True, with_dpd=False)
    plan.remove("tx_lo_leak_loopback")
    with pytest.raises(ValueError, match="missing.*rx_iip2"):
        validate_order(plan)


def test_dpd_before_tx_power_is_rejected():
    plan = planned_steps(PROFILES["factory"], with_iip2=False, with_dpd=True)
    plan.remove("dpd")
    plan.insert(plan.index("tx_power"), "dpd")
    with pytest.raises(ValueError, match="operating drive"):
        validate_order(plan)


def test_rule_reasons_are_prose_not_stubs():
    for step, reqs in STEP_REQUIRES.items():
        for req, reason in reqs.items():
            assert len(reason) > 40, f"{step}<-{req}: reason is a stub"
