#!/usr/bin/env python3
"""
Irreversibly pseudonymise every personal field in the generated CSVs, in place.

- Names, emails and phone numbers -> 16-hex-char tokens: SHA-256 of
  (random secret salt + field type + value). The salt is created fresh for
  each run and never saved, so tokens cannot be reversed, recomputed or
  matched against outside data (a plain unsalted hash of an email could be
  matched by hashing candidate emails; a discarded salt prevents that).
- The same value always gets the same token within one run, so a person's
  Lead, Account and Contact still match and duplicates can still be found.
- Addresses need no treatment: towns, state codes and ZIPs are fictional by construction.
- Opportunity names embed the customer name; that part is tokenised too.
- Business data (showroom addresses, campaigns, vehicles) is not personal and is left as is.

Usage: python anonymize_pii.py DATA_DIR
"""
import os
import secrets
import sys

import duckdb

d = sys.argv[1]
SALT = secrets.token_hex(32)          # never written anywhere
con = duckdb.connect()
con.execute("SET threads=2; SET preserve_insertion_order=true")


def h(col, kind):
    return (f"CASE WHEN {col} IS NULL THEN NULL ELSE "
            f"left(sha256('{SALT}' || '{kind}:' || {col}), 16) END")


RULES = {
    "Lead": {"FirstName": h("FirstName", "name"), "LastName": h("LastName", "name"),
             "Email": h("Email", "email"), "MobilePhone": h("MobilePhone", "phone")},
    "Account": {"FirstName": h("FirstName", "name"), "LastName": h("LastName", "name"),
                "Name": h("Name", "name"), "PersonEmail": h("PersonEmail", "email"),
                "PersonMobilePhone": h("PersonMobilePhone", "phone")},
    "Contact": {"FirstName": h("FirstName", "name"), "LastName": h("LastName", "name"),
                "Email": h("Email", "email"), "MobilePhone": h("MobilePhone", "phone")},
    "User": {"FirstName": h("FirstName", "name"), "LastName": h("LastName", "name"),
             "Name": h("Name", "name"), "Email": h("Email", "email")},
    # "First Last - 2025 Tarvessa Orvik LX" -> "<token> - 2025 Tarvessa Orvik LX"
    "Opportunity": {"Name": h("split_part(Name, ' - ', 1)", "name")
                            + " || ' - ' || substr(Name, length(split_part(Name, ' - ', 1)) + 4)"},
}

for table, rules in RULES.items():
    path = os.path.join(d, f"{table}.csv")
    cols = [r[0] for r in con.execute(
        f"DESCRIBE SELECT * FROM read_csv('{path}', header=true, all_varchar=true)").fetchall()]
    select = ", ".join(f"{rules[c]} AS \"{c}\"" if c in rules else f"\"{c}\"" for c in cols)
    tmp = path + ".tmp"
    con.execute(f"COPY (SELECT {select} FROM read_csv('{path}', header=true, all_varchar=true)) "
                f"TO '{tmp}' (HEADER, DELIMITER ',')")
    os.replace(tmp, path)
    print(f"anonymised {table}: {', '.join(rules)}")
