"""脱敏召回跑分脚本：输出 JSON 指标（不联网、可复跑）。

用法：
    backend/.venv/Scripts/python.exe backend/scripts/eval_anonymize.py
    backend/.venv/Scripts/python.exe backend/scripts/eval_anonymize.py --samples 300 --out metrics.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.security import anonymize  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="脱敏库召回/误报跑分")
    parser.add_argument("--samples", type=int, default=200, help="合成正样本条数（默认 200）")
    parser.add_argument("--negatives", type=int, default=200, help="合成负样本条数（默认 200）")
    parser.add_argument("--out", type=str, default="", help="可选：把 JSON 写入文件")
    args = parser.parse_args()

    samples = anonymize.generate_samples(args.samples)
    negatives = anonymize.generate_negatives(args.negatives)
    metrics = anonymize.evaluate(samples, negatives)
    payload = json.dumps(metrics, ensure_ascii=False, indent=2)
    print(payload)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
