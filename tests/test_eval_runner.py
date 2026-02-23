import json
from pathlib import Path
import pytest

# test eval runner in mock mode
class TestEvalRunnerMock:
    # test mock eval run produces a valid report dict
    @pytest.mark.asyncio
    async def test_mock_eval_produces_report(self) -> None:
        from eval.run_eval import run_eval

        report = await run_eval(use_mock=True)

        assert report["mode"] == "mock"
        assert report["model"] == "gpt-4o-mini"
        assert report["sample_count"] == 50
        assert "metrics" in report
        assert "results" in report

    # test mock eval returns perfect scores
    @pytest.mark.asyncio
    async def test_mock_eval_perfect_metrics(self) -> None:
        from eval.run_eval import run_eval

        report = await run_eval(use_mock=True)
        metrics = report["metrics"]

        assert metrics["priority_accuracy"] == 1.0
        assert metrics["schema_valid_rate"] == 1.0
        assert metrics["compliance_score"] == 1.0

    # test mock eval has all required fields
    @pytest.mark.asyncio
    async def test_mock_eval_has_all_required_fields(self) -> None:
        from eval.run_eval import run_eval

        report = await run_eval(use_mock=True)

        assert "timestamp" in report
        assert "model" in report
        assert "prompt_version" in report
        assert "metrics" in report
        assert "sample_count" in report
        assert "results" in report
        assert len(report["results"]) == 50

    # test mock eval results have detail fields
    @pytest.mark.asyncio
    async def test_mock_eval_results_have_detail_fields(self) -> None:
        from eval.run_eval import run_eval

        report = await run_eval(use_mock=True)
        result = report["results"][0]

        assert "sample_id" in result
        assert "expected" in result
        assert "actual" in result
        assert "schema_valid" in result
        assert "repair_attempted" in result
        assert "priority_match" in result
        assert "policy_match" in result

    # test write report creates a valid JSON file
    @pytest.mark.asyncio
    async def test_write_report_creates_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import eval.run_eval as run_eval_module
        from eval.run_eval import run_eval, write_report

        test_report_path = tmp_path / "report.json"
        monkeypatch.setattr(run_eval_module, "REPORT_PATH", test_report_path)

        report = await run_eval(use_mock=True)
        write_report(report)

        assert test_report_path.exists()
        loaded = json.loads(test_report_path.read_text())
        assert loaded["sample_count"] == 50
        assert loaded["metrics"]["priority_accuracy"] == 1.0
