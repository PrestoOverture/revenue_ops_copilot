from decimal import Decimal
import pytest
from src.llm.pricing import calculate_cost

# test that the calculate_cost function calculates the cost for GPT-4o
def test_calculate_cost_gpt_4o() -> None:
    cost = calculate_cost("gpt-4o", 1000, 500)
    assert cost == Decimal("0.0075")

# test that the calculate_cost function calculates the cost for GPT-4o-mini
def test_calculate_cost_gpt_4o_mini() -> None:
    cost = calculate_cost("gpt-4o-mini", 1000, 500)
    assert cost == Decimal("0.00045")

# test that the calculate_cost function calculates the cost for zero tokens
def test_calculate_cost_zero_tokens() -> None:
    cost = calculate_cost("gpt-4o", 0, 0)
    assert cost == Decimal("0")

# test that the calculate_cost function raises a ValueError if the model is unknown
def test_calculate_cost_unknown_model_raises_value_error() -> None:
    with pytest.raises(ValueError):
        calculate_cost("gpt-5-turbo", 100, 100)
