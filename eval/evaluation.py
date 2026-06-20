import sys
import json
import asyncio
from pathlib import Path
from decimal import Decimal
from datetime import datetime

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))


from invoiceprocessor import InvoiceProcessor
from storage import clear_identities

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
EVAL_PATH = Path(__file__).resolve().parent.parent / "eval" / "pipeline_eval_set.json"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "output" / "evaluation_results"

SCALAR_FIELDS = [
    "vendor", "buyer_name", "invoice_number", "invoice_date",
    "net_total", "vat_total", "gross_total", "currency", "category",
]
ITEM_FIELDS = ["description", "quantity", "net_price", "vat_pct", "line_gross_total"]


def load_eval() -> list[dict]:
    with open(EVAL_PATH, encoding="utf-8") as f:
        return json.load(f)["pipeline_eval"]


def as_str(value) -> str:
    """
    Normalizes a value to a string for exact comparison (handles None, Decimal, date).
    """
    return "" if value is None else str(value)


async def evaluate() -> Path:
    eval_cases = load_eval()

    # Empty identity set so eval invoices aren't all flagged as duplicates.
    processor = InvoiceProcessor(processed_invoices=set())

    field_stats = {f: {"correct": 0, "total": 0} for f in SCALAR_FIELDS}
    item_field_stats = {f: {"correct": 0, "total": 0} for f in ITEM_FIELDS}
    item_count_stats = {"correct": 0, "total": 0}
    decision_stats = {"correct": 0, "total": 0}
    type_stats = {}

    sum_line_totals = Decimal("0")
    sum_gross_totals = Decimal("0")
    line_sum_consistent = 0
    fully_correct = 0
    rows = []

    for case in eval_cases:
        source_file = case["source_file"]
        file_type = case["file_type"]
        expected = case["expected_extraction"]
        expected_items = expected.get("items", [])

        path = DATA_DIR / source_file
        result = await processor.process_one(path.read_bytes(), source_file)
        extracted = result.extracted

        type_stats.setdefault(file_type, {"correct": 0, "total": 0})
        type_stats[file_type]["total"] += 1

        invoice_correct = True
        field_results = {}

        # Scalar fields.
        for field in SCALAR_FIELDS:
            exp = as_str(expected.get(field))
            act = as_str(getattr(extracted, field))
            ok = exp == act
            field_stats[field]["total"] += 1
            field_stats[field]["correct"] += ok
            invoice_correct &= ok
            field_results[field] = (ok, exp, act)

        # Item count.
        expected_count = len(expected_items)
        actual_count = len(extracted.items)
        count_ok = expected_count == actual_count
        item_count_stats["total"] += 1
        item_count_stats["correct"] += count_ok
        invoice_correct &= count_ok

        # Item fields, positional, only where counts overlap.
        item_mismatches = []
        for i in range(min(expected_count, actual_count)):
            exp_item = expected_items[i]
            act_item = extracted.items[i]
            for field in ITEM_FIELDS:
                exp = as_str(exp_item.get(field))
                act = as_str(getattr(act_item, field))
                ok = exp == act
                item_field_stats[field]["total"] += 1
                item_field_stats[field]["correct"] += ok
                if not ok:
                    invoice_correct = False
                    item_mismatches.append((i, field, exp, act))

        # Decision.
        decision_ok = result.decision.value == case["expected_decision"]
        decision_stats["total"] += 1
        decision_stats["correct"] += decision_ok

        # Financial consistency (over extracted values).
        if extracted.gross_total is not None:
            sum_gross_totals += extracted.gross_total
            line_sum = sum((it.line_gross_total for it in extracted.items), Decimal("0"))
            sum_line_totals += line_sum
            tolerance = Decimal(str(processor.config["rules"]["line_total_tolerance"]))
            if abs(line_sum - extracted.gross_total) <= tolerance:
                line_sum_consistent += 1

        if invoice_correct:
            fully_correct += 1
            type_stats[file_type]["correct"] += 1

        rows.append({
            "source_file": source_file,
            "file_type": file_type,
            "fully_correct": invoice_correct,
            "count_ok": count_ok,
            "expected_count": expected_count,
            "actual_count": actual_count,
            "decision_ok": decision_ok,
            "expected_decision": case["expected_decision"],
            "actual_decision": result.decision.value,
            "fields": field_results,
            "item_mismatches": item_mismatches,
        })

    clear_identities()
    return write_report(eval_cases, field_stats, item_field_stats, item_count_stats,
                 decision_stats, type_stats, rows, fully_correct,
                 sum_line_totals, sum_gross_totals, line_sum_consistent)

def write_report(eval_cases, field_stats, item_field_stats, item_count_stats,
    decision_stats, type_stats, rows, fully_correct, sum_line_totals,
                 sum_gross_totals, line_sum_consistent) -> Path:

    total = len(eval_cases)
    lines = []

    def section(title: str):
        lines.append("")
        lines.append(title)
        lines.append("-" * len(title))

    def percentage(correct: int, total_count: int) -> float:
        return (correct / total_count * 100) if total_count else 0.0

    lines.append("Invoice Processing Evaluation")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Dataset size: {total} invoices")

    decision_accuracy = percentage(
        decision_stats["correct"],
        decision_stats["total"]
    )

    exact_match_rate = percentage(
        fully_correct,
        total
    )

    section("Overall Results")
    lines.append(
        f"Decision accuracy: "
        f"{decision_stats['correct']}/{decision_stats['total']} "
        f"({decision_accuracy:.1f}%)"
    )
    lines.append(
        f"Exact extraction matches: "
        f"{fully_correct}/{total} "
        f"({exact_match_rate:.1f}%)"
    )

    section("Field Accuracy")
    for field, stats in field_stats.items():
        acc = percentage(stats["correct"], stats["total"])
        lines.append(
            f"{field:<20} "
            f"{stats['correct']}/{stats['total']} "
            f"({acc:.1f}%)"
        )

    section("Line Item Accuracy")

    count_acc = percentage(
        item_count_stats["correct"],
        item_count_stats["total"]
    )

    lines.append(
        f"{'item_count':<20} "
        f"{item_count_stats['correct']}/{item_count_stats['total']} "
        f"({count_acc:.1f}%)"
    )

    for field, stats in item_field_stats.items():
        acc = percentage(stats["correct"], stats["total"])
        lines.append(
            f"{field:<20} "
            f"{stats['correct']}/{stats['total']} "
            f"({acc:.1f}%)"
        )

    section("Results by File Type")

    for file_type, stats in sorted(type_stats.items()):
        acc = percentage(stats["correct"], stats["total"])
        lines.append(
            f"{file_type:<8} "
            f"{stats['correct']}/{stats['total']} "
            f"({acc:.1f}%)"
        )

    section("Financial Consistency")

    lines.append(
        f"Invoices within tolerance: "
        f"{line_sum_consistent}/{total}"
    )
    lines.append(
        f"Total line amounts:  {sum_line_totals}"
    )
    lines.append(
        f"Total gross amounts: {sum_gross_totals}"
    )
    lines.append(
        f"Difference: {abs(sum_line_totals - sum_gross_totals)}"
    )

    section("Incorrect Extractions")

    failures_found = False

    for row in rows:
        if row["fully_correct"] and row["decision_ok"]:
            continue

        failures_found = True

        lines.append("")
        lines.append(row["source_file"])

        for field, (ok, expected, actual) in row["fields"].items():
            if not ok:
                lines.append(
                    f"  - {field}: expected '{expected}', got '{actual}'"
                )

        if not row["count_ok"]:
            lines.append(
                f"  - item_count: expected "
                f"{row['expected_count']}, got {row['actual_count']}"
            )

        for index, field, expected, actual in row["item_mismatches"]:
            lines.append(
                f"  - item[{index}].{field}: "
                f"expected '{expected}', got '{actual}'"
            )

        if not row["decision_ok"]:
            lines.append(
                f"  - decision: expected "
                f"'{row['expected_decision']}', "
                f"got '{row['actual_decision']}'"
            )

    if not failures_found:
        lines.append("")
        lines.append("No extraction or decision errors were detected.")

    section("Summary")

    lines.append(
        f"The pipeline produced exact extraction matches for "
        f"{fully_correct} out of {total} invoices "
        f"({exact_match_rate:.1f}%)."
    )

    lines.append(
        f"Decision accuracy was "
        f"{decision_accuracy:.1f}% "
        f"across the evaluation dataset."
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_path = RESULTS_DIR / f"eval_report_{timestamp}.txt"

    report_path.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    print(f"Report written to {report_path}")
    return report_path

if __name__ == "__main__":
    asyncio.run(evaluate())