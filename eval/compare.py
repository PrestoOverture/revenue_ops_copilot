"""
Compare eval report against baseline and enforce regression thresholds.

Usage:
    python -m eval.compare

Exit codes:
    0 = pass (no regression beyond thresholds)
    1 = fail (regression detected)
"""

import json
import sys
from pathlib import Path

BASELINE_PATH = Path("eval/baseline.json")
REPORT_PATH = Path("eval/report.json")

REGRESSION_THRESHOLDS = {
    "priority_accuracy": 0.03,
    "schema_valid_rate": 0.02,
    "compliance_score": 0.10,
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())

# compare the report metrics against the baseline
def compare(baseline: dict, report: dict) -> tuple[bool, list[str]]:
    baseline_metrics = baseline["metrics"]
    report_metrics = report["metrics"]
    failures: list[str] = []

    for metric, max_regression in REGRESSION_THRESHOLDS.items():
        baseline_val = baseline_metrics[metric]
        report_val = report_metrics[metric]
        regression = baseline_val - report_val

        if regression > max_regression:
            failures.append(
                f"FAIL: {metric} regressed {regression:.4f} "
                f"(baseline={baseline_val:.4f}, current={report_val:.4f}, "
                f"max_allowed={max_regression:.4f})"
            )
        else:
            print(
                f"PASS: {metric} "
                f"(baseline={baseline_val:.4f}, current={report_val:.4f}, "
                f"regression={regression:.4f}, max_allowed={max_regression:.4f})"
            )

    return len(failures) == 0, failures


def main() -> None:
    if not BASELINE_PATH.exists():
        print(f"ERROR: Baseline not found at {BASELINE_PATH}")
        sys.exit(1)

    if not REPORT_PATH.exists():
        print(f"ERROR: Report not found at {REPORT_PATH}")
        sys.exit(1)

    baseline = load_json(BASELINE_PATH)
    report = load_json(REPORT_PATH)

    print(
        f"Baseline: {baseline.get('prompt_version', 'unknown')} "
        f"({baseline.get('mode', 'unknown')} mode)"
    )
    print(
        f"Report:   {report.get('prompt_version', 'unknown')} "
        f"({report.get('mode', 'unknown')} mode)"
    )
    print()

    passed, failures = compare(baseline, report)

    if not passed:
        print()
        for failure in failures:
            print(failure)
        print("\nRegression gate FAILED")
        sys.exit(1)

    print("\nRegression gate PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
