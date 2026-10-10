"""CLI entrypoint for running the DevMemory AI Engine reproducible evaluation harness."""

import argparse
import os
import sys
from ai_engine.evaluation.evaluator import export_evaluation_reports, run_evaluation


def main() -> int:
    parser = argparse.ArgumentParser(description="DevMemory AI Engine Reproducible Evaluation Runner")
    parser.add_argument(
        "--live-llm",
        action="store_true",
        help="Run live Groq LLM queries if GROQ_API_KEY is configured (defaults to deterministic offline mock)",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Directory to save evaluation reports (default: reports)",
    )
    args = parser.parse_args()

    if args.live_llm and not os.getenv("GROQ_API_KEY"):
        print("[!] Note: --live-llm requested, but GROQ_API_KEY is not configured in environment.")
        print("    Live evaluation skipped; running with deterministic offline MockLLMClient.")

    print(f"[*] Running DevMemory AI Engine Evaluation (live_llm={args.live_llm})...")
    metrics, details = run_evaluation(live_llm=args.live_llm)

    json_path, md_path = export_evaluation_reports(metrics, details, output_dir=args.output_dir)

    print("\n[+] Evaluation Completed Successfully!")
    print(f"    Total Scenarios: {metrics.total_scenarios}")
    print(f"    Passed:          {metrics.passed_scenarios}")
    print(f"    Failed:          {metrics.failed_scenarios}")
    print(f"    Quality Pass Rate: {metrics.to_dict()['pass_rate_percent']}%")
    print(f"    JSON Report:     {json_path}")
    print(f"    Markdown Report: {md_path}\n")

    return 0 if metrics.failed_scenarios == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
