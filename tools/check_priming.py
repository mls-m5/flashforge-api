#!/usr/bin/env python3
"""Read-only nominal first-layer priming diagnostics; never a print-safety gate."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finderlab.priming_review import review_priming, candidate_issues

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    args = parser.parse_args()
    try:
        report = review_priming(args.file)
        report['candidate_issues'] = candidate_issues(report)
        print(json.dumps(report, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(1, f'No complete priming report: {exc}\n')
