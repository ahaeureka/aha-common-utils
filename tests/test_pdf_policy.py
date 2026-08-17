"""AC-6(M6): aha_common_utils.pdf.policy 分区策略。

FrontMatterPolicy 消费：strategy（auto/strict/off）与 zone_action
（separate/discard）决定 how boundary 结果被应用。
"""

from __future__ import annotations

from aha_common_utils.pdf.policy import (
    apply_zone_action,
    effective_strategy,
    should_apply_boundary,
)
from aha_common_utils.pdf.types import FrontMatterDecision, FrontMatterPolicy


def test_should_apply_boundary_auto_with_decision() -> None:
    policy = FrontMatterPolicy()
    decision = FrontMatterDecision(boundary_page=5, confidence=0.8)
    assert should_apply_boundary(policy, decision) is True


def test_should_apply_boundary_auto_none_boundary() -> None:
    """fail-open：boundary=None → 不应用分区（whole 正文）。"""
    policy = FrontMatterPolicy()
    decision = FrontMatterDecision(boundary_page=None, confidence=0.0)
    assert should_apply_boundary(policy, decision) is False


def test_should_apply_boundary_off_disables() -> None:
    policy = FrontMatterPolicy(strategy="off")
    decision = FrontMatterDecision(boundary_page=3, confidence=0.9)
    assert should_apply_boundary(policy, decision) is False


def test_should_apply_boundary_strict_low_confidence() -> None:
    """strict 也要最低置信度门槛（低置信 → 不应用，防误杀）。"""
    policy = FrontMatterPolicy(strategy="strict")
    decision = FrontMatterDecision(boundary_page=3, confidence=0.2)
    assert should_apply_boundary(policy, decision) is False


def test_should_apply_boundary_strict_high_confidence() -> None:
    policy = FrontMatterPolicy(strategy="strict")
    decision = FrontMatterDecision(boundary_page=3, confidence=0.95)
    assert should_apply_boundary(policy, decision) is True


def test_effective_strategy_default() -> None:
    assert effective_strategy(FrontMatterPolicy()) == "auto"


def test_apply_zone_action_separate_discard() -> None:
    assert apply_zone_action(FrontMatterPolicy(zone_action="separate")) == "separate"
    assert apply_zone_action(FrontMatterPolicy(zone_action="discard")) == "discard"