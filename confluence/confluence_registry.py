"""Registry of available confluence rules.

Usage::

    from confluence.confluence_registry import get_rule, list_rules

    rule_cls = get_rule("ema_alignment")
    rule = rule_cls()
    result = rule.evaluate(indicators)

    all_names = list_rules()
"""
from __future__ import annotations

from confluence.confluence_rules import (
    AdxStrengthRule,
    BreakoutConfirmationRule,
    EmaAlignmentRule,
    MacdConfirmationRule,
    ObvConfirmationRule,
    RsiMomentumRule,
    SupertrendRule,
    VWAPConfirmationRule,
)

# ---------------------------------------------------------------------------
# Registry — name → rule class
# ---------------------------------------------------------------------------

CONFLUENCE_RULES: dict[str, type] = {
    "ema_alignment": EmaAlignmentRule,
    "adx_strength": AdxStrengthRule,
    "vwap_confirmation": VWAPConfirmationRule,
    "supertrend": SupertrendRule,
    "rsi_momentum": RsiMomentumRule,
    "macd_confirmation": MacdConfirmationRule,
    "obv_confirmation": ObvConfirmationRule,
    "breakout_confirmation": BreakoutConfirmationRule,
}


def get_rule(name: str) -> type:
    """Return the rule class registered under *name*.

    Args:
        name: Rule key (e.g. ``"ema_alignment"``).

    Returns:
        The rule class (not an instance — caller must instantiate it).

    Raises:
        KeyError: If *name* is not registered.
    """
    if name not in CONFLUENCE_RULES:
        raise KeyError(
            f"Unknown confluence rule '{name}'. "
            f"Available: {list(CONFLUENCE_RULES)}"
        )
    return CONFLUENCE_RULES[name]


def list_rules() -> list[str]:
    """Return all registered rule names in registration order."""
    return list(CONFLUENCE_RULES.keys())
