import sys
import json
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

import yaml

from datamodel import ExtractedInvoice
from decisionmaker import DecisionMaker

CONFIG_PATH = Path(__file__).resolve().parent.parent / "src" / "config.yaml"
EVAL_PATH = Path(__file__).resolve().parent.parent / "eval" / "rules_eval_set.json"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_eval() -> list[dict]:
    with open(EVAL_PATH, encoding="utf-8") as f:
        return json.load(f)["rule_eval"]


def run():
    config = load_config()
    eval_cases = load_eval()

    passed = 0
    failed = 0

    for case in eval_cases:
        case_id = case["id"]
        expected_decision = case["expected_decision"]
        expected_rules = set(case["expected_failed_rules"])

        # The duplicate case needs its identity pre-loaded into the store.
        processed = set()
        if case_id == "R6_duplicate":
            processed = {"Acme Ltd-INV-001"}

        engine = DecisionMaker(config, processed_invoices=processed)
        invoice = ExtractedInvoice(**case["extracted"])
        result = engine.evaluate(invoice, source_file=f"{case_id}.test", file_hash="testhash")

        actual_decision = result.decision.value
        actual_rules = {f.rule_id for f in result.failures}

        if actual_decision == expected_decision and actual_rules == expected_rules:
            passed += 1
            print(f"PASS  {case_id}")
        else:
            failed += 1
            print(f"FAIL  {case_id}")
            if actual_decision != expected_decision:
                print(f"        decision: expected '{expected_decision}', got '{actual_decision}'")
            if actual_rules != expected_rules:
                print(f"        rules expected: {expected_rules}")
                print(f"        rules actual:   {actual_rules}")

    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")


if __name__ == "__main__":
    run()