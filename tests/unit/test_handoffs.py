import pytest
from pydantic import ValidationError

from agent.handoffs import BidDecision, FitReport, PriceQuote, RiskReport


def test_risk_bounds():
    with pytest.raises(ValidationError):
        RiskReport(risk_score=1.5, is_scam=False)


def test_flags_are_closed_vocabulary():
    with pytest.raises(ValidationError):
        RiskReport(risk_score=0.2, is_scam=False, flags=["made_up_flag"])


def test_decision_actions():
    assert BidDecision(action="watch").action == "watch"
    with pytest.raises(ValidationError):
        BidDecision(action="maybe")


def test_price_positive():
    with pytest.raises(ValidationError):
        PriceQuote(amount=0)


def test_fit_score_range():
    with pytest.raises(ValidationError):
        FitReport(fit_score=-0.1)
