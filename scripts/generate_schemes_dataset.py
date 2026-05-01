from __future__ import annotations

import json
from pathlib import Path

from backend.rag_service import EMBEDDED_SCHEMES


def main() -> None:
    output_path = Path(__file__).resolve().parent.parent / "datasets" / "schemes_small.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(EMBEDDED_SCHEMES, file, indent=2, ensure_ascii=False)
    print(f"Wrote {len(EMBEDDED_SCHEMES)} lightweight schemes to {output_path}")


if __name__ == "__main__":
    main()