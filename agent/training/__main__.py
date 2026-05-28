"""CLI for agent training data extraction.

Subcommands:
  pairs        — preference pairs from labeled reviews (legacy)
  feedback     — SFT + DPO data built from /agent good|bad ratings
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent.training.feedback import (
    build_dpo_pairs,
    build_sft,
    join_feedback,
    write_jsonl,
)
from agent.training.pairs import build_pairs_from_reviews, write_pairs_jsonl


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m agent.training")
    sub = parser.add_subparsers(dest="command", required=True)

    pairs_p = sub.add_parser("pairs", help="Build preference pairs from labeled reviews")
    pairs_p.add_argument("reviews", type=Path)
    pairs_p.add_argument("out", type=Path)

    fb_p = sub.add_parser(
        "feedback",
        help="Convert /agent good|bad ratings into SFT and DPO datasets",
    )
    fb_p.add_argument(
        "--feedback",
        type=Path,
        default=None,
        help="Path to agent-feedback.jsonl (defaults to data/agent-feedback.jsonl)",
    )
    fb_p.add_argument(
        "--audit",
        type=Path,
        default=None,
        help="Path to agent-audit.log (defaults to data/agent-audit.log)",
    )
    fb_p.add_argument(
        "--sft-out",
        type=Path,
        default=Path("training/sft-from-feedback.jsonl"),
    )
    fb_p.add_argument(
        "--dpo-out",
        type=Path,
        default=Path("training/dpo-from-feedback.jsonl"),
    )
    fb_p.add_argument(
        "--system-prompt",
        type=Path,
        default=Path("agent/prompts/system.md"),
        help="Inject this file as the system message in SFT examples.",
    )
    fb_p.add_argument(
        "--include-bad-as-negative",
        action="store_true",
        help="Emit 'bad' rows in the SFT file tagged with meta.negative=true.",
    )
    fb_p.add_argument(
        "--report",
        action="store_true",
        help="Print summary stats instead of writing files.",
    )

    args = parser.parse_args(argv)

    if args.command == "pairs":
        pairs = build_pairs_from_reviews(args.reviews.resolve())
        n = write_pairs_jsonl(pairs, args.out.resolve())
        print(f"pairs={n} path={args.out}")
        if n == 0:
            raise SystemExit(1)
        return

    if args.command == "feedback":
        rows = list(join_feedback(args.feedback, args.audit))
        good = sum(1 for r in rows if r.rating == "good")
        bad = sum(1 for r in rows if r.rating == "bad")
        if args.report:
            print(
                json.dumps(
                    {"rows": len(rows), "good": good, "bad": bad},
                    indent=2,
                )
            )
            return
        system_prompt = (
            args.system_prompt.read_text(encoding="utf-8")
            if args.system_prompt.exists()
            else None
        )
        sft = build_sft(
            rows,
            system_prompt=system_prompt,
            include_bad_as_negative=args.include_bad_as_negative,
        )
        dpo = build_dpo_pairs(rows)
        sft_n = write_jsonl(sft, args.sft_out)
        dpo_n = write_jsonl(dpo, args.dpo_out)
        print(
            json.dumps(
                {
                    "rows": len(rows),
                    "good": good,
                    "bad": bad,
                    "sft_examples": sft_n,
                    "dpo_pairs": dpo_n,
                    "sft_out": str(args.sft_out),
                    "dpo_out": str(args.dpo_out),
                },
                indent=2,
            )
        )
        return


if __name__ == "__main__":
    main(sys.argv[1:])
