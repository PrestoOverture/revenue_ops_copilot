from decimal import Decimal

MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input_per_1k": 0.0025, "output_per_1k": 0.01},
    "gpt-4o-mini": {"input_per_1k": 0.00015, "output_per_1k": 0.0006},
}

_TOKENS_PER_1K = Decimal("1000")
_USD_PRECISION = Decimal("0.000001")

# calculate the cost for a given model, tokens_in, and tokens_out
def calculate_cost(model: str, tokens_in: int, tokens_out: int) -> Decimal:
    if model not in MODEL_PRICING:
        raise ValueError(f"Unknown model '{model}' in MODEL_PRICING")

    pricing = MODEL_PRICING[model]
    input_per_1k = Decimal(str(pricing["input_per_1k"]))
    output_per_1k = Decimal(str(pricing["output_per_1k"]))

    input_cost = (Decimal(tokens_in) / _TOKENS_PER_1K) * input_per_1k
    output_cost = (Decimal(tokens_out) / _TOKENS_PER_1K) * output_per_1k
    total_cost = input_cost + output_cost
    return total_cost.quantize(_USD_PRECISION)
