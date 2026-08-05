"""Validate a CDSCO export against the ICH ICSR v2.1 DTD.

The DTD is not shipped with this repo. It is ICH M2 public-domain but its
header states "No commercial distribution is allowed", so fetch your own copy:

    python scripts/validate_cdsco_xml.py --fetch-dtd ./ich-icsr-v2.1.dtd

Then validate a generated export:

    python scripts/validate_cdsco_xml.py export.xml --dtd ./ich-icsr-v2.1.dtd

Set CDSCO_DTD_PATH in .env to the same file and every export is validated at
generation time.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

EMA_DTD_URL = "https://eudravigilance.ema.europa.eu/dtd/icsr21xml.dtd"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fetch_dtd(dest: str) -> int:
    import urllib.request

    print(f"Fetching {EMA_DTD_URL}")
    data = urllib.request.urlopen(EMA_DTD_URL, timeout=60).read()
    Path(dest).write_bytes(data)
    print(f"Wrote {len(data)} bytes to {dest}")
    print("Do not commit this file — ICH forbids commercial redistribution.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("xml", nargs="?", help="XML file to validate")
    ap.add_argument("--dtd", help="Path to ich-icsr-v2.1.dtd")
    ap.add_argument("--fetch-dtd", metavar="DEST", help="Download the DTD and exit")
    args = ap.parse_args()

    if args.fetch_dtd:
        return fetch_dtd(args.fetch_dtd)
    if not args.xml or not args.dtd:
        ap.error("both an XML file and --dtd are required")

    from app.services.cdsco_xml import validate_ichicsr

    xml_text = Path(args.xml).read_text(encoding="utf-8")
    ok, errors = validate_ichicsr(xml_text, args.dtd)
    if ok:
        print(f"VALID against ICH ICSR v2.1 DTD: {args.xml}")
        return 0
    print(f"INVALID: {args.xml}")
    for e in errors:
        print(f"  - {e}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
