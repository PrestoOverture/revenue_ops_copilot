from dataclasses import dataclass

# expected output from the dataset
@dataclass
class ExpectedOutput:
    priority: str
    budget_range: str
    timeline: str
    routing: str
    policy_decision: str


# actual output from the LLM
@dataclass
class ActualOutput:
    priority: str
    budget_range: str
    timeline: str
    routing: str
    policy_decision: str
    notes: str = ""


# result of evaluating a single sample
@dataclass
class EvalResult:
    sample_id: str
    expected: ExpectedOutput
    actual: ActualOutput
    schema_valid: bool
    repair_attempted: bool


# calculate the priority accuracy
def calculate_priority_accuracy(results: list[EvalResult]) -> float:
    # fraction of samples where actual.priority == expected.priority.
    if not results:
        return 0.0
    correct = sum(1 for r in results if r.actual.priority == r.expected.priority)
    return correct / len(results)


# calculate the schema valid rate
def calculate_schema_valid_rate(results: list[EvalResult]) -> float:
    # fraction of samples with valid schema on first try (no repair).
    if not results:
        return 0.0
    valid = sum(1 for r in results if r.schema_valid and not r.repair_attempted)
    return valid / len(results)


# calculate the compliance score
def calculate_compliance_score(results: list[EvalResult]) -> float:
    """
    Weighted compliance score, normalized to 0-1.

    For each sample, compare actual.policy_decision vs expected.policy_decision:
    - True Positive (correct match): +1.0
    - False Negative (actual=ALLOW when expected=REQUIRE_REVIEW or BLOCK): -0.5
    - False Positive (actual=REQUIRE_REVIEW when expected=ALLOW): -0.2
    - BLOCK error (actual=BLOCK when expected!=BLOCK, or expected=BLOCK when actual!=BLOCK): -1.0

    Raw score = sum of per-sample scores.
    Normalized = (raw_score + len(results)) / (2 * len(results))
    This maps the range [-N, +N] to [0, 1].
    """
    if not results:
        return 0.0

    raw_score = 0.0
    for r in results:
        actual_pd = r.actual.policy_decision
        expected_pd = r.expected.policy_decision

        if actual_pd == expected_pd:
            raw_score += 1.0
        elif expected_pd == "BLOCK" and actual_pd != "BLOCK":
            raw_score -= 1.0
        elif actual_pd == "BLOCK" and expected_pd != "BLOCK":
            raw_score -= 1.0
        elif actual_pd == "ALLOW" and expected_pd in ("REQUIRE_REVIEW", "BLOCK"):
            raw_score -= 0.5
        elif actual_pd == "REQUIRE_REVIEW" and expected_pd == "ALLOW":
            raw_score -= 0.2
        else:
            raw_score -= 0.5

    return (raw_score + len(results)) / (2 * len(results))
