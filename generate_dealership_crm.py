#!/usr/bin/env python3
"""
Synthetic Salesforce-style CRM for a car dealership group (B2C).

"Quillon Auto Group" runs 12 showrooms across the US (4 time zones) and sells vehicles from a
fictional manufacturer, Tarvessa Motors (new, used and certified pre-owned).
Shoppers arrive as Leads (web forms, marketplaces, walk-ins, phone calls...),
BDC reps and sales consultants work them (calls, SMS, email, appointments),
showroom visits become Opportunities (needs assessment -> test drive ->
proposal -> negotiation -> financing) and about 15% of leads end in a
purchase (Closed Won + vehicle delivery).

Output: Salesforce-shaped CSVs (object names, field API names, real 18-char
Id checksums, Salesforce export datetime format, times stored in UTC).

Usage:
    python generate_dealership_crm.py OUT_DIR [--leads 500000] [--seed 7]
                                       [--shards 20] [--workers 2]
"""
import argparse
import math
import os
import shutil
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd
from faker.providers.person.en_US import Provider as NameProvider

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--leads", type=int, default=500000)
ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--shards", type=int, default=20)
ap.add_argument("--workers", type=int, default=2)
ap.add_argument("--keep-pii", action="store_true", help="skip hashing of names/emails/phones")
ARGS = ap.parse_args()
SEED = ARGS.seed
G = np.random.default_rng(SEED)          # global generator (setup only)

# ============================================================== calendar
D0 = pd.Timestamp("2022-12-01")          # local-date index origin
DATES = pd.date_range(D0, "2027-03-31")
ND = len(DATES)
T0 = D0.value / 1e9                       # epoch seconds of 2022-12-01 00:00 UTC
def dix(ts):
    return int((pd.Timestamp(ts) - D0).days)


START_D = dix("2023-01-01")
ASOF_D = dix("2026-09-30")
ASOF = pd.Timestamp("2026-10-01 03:59:59").value / 1e9   # extract: midnight Sep 30 Eastern (UTC epoch)


def _thanksgiving(y):
    d = pd.Timestamp(year=y, month=11, day=1)
    return d + pd.Timedelta(days=(3 - d.weekday()) % 7 + 21)


HOLIDAYS = set()
for y in range(2022, 2028):
    for h in (pd.Timestamp(year=y, month=1, day=1), _thanksgiving(y), pd.Timestamp(year=y, month=12, day=25)):
        if D0 <= h <= DATES[-1]:
            HOLIDAYS.add(dix(h))
DATE_STR = np.array(DATES.strftime("%Y-%m-%d"))
WEEKDAY = DATES.weekday.values
MONTH = DATES.month.values
YEAR = DATES.year.values

# sales events (also drive the "Sales Event" lead source)
EVENT_DEFS = [("Presidents' Day Sales Event", 2, 10, 11), ("Spring Sales Event", 3, 15, 17),
              ("Memorial Day Sales Event", 5, 20, 12), ("Fourth of July Sales Event", 6, 28, 10),
              ("Labor Day Sales Event", 8, 28, 11), ("Model Year-End Clearance", 9, 15, 31),
              ("Black Friday Sales Event", 11, 20, 11), ("Year-End Sales Event", 12, 15, 17)]
EVENT_DAY = np.full(ND, -1)   # campaign index per day (filled later)

# ============================================================== Ids
B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
SUFFIX = "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"


def _b62(n, w):
    s = []
    for _ in range(w):
        s.append(B62[n % 62])
        n //= 62
    return "".join(reversed(s))


def _checksum(id15):
    out = []
    for i in range(3):
        f = 0
        for j, ch in enumerate(id15[i * 5:i * 5 + 5]):
            if "A" <= ch <= "Z":
                f |= 1 << j
        out.append(SUFFIX[f])
    return id15 + "".join(out)


class IdGen:
    """Sequential, Salesforce-checksummed Ids; the shard is baked in so shards never collide."""
    def __init__(self, shard):
        self.sc = B62[shard]
        self.n = {}

    def __call__(self, prefix):
        n = self.n.get(prefix, 2_000_000_000_000) + 1 + int(R.integers(0, 3))
        self.n[prefix] = n
        return _checksum(prefix + "Hx" + self.sc + _b62(n, 9))


R = G                                   # per-process generator (re-bound in workers)
GID = IdGen(61)

# ============================================================== showrooms
# name, city, zip, type, opened, nearby (city, zip3/zip prefix) for customers
# FICTIONAL geography: invented towns, invented 2-letter state codes (none is a USPS code) and
# ZIP codes from 00100-00499 (prefixes 001-004 have never been assigned by USPS).
# Real IANA time zones are used only to drive local business hours; Sunday closures mimic
# state "blue laws" for car sales.
# name, city, state, zip, type, opened, time zone, open Sundays?, area codes, nearby [(town, zip base)]
STATE_NAMES = {}
SHOWROOMS = [
    ("Quillon Auto Larkhaven", "Larkhaven", "QX", "00100", "Flagship", "2014-03-01", "America/Chicago", False,
     ['214', '469'], [('Larkhaven', 100), ('Dunmoor Springs', 108), ('Feltwick', 116), ('Orrenby', 124)]),
    ("Quillon Auto Port Valerne", "Port Valerne", "QX", "00132", "Flagship", "2015-09-01", "America/Chicago", False,
     ['713', '832'], [('Port Valerne', 132), ('Sablecross', 140), ('Kestrimont', 148), ('Wynnfold', 156)]),
    ("Quillon Auto Coralmont Bay", "Coralmont Bay", "ZR", "00164", "Flagship", "2016-06-01", "America/Los_Angeles", True,
     ['310', '424'], [('Coralmont Bay', 164), ('Seravelle', 172), ('Tidewick', 180), ('Mirandel', 188)]),
    ("Quillon Auto Sunvesta", "Sunvesta", "XV", "00196", "Standard", "2017-04-01", "America/Phoenix", True,
     ['480', '602'], [('Sunvesta', 196), ('Dravenpoint', 204), ('Copperlane', 212), ('Tolluca', 220)]),
    ("Quillon Auto Velmont Hills", "Velmont Hills", "ZR", "00228", "Standard", "2019-08-01", "America/Los_Angeles", True,
     ['408', '669'], [('Velmont Hills', 228), ('Orchardine', 236), ('Castelbrook', 244), ('Linnaria', 252)]),
    ("Quillon Auto Cedarwyn", "Cedarwyn", "JD", "00260", "Standard", "2018-02-01", "America/Los_Angeles", True,
     ['425', '206'], [('Cedarwyn', 260), ('Fallowmere', 268), ('Harrowby Lake', 276), ('Pinewhistle', 284)]),
    ("Quillon Auto Granitefell", "Granitefell", "KW", "00292", "Standard", "2017-10-01", "America/Denver", False,
     ['303', '720'], [('Granitefell', 292), ('Highmarrow', 300), ('Aspendrell', 308), ('Silvercrag', 316)]),
    ("Quillon Auto Brackenford", "Brackenford", "QO", "00324", "Standard", "2018-09-01", "America/Chicago", False,
     ['847', '630'], [('Brackenford', 324), ('Elmsworth Park', 332), ('Northvane', 340), ('Ruddock Grove', 348)]),
    ("Quillon Auto Magnolind", "Magnolind", "XB", "00356", "Standard", "2019-03-01", "America/New_York", True,
     ['770', '678'], [('Magnolind', 356), ('Peachmire', 364), ('Thornhaven', 372), ('Calderwyn', 380)]),
    ("Quillon Auto Palmora", "Palmora", "ZL", "00388", "Standard", "2020-05-01", "America/New_York", True,
     ['407', '321'], [('Palmora', 388), ('Lakeshire Point', 396), ('Sunmerro', 404), ('Brivenna Key', 412)]),
    ("Quillon Auto Queensmarch", "Queensmarch", "YQ", "00420", "Satellite", "2024-09-03", "America/New_York", True,
     ['704', '980'], [('Queensmarch', 420), ('Hollowmere', 428), ('Ravelmoor', 436), ('Dunstanbrook', 444)]),
    ("Quillon Auto Kingsbrae", "Kingsbrae", "JX", "00452", "Satellite", "2025-04-07", "America/New_York", False,
     ['610', '484'], [('Kingsbrae', 452), ('Norrowgate', 460), ('Ashkettle', 468), ('Fairwyn', 476)]),
]
STATE_NAMES.update({'QX': 'Corvain', 'ZR': 'Pellandra', 'XV': 'Durnhal', 'JD': 'Wendmark', 'KW': 'Halcrest', 'QO': 'Merrowfield', 'XB': 'Tallisand', 'ZL': 'Calvessa', 'YQ': 'Brennoch', 'JX': 'Ardwyn'})
TZ_LABEL = {"America/Chicago": "Central", "America/Los_Angeles": "Pacific", "America/Denver": "Mountain",
            "America/Phoenix": "Mountain (no DST)", "America/New_York": "Eastern"}
NS = len(SHOWROOMS)
SR_ID = [GID("a0S") for _ in range(NS)]
SR_IDX = {x: i for i, x in enumerate(SR_ID)}
SR_OPEN_D = np.array([max(dix(s[5]), 0) for s in SHOWROOMS])
SR_W = np.array([{"Flagship": 1.6, "Standard": 1.0, "Satellite": .65}[s[4]] for s in SHOWROOMS])
# per-showroom UTC offset and opening hours for every local date
OFFM = np.zeros((NS, ND))
OPEN_SM = np.full((NS, ND), -1.0)
CLOSE_SM = np.full((NS, ND), -1.0)
for s, sr_ in enumerate(SHOWROOMS):
    noon = pd.DatetimeIndex(DATES + pd.Timedelta(hours=12)).tz_localize(sr_[6])
    OFFM[s] = [x.utcoffset().total_seconds() for x in noon]
    for i in range(ND):
        if i in HOLIDAYS:
            continue
        wd = WEEKDAY[i]
        if wd == 6:
            if sr_[7]:
                OPEN_SM[s, i], CLOSE_SM[s, i] = 11 * 3600, 17 * 3600
        else:
            OPEN_SM[s, i], CLOSE_SM[s, i] = 9 * 3600, (19 if wd == 5 else 20) * 3600
OPEN_DAYM = OPEN_SM >= 0

# ============================================================== vehicles (Product2)
CATALOG = [  # model, body, fuel, [(trim, msrp)], popularity
    ("Zevi", "Hatchback", "Gasoline", [("S", 20400), ("SE", 22900)], .05),
    ("Ostra", "Sedan", "Gasoline", [("LX", 23500), ("SE", 26200), ("Sport", 29400)], .14),
    ("Kaveno", "Sedan", "Gasoline", [("LX", 28300), ("Hybrid", 32100), ("Touring", 36400)], .10),
    ("Orvik", "SUV", "Gasoline", [("LX", 30200), ("EX", 34100), ("Hybrid", 37300)], .24),
    ("Talmar", "SUV", "Gasoline", [("LX", 39400), ("EX", 45200), ("Platinum", 54300)], .15),
    ("Draxen", "Truck", "Gasoline", [("Work", 38200), ("Sport", 46400), ("Limited", 58700)], .16),
    ("Nuvessa", "Minivan", "Hybrid", [("LX", 37600), ("Touring", 45300)], .06),
    ("Elarion", "SUV", "Electric", [("Standard Range", 42900), ("Long Range", 49500), ("Performance", 57800)], .10),
]
PROD = []
for model, body, fuel, trims, pop in CATALOG:
    for k, (trim, msrp) in enumerate(trims):
        PROD.append(dict(Id=GID("01t"), Name=f"Tarvessa {model} {trim}", ProductCode=f"TRV-{model[:3].upper()}-{k + 1}",
                         Family=body, Make__c="Tarvessa", Model__c=model, Trim__c=trim,
                         Fuel_Type__c="Hybrid" if trim == "Hybrid" else fuel,
                         MSRP__c=msrp, IsActive=True, CreatedDate=T0 - 400 * 86400,
                         _pop=pop / len(trims) * (1.25 if k == 1 else 1.0), _ev=fuel == "Electric"))
NP = len(PROD)
P_MSRP = np.array([p["MSRP__c"] for p in PROD], float)
P_MODEL = [p["Model__c"] for p in PROD]
P_COND_OK = np.array([True] * NP)
MODEL_PRODS = {}
for i, p in enumerate(PROD):
    MODEL_PRODS.setdefault(p["Model__c"], []).append(i)

# ============================================================== users & roles
ROLES = ["VP of Sales", "Marketing Manager", "General Manager", "Sales Manager", "F&I Manager",
         "Sales Consultant", "BDC Representative"]
ROLE_PARENT = {"Marketing Manager": "VP of Sales", "General Manager": "VP of Sales",
               "Sales Manager": "General Manager", "F&I Manager": "General Manager",
               "Sales Consultant": "Sales Manager", "BDC Representative": "Sales Manager"}
ROLE_ID = {r: GID("00E") for r in ROLES}
USERS = []
first_names = list(NameProvider.first_names.keys()) if isinstance(NameProvider.first_names, dict) \
    else list(NameProvider.first_names)
last_names = list(NameProvider.last_names.keys()) if isinstance(NameProvider.last_names, dict) \
    else list(NameProvider.last_names)
FN = np.array(first_names)
LN = np.array(last_names)


def add_user(role, sr, hire_d, term_d):
    fn, ln = str(G.choice(FN)), str(G.choice(LN))
    u = dict(Id=GID("005"), FirstName=fn, LastName=ln, Name=f"{fn} {ln}",
             Email=f"{fn.lower()}.{ln.lower()}{len(USERS)}@quillonauto.example", Title=role,
             Department="Marketing" if role == "Marketing Manager" else "Sales", UserRoleId=ROLE_ID[role],
             ManagerId=None, Showroom__c=SR_ID[sr] if sr is not None else None,
             IsActive=term_d is None, Hire_Date__c=hire_d, Termination_Date__c=term_d,
             CreatedDate=T0 + hire_d * 86400 + 15 * 3600,
             _role=role, _sr=sr, _skill=float(G.normal(0, .35)))
    USERS.append(u)
    return u


VP = add_user("VP of Sales", None, dix("2014-01-06") if False else -2000, None)
MKT = add_user("Marketing Manager", None, -900, None)
SEATS = {"Flagship": {"Sales Consultant": 16, "BDC Representative": 6},
         "Standard": {"Sales Consultant": 12, "BDC Representative": 4},
         "Satellite": {"Sales Consultant": 8, "BDC Representative": 3}}
TENURE = {"Sales Consultant": 600, "BDC Representative": 480, "General Manager": 2400,
          "Sales Manager": 1500, "F&I Manager": 1600}
for s, sr in enumerate(SHOWROOMS):
    seats = dict(SEATS[sr[4]])
    seats.update({"General Manager": 1, "Sales Manager": 1, "F&I Manager": 2 if sr[4] == "Flagship" else 1})
    first_possible = SR_OPEN_D[s] if SR_OPEN_D[s] > 0 else -1500
    for role, n in seats.items():
        for _ in range(n):
            if SR_OPEN_D[s] > 0:     # new showroom: staffed a few weeks before opening
                hire = SR_OPEN_D[s] - int(G.integers(14, 35))
            else:
                hire = -int(G.integers(30, 1400))
            while hire <= ASOF_D:
                tenure = int(G.exponential(TENURE[role])) + 30
                term = hire + tenure
                if term > ASOF_D:
                    add_user(role, s, hire, None)
                    break
                if term >= START_D - 60:
                    add_user(role, s, hire, term)
                hire = term + int(G.integers(10, 50))          # seat vacancy, then a new hire
for u in USERS:
    if u["_role"] in ("Sales Consultant", "BDC Representative", "F&I Manager"):
        mgr = [m for m in USERS if m["_sr"] == u["_sr"] and m["_role"] == ("Sales Manager" if u["_role"] != "F&I Manager" else "General Manager")]
    elif u["_role"] == "Sales Manager":
        mgr = [m for m in USERS if m["_sr"] == u["_sr"] and m["_role"] == "General Manager"]
    elif u["_role"] in ("General Manager", "Marketing Manager"):
        mgr = [VP]
    else:
        mgr = []
    if mgr:   # the manager in seat at the user's hire date (else the latest)
        cand = [m for m in mgr if m["Hire_Date__c"] <= max(u["Hire_Date__c"], START_D)]
        u["ManagerId"] = (cand[-1] if cand else mgr[0])["Id"]
NU = len(USERS)
U_SKILL = np.array([u["_skill"] for u in USERS])
U_HIRE = np.array([u["Hire_Date__c"] for u in USERS])
U_ID = [u["Id"] for u in USERS]
# active users per (showroom, role, day)
ACTIVE = {}
for i, u in enumerate(USERS):
    if u["_sr"] is None:
        continue
    lo = max(u["Hire_Date__c"], 0)
    hi = min(u["Termination_Date__c"] if u["Termination_Date__c"] is not None else ND - 1, ND - 1)
    for d in range(lo, hi + 1):
        ACTIVE.setdefault((u["_sr"], u["_role"], d), []).append(i)

# ============================================================== campaigns
CAMPS = []


def add_campaign(name, ctype, d0, d1, cost):
    st = "Completed" if d1 < ASOF_D else ("In Progress" if d0 <= ASOF_D else "Planned")
    CAMPS.append(dict(Id=GID("701"), Name=name, Type=ctype, Status=st, StartDate=d0, EndDate=d1,
                      IsActive=st == "In Progress", BudgetedCost=round(cost, -2),
                      ActualCost=round(cost * G.uniform(.88, 1.12), -2) if st != "Planned" else None,
                      OwnerId=MKT["Id"], CreatedDate=T0 + (d0 - int(G.integers(20, 50))) * 86400 + 16 * 3600))
    return len(CAMPS) - 1


CAMP_DAY = {t: np.full(ND, -1) for t in ("Sales Event", "Paid Search", "Social Media",
                                          "Third-Party Marketplace", "OEM Program", "Referral Program")}
for y in (2023, 2024, 2025, 2026):
    for name, mo, day, length in EVENT_DEFS:
        d0 = dix(pd.Timestamp(year=y, month=mo, day=day))
        d1 = d0 + length - 1
        if d0 > ASOF_D:
            continue
        ci = add_campaign(f"{name} {y}", "Sales Event", d0, d1, G.uniform(60000, 140000))
        CAMP_DAY["Sales Event"][d0:d1 + 1] = ci
    for ctype, cost in (("OEM Program", 90000), ("Referral Program", 25000)):
        d0, d1 = dix(f"{y}-01-01"), dix(f"{y}-12-31")
        ci = add_campaign(f"{'Tarvessa OEM Lead Program' if ctype == 'OEM Program' else 'Customer Referral Program'} {y}",
                          ctype, d0, d1, cost * G.uniform(.9, 1.1))
        CAMP_DAY[ctype][d0:d1 + 1] = ci
for q in pd.period_range("2023Q1", "2026Q3", freq="Q"):
    d0, d1 = dix(q.start_time), dix(q.end_time.normalize())
    for ctype, nm, cost in (("Paid Search", "Paid Search - Google Ads", 70000),
                            ("Social Media", "Social Media - Meta & TikTok Ads", 45000),
                            ("Third-Party Marketplace", "Third-Party Marketplace Listings", 85000)):
        ci = add_campaign(f"{nm} {q}", ctype, d0, d1, cost * G.uniform(.85, 1.15))
        CAMP_DAY[ctype][d0:d1 + 1] = ci
EVENT_DAY = CAMP_DAY["Sales Event"]
IN_EVENT = EVENT_DAY >= 0

# ============================================================== lead sources
#            share, effect, class, campaign type
SOURCES = {
    "Website":                 (.21, .15, "internet", None),
    "Third-Party Marketplace": (.19, -.35, "internet", "Third-Party Marketplace"),
    "OEM Referral":            (.08, .05, "internet", "OEM Program"),
    "Walk-In":                 (.14, .05, "showroom", None),
    "Phone Inquiry":           (.08, .30, "showroom", None),
    "Paid Search":             (.08, -.10, "internet", "Paid Search"),
    "Social Media":            (.08, -.60, "internet", "Social Media"),
    "Referral":                (.04, .70, "internet", "Referral Program"),
    "Sales Event":             (.06, .20, "event", "Sales Event"),
    "Chat":                    (.04, -.20, "internet", None),
}
SRC = list(SOURCES)
SRC_EFF = np.array([SOURCES[s][1] for s in SRC])
REPEAT_EFF = .9
S_WALK, S_PHONE = SRC.index("Walk-In"), SRC.index("Phone Inquiry")
S_REPEAT = len(SRC)          # assigned during simulation
SRC_NAMES = SRC + ["Repeat Customer"]

# ============================================================== people & leads (vectorised)
t_setup = time.time()
N = ARGS.leads
k_per = G.choice([1, 2, 3], size=int(N * .95) + 10, p=[.9, .08, .02])
cs = np.cumsum(k_per)
NPERS = int(np.searchsorted(cs, N) + 1)
k_per = k_per[:NPERS]
k_per[-1] -= cs[NPERS - 1] - N
P_SR = G.choice(NS, size=NPERS, p=SR_W / SR_W.sum())
P_FN = G.integers(len(FN), size=NPERS)
P_LN = G.integers(len(LN), size=NPERS)
P_DIST = np.clip(G.lognormal(np.log(9), .75, NPERS), .5, 180)
P_CREDIT = G.choice(5, size=NPERS, p=[.20, .40, .20, .15, .05])      # super-prime .. deep subprime
P_LATENT = G.normal(0, .3, NPERS)
P_CITY = G.integers(4, size=NPERS)
P_ZIP = G.integers(0, 100, size=NPERS)
P_EMAILDOM = G.choice(["gmail.com", "yahoo.com", "outlook.com", "icloud.com", "hotmail.com", "att.net"],
                      size=NPERS, p=[.48, .17, .12, .12, .07, .04])
P_EMAILNUM = np.where(G.random(NPERS) < .55, G.integers(1, 999, NPERS), -1)
P_PHONE = G.integers(2_000_000, 9_999_999, NPERS)
P_AREA = G.integers(0, 3, NPERS)

L_P = np.repeat(np.arange(NPERS), k_per)
L_IDX_IN_P = np.concatenate([np.arange(k) for k in k_per])
L_SRC = G.choice(len(SRC), size=N, p=np.array([SOURCES[s][0] for s in SRC]) / sum(SOURCES[s][0] for s in SRC))
L_SR = P_SR[L_P].copy()
other = (L_IDX_IN_P > 0) & (G.random(N) < .15)
L_SR[other] = G.integers(NS, size=other.sum())

# day weights
dd = np.arange(ND)
growth = 1 + .07 * (dd - START_D) / 365
MSEAS = {1: .8, 2: .9, 3: 1.15, 4: 1.0, 5: 1.1, 6: 1.0, 7: 1.0, 8: 1.1, 9: 1.0, 10: .95, 11: .95, 12: 1.1}
base_w = growth * np.vectorize(MSEAS.get)(MONTH) * np.where(IN_EVENT, 1.25, 1.0)
base_w[(dd < START_D) | (dd > ASOF_D)] = 0
WK_INT = np.array([1.05, 1.0, 1.0, .95, .9, 1.1, 1.15])[WEEKDAY]
WK_SHOW = np.array([.8, .8, .85, .9, 1.0, 2.0, .9])[WEEKDAY]
CLASS_W = {"internet": base_w * WK_INT, "showroom": base_w * WK_SHOW, "event": base_w * WK_INT * IN_EVENT}


def ramp(s):
    r = np.clip((dd - SR_OPEN_D[s]) / 180, 0, 1) * .5 + .5
    r[dd < SR_OPEN_D[s]] = 0
    return r


CDF = {}
for s in range(NS):
    rs = ramp(s)
    for c, w in CLASS_W.items():
        x = np.cumsum(w * rs * (OPEN_DAYM[s] if c == "showroom" else 1))
        CDF[(s, c)] = x / x[-1]
L_CLASS = np.array([SOURCES[SRC[i]][2] for i in L_SRC])
L_DAY = np.zeros(N, int)
first = L_IDX_IN_P == 0
for s in range(NS):
    for c in CLASS_W:
        m = first & (L_SR == s) & (L_CLASS == c)
        L_DAY[m] = np.searchsorted(CDF[(s, c)], G.random(m.sum()))
# later leads of the same person: after a gap
gap = (G.exponential(75, N) + 1).astype(int)
for k in (1, 2):
    m = L_IDX_IN_P == k
    prev = np.where(m)[0] - 1
    d = L_DAY[prev] + gap[m]
    over = d > ASOF_D
    d[over] = L_DAY[prev][over] + (G.random(over.sum()) * (ASOF_D - L_DAY[prev][over] + 1)).astype(int)
    L_DAY[m] = np.minimum(d, ASOF_D)
    # a showroom that wasn't open yet -> home showroom
    bad = m & (L_DAY < SR_OPEN_D[L_SR])
    L_SR[bad] = P_SR[L_P[bad]]
    # sales-event source outside an event window -> website
    ev_bad = m & (L_CLASS == "event") & ~IN_EVENT[L_DAY]
    L_SRC[ev_bad] = SRC.index("Website")
    L_CLASS[ev_bad] = "internet"
# showroom-class leads must fall on an open day
for _ in range(10):
    bad = (L_CLASS == "showroom") & ~OPEN_DAYM[L_SR, L_DAY]
    if not bad.any():
        break
    L_DAY[bad] = np.where(L_DAY[bad] + 1 <= ASOF_D, L_DAY[bad] + 1, L_DAY[bad] - 1)
L_DAY = np.clip(L_DAY, START_D, ASOF_D)
# time of day (local seconds)
H_INT = np.array([.6, .3, .2, .15, .15, .3, .7, 1.2, 1.8, 2.2, 2.4, 2.5, 2.7, 2.6, 2.5, 2.5, 2.6, 2.9,
                  3.3, 3.8, 4.1, 3.7, 2.6, 1.4])
H_INT = H_INT / H_INT.sum()
secs = np.zeros(N)
mi = L_CLASS != "showroom"
secs[mi] = G.choice(24, size=mi.sum(), p=H_INT) * 3600 + G.random(mi.sum()) * 3600
mw = L_SRC == S_WALK
o, c_ = OPEN_SM[L_SR[mw], L_DAY[mw]], CLOSE_SM[L_SR[mw], L_DAY[mw]]
secs[mw] = o + G.beta(2.2, 1.6, mw.sum()) * (c_ - o - 1800)
mp = L_SRC == S_PHONE
o, c_ = OPEN_SM[L_SR[mp], L_DAY[mp]], CLOSE_SM[L_SR[mp], L_DAY[mp]]
secs[mp] = o + G.beta(1.6, 1.6, mp.sum()) * (c_ - o - 600)
L_T = T0 + L_DAY * 86400 + secs - OFFM[L_SR, L_DAY]
L_T = np.minimum(L_T, ASOF - 60)
# order each person's leads by time
order = np.lexsort((L_T, L_P))
for arr_name in ("L_P", "L_IDX_IN_P", "L_SRC", "L_SR", "L_CLASS", "L_DAY", "L_T"):
    globals()[arr_name] = globals()[arr_name][order]

# lead attributes
yr_frac = (L_DAY - START_D) / 365
pop = np.array([p["_pop"] for p in PROD])
ev = np.array([p["_ev"] for p in PROD])
L_PROD = np.zeros(N, int)
for yb in range(4):
    m = np.floor(yr_frac).astype(int) == yb
    w = pop * np.where(ev, 1 + .35 * yb, 1.0)
    L_PROD[m] = G.choice(NP, size=m.sum(), p=w / w.sum())
src_used = np.isin(L_SRC, [SRC.index("Third-Party Marketplace"), SRC.index("Social Media")])
pcond = np.where(src_used[:, None], [[.35, .45, .20]], [[.60, .27, .13]])
L_COND = (G.random(N)[:, None] > np.cumsum(pcond, 1)).sum(1)            # 0 New, 1 Used, 2 CPO
L_COND[ev[L_PROD] & (L_COND == 1) & (G.random(N) < .5)] = 0
L_VI_BLANK = G.random(N) < np.where(L_SRC == S_WALK, .55, .22)
TL = ["Immediately", "1-3 Months", "3-6 Months", "Just Browsing"]
TL_EFF = np.array([.95, .25, -.55, -1.3, 0])
L_TL = G.choice(5, size=N, p=[.22, .27, .12, .09, .30])                # 4 = blank
L_TL[L_SRC == S_WALK] = G.choice([0, 1, 4], size=mw.sum(), p=[.25, .1, .65])
L_TRADE_TRUE = G.random(N) < .45
L_TRADE_FIELD = np.where(G.random(N) < .35, -1, L_TRADE_TRUE.astype(int))  # -1 blank
L_PAY = G.choice(4, size=N, p=[.50, .15, .15, .20])                      # Finance, Lease, Cash, Undecided
L_PREQ = G.random(N) < np.where(np.isin(L_SRC, [SRC.index("Website"), SRC.index("OEM Referral")]), .2, .07)
L_DIST = np.round(np.clip(P_DIST[L_P] * G.lognormal(0, .15, N), .3, 200), 1)
L_DIST[L_SR != P_SR[L_P]] = np.round(L_DIST[L_SR != P_SR[L_P]] + G.uniform(10, 40, (L_SR != P_SR[L_P]).sum()), 1)
L_NOPHONE = (L_CLASS != "showroom") & (G.random(N) < .10)
L_NOEMAIL = G.random(N) < np.where(L_SRC == S_WALK, .25, np.where(L_SRC == S_PHONE, .35, 0))
L_PREF = G.choice(3, size=N, p=[.42, .38, .20])                           # Phone, Text, Email
L_PREF[L_NOPHONE] = 2
L_OPTOUT = G.random(N) < .04
# list price of the vehicle of interest (for affordability)
BUD_EDGES = np.array([20000, 30000, 40000, 55000])
BUD_LBL = ["Under $20k", "$20k-$30k", "$30k-$40k", "$40k-$55k", "$55k+"]
BUD_MID = np.array([16000, 25000, 35000, 47500, 62000])
cond_factor = np.array([1.0, .58, .78])
est_price = P_MSRP[L_PROD] * cond_factor[L_COND]
true_budget = est_price * G.lognormal(0, .25, N)
L_BUD = np.searchsorted(BUD_EDGES, true_budget)
L_BUD_BLANK = G.random(N) < .45
afford = np.where(BUD_MID[L_BUD] < .8 * est_price, -.45, 0)
L_QBASE = (TL_EFF[L_TL] + .55 * L_PREQ + .25 * L_TRADE_TRUE + afford
           - np.clip(.02 * np.maximum(0, L_DIST - 10), 0, 1.0) + .15 * IN_EVENT[L_DAY]
           - .9 * L_NOPHONE + P_LATENT[L_P] + G.normal(0, .8, N))
P_START = np.concatenate([[0], np.cumsum(k_per)[:-1]])
P_SHARD = np.arange(NPERS) % ARGS.shards
print(f"setup: {NPERS:,} people, {N:,} leads, {NU} users, {len(CAMPS)} campaigns ({time.time() - t_setup:.1f}s)")

# ============================================================== tables
COLS = {
    "Lead": ["Id", "FirstName", "LastName", "Email", "MobilePhone", "City", "State", "PostalCode", "LeadSource",
             "Status", "Rating", "OwnerId", "Showroom__c", "Vehicle_Interest__c", "Condition_Interest__c",
             "Purchase_Timeline__c", "Budget_Range__c", "Trade_In__c", "Payment_Preference__c", "Prequalified__c",
             "Preferred_Contact_Method__c", "Distance_Miles__c", "IsConverted", "ConvertedDate",
             "ConvertedAccountId", "ConvertedContactId", "ConvertedOpportunityId", "HasOptedOutOfEmail",
             "Lost_Reason__c", "CreatedDate", "LastModifiedDate", "LastActivityDate"],
    "Account": ["Id", "IsPersonAccount", "FirstName", "LastName", "Name", "PersonEmail", "PersonMobilePhone",
                "PersonContactId", "BillingCity", "BillingState", "BillingPostalCode", "AccountSource",
                "Showroom__c", "Type", "OwnerId", "CreatedDate"],
    "Contact": ["Id", "AccountId", "FirstName", "LastName", "Email", "MobilePhone", "MailingCity", "MailingState",
                "MailingPostalCode", "LeadSource", "OwnerId", "HasOptedOutOfEmail", "CreatedDate"],
    "Opportunity": ["Id", "AccountId", "ContactId", "Name", "Type", "StageName", "Amount", "Probability",
                    "ExpectedRevenue", "CloseDate", "IsClosed", "IsWon", "ForecastCategoryName", "LeadSource",
                    "CampaignId", "OwnerId", "Showroom__c", "Vehicle__c", "Vehicle_Model_Year__c", "List_Price__c",
                    "Discount__c", "Trade_In__c", "Trade_In_Value__c", "Payment_Method__c", "Credit_Tier__c",
                    "Finance_Term_Months__c", "Test_Drive_Completed__c", "Loss_Reason__c", "CreatedDate",
                    "LastStageChangeDate", "LastModifiedDate", "LastActivityDate", "FiscalYear", "FiscalQuarter"],
    "OpportunityHistory": ["Id", "OpportunityId", "StageName", "Amount", "ExpectedRevenue", "Probability",
                           "ForecastCategory", "CloseDate", "CreatedById", "CreatedDate"],
    "Task": ["Id", "WhoId", "WhatId", "AccountId", "OwnerId", "Subject", "Type", "TaskSubtype", "Status", "Priority",
             "ActivityDate", "CompletedDateTime", "CallType", "CallDisposition", "CallDurationInSeconds", "IsClosed",
             "CreatedDate"],
    "Event": ["Id", "WhoId", "WhatId", "AccountId", "OwnerId", "Showroom__c", "Subject", "Type", "StartDateTime",
              "EndDateTime", "DurationInMinutes", "ActivityDate", "Location", "ShowAs", "IsAllDayEvent", "Outcome__c",
              "CreatedById", "CreatedDate"],
    "CampaignMember": ["Id", "CampaignId", "LeadId", "ContactId", "Status", "HasResponded", "FirstRespondedDate",
                       "CreatedDate"],
}
DT_COLS = {"CreatedDate", "LastModifiedDate", "CompletedDateTime", "StartDateTime", "EndDateTime",
           "LastStageChangeDate"}
D_COLS = {"ConvertedDate", "LastActivityDate", "CloseDate", "ActivityDate", "FirstRespondedDate"}
STAGE = {"Needs Assessment": (20, "Pipeline"), "Test Drive": (40, "Pipeline"), "Proposal": (60, "Best Case"),
         "Negotiation": (75, "Commit"), "Financing": (90, "Commit"), "Closed Won": (100, "Closed"),
         "Closed Lost": (0, "Omitted")}
CREDIT = ["Super Prime", "Prime", "Near Prime", "Subprime", "Deep Subprime"]
APPROVE = [.995, .975, .88, .68, .38]
PAYM = ["Finance", "Lease", "Cash"]
OPP_TYPE = ["New Vehicle", "Used Vehicle", "Certified Pre-Owned"]
COND = ["New", "Used", "Certified Pre-Owned"]


def sig(x):
    return 1.0 / (1.0 + math.exp(-x))


# ---------------------------------------------------------- time helpers (scalar, fast)
# All helpers work in the local time of the showroom currently being simulated (CUR).
CUR = 0


def lday(t):
    off = OFFM[CUR]
    d = int((t - T0) // 86400)
    lt = t + off[min(max(d, 0), ND - 1)]
    dl = int((lt - T0) // 86400)
    return dl, lt - T0 - dl * 86400


def ldate(t):
    return None if t is None else DATE_STR[min(lday(t)[0], ND - 1)]


def utc(dl, s):
    return T0 + dl * 86400 + s - OFFM[CUR][dl]


def is_open(t):
    dl, s = lday(t)
    o = OPEN_SM[CUR]
    return o[dl] >= 0 and o[dl] <= s < CLOSE_SM[CUR][dl]


def next_open(t, jitter=1800.0):
    o, c = OPEN_SM[CUR], CLOSE_SM[CUR]
    dl, s = lday(t)
    if o[dl] >= 0 and s < c[dl] - 600:
        return t if s >= o[dl] else utc(dl, o[dl] + R.random() * jitter)
    dl += 1
    while o[dl] < 0:
        dl += 1
    return utc(dl, o[dl] + R.random() * jitter)


def work_after(t, days):
    """A working-hours time `days` after t (BDC/consultant follow-up)."""
    t2 = t + days * 86400
    dl, s = lday(t2)
    o, c = OPEN_SM[CUR], CLOSE_SM[CUR]
    if o[dl] >= 0 and o[dl] <= s < c[dl] - 600:
        return t2
    return next_open(t2, jitter=3 * 3600)


def appt_slot(t, days):
    o_, c_ = OPEN_SM[CUR], CLOSE_SM[CUR]
    dl, _ = lday(t)
    dl += days
    while o_[dl] < 0:
        dl += 1
    o, c = o_[dl] + 3600, c_[dl] - 5400
    t2 = utc(dl, o + R.random() * max(c - o, 0))
    t2 = round((t2 - T0) / 900) * 900 + T0          # quarter-hour slots
    return t2 if t2 > t + 3600 else next_open(t + 7200)


def pick(sr, role, t):
    dl, _ = lday(t)
    c = ACTIVE.get((sr, role, dl))
    if not c:
        for alt in ("Sales Manager", "General Manager"):
            c = ACTIVE.get((sr, alt, dl))
            if c:
                break
    if not c:
        c = [VP_IDX]
    return c[int(R.integers(len(c)))]


VP_IDX = 0


def skill(u, t):
    tenure = (t - T0) / 86400 - U_HIRE[u]
    return U_SKILL[u] - .6 * math.exp(-max(tenure, 0) / 60)     # new hires ramp up


# ============================================================== shard simulation
def run_shard(sh):
    global R, CUR
    R = np.random.default_rng([SEED, 1000 + sh])
    ID = IdGen(sh)
    T = {k: [] for k in COLS}
    opp_last_act = {}

    def task(who, what, acct, owner, t, kind, subject, disp=None, status="Completed", created=None,
             prio="Normal", inbound=False):
        typ, sub = {"Call": ("Call", "Call"), "Email": ("Email", "Email"), "SMS": ("SMS", "Task"),
                    "Todo": ("Other", "Task")}[kind]
        dur = None
        if kind == "Call":
            dur = {"Connected": int(R.integers(90, 1100)), "Left Voicemail": int(R.integers(15, 55)),
                   "No Answer": int(R.integers(0, 25)), "Wrong Number": int(R.integers(5, 35))}.get(disp)
        closed = status == "Completed"
        if closed and t > ASOF:          # nothing after the extract is known
            return t
        T["Task"].append([ID("00T"), who, what, acct, U_ID[owner], subject, typ, sub, status, prio, ldate(t),
                          t if closed else None, ("Inbound" if inbound else "Outbound") if kind == "Call" else None,
                          disp if kind == "Call" else None, dur, closed, created if created is not None else t])
        if what and closed:
            opp_last_act[what] = max(opp_last_act.get(what, 0), t)
        return t

    def event(who, what, acct, owner, sr, t, mins, subject, etype, outcome, creator, created):
        if t > ASOF and outcome != "Scheduled":
            if what is None or created > ASOF:
                return
            outcome = "Scheduled"
        T["Event"].append([ID("00U"), who, what, acct, U_ID[owner], SR_ID[sr], subject, etype, t, t + mins * 60,
                           mins, ldate(t), SHOWROOMS[sr][0], "Busy", False, outcome, U_ID[creator], created])
        if what and t <= ASOF:
            opp_last_act[what] = max(opp_last_act.get(what, 0), t)

    for p in np.where(P_SHARD == sh)[0]:
        acct = contact = None
        bought = False
        prev_t, prev_conv = -1e18, True
        home = SHOWROOMS[P_SR[p]]
        city, zip3 = home[9][P_CITY[p]]
        state = home[2]
        fn, ln = str(FN[P_FN[p]]), str(LN[P_LN[p]])
        email = f"{fn.lower()}.{ln.lower()}{'' if P_EMAILNUM[p] < 0 else P_EMAILNUM[p]}@{P_EMAILDOM[p]}"
        phone = f"({home[8][P_AREA[p] % len(home[8])]}) " \
                f"{str(P_PHONE[p])[:3]}-{str(P_PHONE[p])[3:]}"
        postal = f"{zip3 + P_ZIP[p] % 8:05d}"
        for li in range(P_START[p], P_START[p] + k_per[p]):
            t0, sr, src = float(L_T[li]), int(L_SR[li]), int(L_SRC[li])
            CUR = sr
            if bought and src not in (S_WALK, S_PHONE) and R.random() < .6:
                src = S_REPEAT
            q = L_QBASE[li] + (REPEAT_EFF if src == S_REPEAT else SRC_EFF[src])
            lid = ID("00Q")
            walk = src == S_WALK
            nt0, ne0 = len(T["Task"]), len(T["Event"])
            status, reason, rating, conv_t = None, None, None, None
            converted, oid_conv = False, None
            last_t = t0
            dup = (t0 - prev_t < 30 * 86400) and not prev_conv and not walk and R.random() < .5
            ctype = SOURCES[SRC[src]][3] if src < len(SRC) else None
            dl0 = lday(t0)[0]
            camp = int(CAMP_DAY[ctype][dl0]) if ctype else -1
            if camp >= 0:
                T["CampaignMember"].append([ID("00v"), CAMPS[camp]["Id"], lid, None, "Responded", True, ldate(t0), t0])
            cm_row = T["CampaignMember"][-1] if camp >= 0 else None

            if dup:
                owner = pick(sr, "BDC Representative", t0)
                status, reason = "Closed - Not Converted", "Duplicate"
                last_t = work_after(t0, R.uniform(.05, 1))
            elif walk:
                owner = pick(sr, "Sales Consultant", t0)
                event(lid, None, None, owner, sr, t0, int(R.integers(25, 75)), "Showroom Visit", "Walk-In",
                      "Completed", owner, t0)
                converted, conv_t = True, t0 + R.uniform(600, 1800)
                cons = owner
            else:
                owner = pick(sr, "BDC Representative", t0)
                sk = skill(owner, t0)
                if src == S_PHONE:
                    rt = t0
                    task(lid, None, None, owner, t0, "Call", "Inbound call", "Connected", inbound=True)
                    contacted_k, contact_t = -1, t0
                else:
                    if is_open(t0):
                        rt = t0 + 60 * R.lognormal(math.log(7) - .9 * sk, 1.0)
                        if R.random() < .12:
                            rt += R.uniform(3600, 6 * 3600)
                        if not is_open(rt):
                            rt = next_open(rt)
                    else:
                        rt = next_open(t0) + 60 * R.lognormal(math.log(25), .8)
                    mins = (rt - t0) / 60
                    speff = .4 if mins < 5 else .15 if mins < 30 else 0 if mins < 120 else -.25 if mins < 1440 else -.6
                    p_c = sig(.6 * q + .55 + speff + .4 * sk)
                    contacted = R.random() < p_c
                    contacted_k = min(int(R.geometric(.42)) - 1, 7) if contacted else -2
                    contact_t = None
                    seq = ["Call", "SMS", "Email", "Call", "SMS", "Call", "Email", "SMS", "Email"]
                    offs = [0, .003, .01, 1, 2, 4, 7, 10, 14]
                    n = contacted_k + 1 if contacted else int(R.integers(5, 10))
                    for k in range(n):
                        tk = rt + offs[k] * 86400 if k < 3 else work_after(rt, offs[k])
                        if tk > ASOF:
                            contacted_k = -3
                            break
                        kind = seq[k]
                        if L_NOPHONE[li] and kind != "Email":
                            kind = "Email"
                        if L_OPTOUT[li] and kind == "Email" and k > 2:
                            kind = "Call" if not L_NOPHONE[li] else "Email"
                        last_t = tk
                        if k == contacted_k:
                            if kind == "Call":
                                task(lid, None, None, owner, tk, "Call", "Call", "Connected")
                            else:
                                task(lid, None, None, owner, tk, kind, f"{kind}: Follow up")
                                tk = tk + 60 * R.lognormal(math.log(40), 1.0)
                                task(lid, None, None, owner, min(tk, ASOF), kind, f"{kind}: Customer reply")
                            contact_t = min(tk, ASOF)
                        elif kind == "Call":
                            task(lid, None, None, owner, tk, "Call", "Call",
                                 "Left Voicemail" if R.random() < .45 else ("No Answer" if R.random() < .93 else "Wrong Number"))
                        else:
                            subj = {0: "Intro", 1: "Intro", 2: "Vehicle info & pricing"}.get(k, "Follow up")
                            task(lid, None, None, owner, tk, kind, f"{kind}: {subj if k < n - 1 or contacted else 'Last attempt'}")
                if contacted_k == -3:
                    status = "Working - Contacted" if len(T["Task"]) > nt0 else "Open - Not Contacted"
                elif contacted_k == -2:
                    status, reason = "Closed - Not Converted", "Unresponsive"
                    last_t = work_after(last_t, R.uniform(2, 7))
                else:
                    if R.random() < .5:
                        rating = "Hot" if q + R.normal(0, .7) > .8 else "Warm" if q + R.normal(0, .7) > -.4 else "Cold"
                    # appointment
                    visit_t = None
                    if R.random() < sig(.9 * q - .3 + .3 * sk):
                        cons = pick(sr, "Sales Consultant", contact_t)
                        appt = appt_slot(contact_t, int(R.choice([0, 1, 1, 2, 2, 3, 4, 5, 6])))
                        for attempt in range(2):
                            if lday(appt)[0] > lday(contact_t)[0] and appt - 86400 * .6 < ASOF:
                                task(lid, None, None, owner, max(work_after(appt, -.6), contact_t + 600),
                                     "Call" if L_NOPHONE[li] else "SMS", "Appointment confirmation")
                            if appt > ASOF:
                                event(lid, None, None, cons, sr, appt, 60, "Showroom Appointment", "Appointment",
                                      "Scheduled", owner, contact_t)
                                status = "Working - Contacted"
                                break
                            show = R.random() < sig(.75 * q + .55)
                            event(lid, None, None, cons, sr, appt, 60, "Showroom Appointment", "Appointment",
                                  "Completed" if show else "No Show", owner, contact_t)
                            last_t = appt
                            if show:
                                visit_t = appt + R.uniform(-600, 1200)
                                break
                            fu = work_after(appt, R.uniform(.05, 1.0))
                            if fu <= ASOF:
                                task(lid, None, None, owner, fu, "Call", "Call", "Left Voicemail")
                                last_t = fu
                            if attempt == 0 and R.random() < .45:
                                contact_t = fu
                                appt = appt_slot(fu, int(R.integers(1, 5)))
                            else:
                                status, reason = "Closed - Not Converted", R.choice(
                                    ["Unresponsive", "Bought Elsewhere", "Not Ready to Buy"], p=[.5, .3, .2])
                                last_t = work_after(last_t, R.uniform(3, 10))
                                break
                    elif status is None:
                        # no appointment: a few nurture touches, maybe an unannounced visit
                        tk = contact_t
                        for _ in range(int(R.integers(1, 4))):
                            tk = work_after(tk, R.uniform(3, 12))
                            if tk > ASOF:
                                break
                            kind = "Email" if L_NOPHONE[li] or R.random() < .5 else "SMS"
                            task(lid, None, None, owner, tk, kind, f"{kind}: Checking in")
                            last_t = tk
                        if R.random() < .1 * sig(q + 1):
                            vt = next_open(contact_t + R.uniform(1, 14) * 86400)
                            if vt <= ASOF:
                                cons = pick(sr, "Sales Consultant", vt)
                                event(lid, None, None, cons, sr, vt, int(R.integers(25, 75)), "Showroom Visit",
                                      "Walk-In", "Completed", cons, vt)
                                visit_t = vt
                        if visit_t is None and status is None:
                            if ASOF - last_t < 14 * 86400:
                                status = "Working - Contacted"
                            else:
                                status = "Closed - Not Converted"
                                reason = R.choice(["Not Ready to Buy", "Bought Elsewhere", "Price Shopping",
                                                   "Credit Concerns", "Out of Area"],
                                                  p=[.34, .28, .22, .1, .06] if L_DIST[li] < 40 else [.2, .2, .15, .05, .4])
                                last_t = work_after(last_t, R.uniform(2, 10))
                    if visit_t is not None and visit_t <= ASOF:
                        converted, conv_t = True, visit_t + R.uniform(300, 1500)
            # ------------------------------------------------ conversion & opportunity
            if converted and conv_t > ASOF:
                converted, status = False, "Working - Contacted"
            if converted:
                if acct is None:
                    acct, contact = ID("001"), ID("003")
                    T["Account"].append([acct, True, fn, ln, f"{fn} {ln}", None if L_NOEMAIL[li] else email,
                                         phone, contact, city, state, postal, SRC_NAMES[src], SR_ID[sr], "Prospect",
                                         U_ID[cons], conv_t])
                    T["Contact"].append([contact, acct, fn, ln, None if L_NOEMAIL[li] else email, phone, city, state,
                                         postal, SRC_NAMES[src], U_ID[cons], bool(L_OPTOUT[li]), conv_t])
                for row in T["Task"][nt0:]:
                    row[1], row[3] = contact, acct           # activities move to the contact on conversion
                for row in T["Event"][ne0:]:
                    row[1], row[3] = contact, acct
                if cm_row is not None:
                    cm_row[3] = contact
                status, owner = "Closed - Converted", cons
                won, oid_conv = simulate_opp(T, ID, task, event, opp_last_act, li, src, q, sr, cons, acct, contact,
                                             conv_t, camp, fn, ln)
                bought = bought or won
            # ------------------------------------------------ lead row
            lead_acts = [r[11] for r in T["Task"][nt0:] if r[15] and r[11] is not None and (not converted or r[11] <= conv_t)] + \
                        [r[8] for r in T["Event"][ne0:] if r[8] <= ASOF and (not converted or r[8] <= conv_t)]
            last_act = max(lead_acts) if lead_acts else None
            lm = conv_t if converted else max([last_t, t0] + ([last_act] if last_act else []))
            vi = None if L_VI_BLANK[li] else PROD[L_PROD[li]]["Id"]
            T["Lead"].append([lid, fn, ln, None if L_NOEMAIL[li] else email, None if L_NOPHONE[li] else phone,
                              city, state, postal, SRC_NAMES[src], status or "Working - Contacted", rating, U_ID[owner],
                              SR_ID[sr], vi, None if vi is None and R.random() < .5 else COND[L_COND[li]],
                              None if L_TL[li] == 4 else TL[L_TL[li]], None if L_BUD_BLANK[li] else BUD_LBL[L_BUD[li]],
                              {-1: None, 0: "No", 1: "Yes"}[int(L_TRADE_FIELD[li])],
                              ["Finance", "Lease", "Cash", "Undecided"][L_PAY[li]], bool(L_PREQ[li]),
                              ["Phone", "Text", "Email"][L_PREF[li]], float(L_DIST[li]), converted,
                              ldate(conv_t) if converted else None, acct if converted else None,
                              contact if converted else None, oid_conv, bool(L_OPTOUT[li]),
                              reason if status == "Closed - Not Converted" else None, t0, min(lm, ASOF), ldate(last_act)])
            prev_t, prev_conv = t0, converted
        if bought and acct is not None:
            for row in reversed(T["Account"]):
                if row[0] == acct:
                    row[13] = "Customer"
                    break
    # opportunity LastActivityDate / LastModifiedDate
    for row in T["Opportunity"]:
        CUR = SR_IDX[row[16]]
        la = opp_last_act.get(row[0])
        row[31] = ldate(la) if la else None
        row[30] = min(max(row[29], la or 0), ASOF)
    return write_shard(sh, T)


def simulate_opp(T, ID, task, event, opp_last_act, li, src, q, sr, cons, acct, contact, t, camp, fn, ln):
    oid = ID("006")
    ownr = U_ID[cons]
    w = .85 * q + .5 * skill(cons, t) + R.normal(0, .7)
    prod = int(L_PROD[li]) if R.random() < .7 else int(R.choice(MODEL_PRODS[P_MODEL[int(L_PROD[li])]])) \
        if R.random() < .6 else int(R.integers(NP))
    cond = int(L_COND[li])
    if PROD[prod]["_ev"] and cond == 1 and R.random() < .5:
        cond = 0
    yr = pd.Timestamp(t, unit="s").year if False else int(YEAR[lday(t)[0]])
    mo = int(MONTH[lday(t)[0]])
    if cond == 0:
        my = yr + (1 if mo >= 8 else 0)
        price = P_MSRP[prod] * (1 + .03 * (yr - 2023))
    elif cond == 1:
        age = int(R.integers(1, 8))
        my = yr - age
        price = P_MSRP[prod] * R.uniform(.62, .82) * (1 - .055 * age)
    else:
        age = int(R.integers(1, 5))
        my = yr - age
        price = P_MSRP[prod] * R.uniform(.80, .90) * (1 - .04 * age)
    lst = float(round(price / 100) * 100 - 5)
    event_day = IN_EVENT[lday(t)[0]]
    disc_pct = min(max(R.normal(.045 if cond == 0 else .022, .02 if cond == 0 else .014) + .015 * event_day, 0), .12)
    disc = float(round(lst * disc_pct / 50) * 50)
    trade = bool(L_TRADE_TRUE[li])
    trade_val = float(round(np.clip(R.lognormal(math.log(12500), .6), 1500, 48000), -2)) if trade else None
    payp = int(L_PAY[li])
    pay = payp if payp < 3 else int(R.choice(3, p=[.68, .12, .20]))
    if pay == 1 and cond != 0:
        pay = 0
    hist = []
    stage_t = {}

    def enter(st, ts, amt):
        if ts > ASOF and hist:
            return
        hist.append((st, ts, amt))
        stage_t[st] = ts

    enter("Needs Assessment", t, lst)
    td = R.random() < sig(w + 1.4)
    cur = t + R.uniform(900, 2400)
    status, loss, close_t, credit, term = None, None, None, None, None
    amount = lst
    if td:
        event(contact, oid, acct, cons, sr, cur, int(R.integers(15, 40)), "Test Drive", "Test Drive", "Completed",
              cons, cur)
        enter("Test Drive", cur, lst)
        cur += R.uniform(1500, 3000)
    proposal = R.random() < sig(w + (.75 if td else -1.0))
    if not proposal:
        fu_t = cur
        for _ in range(int(R.integers(1, 4))):
            fu_t = work_after(fu_t, R.uniform(1, 5))
            if fu_t > ASOF:
                break
            task(contact, oid, acct, cons, fu_t, "Call" if R.random() < .6 else "SMS", "Follow up after visit",
                 "No Answer" if R.random() < .6 else "Connected")
        close_t = work_after(fu_t, R.uniform(1, 6))
        status, loss = "lost", R.choice(["Not Ready to Buy", "Just Looking", "Vehicle Not Available", "Bought Elsewhere"],
                                        p=[.4, .3, .1, .2])
    else:
        amount = lst - disc
        task(contact, oid, acct, cons, cur, "Todo", "Present pricing worksheet")
        enter("Proposal", cur, amount)
        same_day = R.random() < .5
        nego_p = sig(w - .22 + 9 * (disc_pct - .035) - (.25 if trade and trade_val and trade_val < 6000 else 0))
        nego = R.random() < nego_p
        if not same_day:      # be-back: follow-ups, then a return visit
            fu_t = cur
            nf = int(R.integers(1, 4))
            for _ in range(nf):
                fu_t = work_after(fu_t, R.uniform(.6, 3))
                if fu_t > ASOF:
                    break
                kind = "Call" if R.random() < .55 else "SMS"
                task(contact, oid, acct, cons, fu_t, kind, "Be-back follow up" if kind == "Call" else "SMS: Following up on your quote",
                     "Connected" if R.random() < .5 else "Left Voicemail")
            if nego and cond != 0 and R.random() < .08:
                nego, loss_override = False, "Vehicle No Longer Available"
            else:
                loss_override = None
            if nego:
                rv = appt_slot(fu_t, int(R.integers(0, 4)))
                if rv > ASOF:
                    status = "open"
                else:
                    event(contact, oid, acct, cons, sr, rv, 60, "Return Visit", "Appointment", "Completed", cons, fu_t)
                    cur = rv + R.uniform(600, 1800)
            else:
                close_t = work_after(fu_t, R.uniform(2, 12))
                status = "lost"
                loss = loss_override or R.choice(["Price", "Bought Elsewhere", "Trade-In Value", "Not Ready to Buy",
                                                  "Monthly Payment Too High"],
                                                 p=[.32, .3, .14 if trade else 0, .12, .12 + (0 if trade else .14)])
        elif not nego:
            fu_t = cur
            for _ in range(int(R.integers(1, 4))):
                fu_t = work_after(fu_t, R.uniform(1, 4))
                if fu_t > ASOF:
                    break
                task(contact, oid, acct, cons, fu_t, "Call", "Follow up on quote",
                     "Connected" if R.random() < .4 else "Left Voicemail")
            close_t = work_after(fu_t, R.uniform(2, 10))
            status = "lost"
            loss = R.choice(["Price", "Bought Elsewhere", "Trade-In Value", "Not Ready to Buy", "Monthly Payment Too High"],
                            p=[.32, .3, .14 if trade else 0, .12, .12 + (0 if trade else .14)])
        if status is None:
            amount = float(round((amount - lst * R.uniform(0, .012)) / 50) * 50)
            enter("Negotiation", cur, amount)
            cur += R.uniform(1200, 3600)
            if pay in (0, 1):
                fi = pick(sr, "F&I Manager", cur)
                credit = int(P_CREDIT[L_P[li]])
                task(contact, oid, acct, fi, cur, "Todo", "Credit application submitted")
                enter("Financing", cur, amount)
                ok = R.random() < APPROVE[credit] or R.random() < .35       # second lender / co-signer
                cur += R.uniform(1800, 5400)
                if ok:
                    term = int(R.choice([48, 60, 72, 84], p=[.12, .33, .38, .17])) if pay == 0 else \
                        int(R.choice([24, 36, 39], p=[.25, .6, .15]))
                else:
                    status, loss, close_t = "lost", "Financing Declined", cur
            if status is None:
                status, close_t = "won", cur
    if close_t is not None and close_t > ASOF:
        status = "open"
    if status == "won":
        enter("Closed Won", close_t, amount)
        dt_ = close_t + R.uniform(1800, 5400) if R.random() < .7 else appt_slot(close_t, int(R.integers(1, 3)))
        if dt_ <= ASOF:
            event(contact, oid, acct, cons, sr, dt_, 60, "Vehicle Delivery", "Delivery", "Completed", cons, close_t)
        else:
            event(contact, oid, acct, cons, sr, dt_, 60, "Vehicle Delivery", "Delivery", "Scheduled", cons, close_t)
    elif status == "lost":
        enter("Closed Lost", close_t, amount)
    final = hist[-1][0]
    prob, fc = STAGE[final]
    if status == "open":
        exp_close = t + R.uniform(3, 21) * 86400
        close_d = exp_close if exp_close > ASOF or R.random() < .7 else exp_close
        if R.random() < .3:
            task(contact, oid, acct, cons, ASOF + R.uniform(-3, 5) * 86400, "Todo", "Follow up",
                 status="Not Started", prio="High", created=min(ASOF - 3600, hist[-1][1] + 3600))
    else:
        close_d = close_t
    name = f"{fn} {ln} - {my} Tarvessa {PROD[prod]['Model__c']} {PROD[prod]['Trim__c']}"
    for st, ts, amt in hist:
        p_, f_ = STAGE[st]
        T["OpportunityHistory"].append([ID("008"), oid, st, amt, round(amt * p_ / 100, 2), p_, f_,
                                        ldate(close_t if st.startswith("Closed") else t + 7 * 86400), ownr, ts])
    ld = lday(close_d)[0]
    T["Opportunity"].append([oid, acct, contact, name, OPP_TYPE[cond], final, amount, prob,
                             round(amount * prob / 100, 2), ldate(close_d), status != "open", status == "won", fc,
                             SRC_NAMES[src], CAMPS[camp]["Id"] if camp >= 0 else None, ownr, SR_ID[sr],
                             PROD[prod]["Id"], my, lst, disc if "Proposal" in stage_t else None, trade, trade_val,
                             PAYM[pay] if "Negotiation" in stage_t else None,
                             CREDIT[credit] if credit is not None else None, term, td,
                             (loss if status == "lost" else None), t, hist[-1][1], None, None,
                             int(YEAR[ld]), (int(MONTH[ld]) - 1) // 3 + 1])
    return status == "won", oid


# ============================================================== output
def _fmt(df):
    for c in df.columns:
        if c in DT_COLS:
            v = pd.to_numeric(df[c], errors="coerce")
            df[c] = pd.to_datetime(v, unit="s").dt.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
        elif c in ("Hire_Date__c", "Termination_Date__c", "StartDate", "EndDate"):
            v = pd.to_numeric(df[c], errors="coerce")
            if c in ("Hire_Date__c", "Termination_Date__c", "StartDate", "EndDate"):
                df[c] = (D0 + pd.to_timedelta(v, unit="D")).dt.strftime("%Y-%m-%d")
    return df


INT_COLS = {"Finance_Term_Months__c", "CallDurationInSeconds", "Vehicle_Model_Year__c", "DurationInMinutes",
            "Probability", "FiscalYear", "FiscalQuarter"}


def write_shard(sh, T):
    os.makedirs(os.path.join(ARGS.out, "_parts"), exist_ok=True)
    counts = {}
    for k, rows in T.items():
        df = pd.DataFrame(rows, columns=COLS[k])
        for c in INT_COLS & set(df.columns):      # whole numbers stay whole even when some are blank
            df[c] = pd.to_numeric(df[c]).round().astype("Int64")
        df = _fmt(df)
        df.to_csv(os.path.join(ARGS.out, "_parts", f"{k}.{sh:03d}.csv"), index=False, header=False)
        counts[k] = len(df)
    return counts


def write_global():
    users = pd.DataFrame(USERS)
    users = users[[c for c in users.columns if not c.startswith("_")]]
    _fmt(users).to_csv(os.path.join(ARGS.out, "User.csv"), index=False)
    pd.DataFrame([dict(Id=ROLE_ID[r], Name=r, ParentRoleId=ROLE_ID.get(ROLE_PARENT.get(r)) if r in ROLE_PARENT else None)
                  for r in ROLES]).to_csv(os.path.join(ARGS.out, "UserRole.csv"), index=False)
    gm = {}
    for u in USERS:
        if u["_role"] == "General Manager" and u["IsActive"]:
            gm[u["_sr"]] = u["Id"]
    sr = pd.DataFrame([dict(Id=SR_ID[i], Name=s[0], City__c=s[1], State__c=s[2], Postal_Code__c=s[3],
                            Time_Zone__c=TZ_LABEL[s[6]], Showroom_Type__c=s[4], Opened_Date__c=s[5],
                            Open_Sundays__c=s[7], General_Manager__c=gm.get(i),
                            CreatedDate=T0 + min(dix(s[5]), 0) * 86400 + 15 * 3600)
                       for i, s in enumerate(SHOWROOMS)])
    _fmt(sr).to_csv(os.path.join(ARGS.out, "Showroom__c.csv"), index=False)
    pr = pd.DataFrame(PROD)
    _fmt(pr[[c for c in pr.columns if not c.startswith("_")]]).to_csv(os.path.join(ARGS.out, "Product2.csv"), index=False)


if __name__ == "__main__":
    t_start = time.time()
    if os.path.exists(ARGS.out):
        shutil.rmtree(ARGS.out)
    os.makedirs(ARGS.out)
    write_global()
    totals = {}
    with Pool(ARGS.workers) as pool:
        for c in pool.imap_unordered(run_shard, range(ARGS.shards)):
            for k, v in c.items():
                totals[k] = totals.get(k, 0) + v
    for k in COLS:   # stitch shard parts into one CSV per object
        with open(os.path.join(ARGS.out, f"{k}.csv"), "wb") as out:
            out.write((",".join(COLS[k]) + "\n").encode())
            for sh in range(ARGS.shards):
                with open(os.path.join(ARGS.out, "_parts", f"{k}.{sh:03d}.csv"), "rb") as f:
                    shutil.copyfileobj(f, out)
    shutil.rmtree(os.path.join(ARGS.out, "_parts"))
    # campaign roll-ups
    camp = pd.DataFrame(CAMPS)
    cm = pd.read_csv(os.path.join(ARGS.out, "CampaignMember.csv"), usecols=["CampaignId", "LeadId"])
    ld = pd.read_csv(os.path.join(ARGS.out, "Lead.csv"), usecols=["Id", "IsConverted"])
    op = pd.read_csv(os.path.join(ARGS.out, "Opportunity.csv"), usecols=["CampaignId", "IsWon", "Amount"])
    cm = cm.merge(ld, left_on="LeadId", right_on="Id", how="left")
    a = cm.groupby("CampaignId").agg(NumberOfLeads=("LeadId", "nunique"), NumberOfConvertedLeads=("IsConverted", "sum"))
    b = op.groupby("CampaignId").agg(NumberOfOpportunities=("IsWon", "size"), NumberOfWonOpportunities=("IsWon", "sum"),
                                     AmountWonOpportunities=("Amount", lambda s: s[op.loc[s.index, "IsWon"]].sum()))
    camp = camp.merge(a, left_on="Id", right_index=True, how="left").merge(b, left_on="Id", right_index=True, how="left")
    for c in ("NumberOfLeads", "NumberOfConvertedLeads", "NumberOfOpportunities", "NumberOfWonOpportunities",
              "AmountWonOpportunities"):
        camp[c] = camp[c].fillna(0)
        if c != "AmountWonOpportunities":
            camp[c] = camp[c].astype(int)
    _fmt(camp).to_csv(os.path.join(ARGS.out, "Campaign.csv"), index=False)
    for k in ["Lead", "Account", "Contact", "Opportunity", "OpportunityHistory", "Task", "Event", "CampaignMember"]:
        print(f"{k:20s} {totals.get(k, 0):>10,}")
    if not ARGS.keep_pii:   # irreversibly pseudonymise personal fields (see anonymize_pii.py)
        import subprocess
        import sys
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "anonymize_pii.py"),
                        ARGS.out], check=True)
    print(f"done in {time.time() - t_start:.0f}s")
