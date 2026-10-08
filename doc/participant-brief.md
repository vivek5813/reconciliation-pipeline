# Hackathon Case Study — Reinventing the Monthly Client Billing Cycle at Meridian Atlas Partners

> **Hackathon · Day 2 of 3 · Teams of 3–4**
> **Goal:** Redesign a manual, exception-heavy billing process and demonstrate a working prototype of the most valuable slice. Presentations are on Day 3.

---

## 1. Executive Summary

Meridian Atlas Partners ("Meridian"), a global project-based professional services firm, has identified its monthly client billing cycle as a growing bottleneck. The process today is highly manual, sensitive to upstream data quality, and consumes a disproportionate share of senior billing-team time. As Meridian grows and expands across regions, leadership is concerned that the current model will not scale economically.

You and your team have been asked to simulate an **RDE pod**: qualify the billing reinvention as a Rapid Reinvention opportunity, design the target process, prove the highest-value slice with a working prototype, and make the case for a 90-day Rapid Reinvention engagement. **Day 2** is a full build day — by the end of it your team will have a qualified use case, a target-process design, a runnable prototype, a go-live readiness view, and a Day-91 roadmap ready to present. **Day 3** is presentation day — your executive pitch with live demo is delivered then.

You are not required (or expected) to solve every problem. You are expected to *analyse* the current state, make defensible choices about where to focus, and show — concretely — how your future-state design unlocks measurable value.

---

## 2. About Meridian Atlas Partners

| | |
|---|---|
| Headcount | ~12,000 staff |
| Regions | North America (largest), Latin America, EMEA, APAC, Australia/New Zealand |
| Revenue model | Predominantly time-based client engagements with reimbursable expenses; a smaller portion of fixed-fee, milestone, and percent-complete work |
| Engagements | Several thousand active client projects at any time, ranging from small advisory engagements to multi-year programmes |
| Core ERP | **SAP** — system of record for contracts, rates, costs, unbilled transactions, draft invoices, and invoice status. Will remain the source of truth in the future state. |
| Document repository | **SharePoint** — central store for client-facing invoices, expense receipts, vendor invoices, hotel folios, mileage logs, and per-diem records |
| Day-to-day biller tools | Microsoft Excel and a PDF editor — used by Billing Analysts to assemble invoices, reconcile, and prepare backup packages |
| Communication channels | Project Lead and Project Finance Analyst guidance arrives over multiple channels: comments and notes inside SAP, email, Microsoft Teams chats, and ServiceNow tickets — used inconsistently by different Project Leads and projects |
| Governance | Internal compliance, audit, and finance controls; some regional regulators apply tax and invoicing format rules |

Meridian's billing function is a centralised in-house shared-services team supporting all regions, with regional sub-teams handling local nuances.

---

## 3. Today's Billing Process

The monthly billing cycle runs across roughly the same shape in every region, with regional variations on top. Drafts of each invoice already exist in SAP — generated either by a Billing Analyst or by Meridian's existing scheduled batch jobs. The work this case is concerned with begins **after** the draft exists and ends with a delivered invoice.

A typical end-to-end flow:

1. **Cost & time capture.** Staff log time and submit expenses through corporate systems. Approved costs accumulate in SAP as **unbilled transactions** against the project.
2. **Draft invoice generation.** The Billing Analyst (or a scheduled batch job) generates a draft invoice in SAP from the unbilled transactions, applying contract terms, rate tables, and any existing holds or classifications.
3. **Backup-document collation.** The Billing Analyst pulls all supporting expense documents (receipts, vendor invoices, hotel folios, mileage logs, per-diem records) for the cycle from SharePoint. These vary in number — anywhere from a handful to several hundred per invoice. The Analyst typically assembles the package using Excel and a PDF editor.
4. **Reconciliation.** The Billing Analyst manually verifies that the draft invoice, the unbilled-transaction report, and the backup documents agree — a three-way check. Mismatches in totals, missing receipts, duplicate entries, or holds applied late are flagged. Where a receipt or vendor invoice covers only part of a claim, or the totals differ, the Analyst will often **annotate the validated amount directly on the document** (using a PDF editor) and attach the annotated copy to the backup package that ships with the draft invoice. *(In the hackathon data pack, the SAP draft invoice and unbilled-transaction extract are both provided as SAP outputs and act as one side of the reconciliation. The exercise is therefore two-way: SAP outputs vs. backup documents — see §14.)*
5. **Exception triage.** Each anomaly (e.g., a non-billable item still on the invoice, a receipt that doesn't match a transaction, a rate that looks wrong) is investigated. The Analyst searches SAP notes, prior email threads, Microsoft Teams chats, and ServiceNow tickets, and sometimes contacts the Project Lead or Project Finance Analyst before deciding how to resolve it.
6. **Two-stage review and approval.** The Analyst sends the draft package (invoice + backup) first to the **Project Finance Analyst** — the finance partner on the engagement — for first-level review. They check cost positions, margin, and any open exceptions; they may approve, reject, or ask for changes before passing the package on. Once cleared, the package goes to the **Project Lead** — the person accountable for the engagement to the client — for final review. The Project Lead may approve, reject, ask for changes, or provide instructions for this and future cycles. Replies from either reviewer may come back over any of the above channels. The invoice cannot be released until the Project Lead has approved.
7. **Adjustments.** The Analyst makes any approved adjustments in SAP (rate overrides, expense exclusions, line splits, non-billable flags, etc.). All adjustments are made by the Analyst manually in SAP.
8. **Invoice release & delivery.** Once approved, the Analyst releases the invoice in SAP and delivers it via the agreed channel — direct email, client portal upload, or third-party invoicing platform — and archives the package in SharePoint.
9. **Disputes & follow-ups.** If a client questions a line item later, the Analyst returns to the package to reconstruct what happened.

Most of an Analyst's time is consumed in steps 3–7. Steps 5 and 6 in particular are where instructions, emails, Teams messages, and tribal knowledge accumulate — and where the same exception types tend to reappear cycle after cycle, often re-decided from scratch.

The bulk of analyst time is spent on **time-and-materials (T&M) invoices**. A smaller portion of invoices follow a different shape — fixed-fee, milestone, and percent-complete billing — and these are typically more straightforward and consume far less analyst time per invoice. The mix of these types varies meaningfully by region (see §8).

---

## 4. Stakeholders

| Role | Who they are | What they own | Authority |
|------|--------------|---------------|-----------|
| **Billing Analyst** | In-house shared-services billing team. ~200 globally; the largest contingent supports the United States (~100). Mix of junior and senior. | Day-to-day execution of the cycle: collation, reconciliation, exception handling, adjustments in SAP, release, delivery, archiving. | Operational. May execute SAP adjustments and release invoices. |
| **Senior Billing Analyst** | Tenured analysts who handle the most complex projects, custom invoice templates, and act as escalation point. A small named group per region. | Edge cases, dispute resolution, knowledge transfer to junior analysts. | Same as Billing Analyst plus informal oversight. |
| **Project Finance Analyst** | Finance partner assigned to an engagement, sitting between Billing and the Project Lead. Reviews every draft invoice package before it goes to the Project Lead. | First-level review of the draft invoice package: cost confirmation, margin check, exception sanity, billing instructions. | First-level approver. The package cannot reach the Project Lead without their sign-off. Cannot edit SAP directly for billing. |
| **Project Lead** | The person accountable to the client for an engagement. May lead one or many projects. Thousands across the firm. | Final review and approval of the draft invoice package after the Project Finance Analyst has signed off; providing billing instructions; answering exception questions. | Final approver. Once the Project Lead approves, the invoice can be released. Cannot edit SAP directly for billing. |
| **Billing Operations Lead** | Manages the Billing Analyst team. | Process design, performance, and KPI accountability. | Sponsor for change within billing operations. |
| **Finance Sponsor** | Senior finance executive accountable for working capital and revenue assurance. | Strategic direction, funding, KPI targets. | Final budget and scope authority. |

> **Important constraint for this case:** Project Leads' day-to-day experience must remain **undisturbed** during this initiative. Your future-state design may *describe* a future where Project Leads experience changes, but the prototype must not assume any new Project Lead-facing tool, training, or behaviour change.

---

## 5. Data Sources & Inputs

Information needed to bill a single project for a single cycle is scattered across multiple systems and channels.

### SAP (ERP — system of record, today and in the future state)
- Contract header and terms
- Rate tables (by role, region, project, individual)
- Unbilled labour lines (employee, hours, role, rate, project, task)
- Unbilled expense lines (employee, category, amount, currency, project, task)
- Vendor invoices and subcontractor costs
- Holds (e.g., *Hold Once*, *Hold Until Released*) applied at line, transaction, or project level
- Invoice classification codes (used for tax, regional reporting, and client-specific groupings)
- Free-text project notes, invoice notes, and an internal "tracker" field used inconsistently
- Draft invoice records (already generated)
- Invoice delivery instructions (per project)

### SharePoint (document repository)
- Expense receipts (paper-photo, mobile-app capture, web download, scanned PDF)
- Vendor invoices and hotel folios
- Mileage logs and per-diem records (often without receipts)
- Prior cycles' billing packages (for reference)
- Client-specific invoice templates

### Project Lead and Project Finance Analyst communications
Guidance, approvals, rejections, and exception decisions arrive across **multiple channels, used inconsistently**:

- **Comments and notes inside SAP** (project notes, invoice notes, tracker fields)
- **Email** — the most common channel today
- **Microsoft Teams** — chat, channel posts, and DMs
- **ServiceNow tickets** — used by some teams to track billing questions and decisions
- Occasionally: phone calls and verbal handoffs

The same Project Lead may use different channels for different topics. A standing instruction may live in a Teams message that no new Analyst will ever find. A one-off exception may be logged as a ServiceNow ticket and then re-asked by email.

### Analyst working tools
- **Microsoft Excel** — for reconciliation worksheets, working out splits, tracking exceptions
- **A PDF editor** — for assembling the backup package and adding annotations
- Personal spreadsheets and notebooks tracking open items
- Verbal handoffs between junior and senior Analysts

### Legacy automation
- An existing automation that pulls some documents from email into SharePoint. Reliability is variable; some Analysts trust it, others rerun it manually.

### Outbound
- Client portals (per client, often unique)
- Direct email
- Third-party invoicing platforms in some regions
- Archive copies into SharePoint

> **Observation worth sitting with:** the same fact (e.g., "Project Lead said: never bill mileage on this engagement") can live in an SAP note, an email thread, a Teams chat, a ServiceNow ticket, an Analyst's spreadsheet, and a senior Analyst's head — simultaneously. None is canonical.

---

## 6. Pain Points

Reported by Billing Analysts, Senior Billing Analysts, and the Billing Operations Lead during interviews:

- **Document chaos.** Backup files arrive in inconsistent formats and orders. Composite scans (multiple receipts on one page) are common. Some documents are unreadable. Some claimed expenses have no backup at all. Ordering rarely matches the invoice line sequence.
- **Three-way reconciliation is manual — and document-side matching is the biggest time sink.** Matching the draft invoice to the unbilled-transaction report and to the backup documents is done line by line, in Excel, by the Analyst. Reconciling **expense receipts and vendor invoices** to their underlying transactions is consistently reported as one of the most time-consuming sub-tasks in the cycle — confirming amounts, currency conversions, splitting partial claims, removing duplicates, and writing the validated amount directly onto the document. Variances require judgement on materiality. *(The hackathon data pack simplifies this to a two-way reconciliation: SAP outputs vs. backup documents. This is by design — it isolates the document-matching challenge, which is the dominant time sink.)*
- **Adjustments trigger full re-validation.** When approved adjustments are made in SAP — rate overrides, expense exclusions, line splits, non-billable flags — the **draft invoice regenerates**. The Analyst must then re-run reconciliation, re-check totals against the unbilled-transaction report, re-walk the backup package, and re-route for review. A single late instruction or adjustment can cause two or three full validation passes on the same invoice.
- **Institutional memory is personal, not shared.** The same exception types — a particular non-billable category, a recurring rate question, a known client-specific rule — show up cycle after cycle. Experienced Analysts keep their own trackers (Excel sheets, OneNote pages) of prior comments, decisions, and feedback to reuse cycle-on-cycle. That helps **within an individual Analyst's caseload** but is not shared, not consolidated, and not held in any system of record. New Analysts, hand-offs between Analysts, and any project the long-tenured Analyst doesn't personally cover end up re-deciding exceptions that have already been answered before.
- **Instructions are fragmented across channels.** Project Lead and Project Finance Analyst guidance arrives over SAP notes, email, Microsoft Teams, ServiceNow tickets, and the occasional phone call. New Analysts cannot find prior decisions. Long-tenured Analysts carry it in their heads.
- **Confirming invoicing requirements often means opening last cycle's invoice.** Because contract-specific rules are scattered across channels and rarely consolidated anywhere, Analysts routinely pull up the **prior cycle's invoice** as the most reliable single reference for what this contract actually wants — formatting, groupings, expense handling, special line treatment, narrative wording. This works but is slow, and a flawed prior cycle silently propagates errors into the current one.
- **Custom invoice templates require senior time.** Some clients require bespoke invoice formats with non-standard groupings, markups, retainer credits, or annotations on receipts. Today these are produced manually by Senior Analysts using Excel and a PDF editor.
- **Compliance variation.** Tax rules, currency handling, contract format, and approval norms differ across regions. Analysts in any one region tend to know their region's rules but not others'.
- **Upstream data gaps surface as billing problems.** When contract rate tables are missing, classification codes are inconsistent, or holds are applied late, the symptom shows up at billing time. Analysts spend significant time chasing fixes upstream — fixes that, by the time they take effect, often arrive too late for the current cycle.
- **Disputes and lookbacks are painful.** When a client questions a six-month-old invoice, reconstructing why a particular line was billed a particular way often involves trawling through emails, Teams histories, ServiceNow tickets, and SAP notes.

---

## 7. KPI Targets

Meridian's leadership has set the following targets for the future-state process:

| KPI | Target |
|-----|--------|
| Cost per invoice (fully-loaded processing cost) | **≥ 50% reduction** vs. current baseline |
| Invoice cycle time (cost incurrence → delivered invoice) | **≥ 25% reduction** vs. current baseline |
| Billing Analyst hours per invoice | **≥ 50% reduction** |
| Exceptions resolved without Project Lead involvement | **≥ 55%** |
| Document data-extraction accuracy on amount fields | **≥ 90%** |
| First-pass Project Lead approval rate (no rework) | **≥ 90%** |
| Critical compliance failures (tax, regulatory, audit) | **0** |

These are minimum thresholds, not stretch targets. Your business case should explicitly map your design to one or more of these.

---

## 8. Volume, Team Size & Bill-Type Mix

### Today's volumes

| | Volume |
|---|---|
| Invoices per month, firmwide | **~20,000** |
| Billing Analysts globally | **~200** |
| Average invoices per Analyst per month | ~100 |
| Project Leads served | thousands |
| Avg expense documents per invoice | 30–80 (range: handful to several hundred) |

### Regional split

The United States is by far the largest region, accounting for **more than 50%** of monthly invoice volume — roughly **10,000+ invoices per month**, supported by approximately **100 Billing Analysts**. The remaining ~10,000 invoices per month are spread across Latin America, EMEA, APAC, and Australia/New Zealand, with team sizes broadly proportional to volume but with regional variation.

### Bill-type mix — the part that matters for the business case

Not all invoice types take the same amount of analyst time:

- **Time-and-materials (T&M)** invoices are the most labour-intensive per invoice. They drive almost all of the document handling, reconciliation, and exception-resolution work described in §3 and §6.
- **Fixed-fee, milestone, and percent-complete** invoices are comparatively straightforward. The same Analyst can produce many of them per cycle with limited touchpoints, and they do not generate the same exception load.

The mix varies meaningfully across regions:

- **United States**: heavily weighted to T&M. Most analyst hours in the US are spent on T&M invoices.
- **Other regions**: a higher share of fixed-fee and milestone invoices in some geographies. Per-invoice analyst time in those regions is therefore lower on average.

This regional difference in bill-type mix is **not by itself a pain point** — the existing process handles fixed-fee and milestone work fine. But it is a major input to any business case: a solution that improves T&M handling delivers most of its value where T&M concentration is highest (the US), and proportionally less in regions where fixed-fee and milestone work dominate. Your business case should reason about this explicitly.

Today, the in-region teams keep up only because of senior-Analyst experience and a high tolerance for cycle-end overtime. The firm wants to remove that pressure, not just hold it constant.

---

## 9. Challenges & Constraints

### Regional differences
- **Tax & regulation.** VAT, GST, sales-tax, and local invoicing-format rules vary substantially by jurisdiction. Some regions require government-mandated e-invoicing.
- **Currency.** Multi-currency transactions and conversion at transaction-date or invoice-date rates depending on the contract.
- **Language.** Documents (receipts, vendor invoices) arrive in many languages. Some clients require invoices in a specific language.
- **Contract & approval norms.** Country-specific contract templates and locally signed amendments. Approval workflows differ between regions.

The case does not ask you to solve regional compliance — but your design must not break in their presence.

### Scalability & cost
- The per-invoice cost of the current process is not well measured. The dominant current cost is **Analyst time** — software/licensing is *not* a current cost driver, since the existing process leans on tools the firm already pays for (SAP, Excel, PDF editor, SharePoint).
- Any new solution will be a **net new investment**. The business case must justify build cost (engineering, integration, change management) and run cost (per-invoice ongoing operating cost — third-party services, infrastructure, model/usage fees, support) against the analyst-hour and cycle-time savings it produces.
- Volume matters: scaling a solution from the US (~10K/mo) across to all regions (~20K/mo) approximately doubles run cost — but bill-type mix means the marginal value in some regions is smaller. The shape of the cost-and-value curve at different scales should appear in your business case.
- A solution that is **cheaper per invoice as volume grows** is more valuable than one with a flat cost curve.

### Dependencies

- **SAP is the system of record** for contracts, rates, transactions, draft invoices, and invoice status. Your solution integrates with SAP — it does not replace it.
- **SAP holds financial data — any update to it must be risk-free.** Mistaken or unauthorised changes to financial records are not acceptable. How you ensure that is part of what you have to design.
- **Project Lead workflow must remain undisturbed** during this initiative.
- **Legacy automation** for document retrieval may or may not be reliable — you can choose to replace it, supplement it, or design around it.
- **Appropriate firm sign-offs** would be required for any production change. Assume normal enterprise governance applies.
- **The target process must achieve or exceed the §7 KPI targets.**

### Upstream limitations
The billing team experiences problems whose root cause is upstream:

- Contract terms not captured in SAP in a structured way
- Rate tables incomplete or out of date
- Classification codes inconsistent across projects
- Project Lead instructions arriving via channels that don't connect back to the project record
- Document quality issues at the point of capture (composite scans, missing receipts, etc.)

> **Forward-looking hint:** the future-state design Meridian wants is one where **today's bottlenecks are removed and the design has clear seams to extend upstream later** — into contract setup, instruction capture, and document quality at the source. You are not asked to solve those upstream problems on day one. You *are* asked to design a future state that will not need to be rebuilt to address them.

---

## 10. Out of Scope / Non-negotiables

Your design and your prototype must respect these:

1. **No Project Lead-facing changes** during the initiative window. (Future Project Lead experience may be described, but not built.)
2. **SAP remains the system of record.** Your solution integrates with SAP — it does not replace it.
3. **Any update to SAP must be risk-free.** SAP holds financial data; mistaken or unauthorised changes are not acceptable. How you ensure that is part of your design.
4. **Compliance and audit traceability are non-negotiable.**
5. **Achieve or exceed the §7 KPI targets.**
6. **No real client data.** Use only the synthetic data in Appendix A or your own clearly synthetic equivalents.

---

## 11. Your Mission

Day 2 is a full build day. By end of Day 2, your team will have:

1. **Redesign the future-state billing process** end-to-end, with clear identification of what changes versus what stays the same, and where humans remain in the loop.
2. Pick **one or two** of the candidate focus areas below, and build a **demonstrable prototype** of the redesigned slice using Appendix A data:
   - **Document handling & extraction** — turning the messy SharePoint inflow into structured, matched data.
   - **Exception triage & resolution** — handling the recurring exception types without re-deciding from scratch each cycle.
   - **Reconciliation** — between SAP outputs (draft invoice and unbilled-transaction extract) and backup documents. In this dataset this is a two-way reconciliation; in production the same design should extend to a full three-way check.
   - **Instruction & feedback capture** — making Project Lead and Project Finance Analyst guidance, however it arrives, findable, reusable, and tied to the project.
3. Build the **business case** — investment, run cost, value, payback, and sensitivity to regional bill-type mix.

You may, of course, propose to address other slices. Defend your choice.

---

## 12. Deliverables

> **Day 2** — build and prepare everything below. **Day 3** — present to the group; the executive pitch and live demo are delivered then.

| Deliverable | Format | Notes |
|---|---|---|
| **Qualified use case** | Written statement | Problem statement, success criteria, MVP boundary, and RDE-fit rationale. |
| **Target process design** | Swim-lane / flow diagram or written narrative | Current vs. future. Roles, hand-offs, human-in-the-loop touchpoints. |
| **Solution design** | Architecture diagram + short narrative | Components, data stores, SAP and SharePoint integrations, exception routing, HITL points. Enough to scope a build. |
| **Working prototype** | Runnable code / UI / notebook | Demonstrate on Appendix A data. Edge-case handling and escalation paths included. |
| **Business case** | 1–2 pages or slide section | Build cost, run cost per invoice at 10K and 20K volume, value against KPI targets, payback, regional sensitivity, risk-adjusted view. |
| **Go-live readiness view** | Slide or written summary | Data inputs required, dependency and risk register, security and controls, adoption plan, support model. |
| **Day-91 scale-up roadmap** | Slide | Phased plan from pilot to production — assumptions, decision gates, scale costs. |
| **Executive pitch** | 5–7 slides + live demo | Delivered on Day 3. Problem → qualified use case → target process → prototype walkthrough → business case → go-live → Day-91 roadmap → asks. |

### What the business case must cover

A new solution is a substantial investment. Treat the business case as the document a finance committee would ask for before approving build funding.

- **Investment required (build).** A defensible estimate of one-off cost: engineering effort, integrations to SAP and SharePoint, change management, training. Order-of-magnitude is fine; show your reasoning.
- **Run cost (ongoing per-invoice cost).** What does it cost to operate the new solution per invoice — third-party services, infrastructure, any usage-based fees, support? How does that cost behave from 10K/month (US) to 20K/month (firmwide)?
- **Value delivered.** Quantitative: analyst hours saved, cycle-time reduction, first-pass approval improvement, error/compliance reduction. Qualitative: Analyst experience, client experience, audit traceability, retention, growth headroom. Map to the KPIs in §7.
- **Payback / ROI.** When does cumulative value exceed cumulative investment? State the assumptions you used.
- **Sensitivity to regional bill-type mix.** Because T&M is concentrated in the US and is where most analyst hours go, value is not uniform across regions. Show how the case changes if a region has 70% T&M vs. 30% T&M. Identify which regions justify rollout first.
- **Phasing and option value.** A staged investment that proves value early and scales costs only when warranted is more attractive than an all-or-nothing build. What is your phasing?
- **Risk-adjusted view.** What is the case if the solution captures only 70% of the projected value?

---

## 13. Guiding Questions

Use these to steer your analysis. They are not a checklist.

- Which bottleneck releases the most Analyst hours per dollar of effort?
- What information gets reused across invoices versus what is invoice-specific?
- How would your design avoid re-deciding the same exception twice — within a project, across a Project Lead's portfolio, or across the firm?
- How does run cost per invoice behave between 10,000/month (US) and 20,000/month (firmwide)? What flips at scale?
- How does the business case differ for a T&M-heavy region versus a region with more fixed-fee and milestone work?
- Which "plug points" in your design would let you extend later into contract setup, instruction capture (across SAP, email, Teams, ServiceNow), or document quality at the source — *without* rebuilding the core?
- What stays human in the loop, and where? What changes for the Billing Analyst's day?
- What does compliance and audit traceability look like in your future state?
- How does your design behave when a region adds a new tax rule, language, or invoicing-format requirement?
- What's the smallest viable first phase that proves the case before the firm commits to the full investment?

---

## 14. What's in Appendix A

A folder of synthetic data you can use for your prototype:

- A sample contract excerpt with rate table and billing terms
- A SAP-generated draft invoice for the cycle — the system's billing proposal before any analyst review
- An unbilled-transactions extract for one project, one cycle (~50 lines)
- A timecard extract for all labour transactions in the cycle
- A set of synthetic backup documents (clean, composite, unreadable, mismatched, missing) in text form — receipts, vendor invoices, hotel folios, mileage logs
- A handful of representative Project Lead emails
- A small set of prior exception/resolution pairs you may use as seed data

> **Reconciliation scope in this dataset.** The real process involves three-way reconciliation: draft invoice ↔ unbilled-transaction report ↔ backup documents. In this data pack, the draft invoice and unbilled-transaction extract are both SAP outputs and together form one side of the reconciliation. **Your prototype will work with two-way reconciliation: SAP outputs vs. backup documents.** This is a deliberate simplification that isolates the document-matching challenge — the dominant time sink in the real process. A production design should extend to full three-way.

> **On document formats.** In a real cycle, backup documents arrive as PDFs, scanned JPGs, or electronically-issued receipts. All documents in this pack are plain-text Markdown with a simulated OCR section. You may render them to PDF or image if your prototype requires it.

You are free to extend, mock, or generate additional synthetic data if your prototype needs it. Do not use any real-world data.

---

*Good luck. Defend your choices.*
