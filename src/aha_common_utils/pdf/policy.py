"""PDF 分区策略（pdf-foundation.md §8 policy）。

FrontMatterPolicy 消费：strategy（auto/strict/off）与 zone_action
（separate/discard）决定 boundary 结果如何被应用。
"""

from __future__ import annotations

from aha_common_utils.pdf.types import FrontMatterDecision, FrontMatterPolicy

# 置信度门槛：低于该值不应用边界（防误杀）
_MIN_CONFIDENCE = 0.6


def effective_strategy(policy: FrontMatterPolicy) -> str:
    """策略归一（auto/strict/off）。"""
    return policy.strategy


def should_apply_boundary(policy: FrontMatterPolicy, decision: FrontMatterDecision) -> bool:
    """是否应用 boundary 分区（fail-open 主约束）。

    - strategy=off → 永不分区
    - boundary=None → 无 front matter，不分区
    - 置信度 < 门槛 → 不分区（防误杀，strict 同样受约束）
    """
    if policy.strategy == "off":
        return False
    if decision.boundary_page is None:
        return False
    return decision.confidence >= _MIN_CONFIDENCE


def apply_zone_action(policy: FrontMatterPolicy) -> str:
    """zone_action 归一（separate/discard）。"""
    return policy.zone_action