#!/usr/bin/env python3
"""
Fetch commodity prices and write prices.json for the NFI dashboard.
Runs via GitHub Actions on a schedule. Uses Yahoo Finance (no API key needed).
"""
import json
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Yahoo Finance futures symbols
# These are continuous front-month contracts
SYMBOLS = {
    "corn":     "ZC=F",   # Corn futures ($/bu, but returned in cents)
    "soybeans": "ZS=F",   # Soybean futures ($/bu, returned in cents)
    "wheat":    "ZW=F",   # Wheat futures ($/bu, returned in cents)
    "cattle":   "LE=F",   # Live Cattle futures ($/cwt)
    "hogs":     "HE=F",   # Lean Hogs futures ($/cwt)
    "dairy":    "DC=F",   # Class III Milk futures ($/cwt)
    "crudeOil": "CL=F",   # WTI Crude Oil ($/bbl)
}

# Yahoo returns grains in cents per bushel — these need to be divided by 100
CENTS_TO_DOLLARS = {"corn", "soybeans", "wheat"}

# Static fallbacks (April 2026 closing prices) in case fetch fails
FALLBACK = {
    "corn": 4.52, "soybeans": 11.63, "wheat": 5.98,
    "cattle": 246.32, "hogs": 104.47, "dairy": 18.21,
    "crudeOil": 111.54, "urea": 826,
}


def fetch_yahoo_price(symbol: str) -> float | None:
    """Fetch the latest price for a Yahoo Finance symbol."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; NFI-Dashboard/1.0)"
    })
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        meta = result[0].get("meta", {})
        # Prefer regularMarketPrice, fall back to the last close
        price = meta.get("regularMarketPrice")
        if price is None:
            closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
            closes = [c for c in closes if c is not None]
            if closes:
                price = closes[-1]
        return float(price) if price is not None else None
    except (URLError, HTTPError, KeyError, json.JSONDecodeError, ValueError) as e:
        print(f"  ! Error fetching {symbol}: {e}", file=sys.stderr)
        return None


def main():
    prices = {}
    errors = []

    print(f"Fetching prices at {datetime.now(timezone.utc).isoformat()}")
    for key, symbol in SYMBOLS.items():
        print(f"  Fetching {key} ({symbol})...", end=" ")
        price = fetch_yahoo_price(symbol)
        if price is not None:
            # Grains come back in cents per bushel; convert to dollars
            if key in CENTS_TO_DOLLARS:
                price = price / 100.0
            prices[key] = round(price, 2)
            print(f"${prices[key]}")
        else:
            prices[key] = FALLBACK[key]
            errors.append(key)
            print(f"FAILED, using fallback ${FALLBACK[key]}")

    # Urea isn't on Yahoo Finance — keep a fallback until we find a better source
    prices["urea"] = FALLBACK["urea"]

    # Build metadata
    now = datetime.now(timezone.utc)
    prices["asOf"] = now.strftime("%b %d, %Y %H:%M UTC")
    prices["fetchedAt"] = now.isoformat()

    if errors:
        prices["notes"] = (
            f"Auto-updated via GitHub Actions. {len(errors)} commodity fetches failed "
            f"and used fallback values: {', '.join(errors)}. Urea is always a static estimate."
        )
    else:
        prices["notes"] = (
            "Auto-updated via GitHub Actions using Yahoo Finance futures data. "
            "Urea fertilizer price is a static estimate (no free API available)."
        )

    # Write to prices.json in the repo root
    with open("prices.json", "w") as f:
        json.dump(prices, f, indent=2)

    print(f"\nWrote prices.json with {len([k for k in prices if k not in ('asOf','fetchedAt','notes')])} prices")
    print(json.dumps(prices, indent=2))

    # Exit non-zero only if EVERY fetch failed (partial failures are OK)
    if len(errors) == len(SYMBOLS):
        print("ERROR: All fetches failed", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
