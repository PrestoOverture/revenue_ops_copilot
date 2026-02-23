import json
from collections import Counter
from pathlib import Path
import pytest

# test eval dataset
DATASET_PATH = Path("eval/dataset.jsonl")

VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}
VALID_BUDGET_RANGES = {"enterprise", "mid_market", "smb", "unknown"}
VALID_TIMELINES = {"immediate", "30_days", "90_days", "exploratory"}
VALID_ROUTINGS = {"AUTO", "REQUIRE_REVIEW"}
VALID_POLICY_DECISIONS = {"ALLOW", "BLOCK", "REQUIRE_REVIEW"}

REQUIRED_LEAD_FIELDS = {"email", "name", "company", "source"}
REQUIRED_EXPECTED_FIELDS = {
    "priority",
    "budget_range",
    "timeline",
    "routing",
    "policy_decision",
}

# helper function to load dataset
def load_dataset() -> list[dict]:
    lines = DATASET_PATH.read_text().strip().split("\n")
    return [json.loads(line) for line in lines]

# test eval dataset
class TestEvalDataset:
    # test dataset has 50 samples
    def test_dataset_has_50_samples(self) -> None:
        samples = load_dataset()
        assert len(samples) == 50

    # test all ids are unique
    def test_all_ids_unique(self) -> None:
        samples = load_dataset()
        ids = [s["id"] for s in samples]
        assert len(ids) == len(set(ids))

    # test all emails are unique
    def test_all_emails_unique(self) -> None:
        samples = load_dataset()
        emails = [s["lead"]["email"] for s in samples]
        assert len(emails) == len(set(emails))

    # test required fields are present
    def test_required_fields_present(self) -> None:
        samples = load_dataset()
        for s in samples:
            assert "id" in s
            assert "lead" in s
            assert "expected" in s
            lead_keys = set(s["lead"].keys())
            assert REQUIRED_LEAD_FIELDS.issubset(lead_keys), (
                f"Sample {s['id']} missing lead fields"
            )
            expected_keys = set(s["expected"].keys())
            assert REQUIRED_EXPECTED_FIELDS == expected_keys, (
                f"Sample {s['id']} expected field mismatch"
            )

    # test expected values are valid
    def test_expected_values_are_valid(self) -> None:
        samples = load_dataset()
        for s in samples:
            exp = s["expected"]
            assert exp["priority"] in VALID_PRIORITIES, (
                f"Sample {s['id']}: invalid priority {exp['priority']}"
            )
            assert exp["budget_range"] in VALID_BUDGET_RANGES, (
                f"Sample {s['id']}: invalid budget_range"
            )
            assert exp["timeline"] in VALID_TIMELINES, (
                f"Sample {s['id']}: invalid timeline"
            )
            assert exp["routing"] in VALID_ROUTINGS, (
                f"Sample {s['id']}: invalid routing"
            )
            assert exp["policy_decision"] in VALID_POLICY_DECISIONS, (
                f"Sample {s['id']}: invalid policy_decision"
            )

    # test priority distribution
    def test_priority_distribution(self) -> None:
        samples = load_dataset()
        _counts = Counter(s["expected"]["priority"] for s in samples)
        non_edge = [s for s in samples if int(s["id"]) <= 45]
        edge = [s for s in samples if int(s["id"]) > 45]
        non_edge_counts = Counter(s["expected"]["priority"] for s in non_edge)
        assert non_edge_counts["P0"] == 8
        assert non_edge_counts["P1"] == 12
        assert non_edge_counts["P2"] == 15
        assert non_edge_counts["P3"] == 10
        assert len(edge) == 5

    # test each line is valid JSON
    def test_each_line_is_valid_json(self) -> None:
        text = DATASET_PATH.read_text().strip()
        for i, line in enumerate(text.split("\n"), 1):
            try:
                json.loads(line)
            except json.JSONDecodeError:
                pytest.fail(f"Line {i} is not valid JSON")
