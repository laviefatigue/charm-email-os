#!/usr/bin/env python3
"""
Validate strategy generation output against quality standards.

Checks output against the reference skill requirements:
- ICP Mapping: Target ICP + 4 pain point categories + 3 objections
- Variable Schema: Core + High-Signal + AI-Generated with sources
- Word Count: 50-90 words per email (strict)
- QA Scoring: 6-dimension breakdown with notes
- Strategy Notes: Callouts + data enrichment sources
- Email Structure: 4 positions with 2-3 variants each

Reference: D:\\Work\\Claude Campaign Copywriting Skill-20251120T015618Z-1-001

Usage:
    python scripts/validate_output.py
    python scripts/validate_output.py path/to/campaign_document.json
"""
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class ValidationResult:
    """Single validation check result."""
    dimension: str
    passed: bool
    score: str
    notes: str
    critical: bool = False


def count_words(text: str) -> int:
    """Count words in text."""
    if not text:
        return 0
    return len(text.split())


def validate_icp_mapping(doc: dict) -> ValidationResult:
    """Validate ICP mapping completeness."""
    icp = doc.get("icp_mapping", {})

    # Check target ICP
    target = icp.get("target_icp", {})
    has_role = bool(target.get("role"))
    has_company_type = bool(target.get("company_type"))
    has_company_size = bool(target.get("company_size"))
    has_target = has_role and has_company_type

    # Check pain points (need 4 categories)
    pain_points = icp.get("pain_points", [])
    pain_count = len(pain_points)
    has_4_categories = pain_count >= 4

    # Check objections (need 3 with preemption)
    objections = icp.get("objections", [])
    obj_count = len(objections)
    has_preemption = all(o.get("preemption") for o in objections)
    has_3_objections = obj_count >= 3 and has_preemption

    passed = has_target and has_4_categories and has_3_objections
    score_num = sum([has_target, has_4_categories, has_3_objections])

    notes_parts = []
    if has_target:
        notes_parts.append(f"Target ICP: {target.get('role', 'N/A')}")
    else:
        notes_parts.append("Target ICP: MISSING")
    notes_parts.append(f"Pain Points: {pain_count}/4 categories")
    notes_parts.append(f"Objections: {obj_count}/3 with preemption")

    return ValidationResult(
        dimension="ICP Mapping",
        passed=passed,
        score=f"{score_num}/3",
        notes=" | ".join(notes_parts),
        critical=True
    )


def validate_variable_schema(doc: dict) -> ValidationResult:
    """Validate variable schema completeness."""
    schema = doc.get("variable_schema", {})

    core = schema.get("core", [])
    high_signal = schema.get("high_signal", [])
    ai_generated = schema.get("ai_generated", [])

    has_core = len(core) > 0
    has_high_signal = len(high_signal) > 0
    has_ai = len(ai_generated) > 0

    # Check if high_signal has sources
    has_sources = all(v.get("source") for v in high_signal) if high_signal else False

    passed = has_core and has_high_signal
    score_num = sum([has_core, has_high_signal, has_ai])

    notes = (f"Core: {len(core)} | High-Signal: {len(high_signal)} "
             f"{'(with sources)' if has_sources else '(missing sources)'} | "
             f"AI-Generated: {len(ai_generated)}")

    return ValidationResult(
        dimension="Variable Schema",
        passed=passed,
        score=f"{score_num}/3",
        notes=notes,
        critical=True
    )


def validate_word_counts(doc: dict) -> ValidationResult:
    """Validate email word counts (50-90 words target)."""
    positions = doc.get("email_positions", [])

    word_counts = []
    violations = []

    for pos in positions:
        pos_num = pos.get("position", "?")
        for variant in pos.get("variants", []):
            body = variant.get("email_body", "")
            wc = variant.get("word_count") or count_words(body)
            word_counts.append(wc)

            if wc < 50:
                violations.append(f"P{pos_num}V{variant.get('variant_number', '?')}: {wc}w (too short)")
            elif wc > 90:
                violations.append(f"P{pos_num}V{variant.get('variant_number', '?')}: {wc}w (too long)")

    passed = len(violations) == 0
    in_range = len(word_counts) - len(violations)

    if word_counts:
        avg_wc = sum(word_counts) / len(word_counts)
        notes = f"Avg: {avg_wc:.0f} words | {in_range}/{len(word_counts)} in 50-90 range"
        if violations:
            notes += f" | Issues: {', '.join(violations[:3])}"
            if len(violations) > 3:
                notes += f"... +{len(violations)-3} more"
    else:
        notes = "No emails found"

    return ValidationResult(
        dimension="Word Count (50-90)",
        passed=passed,
        score=f"{in_range}/{len(word_counts)}",
        notes=notes,
        critical=True
    )


def validate_qa_scoring(doc: dict) -> ValidationResult:
    """Validate QA scoring presence and completeness."""
    qa = doc.get("qa_scoring", {})

    has_overall = "overall_score" in qa
    dimensions = qa.get("dimensions", [])
    has_6_dimensions = len(dimensions) >= 6
    has_verdict = "verdict" in qa

    # Check dimension structure
    has_notes = all(d.get("notes") for d in dimensions) if dimensions else False

    passed = has_overall and has_6_dimensions and has_verdict
    score_num = sum([has_overall, has_6_dimensions, has_verdict])

    notes_parts = []
    if has_overall:
        notes_parts.append(f"Score: {qa.get('overall_score')}")
    else:
        notes_parts.append("Score: MISSING")
    notes_parts.append(f"Dimensions: {len(dimensions)}/6")
    if has_verdict:
        notes_parts.append(f"Verdict: {qa.get('verdict')}")

    return ValidationResult(
        dimension="QA Scoring",
        passed=passed,
        score=f"{score_num}/3",
        notes=" | ".join(notes_parts),
        critical=True
    )


def validate_strategy_notes(doc: dict) -> ValidationResult:
    """Validate strategy notes completeness."""
    notes = doc.get("strategy_notes", {})

    callouts = notes.get("callouts", [])
    enrichment = notes.get("data_enrichment", [])
    ab_testing = notes.get("ab_testing", [])

    has_callouts = len(callouts) > 0
    has_enrichment = len(enrichment) > 0
    has_ab = len(ab_testing) > 0

    passed = has_callouts and has_enrichment
    score_num = sum([has_callouts, has_enrichment, has_ab])

    notes_text = (f"Callouts: {len(callouts)} | "
                  f"Data Enrichment: {len(enrichment)} | "
                  f"A/B Testing: {len(ab_testing)}")

    return ValidationResult(
        dimension="Strategy Notes",
        passed=passed,
        score=f"{score_num}/3",
        notes=notes_text,
        critical=False
    )


def validate_email_structure(doc: dict) -> ValidationResult:
    """Validate email structure (4 positions, 2-3 variants each)."""
    positions = doc.get("email_positions", [])

    pos_count = len(positions)
    has_4_positions = pos_count >= 4

    # Check variants per position
    variant_counts = []
    recommended_flags = []
    for pos in positions:
        variants = pos.get("variants", [])
        variant_counts.append(len(variants))
        recommended_flags.append(any(v.get("is_recommended") for v in variants))

    has_variants = all(c >= 1 for c in variant_counts)
    has_recommended = all(recommended_flags) if recommended_flags else False

    passed = has_4_positions and has_variants
    total_variants = sum(variant_counts)

    notes_parts = []
    notes_parts.append(f"Positions: {pos_count}/4")
    notes_parts.append(f"Variants: {variant_counts}")
    if has_recommended:
        notes_parts.append("Recommended flags: OK")
    else:
        notes_parts.append("Recommended flags: MISSING")

    return ValidationResult(
        dimension="Email Structure",
        passed=passed,
        score=f"{pos_count}/4 pos, {total_variants} vars",
        notes=" | ".join(notes_parts),
        critical=True
    )


def validate_document(doc_path: Path) -> List[ValidationResult]:
    """Run all validation checks on a campaign document."""
    with open(doc_path, encoding="utf-8") as f:
        doc = json.load(f)

    results = [
        validate_icp_mapping(doc),
        validate_variable_schema(doc),
        validate_word_counts(doc),
        validate_qa_scoring(doc),
        validate_strategy_notes(doc),
        validate_email_structure(doc),
    ]

    return results


def print_report(results: List[ValidationResult], doc_path: Path):
    """Print formatted validation report."""
    print(f"\n{'='*70}")
    print(f"VALIDATION REPORT")
    print(f"File: {doc_path.name}")
    print(f"{'='*70}\n")

    critical_passed = all(r.passed for r in results if r.critical)
    all_passed = all(r.passed for r in results)

    for r in results:
        if r.passed:
            status = "\033[92m PASS\033[0m"  # Green
        elif r.critical:
            status = "\033[91m FAIL\033[0m"  # Red
        else:
            status = "\033[93m WARN\033[0m"  # Yellow

        critical_marker = "*" if r.critical else " "
        print(f"{status} {critical_marker}| {r.dimension:<20} [{r.score}]")
        print(f"       {r.notes}\n")

    print(f"{'='*70}")

    if all_passed:
        print("\033[92m VERDICT: SHIP IT\033[0m - All checks passed")
    elif critical_passed:
        print("\033[93m VERDICT: REVIEW\033[0m - Critical checks passed, minor issues")
    else:
        print("\033[91m VERDICT: NEEDS WORK\033[0m - Critical checks failed")

    print(f"{'='*70}")
    print("* = Critical check (must pass for production)")
    print(f"{'='*70}\n")


def find_latest_output() -> Optional[Path]:
    """Find the most recent output file."""
    scripts_dir = Path(__file__).parent
    output_dir = scripts_dir.parent / "test-output"

    # Try latest.json first
    latest = output_dir / "latest.json"
    if latest.exists():
        return latest

    # Find most recent job directory
    jobs_dir = output_dir / "jobs"
    if not jobs_dir.exists():
        return None

    job_dirs = sorted(jobs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for job_dir in job_dirs:
        doc_path = job_dir / "campaign_document.json"
        if doc_path.exists():
            return doc_path

    return None


def main():
    if len(sys.argv) > 1:
        doc_path = Path(sys.argv[1])
    else:
        doc_path = find_latest_output()

    if not doc_path:
        print("No output file found.")
        print("Usage: python scripts/validate_output.py [path/to/campaign_document.json]")
        print("\nCreate a test job first:")
        print("  python scripts/test_strategy_generation.py")
        sys.exit(1)

    if not doc_path.exists():
        print(f"File not found: {doc_path}")
        sys.exit(1)

    try:
        results = validate_document(doc_path)
        print_report(results, doc_path)

        # Exit with error code if critical checks failed
        critical_passed = all(r.passed for r in results if r.critical)
        sys.exit(0 if critical_passed else 1)

    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error validating document: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
