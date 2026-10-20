# Quillon Auto Group: synthetic dealership CRM (Salesforce-style)

**Version 1.0** · generated with seed 7 · extract date 2026-09-30 · 100% synthetic

A simulated car-dealership group exported in Salesforce's shape. Files are named after objects,
columns use field API names, Ids are 18 characters with valid Salesforce checksums and real key
prefixes, and datetimes use Salesforce's export format (`2025-03-14T15:22:10.000+0000`, **UTC**).
Date fields (`ActivityDate`, `CloseDate`, `ConvertedDate`, ...) are in the showroom's **local** date.

- **Company:** Quillon Auto Group, 12 showrooms in 10 fictional states across 4 US time zones, selling vehicles from a
  fictional manufacturer, *Tarvessa Motors* (models: Zevi, Ostra, Kaveno, Orvik, Talmar, Draxen, Nuvessa, Elarion): new, used and certified pre-owned (CPO).
- **Period:** leads created 2023-01-01 → 2026-09-30 (the extract date). Records near the end are still open.
- **Volume:** 500,000 leads from 446,934 people. **15.3% of leads end in a purchase** (76,585 vehicles, median sale $31,500).
  Other benchmarks: 38% of leads visit a showroom, 73% of appointments show up, and the median first response to an online lead is ~1.6 h
  (17% within 5 minutes; after-hours leads wait for opening).
- **Everything is fictional.** Quillon Auto Group, Tarvessa Motors and every model, person, email and phone number are invented;
  any resemblance to real businesses or people is coincidental. Patterns in the data come from the generator's rules, not from real dealerships.
- **Reproducible:** `python generate_dealership_crm.py data --leads 500000 --seed 7`
  (about 2 minutes on 2 cores; `pip install numpy pandas faker duckdb`).

## Privacy: nothing links to a real person or place

- **Personal fields are hashed.** First and last names, full names, emails and phone numbers on Lead, Account,
  Contact and User, plus the customer name inside `Opportunity.Name`, are replaced by 16-character tokens.
  Each token is a SHA-256 hash keyed with a random secret that was generated for the run and then discarded,
  so tokens can't be reversed, recomputed, or matched against outside lists of emails or phone numbers.
- **Tokens are consistent within the dataset.** The same person has the same name, email and phone tokens on their
  Lead, Account and Contact, so joins and duplicate detection still work.
- **All geography is fictional.** Town names are invented. State codes (QX, ZR, XV, JD, KW, QO, XB, ZL, YQ, JX) are not
  USPS codes. ZIP codes fall in 00100–00499, a range USPS has never assigned. Time zones are real US zones,
  used only to set business hours.
- **The underlying people never existed.** The values that were hashed were themselves randomly generated.
- The hashing runs automatically at the end of `generate_dealership_crm.py` via `anonymize_pii.py`
  (use `--keep-pii` to skip it when you want readable fake names for demos).

See **SCHEMA.md** for a field-by-field explanation of every table.

## Files

| File | Rows | What it is |
|---|---|---|
| Lead.csv | 500,000 | Every shopper inquiry or walk-in (converted leads stay, with `IsConverted = true`) |
| Account.csv | 181,084 | Person Accounts (B2C): one per shopper who visited a showroom |
| Contact.csv | 181,084 | The contact behind each Person Account (`Account.PersonContactId`) |
| Opportunity.csv | 190,007 | One per showroom visit that became a deal: 76,585 won (vehicles sold) |
| OpportunityHistory.csv | 812,759 | One row per stage change |
| Task.csv | 2,702,844 | Calls (with disposition & duration), texts (SMS), emails, to-dos |
| Event.csv | 506,597 | Appointments, walk-in visits, test drives, return visits, deliveries |
| CampaignMember.csv | 260,794 | Leads attributed to a marketing campaign |
| Campaign.csv | 83 | Sales events, paid search, social, marketplaces, OEM & referral programs |
| Showroom__c.csv | 12 | Custom object: the dealerships (fictional town, state code and ZIP; time zone, type, opening date) |
| Product2.csv | 22 | Vehicle catalog: model, trim, body type, fuel type, MSRP |
| User.csv | 676 | Staff incl. those who left: GMs, sales managers, F&I managers, consultants, BDC reps |
| UserRole.csv | 7 | Role hierarchy |

A Parquet copy of every table is included (about 126 MB versus 1.1 GB of CSV) for pandas, DuckDB or Spark.

## How the objects connect

```
Campaign ─< CampaignMember >─ Lead ──(showroom visit = conversion)──> Account (person) ─ Contact
                                │                                          │
                                └──────< Task / Event >──── Opportunity ───┘ ─< OpportunityHistory
Showroom__c ─< Lead, Opportunity, Event, User          Product2 ─< Opportunity.Vehicle__c, Lead.Vehicle_Interest__c
User ─< OwnerId on everything
```

- `Lead.ConvertedAccountId / ConvertedContactId / ConvertedOpportunityId` link a lead to the visit and deal it produced.
- `Task.WhoId`/`Event.WhoId` point to a Lead or Contact; `WhatId` points to an Opportunity.
- A returning shopper keeps one Person Account; each new visit adds an Opportunity to it.

## The funnel

1. **Lead arrives.** By website form, third-party marketplace, OEM referral, paid search, social ad, chat,
   referral, sales-event promo, phone call, or a walk-in. Volume follows car-buying seasonality (busy in
   March, May, August, December and during sales events; slow in January) and arrives at realistic hours
   (online leads peak in the evening).
2. **BDC works it.** A BDC rep at the showroom responds (response time depends on the hour and the rep),
   then follows a call / text / email cadence for up to 2 weeks until the shopper replies or goes cold.
3. **Appointment.** Booked with a sales consultant, confirmed by text the day before. Some shoppers
   don't show up; some reschedule.
4. **Showroom visit → lead converts → Opportunity** (`Needs Assessment`).
   Walk-ins and phone calls skip the BDC steps.
5. **Test Drive → Proposal** (pricing worksheet) **→ Negotiation → Financing** (credit application with
   the F&I manager for finance or lease deals) → **Closed Won** + a **Vehicle Delivery** event, or **Closed Lost**.
   About half of buyers buy on the day of their visit; the rest come back after follow-ups ("be-backs").

| Stage | Probability | Forecast category |
|---|---|---|
| Needs Assessment | 20 | Pipeline |
| Test Drive | 40 | Pipeline |
| Proposal | 60 | Best Case |
| Negotiation | 75 | Commit |
| Financing | 90 | Commit |
| Closed Won / Closed Lost | 100 / 0 | Closed / Omitted |

### What drives a purchase (the signal a model can learn)

Each lead has a hidden purchase propensity built from:
- **Lead source.** Purchase rates range from 6% for social media to 14% for website, 20% for phone and 34% for walk-ins.
- **Purchase timeline.** "Immediately" leads buy most; "Just Browsing" leads least.
- **Prequalified for credit**, and **has a trade-in**.
- **Distance** from the showroom.
- **Affordability.** Leads whose budget is well below their vehicle of interest buy less.
- **Sales-event timing**, and **no phone number given** (email-only leads buy less).
- **A per-person random effect** plus noise.

On top of that:
- **Speed to lead.** First responses within 5 minutes help; responses over a day late hurt. After-hours and Sunday leads wait for opening.
- **Staff skill and ramp-up.** Reps differ, and new hires underperform for their first ~2 months. Salesperson turnover is high, as in real dealerships.
- **Discount.** Bigger discounts raise the chance a proposal moves to negotiation.
- **Credit tier.** It determines financing approval. "Financing Declined" is a loss reason.
- **Used and CPO inventory.** A used or CPO car can sell to someone else before a be-back returns ("Vehicle No Longer Available").

## Key fields

**Lead**: `LeadSource`, `Status` (Open - Not Contacted, Working - Contacted, Closed - Converted, Closed - Not Converted),
`Rating`, `Showroom__c`, `Vehicle_Interest__c` (→ Product2), `Condition_Interest__c` (New / Used / Certified Pre-Owned),
`Purchase_Timeline__c`, `Budget_Range__c`, `Trade_In__c` (Yes / No / blank), `Payment_Preference__c`
(Finance / Lease / Cash / Undecided), `Prequalified__c`, `Preferred_Contact_Method__c`, `Distance_Miles__c`,
`IsConverted`, `ConvertedDate`, `Lost_Reason__c`, `HasOptedOutOfEmail`, address fields, `CreatedDate`.

**Opportunity**: `Type` (New Vehicle / Used Vehicle / Certified Pre-Owned), `StageName`, `Amount` (sale price),
`List_Price__c`, `Discount__c`, `Vehicle__c` (→ Product2), `Vehicle_Model_Year__c`, `Trade_In__c`,
`Trade_In_Value__c`, `Payment_Method__c`, `Credit_Tier__c` (only once a credit app is run), `Finance_Term_Months__c`,
`Test_Drive_Completed__c`, `Loss_Reason__c`, `Showroom__c`, `CampaignId`, `CloseDate`, `IsWon`.

**Task**: `Type` (Call / SMS / Email / Other), `TaskSubtype`, `Subject`, `CallType` (Inbound / Outbound),
`CallDisposition` (Connected / Left Voicemail / No Answer / Wrong Number), `CallDurationInSeconds`, `Status`, `CompletedDateTime`.

**Event**: `Subject` (Showroom Appointment, Showroom Visit, Test Drive, Return Visit, Vehicle Delivery),
`Type`, `Outcome__c` (Completed / No Show / Scheduled), `Showroom__c`, `StartDateTime`, `CreatedById` (who booked it).

**Showroom__c**: `City__c`, `State__c`, `Postal_Code__c`, `Time_Zone__c` (Eastern / Central / Mountain / Mountain (no DST) / Pacific),
`Showroom_Type__c` (Flagship / Standard / Satellite), `Opened_Date__c`, `Open_Sundays__c`. Queensmarch opened Sept 2024 and
Kingsbrae April 2025; their volume ramps up after opening.

**User**: `Title` (role), `Showroom__c`, `ManagerId`, `Hire_Date__c`, `Termination_Date__c`, `IsActive`.

## Realistic quirks

- **Activities move on conversion.** When a lead converts, its tasks and events are re-parented to the
  new Contact (`WhoId`), as Salesforce does. To rebuild pre-visit history, join through `Lead.ConvertedContactId`.
- **Sunday rules.** Showrooms in states QX, KW, QO and JX are closed Sundays (modelled on US state car-sales laws);
  the others open 11:00–17:00. All are closed on New Year's Day, Thanksgiving and Christmas.
- **Messy data.** Many optional lead fields are blank. Some leads are duplicates of a recent inquiry
  (`Lost_Reason__c = Duplicate`), and some shoppers return months later, or come back as repeat buyers.
- **Point-in-time fields.** `Status`, `IsConverted`, `Rating`, `Lost_Reason__c`, `LastModifiedDate` and
  `LastActivityDate` reflect the extract date. For lead scoring, use only information available at the
  prediction time (lead fields at creation + activity before the cutoff), and split train/test by `CreatedDate`.

## Suggested uses

- **Purchase-propensity / lead scoring:** did the lead buy? (`Lead → ConvertedOpportunityId → IsWon`)
- **Appointment show-rate**, speed-to-lead and BDC cadence analysis
- **Opportunity win prediction** from stage history; deal-size and discount analysis
- **Campaign ROI:** cost per lead / per sale by campaign
- **Showroom and salesperson performance**, including staff turnover and ramp-up
