from __future__ import annotations

import pytest

from confluence.confluence_registry import (
    CONFLUENCE_RULES,
    get_rule,
    list_rules,
)
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

_EXPECTED_RULES = {
    "ema_alignment": EmaAlignmentRule,
    "adx_strength": AdxStrengthRule,
    "vwap_confirmation": VWAPConfirmationRule,
    "supertrend": SupertrendRule,
    "rsi_momentum": RsiMomentumRule,
    "macd_confirmation": MacdConfirmationRule,
    "obv_confirmation": ObvConfirmationRule,
    "breakout_confirmation": BreakoutConfirmationRule,
}


class TestGetRule:
    def test_ema_alignment_returns_class(self):
        assert get_rule("ema_alignment") is EmaAlignmentRule

    def test_adx_strength_returns_class(self):
        assert get_rule("adx_strength") is AdxStrengthRule

    def test_vwap_confirmation_returns_class(self):
        assert get_rule("vwap_confirmation") is VWAPConfirmationRule

    def test_supertrend_returns_class(self):
        assert get_rule("supertrend") is SupertrendRule

    def test_rsi_momentum_returns_class(self):
        assert get_rule("rsi_momentum") is RsiMomentumRule

    def test_macd_confirmation_returns_class(self):
        assert get_rule("macd_confirmation") is MacdConfirmationRule

    def test_obv_confirmation_returns_class(self):
        assert get_rule("obv_confirmation") is ObvConfirmationRule

    def test_breakout_confirmation_returns_class(self):
        assert get_rule("breakout_confirmation") is BreakoutConfirmationRule

    def test_returned_class_is_instantiable(self):
        cls = get_rule("ema_alignment")
        instance = cls()
        assert hasattr(instance, "evaluate")

    def test_unknown_raises_key_error(self):
        with pytest.raises(KeyError, match="unknown_rule"):
            get_rule("unknown_rule")

    def test_empty_string_raises_key_error(self):
        with pytest.raises(KeyError):
            get_rule("")


class TestListRules:
    def test_returns_all_eight_names(self):
        names = list_rules()
        assert set(names) == set(_EXPECTED_RULES.keys())

    def test_returns_exactly_eight(self):
        assert len(list_rules()) == 8

    def test_returns_list_type(self):
        assert isinstance(list_rules(), list)

    def test_order_is_consistent_with_registry(self):
        assert list_rules() == list(CONFLUENCE_RULES.keys())


class TestRegistryCompleteness:
    def test_all_expected_rules_registered(self):
        for name, cls in _EXPECTED_RULES.items():
            assert get_rule(name) is cls

    def test_registry_names_match_rule_name_attribute(self):
        for name in list_rules():
            cls = get_rule(name)
            instance = cls()
            assert instance.name == name

    def test_all_rules_have_positive_max_score(self):
        for name in list_rules():
            instance = get_rule(name)()
            assert instance.max_score > 0
