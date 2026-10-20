# Quillon Auto Group CRM: schema explainer

This file explains every table and every field in the dataset: what it means, its type, how often it is
filled, and the values it can take.

**About the data.** Quillon Auto Group is a fictional dealership group with 12 showrooms selling cars made
by Tarvessa Motors, a fictional manufacturer. The tables mimic a Salesforce org, so names follow Salesforce
conventions:

- Fields ending in `__c` are **custom fields** the dealership added. `Showroom__c` as a table name is a custom object.
- Fields ending in `Id` (and lookup fields such as `Showroom__c`, `Vehicle__c`) hold an **18-character Salesforce Id**
  pointing to a record in another table. The first 3 characters tell you the object:
  `00Q` Lead · `001` Account · `003` Contact · `006` Opportunity · `008` OpportunityHistory · `00T` Task ·
  `00U` Event · `701` Campaign · `00v` CampaignMember · `005` User · `00E` UserRole · `01t` Product2 · `a0S` Showroom__c.
- **Datetime** fields (`CreatedDate`, `StartDateTime`, …) are in **UTC**, Salesforce export format
  `2025-03-14T15:22:10.000+0000`. **Date** fields (`ActivityDate`, `CloseDate`, `ConvertedDate`, …) are the
  showroom's **local** calendar date.
- **🔒 hashed**: personal values replaced by a 16-character one-way code (see the README's privacy section).
  The same person always has the same code, so you can join and de-duplicate on these fields, but they can't be reversed.
- **Fill** = share of rows where the field is not blank. Blanks are meaningful: see each field's note.
- **Extract date:** 2026-09-30. Everything is as of that day. Records created close to it may still be open.

Contents: [Lead](#lead) · [Account](#account) · [Contact](#contact) · [Opportunity](#opportunity) ·
[OpportunityHistory](#opportunityhistory) · [Task](#task) · [Event](#event) · [Campaign](#campaign) ·
[CampaignMember](#campaignmember) · [Showroom__c](#showroom__c) · [Product2](#product2) · [User](#user) ·
[UserRole](#userrole) · [Joining the tables](#joining-the-tables)

---

## Lead

**One row per shopper inquiry** (web form, marketplace lead, phone call, walk-in…). 500,000 rows × 32 columns.
The same person can appear on several leads if they inquire again (see [Joining the tables](#joining-the-tables)).
A lead **converts** when the shopper physically visits a showroom: Salesforce then creates (or reuses) an
Account and Contact, and creates an Opportunity. Converted leads stay in this table with `IsConverted = true`.

| Field | Type | Fill | Meaning |
|---|---|---|---|
| Id | Id | 100% | Unique lead Id (`00Q…`). |
| FirstName | text 🔒 | 100% | Shopper's first name, hashed. |
| LastName | text 🔒 | 100% | Shopper's last name, hashed. |
| Email | text 🔒 | 93.7% | Shopper's email, hashed. Blank when the shopper didn't give one (common for walk-ins and phone calls). |
| MobilePhone | text 🔒 | 92.2% | Shopper's mobile number, hashed. Blank for some online leads that gave only an email; these leads can only be contacted by email. |
| City | text | 100% | Shopper's home town (fictional). |
| State | text | 100% | Shopper's home state: a fictional 2-letter code (QX, ZR, XV, JD, KW, QO, XB, ZL, YQ, JX). |
| PostalCode | text | 100% | Shopper's ZIP code: fictional, 00100–00491. |
| LeadSource | text | 100% | Where the lead came from: **Website** (dealer site form), **Third-Party Marketplace** (car-listing sites), **OEM Referral** (from the manufacturer's site), **Walk-In** (came into the showroom unannounced), **Phone Inquiry** (called the showroom), **Paid Search**, **Social Media**, **Chat** (website chat), **Referral** (friend/family referral program), **Sales Event** (responded to a sales-event promotion), **Repeat Customer** (returning after a previous purchase). |
| Status | text | 100% | Lead stage at the extract date. **Open - Not Contacted**: no one has reached out yet. **Working - Contacted**: being worked (touches in progress or an appointment pending). **Closed - Converted**: the shopper visited; see the Converted* fields. **Closed - Not Converted**: the lead was closed without a visit; see `Lost_Reason__c`. |
| Rating | text | 27.5% | Rep's judgement of how hot the lead is: **Hot / Warm / Cold**. Only set by some reps after talking to the shopper; blank otherwise. |
| OwnerId | Id → User | 100% | Who owns the lead. Before conversion, usually the BDC rep working it. After conversion, the sales consultant who met the shopper. |
| Showroom__c | Id → Showroom__c | 100% | The showroom the lead was routed to. |
| Vehicle_Interest__c | Id → Product2 | 73.4% | The model/trim the shopper asked about. Blank when they didn't specify one (often walk-ins). |
| Condition_Interest__c | text | 86.7% | Whether they want a **New**, **Used** or **Certified Pre-Owned** vehicle. |
| Purchase_Timeline__c | text | 65.1% | Self-reported buying timeline: **Immediately**, **1-3 Months**, **3-6 Months**, **Just Browsing**. Blank = not answered. One of the strongest purchase signals. |
| Budget_Range__c | text | 55.1% | Self-reported budget: **Under $20k**, **$20k-$30k**, **$30k-$40k**, **$40k-$55k**, **$55k+**. Blank = not answered. |
| Trade_In__c | text | 65.0% | Whether the shopper said they have a vehicle to trade in: **Yes** / **No**. Blank = not answered (some of them do have one). |
| Payment_Preference__c | text | 100% | How they plan to pay: **Finance**, **Lease**, **Cash** or **Undecided**. |
| Prequalified__c | true/false | 100% | Whether the shopper completed an online credit pre-qualification. |
| Preferred_Contact_Method__c | text | 100% | How the shopper prefers to be contacted: **Phone**, **Text** or **Email**. |
| Distance_Miles__c | number | 100% | Distance from the shopper's home to the showroom, in miles (median ≈ 9, range 0.3–200). |
| IsConverted | true/false | 100% | Whether the lead converted (visited a showroom). 38% are true. |
| ConvertedDate | date | 38.0% | Local date of conversion (the visit). Blank if not converted. |
| ConvertedAccountId | Id → Account | 38.0% | The person account created or reused at conversion. |
| ConvertedContactId | Id → Contact | 38.0% | The contact created or reused at conversion. **Use this to find the lead's activity history after conversion** (see Task). |
| ConvertedOpportunityId | Id → Opportunity | 38.0% | The deal opened at the visit. Join to Opportunity to see whether the lead **bought** (`IsWon`). |
| HasOptedOutOfEmail | true/false | 100% | The shopper asked not to receive marketing email. |
| Lost_Reason__c | text | 60.5% | Why the lead was closed without a visit (filled for every `Closed - Not Converted` lead): **Unresponsive**, **Not Ready to Buy**, **Bought Elsewhere**, **Price Shopping**, **Credit Concerns**, **Out of Area**, **Duplicate** (a repeat inquiry from the same person shortly after another). |
| CreatedDate | datetime | 100% | When the lead came in (UTC). |
| LastModifiedDate | datetime | 100% | When the lead record last changed (UTC). |
| LastActivityDate | date | 98.9% | Local date of the most recent completed task or event on the lead (before conversion). |

## Account

**One row per shopper who has visited a showroom** (a Salesforce *Person Account*, used for consumer sales).
181,084 rows × 16 columns. Created when the shopper's first lead converts; reused if they come back.

| Field | Type | Fill | Meaning |
|---|---|---|---|
| Id | Id | 100% | Unique account Id (`001…`). |
| IsPersonAccount | true/false | 100% | Always true: every account is an individual, not a business. |
| FirstName | text 🔒 | 100% | Customer's first name, hashed. |
| LastName | text 🔒 | 100% | Customer's last name, hashed. |
| Name | text 🔒 | 100% | Customer's full name, hashed. The same code appears at the start of their Opportunity names. |
| PersonEmail | text 🔒 | 87.5% | Customer's email, hashed. |
| PersonMobilePhone | text 🔒 | 100% | Customer's mobile number, hashed. |
| PersonContactId | Id → Contact | 100% | The Contact record that represents this person. |
| BillingCity | text | 100% | Home town (fictional). |
| BillingState | text | 100% | Home state (fictional code). |
| BillingPostalCode | text | 100% | Home ZIP (fictional). |
| AccountSource | text | 100% | Lead source of the lead that created the account (same values as `Lead.LeadSource`). |
| Showroom__c | Id → Showroom__c | 100% | Showroom where the customer first visited. |
| Type | text | 100% | **Customer** if they have bought at least one vehicle, otherwise **Prospect**. |
| OwnerId | Id → User | 100% | Sales consultant who owns the relationship. |
| CreatedDate | datetime | 100% | When the account was created (= first visit). |

## Contact

**The person behind each Account**, 1-to-1. 181,084 rows × 13 columns.
Tasks and events about a converted shopper point here (`WhoId`).

| Field | Type | Fill | Meaning |
|---|---|---|---|
| Id | Id | 100% | Unique contact Id (`003…`). |
| AccountId | Id → Account | 100% | The person account this contact belongs to. |
| FirstName | text 🔒 | 100% | First name, hashed (same code as on the Account and Lead). |
| LastName | text 🔒 | 100% | Last name, hashed. |
| Email | text 🔒 | 87.5% | Email, hashed. |
| MobilePhone | text 🔒 | 100% | Mobile number, hashed. |
| MailingCity | text | 100% | Home town (fictional). |
| MailingState | text | 100% | Home state (fictional code). |
| MailingPostalCode | text | 100% | Home ZIP (fictional). |
| LeadSource | text | 100% | Source of the lead that created the contact. |
| OwnerId | Id → User | 100% | Owning sales consultant. |
| HasOptedOutOfEmail | true/false | 100% | Opted out of marketing email. |
| CreatedDate | datetime | 100% | When the contact was created (= first visit). |

## Opportunity

**One row per showroom visit that became a potential sale (a "deal")**. 190,007 rows × 34 columns.
Each converted lead creates one. `IsWon = true` means a **vehicle was sold** (76,585 sales).

Stages, in order: **Needs Assessment** (20%) → **Test Drive** (40%) → **Proposal** (pricing worksheet shown, 60%) →
**Negotiation** (75%) → **Financing** (credit application, finance and lease deals only, 90%) → **Closed Won** (100%) or **Closed Lost** (0%).
A deal can be lost at any stage. Stages can be skipped (e.g. no test drive, or a cash deal that skips Financing).

| Field | Type | Fill | Meaning |
|---|---|---|---|
| Id | Id | 100% | Unique opportunity Id (`006…`). |
| AccountId | Id → Account | 100% | The customer. |
| ContactId | Id → Contact | 100% | The customer's contact record. |
| Name | text | 100% | Deal name: hashed customer name + vehicle, e.g. `93e5e63e79c3e2b7 - 2022 Tarvessa Zevi S`. |
| Type | text | 100% | **New Vehicle**, **Used Vehicle** or **Certified Pre-Owned**. |
| StageName | text | 100% | Current stage (see list above). At the extract date most deals are closed; a few hundred are still open in Needs Assessment, Test Drive or Proposal. |
| Amount | number ($) | 100% | Deal value: the agreed sale price once pricing is presented (`List_Price__c − Discount__c`, minus any extra negotiation), otherwise the list price. Excludes trade-in, taxes and fees. |
| Probability | integer (%) | 100% | Win probability attached to the current stage (fixed per stage, see above). |
| ExpectedRevenue | number ($) | 100% | `Amount × Probability / 100`. |
| CloseDate | date | 100% | Local date the deal was won or lost. For open deals, the expected close date. |
| IsClosed | true/false | 100% | Deal is finished (won or lost). |
| IsWon | true/false | 100% | **The vehicle was sold.** This is the purchase outcome. |
| ForecastCategoryName | text | 100% | Salesforce forecast bucket: **Pipeline**, **Best Case**, **Commit**, **Closed** (won), **Omitted** (lost). |
| LeadSource | text | 100% | Source of the lead behind the deal. |
| CampaignId | Id → Campaign | 33.7% | Marketing campaign credited with the deal. Blank for sources with no campaign (Website, Walk-In, Phone, Chat, Repeat Customer). |
| OwnerId | Id → User | 100% | Sales consultant handling the deal. |
| Showroom__c | Id → Showroom__c | 100% | Showroom where the deal happened. |
| Vehicle__c | Id → Product2 | 100% | Vehicle model/trim being sold. |
| Vehicle_Model_Year__c | integer | 100% | Model year of the vehicle. Used and CPO cars are older model years. |
| List_Price__c | number ($) | 100% | Sticker price of that specific vehicle (for used/CPO, depends on age). |
| Discount__c | number ($) | 68.0% | Discount offered on the pricing worksheet. Blank if the deal never reached Proposal. |
| Trade_In__c | true/false | 100% | Whether the customer is trading in a vehicle. |
| Trade_In_Value__c | number ($) | 47.4% | Value offered for the trade-in. Blank when there's no trade-in. |
| Payment_Method__c | text | 42.9% | **Finance**, **Lease** or **Cash**. Set when the deal reaches Negotiation; blank before that. |
| Credit_Tier__c | text | 35.0% | Customer's credit tier from the credit application: **Super Prime**, **Prime**, **Near Prime**, **Subprime**, **Deep Subprime**. Blank for cash deals and deals that never reached Financing. Lower tiers are more often declined. |
| Finance_Term_Months__c | integer | 32.4% | Loan or lease length in months (24, 36, 39 for leases; 48, 60, 72, 84 for loans). Blank for cash or unfinished deals. |
| Test_Drive_Completed__c | true/false | 100% | The customer test-drove a vehicle. |
| Loss_Reason__c | text | 58.7% | Why a lost deal was lost (filled for every Closed Lost deal): **Not Ready to Buy**, **Bought Elsewhere**, **Just Looking**, **Price**, **Monthly Payment Too High**, **Vehicle Not Available**, **Financing Declined**, **Trade-In Value**, **Vehicle No Longer Available** (a used/CPO car sold to someone else before the customer came back). |
| CreatedDate | datetime | 100% | When the deal was opened (= the showroom visit). |
| LastStageChangeDate | datetime | 100% | When the deal last moved stage (for closed deals, the close moment). |
| LastModifiedDate | datetime | 100% | Last change to the record (stage change or logged activity). |
| LastActivityDate | date | 99.9% | Local date of the latest task or event on the deal. |
| FiscalYear | integer | 100% | Year of `CloseDate` (fiscal year = calendar year). |
| FiscalQuarter | integer | 100% | Quarter (1–4) of `CloseDate`. |

## OpportunityHistory

**One row per stage a deal entered.** 812,759 rows × 10 columns. Lets you reconstruct where any deal stood on any
past date (e.g. how much pipeline existed at the start of a month) and how long deals spent in each stage.

| Field | Type | Fill | Meaning |
|---|---|---|---|
| Id | Id | 100% | Unique history row Id (`008…`). |
| OpportunityId | Id → Opportunity | 100% | The deal. |
| StageName | text | 100% | The stage the deal moved into. |
| Amount | number ($) | 100% | Deal amount at that moment (it changes once pricing is presented and during negotiation). |
| ExpectedRevenue | number ($) | 100% | `Amount × Probability / 100` at that moment. |
| Probability | integer (%) | 100% | Stage probability. |
| ForecastCategory | text | 100% | Forecast bucket at that moment. |
| CloseDate | date | 100% | Expected close date at that moment (actual close date on the Closed rows). |
| CreatedById | Id → User | 100% | User who moved the stage (the deal owner). |
| CreatedDate | datetime | 100% | **When the stage change happened.** Order by this to get each deal's path. |

## Task

**One row per logged activity that isn't a meeting**: calls, text messages, emails and to-dos.
2,702,844 rows × 17 columns. Most are outreach by BDC reps to new leads; the rest are sales-consultant follow-ups on deals.

> **Important: activities move on conversion.** When a lead converts, Salesforce re-points its tasks to the new
> Contact. So `WhoId` is a **Lead Id** for leads that never converted, but a **Contact Id** for leads that did,
> including the tasks logged before the visit. To get a lead's full history, match `WhoId` to `Lead.Id` **or**
> `Lead.ConvertedContactId`, and use the timestamps to separate before and after conversion.

| Field | Type | Fill | Meaning |
|---|---|---|---|
| Id | Id | 100% | Unique task Id (`00T…`). |
| WhoId | Id → Lead or Contact | 100% | The person the activity was with (see the note above). |
| WhatId | Id → Opportunity | 18.2% | The deal the task relates to. Blank for tasks logged while the shopper was still a lead. |
| AccountId | Id → Account | 34.8% | The customer's account. Blank while the shopper is still an unconverted lead. |
| OwnerId | Id → User | 100% | Who did the task (BDC rep, sales consultant or F&I manager). |
| Subject | text | 100% | What the task was. **Lead outreach:** Call, Inbound call, SMS: Intro / Follow up / Checking in / Last attempt, Email: Intro / Vehicle info & pricing / Follow up / Checking in / Last attempt, SMS/Email: Customer reply (the shopper replied), Appointment confirmation. **Deal follow-up:** Present pricing worksheet, Follow up after visit, Be-back follow up (chasing a shopper who left without buying), SMS: Following up on your quote, Follow up on quote, Credit application submitted, Follow up (open to-do). |
| Type | text | 100% | Channel: **Call**, **SMS**, **Email**, **Other** (to-dos such as presenting a worksheet). |
| TaskSubtype | text | 100% | Salesforce subtype: **Call**, **Email** or **Task** (SMS and to-dos). |
| Status | text | 100% | **Completed** (done), or **Not Started** (an open to-do due around the extract date). |
| Priority | text | 100% | **Normal** or **High**. |
| ActivityDate | date | 100% | Local date the task was done (or is due). |
| CompletedDateTime | datetime | ~100% | When it was completed (UTC). Blank for the few hundred Not Started to-dos. |
| CallType | text | 34.0% | Calls only: **Outbound** (rep called the shopper) or **Inbound** (shopper called in). |
| CallDisposition | text | 33.7% | Calls only, result of the call: **Connected**, **Left Voicemail**, **No Answer**, **Wrong Number**. |
| CallDurationInSeconds | integer | 33.7% | Calls only, length of the call in seconds. |
| IsClosed | true/false | 100% | true when Status = Completed. |
| CreatedDate | datetime | 100% | When the task was logged. |

**Useful derived metric: speed to lead.** First completed task time − `Lead.CreatedDate`. Faster first responses
lead to more conversions in this data.

## Event

**One row per meeting or visit on the calendar.** 506,597 rows × 18 columns. Same `WhoId` re-pointing rule as Task.

| Field | Type | Fill | Meaning |
|---|---|---|---|
| Id | Id | 100% | Unique event Id (`00U…`). |
| WhoId | Id → Lead or Contact | 100% | The shopper. |
| WhatId | Id → Opportunity | 54.1% | The related deal. Blank for pre-visit appointments and walk-in visits (logged before the deal existed). |
| AccountId | Id → Account | 93.8% | The customer's account. Blank for appointments of leads that never converted. |
| OwnerId | Id → User | 100% | The sales consultant hosting the meeting. |
| Showroom__c | Id → Showroom__c | 100% | Where it took place. |
| Subject | text | 100% | **Showroom Appointment** (booked visit), **Showroom Visit** (walked in unannounced), **Test Drive**, **Return Visit** (came back to finish a deal), **Vehicle Delivery** (picked up the purchased car). |
| Type | text | 100% | **Appointment**, **Walk-In**, **Test Drive**, **Delivery**. |
| StartDateTime | datetime | 100% | Start (UTC). |
| EndDateTime | datetime | 100% | End (UTC). |
| DurationInMinutes | integer | 100% | Length in minutes. |
| ActivityDate | date | 100% | Local date of the event. |
| Location | text | 100% | Showroom name. |
| ShowAs | text | 100% | Calendar availability, always **Busy**. |
| IsAllDayEvent | true/false | 100% | Always false. |
| Outcome__c | text | 100% | **Completed** (it happened), **No Show** (shopper didn't come), **Scheduled** (booked for after the extract date). |
| CreatedById | Id → User | 100% | Who booked it (usually the BDC rep for appointments). |
| CreatedDate | datetime | 100% | When it was booked. |

## Campaign

**One row per marketing campaign.** 83 rows × 16 columns.

| Field | Type | Fill | Meaning |
|---|---|---|---|
| Id | Id | 100% | Unique campaign Id (`701…`). |
| Name | text | 100% | Campaign name, e.g. "Memorial Day Sales Event 2025", "Paid Search - Google Ads 2025Q2". |
| Type | text | 100% | **Sales Event** (8 per year, e.g. Presidents' Day, Labor Day, Black Friday, Year-End), **Paid Search**, **Social Media**, **Third-Party Marketplace** (quarterly listing budgets), **OEM Program** (manufacturer lead program, yearly), **Referral Program** (yearly). |
| Status | text | 100% | **Completed** or **In Progress** (still running at the extract date). |
| StartDate | date | 100% | First day. |
| EndDate | date | 100% | Last day. |
| IsActive | true/false | 100% | true while In Progress. |
| BudgetedCost | number ($) | 100% | Planned spend. |
| ActualCost | number ($) | 100% | Actual spend. Use with the roll-ups below for cost per lead or cost per sale. |
| OwnerId | Id → User | 100% | Marketing manager who runs it. |
| CreatedDate | datetime | 100% | When the campaign record was set up (a few weeks before start). |
| NumberOfLeads | integer | 100% | Leads attributed to the campaign. |
| NumberOfConvertedLeads | integer | 100% | Of those, how many visited a showroom. |
| NumberOfOpportunities | integer | 100% | Deals credited to the campaign. |
| NumberOfWonOpportunities | integer | 100% | Of those, how many were sold. |
| AmountWonOpportunities | number ($) | 100% | Total sale value of those won deals. |

## CampaignMember

**Links a lead to the campaign it responded to.** 260,794 rows × 8 columns. Only leads from campaign-driven sources
have one (Third-Party Marketplace, OEM Referral, Paid Search, Social Media, Referral, Sales Event).

| Field | Type | Fill | Meaning |
|---|---|---|---|
| Id | Id | 100% | Unique member Id (`00v…`). |
| CampaignId | Id → Campaign | 100% | The campaign. |
| LeadId | Id → Lead | 100% | The lead that responded. |
| ContactId | Id → Contact | 24.6% | Filled once that lead converts. |
| Status | text | 100% | Always **Responded**. |
| HasResponded | true/false | 100% | Always true. |
| FirstRespondedDate | date | 100% | Local date of the response (= lead creation date). |
| CreatedDate | datetime | 100% | When the membership was recorded. |

## Showroom__c

**Custom object: one row per dealership location.** 12 rows × 11 columns. All places are fictional.

| Field | Type | Fill | Meaning |
|---|---|---|---|
| Id | Id | 100% | Unique showroom Id (`a0S…`). |
| Name | text | 100% | Showroom name, e.g. "Quillon Auto Larkhaven". |
| City__c | text | 100% | Town (fictional). |
| State__c | text | 100% | State (fictional code). |
| Postal_Code__c | text | 100% | ZIP (fictional). |
| Time_Zone__c | text | 100% | **Eastern**, **Central**, **Mountain**, **Mountain (no DST)** or **Pacific**. Add the UTC offset to datetimes to get local time. |
| Showroom_Type__c | text | 100% | **Flagship** (largest, most traffic), **Standard**, **Satellite** (small, newer). |
| Opened_Date__c | date | 100% | Opening date. Two satellites opened during the data period (Queensmarch Sept 2024, Kingsbrae April 2025), and their volume ramps up after opening. |
| Open_Sundays__c | true/false | 100% | Whether the showroom trades on Sundays (modelled on state laws). Closed-Sunday showrooms have no visits on Sundays, and their Sunday online leads wait until Monday. |
| General_Manager__c | Id → User | 91.7% | Current general manager. Blank where the seat was vacant at the extract date. |
| CreatedDate | datetime | 100% | Record creation. |

## Product2

**The vehicle catalog: one row per model and trim.** 22 rows × 11 columns. All models are fictional.

| Field | Type | Fill | Meaning |
|---|---|---|---|
| Id | Id | 100% | Unique product Id (`01t…`). |
| Name | text | 100% | Full name, e.g. "Tarvessa Orvik EX". |
| ProductCode | text | 100% | Internal code, e.g. `TRV-ORV-2`. |
| Family | text | 100% | Body type: **SUV**, **Sedan**, **Truck**, **Hatchback**, **Minivan**. |
| Make__c | text | 100% | Always **Tarvessa**. |
| Model__c | text | 100% | **Zevi** (hatchback), **Ostra** (compact sedan), **Kaveno** (midsize sedan), **Orvik** (compact SUV, best seller), **Talmar** (3-row SUV), **Draxen** (pickup truck), **Nuvessa** (minivan), **Elarion** (electric SUV, growing share over time). |
| Trim__c | text | 100% | Trim level, e.g. LX, EX, Sport, Platinum, Long Range. |
| Fuel_Type__c | text | 100% | **Gasoline**, **Hybrid** or **Electric**. Hybrid trims (Orvik Hybrid, Kaveno Hybrid) and the Nuvessa minivan are hybrids; every Elarion trim is electric. |
| MSRP__c | integer ($) | 100% | Base price of a new vehicle (2023). New-car prices rise ~3% a year in the data. |
| IsActive | true/false | 100% | Always true. |
| CreatedDate | datetime | 100% | Record creation. |

## User

**One row per employee, including those who have left.** 676 rows × 14 columns.
Dealership sales staff turn over quickly, so many seats have had several people over the period.

| Field | Type | Fill | Meaning |
|---|---|---|---|
| Id | Id | 100% | Unique user Id (`005…`). |
| FirstName | text 🔒 | 100% | Employee first name, hashed. |
| LastName | text 🔒 | 100% | Employee last name, hashed. |
| Name | text 🔒 | 100% | Full name, hashed. |
| Email | text 🔒 | 100% | Work email, hashed. |
| Title | text | 100% | Role: **Sales Consultant** (meets shoppers, runs test drives and deals), **BDC Representative** (Business Development Center: responds to online and phone leads and books appointments), **F&I Manager** (Finance & Insurance: runs credit applications), **Sales Manager**, **General Manager** (runs a showroom), **Marketing Manager**, **VP of Sales**. |
| Department | text | 100% | **Sales** or **Marketing**. |
| UserRoleId | Id → UserRole | 100% | Role in the hierarchy. |
| ManagerId | Id → User | 99.9% | Direct manager. Blank only for the VP of Sales. |
| Showroom__c | Id → Showroom__c | 99.7% | Showroom they work at. Blank for head-office roles (VP, Marketing). |
| IsActive | true/false | 100% | Still employed at the extract date. |
| Hire_Date__c | date | 100% | Start date. New hires perform worse during their first couple of months. |
| Termination_Date__c | date | 65.8% | Leaving date. Blank for current employees. |
| CreatedDate | datetime | 100% | When the user account was created (= hire date). |

## UserRole

**The role hierarchy.** 7 rows × 3 columns.

| Field | Type | Fill | Meaning |
|---|---|---|---|
| Id | Id | 100% | Unique role Id (`00E…`). |
| Name | text | 100% | Role name (same values as `User.Title`). |
| ParentRoleId | Id → UserRole | 85.7% | The role above it: VP of Sales → General Manager / Marketing Manager → Sales Manager / F&I Manager → Sales Consultant / BDC Representative. Blank for the VP. |

---

## Joining the tables

| To answer | Join |
|---|---|
| Did a lead buy? | `Lead.ConvertedOpportunityId = Opportunity.Id` → `Opportunity.IsWon` (no match = didn't visit, so didn't buy) |
| A lead's full activity history | `Task.WhoId` / `Event.WhoId` IN (`Lead.Id`, `Lead.ConvertedContactId`) |
| Activities on a deal | `Task.WhatId` / `Event.WhatId = Opportunity.Id` |
| A deal's stage path | `OpportunityHistory.OpportunityId = Opportunity.Id`, ordered by `CreatedDate` |
| All visits by one person | `Opportunity.AccountId` (a returning shopper keeps one Account) |
| Repeat inquiries by one person | group leads by hashed `Email` or `MobilePhone` |
| Campaign attribution | `CampaignMember.LeadId = Lead.Id`, or `Opportunity.CampaignId` |
| Who did the work | any `OwnerId` / `CreatedById` → `User.Id` → `User.Title`, `User.Showroom__c` |
| Vehicle details | `Opportunity.Vehicle__c` or `Lead.Vehicle_Interest__c` → `Product2.Id` |
| Location & local time | `Showroom__c` field → `Showroom__c.Id` → `Time_Zone__c`, `Open_Sundays__c` |

**Avoid leakage when modelling.** `Status`, `IsConverted`, `Rating`, `Lost_Reason__c`, `LastModifiedDate`,
`LastActivityDate` and all Converted* fields are filled in *after* the outcome is known. To predict whether a lead
will buy, use only the lead's own fields at creation plus activity that happened before your prediction time,
and split training and test data by `CreatedDate`.
