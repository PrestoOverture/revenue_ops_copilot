from eval.compare import compare

# test eval compare
class TestEvalCompare:
    # test no regression passes (all metrics are the same)
    def test_no_regression_passes(self) -> None:
        baseline = {
            "metrics": {
                "priority_accuracy": 1.0,
                "schema_valid_rate": 1.0,
                "compliance_score": 1.0,
            }
        }
        report = {
            "metrics": {
                "priority_accuracy": 1.0,
                "schema_valid_rate": 1.0,
                "compliance_score": 1.0,
            }
        }
        passed, failures = compare(baseline, report)
        assert passed is True
        assert failures == []

    # test small regression passes (all metrics regress)
    def test_small_regression_passes(self) -> None:
        baseline = {
            "metrics": {
                "priority_accuracy": 1.0,
                "schema_valid_rate": 1.0,
                "compliance_score": 1.0,
            }
        }
        report = {
            "metrics": {
                "priority_accuracy": 0.98,
                "schema_valid_rate": 0.99,
                "compliance_score": 0.95,
            }
        }
        passed, failures = compare(baseline, report)
        assert passed is True
        assert failures == []

    # test priority accuracy regression fails (priority accuracy regresses)
    def test_priority_accuracy_regression_fails(self) -> None:
        baseline = {
            "metrics": {
                "priority_accuracy": 1.0,
                "schema_valid_rate": 1.0,
                "compliance_score": 1.0,
            }
        }
        report = {
            "metrics": {
                "priority_accuracy": 0.96,
                "schema_valid_rate": 1.0,
                "compliance_score": 1.0,
            }
        }
        passed, failures = compare(baseline, report)
        assert passed is False
        assert len(failures) == 1
        assert "priority_accuracy" in failures[0]

    # test schema valid rate regression fails (schema valid rate regresses)
    def test_schema_valid_rate_regression_fails(self) -> None:
        baseline = {
            "metrics": {
                "priority_accuracy": 1.0,
                "schema_valid_rate": 1.0,
                "compliance_score": 1.0,
            }
        }
        report = {
            "metrics": {
                "priority_accuracy": 1.0,
                "schema_valid_rate": 0.97,
                "compliance_score": 1.0,
            }
        }
        passed, failures = compare(baseline, report)
        assert passed is False
        assert len(failures) == 1
        assert "schema_valid_rate" in failures[0]

    # test compliance score regression fails (compliance score regresses)
    def test_compliance_score_regression_fails(self) -> None:
        baseline = {
            "metrics": {
                "priority_accuracy": 1.0,
                "schema_valid_rate": 1.0,
                "compliance_score": 1.0,
            }
        }
        report = {
            "metrics": {
                "priority_accuracy": 1.0,
                "schema_valid_rate": 1.0,
                "compliance_score": 0.89,
            }
        }
        passed, failures = compare(baseline, report)
        assert passed is False
        assert len(failures) == 1
        assert "compliance_score" in failures[0]

    # test multiple regressions reported (all metrics regress)
    def test_multiple_regressions_reported(self) -> None:
        baseline = {
            "metrics": {
                "priority_accuracy": 1.0,
                "schema_valid_rate": 1.0,
                "compliance_score": 1.0,
            }
        }
        report = {
            "metrics": {
                "priority_accuracy": 0.90,
                "schema_valid_rate": 0.90,
                "compliance_score": 0.50,
            }
        }
        passed, failures = compare(baseline, report)
        assert passed is False
        assert len(failures) == 3

    # test improvement passes (all metrics improve)
    def test_improvement_passes(self) -> None:
        baseline = {
            "metrics": {
                "priority_accuracy": 0.85,
                "schema_valid_rate": 0.90,
                "compliance_score": 0.80,
            }
        }
        report = {
            "metrics": {
                "priority_accuracy": 0.95,
                "schema_valid_rate": 0.98,
                "compliance_score": 0.95,
            }
        }
        passed, failures = compare(baseline, report)
        assert passed is True
        assert failures == []
