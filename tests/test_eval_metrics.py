import pytest
from eval.metrics import (
    ActualOutput,
    EvalResult,
    ExpectedOutput,
    calculate_compliance_score,
    calculate_priority_accuracy,
    calculate_schema_valid_rate,
)

# helper function to make a test result for a single sample
def _make_result(
    sample_id: str = "001",
    expected_priority: str = "P0",
    actual_priority: str = "P0",
    expected_policy: str = "ALLOW",
    actual_policy: str = "ALLOW",
    schema_valid: bool = True,
    repair_attempted: bool = False,
) -> EvalResult:
    return EvalResult(
        sample_id=sample_id,
        expected=ExpectedOutput(
            priority=expected_priority,
            budget_range="enterprise",
            timeline="immediate",
            routing="AUTO",
            policy_decision=expected_policy,
        ),
        actual=ActualOutput(
            priority=actual_priority,
            budget_range="enterprise",
            timeline="immediate",
            routing="AUTO",
            policy_decision=actual_policy,
        ),
        schema_valid=schema_valid,
        repair_attempted=repair_attempted,
    )


# test priority accuracy
class TestPriorityAccuracy:
    # test all correct
    def test_all_correct(self) -> None:
        results = [_make_result(f"{i:03d}") for i in range(1, 6)]
        assert calculate_priority_accuracy(results) == 1.0

    # test none correct
    def test_none_correct(self) -> None:
        results = [_make_result(f"{i:03d}", actual_priority="P3") for i in range(1, 6)]
        assert calculate_priority_accuracy(results) == 0.0

    # test partial correct
    def test_partial_correct(self) -> None:
        results = [
            _make_result("001", actual_priority="P0"),
            _make_result("002", actual_priority="P1"),
            _make_result("003", actual_priority="P0"),
            _make_result("004", actual_priority="P2"),
        ]
        assert calculate_priority_accuracy(results) == 0.5

    # test empty list
    def test_empty_list(self) -> None:
        assert calculate_priority_accuracy([]) == 0.0


# test schema valid rate
class TestSchemaValidRate:
    # test all valid no repair
    def test_all_valid_no_repair(self) -> None:
        results = [_make_result(f"{i:03d}") for i in range(1, 6)]
        assert calculate_schema_valid_rate(results) == 1.0

    # test repair attempted not counted
    def test_repair_attempted_not_counted(self) -> None:
        results = [
            _make_result("001", schema_valid=True, repair_attempted=False),
            _make_result("002", schema_valid=True, repair_attempted=True),
            _make_result("003", schema_valid=False, repair_attempted=True),
        ]
        assert calculate_schema_valid_rate(results) == pytest.approx(1 / 3)

    # test empty list
    def test_empty_list(self) -> None:
        assert calculate_schema_valid_rate([]) == 0.0


# test compliance score
class TestComplianceScore:
    # test all correct returns 1
    def test_all_correct_returns_1(self) -> None:
        results = [_make_result(f"{i:03d}") for i in range(1, 6)]
        assert calculate_compliance_score(results) == 1.0

    # test false negative allow vs require review
    def test_false_negative_allow_vs_require_review(self) -> None:
        results = [
            _make_result("001", expected_policy="REQUIRE_REVIEW", actual_policy="ALLOW")
        ]
        assert calculate_compliance_score(results) == pytest.approx(0.25)

    # test false positive require review vs allow
    def test_false_positive_require_review_vs_allow(self) -> None:
        results = [
            _make_result("001", expected_policy="ALLOW", actual_policy="REQUIRE_REVIEW")
        ]
        assert calculate_compliance_score(results) == pytest.approx(0.4)

    # test block error actual block
    def test_block_error_actual_block(self) -> None:
        results = [_make_result("001", expected_policy="ALLOW", actual_policy="BLOCK")]
        assert calculate_compliance_score(results) == pytest.approx(0.0)

    # test block error missed block
    def test_block_error_missed_block(self) -> None:
        results = [_make_result("001", expected_policy="BLOCK", actual_policy="ALLOW")]
        assert calculate_compliance_score(results) == pytest.approx(0.0)

    # test empty list
    def test_empty_list(self) -> None:
        assert calculate_compliance_score([]) == 0.0

    # test mixed results
    def test_mixed_results(self) -> None:
        results = [
            _make_result("001", expected_policy="ALLOW", actual_policy="ALLOW"),
            _make_result(
                "002", expected_policy="REQUIRE_REVIEW", actual_policy="ALLOW"
            ),
            _make_result(
                "003", expected_policy="ALLOW", actual_policy="REQUIRE_REVIEW"
            ),
            _make_result("004", expected_policy="BLOCK", actual_policy="BLOCK"),
        ]
        assert calculate_compliance_score(results) == pytest.approx(0.6625)
