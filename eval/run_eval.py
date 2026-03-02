"""
Eval runner for qualification prompt.

Usage:
    python -m eval.run_eval          # Real LLM calls (creates baseline)
    python -m eval.run_eval --mock   # Deterministic mock (for CI)
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from pydantic import ValidationError
from eval.metrics import (
    ActualOutput,
    EvalResult,
    ExpectedOutput,
    calculate_compliance_score,
    calculate_priority_accuracy,
    calculate_schema_valid_rate,
)
from src.llm.client import LLMClient
from src.llm.prompts.qualify import (
    FALLBACK_QUALIFICATION,
    PROMPT_VERSION,
    QualificationOutput,
    build_qualify_prompt,
    parse_qualify_response,
)
from src.llm.repair import repair_json

logger = logging.getLogger(__name__)

DATASET_PATH = Path("eval/dataset.jsonl")
REPORT_PATH = Path("eval/report.json")
QUALIFY_MODEL = "gpt-4o-mini"


# load the eval dataset from the JSONL file
def load_dataset() -> list[dict]:
    lines = DATASET_PATH.read_text().strip().split("\n")
    return [json.loads(line) for line in lines]


# mock qualification
def mock_qualify(
    lead_data: dict, expected: dict
) -> tuple[QualificationOutput, bool, bool]:
    """
    Deterministic mock: returns the expected output as if the LLM produced it perfectly.
    Returns (output, schema_valid, repair_attempted).

    This means in mock mode:
    - priority_accuracy = 1.0
    - schema_valid_rate = 1.0
    - compliance_score = 1.0
    """
    _ = lead_data
    output = QualificationOutput(
        priority=expected["priority"],
        budget_range=expected["budget_range"],
        timeline=expected["timeline"],
        routing=expected["routing"],
        policy_decision=expected["policy_decision"],
        notes="Mock qualification for eval sample",
    )
    return output, True, False


# real qualification
async def real_qualify(
    llm_client: LLMClient, lead_data: dict
) -> tuple[QualificationOutput, bool, bool]:
    """
    Real LLM qualification with parse -> repair -> fallback.
    Returns (output, schema_valid, repair_attempted).
    """
    messages = build_qualify_prompt(lead_data)
    response = await llm_client.chat_completion(
        model=QUALIFY_MODEL,
        messages=messages,
        temperature=0,
    )
    content = str(response["content"])

    schema_valid = True
    repair_attempted = False

    try:
        output = parse_qualify_response(content)
    except (json.JSONDecodeError, ValidationError):
        schema_valid = False
        repair_attempted = True
        repaired = await repair_json(
            llm_client=llm_client,
            invalid_json=content,
            schema=QualificationOutput.model_json_schema(),
        )
        if repaired is not None:
            try:
                output = QualificationOutput(**repaired)
                schema_valid = True
            except ValidationError:
                output = FALLBACK_QUALIFICATION
        else:
            output = FALLBACK_QUALIFICATION

    return output, schema_valid, repair_attempted


# run the evaluation and return the report
async def run_eval(use_mock: bool = False) -> dict:
    dataset = load_dataset()
    llm_client: LLMClient | None = None

    if not use_mock:
        from src.config import Settings

        settings = Settings()  # type: ignore[call-arg]
        llm_client = LLMClient(api_key=settings.OPENAI_API_KEY)

    results: list[EvalResult] = []
    detailed_results: list[dict] = []

    for sample in dataset:
        sample_id = sample["id"]
        lead_data = sample["lead"]
        expected_dict = sample["expected"]

        expected = ExpectedOutput(
            priority=expected_dict["priority"],
            budget_range=expected_dict["budget_range"],
            timeline=expected_dict["timeline"],
            routing=expected_dict["routing"],
            policy_decision=expected_dict["policy_decision"],
        )

        if use_mock:
            output, schema_valid, repair_attempted = mock_qualify(
                lead_data, expected_dict
            )
        else:
            assert llm_client is not None
            output, schema_valid, repair_attempted = await real_qualify(
                llm_client, lead_data
            )

        actual = ActualOutput(
            priority=output.priority,
            budget_range=output.budget_range,
            timeline=output.timeline,
            routing=output.routing,
            policy_decision=output.policy_decision,
            notes=output.notes,
        )

        eval_result = EvalResult(
            sample_id=sample_id,
            expected=expected,
            actual=actual,
            schema_valid=schema_valid,
            repair_attempted=repair_attempted,
        )
        results.append(eval_result)

        detailed_results.append(
            {
                "sample_id": sample_id,
                "expected": expected_dict,
                "actual": {
                    "priority": actual.priority,
                    "budget_range": actual.budget_range,
                    "timeline": actual.timeline,
                    "routing": actual.routing,
                    "policy_decision": actual.policy_decision,
                    "notes": actual.notes,
                },
                "schema_valid": schema_valid,
                "repair_attempted": repair_attempted,
                "priority_match": actual.priority == expected.priority,
                "policy_match": actual.policy_decision == expected.policy_decision,
            }
        )

    metrics = {
        "priority_accuracy": round(calculate_priority_accuracy(results), 4),
        "schema_valid_rate": round(calculate_schema_valid_rate(results), 4),
        "compliance_score": round(calculate_compliance_score(results), 4),
    }

    report = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": QUALIFY_MODEL,
        "prompt_version": PROMPT_VERSION,
        "mode": "mock" if use_mock else "real",
        "metrics": metrics,
        "sample_count": len(results),
        "results": detailed_results,
    }

    return report


# write the report to the eval/report.json file
def write_report(report: dict) -> None:
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    logger.info("Report written to %s", REPORT_PATH)


# main function to run the evaluation
async def main() -> None:
    parser = argparse.ArgumentParser(description="Run qualification eval")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock responses (for CI)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    report = await run_eval(use_mock=args.mock)
    write_report(report)

    metrics = report["metrics"]
    print("\n=== Eval Report ===")
    print(f"Mode:               {report['mode']}")
    print(f"Model:              {report['model']}")
    print(f"Prompt version:     {report['prompt_version']}")
    print(f"Samples:            {report['sample_count']}")
    print(f"Priority accuracy:  {metrics['priority_accuracy']}")
    print(f"Schema valid rate:  {metrics['schema_valid_rate']}")
    print(f"Compliance score:   {metrics['compliance_score']}")
    print(f"\nReport: {REPORT_PATH}")

if __name__ == "__main__":
    asyncio.run(main())
