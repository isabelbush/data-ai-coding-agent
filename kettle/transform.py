from datetime import datetime


def clean_rows(rows, branch, eur_rate=None):
    cleaned = []
    seen = set()
    for row in rows:
        try:
            if len(row) == 0 or row[0] == "":
                continue

            if branch == "dublin":
                txn_id, ts, till, product, qty, price = row[5], row[0], row[4], row[1], row[3], row[2]
            else:
                txn_id, ts, till, product, qty, price = row

            if branch == "leeds" or branch == "york":
                sold_at = datetime.strptime(ts.strip(), "%d/%m/%Y %H:%M")
            else:
                sold_at = datetime.fromisoformat(ts.strip())

            # some tills export negative numbers by mistake
            qty = abs(int(qty))

            if branch == "manchester":
                price_pence = int(price)
            else:
                price_pence = int(round(float(price) * 100))

            if branch == "dublin":
                price_pence = int(round(price_pence * eur_rate))  # convert to GBP

            product = product.strip().title()

            key = (branch, sold_at, product)
            if key in seen:
                continue
            seen.add(key)

            cleaned.append({
                "transaction_id": txn_id,
                "branch": branch,
                "sold_at": sold_at.isoformat(),
                "till_id": till,
                "product": product,
                "quantity": qty,
                "unit_price_pence": price_pence,
                "line_total_pence": qty * price_pence,
            })
        except:
            pass
    return cleaned


# TODO(Andy): pull the parsing logic out of clean_rows into the helpers below so
# it can be tested. Haven't got round to it yet - they just raise for now.


def format_pence(pence):
    """Format an integer number of pence as a pounds string for reports.

    >>> format_pence(340)
    '£3.40'
    >>> format_pence(-120)
    '-£1.20'
    """
    sign = "-" if pence < 0 else ""
    pounds, pence = divmod(abs(pence), 100)
    return f"{sign}£{pounds}.{pence:02d}"


def parse_price_to_pence(value, unit):
    """Turn a till price string into an integer number of pence (or cents).

    `unit` is "pounds" for tills that export prices like "3.40" and "pence"
    for tills that export prices like "340". Surrounding whitespace is ignored.
    Raise ValueError if the value is not a valid price (including fractions
    of a penny, e.g. "3.405" pounds or "340.5" pence).
    """
    raise NotImplementedError


def parse_till_timestamp(value):
    """Parse a till timestamp into a datetime.

    Accepts the UK format "14/09/2026 08:15" (day first!) and ISO 8601
    ("2026-09-14T08:15:00"). Surrounding whitespace is ignored.
    Raise ValueError for anything else.
    """
    value = value.strip()
    for fmt in ("%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"Unrecognised till timestamp: {value!r}")


def normalise_product_name(raw_name, products):
    """Match a messy till product name to its canonical catalogue name.

    `products` is the list loaded from data/reference/products.json. Matching
    ignores case, surrounding whitespace and hyphens-vs-spaces, and also
    checks each product's aliases. Return None if there is no match.

    >>> normalise_product_name(" flat-white ", products)
    'Flat White'
    """

    def key(name):
        return " ".join(name.replace("-", " ").lower().split())

    wanted = key(raw_name)
    if not wanted:
        return None
    for product in products:
        if wanted in (key(n) for n in [product["name"], *product.get("aliases", [])]):
            return product["name"]
    return None
