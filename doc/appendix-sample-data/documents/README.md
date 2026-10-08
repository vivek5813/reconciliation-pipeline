# Synthetic Documents

These are text representations of expense backup documents for the Meridian Atlas Partners billing reinvention hackathon. Each file simulates a single receipt, vendor invoice, hotel folio, mileage log, or composite scan that an Analyst would receive in SharePoint.

Each document has two sections:

- **`# Document` (rendered text)** — what the document looks like on the page, in plain text. You may turn these into PDFs or images if your prototype needs that.
- **`# Raw OCR` (simulated OCR text)** — what an OCR engine might produce if you fed an image of this document through it. Sometimes noisy, sometimes clean, sometimes garbled — like the real thing.

The set is **deliberately varied**. Some documents are clean. Some are composite. Some have mismatches. One is unreadable. One is missing entirely (referenced in transactions but no file here).

Document IDs match the `note` column in [`../transactions/unbilled-2026-04.csv`](../transactions/unbilled-2026-04.csv) where applicable.

| File | Receipt ID | Linked transaction(s) | Quirk |
|---|---|---|---|
| [`RC-001-flight-outbound.md`](RC-001-flight-outbound.md) | RC-001 | TX-2026-04-0022 | Receipt total ($408.30) differs from SAP transaction ($412.80) |
| [`RC-002-flight-return.md`](RC-002-flight-return.md) | RC-002 | TX-2026-04-0023 | Total matches SAP but itemised receipt includes non-reimbursable seat upgrade ($35.00) |
| [`RC-003-hotel-folio.md`](RC-003-hotel-folio.md) | RC-003 | TX-2026-04-0024, TX-2026-04-0025 | Folio with multiple line items |
| [`RC-007-team-dinner.md`](RC-007-team-dinner.md) | RC-007 | TX-2026-04-0029 | Includes alcohol line — should be split |
| [`RC-012-hotel-overcap.md`](RC-012-hotel-overcap.md) | RC-012 | TX-2026-04-0040 | Over per-night cap |
| [`RC-013-client-dinner.md`](RC-013-client-dinner.md) | RC-013 | TX-2026-04-0043 | Over meal cap; PL approved |
| [`RC-014-airport-lounge.md`](RC-014-airport-lounge.md) | RC-014 | TX-2026-04-0046 | PL rejected (see email 2) |
| [`RC-015-foreign-currency.md`](RC-015-foreign-currency.md) | RC-015 | TX-2026-04-0048 | CAD on a USD project |
| [`RC-016-composite.md`](RC-016-composite.md) | RC-016 | TX-2026-04-0049 | Composite scan (multiple items) |
| [`RC-017-personal-laundry.md`](RC-017-personal-laundry.md) | RC-017 | TX-2026-04-0050 | Likely non-reimbursable |
| [`RC-018-unreadable.md`](RC-018-unreadable.md) | RC-018 | (none) | Unreadable; no matching transaction |
| [`VI-001-workshop-vendor.md`](VI-001-workshop-vendor.md) | VI-001 | TX-2026-04-0033, TX-2026-04-0034 | Vendor invoice total ($1,147) differs from SAP ($1,097): room understated by $5, AV line ($45) not in SAP at all |
| [`VI-002-subcontractor.md`](VI-002-subcontractor.md) | VI-002 | TX-2026-04-0044 | Subcontractor (markup needed) |
| [`ML-001-mileage-log.md`](ML-001-mileage-log.md) | ML-001 | TX-2026-04-0031, TX-2026-04-0032 | Mileage log |
| (missing) | (n/a) | TX-2026-04-0037 | Drafting supplies receipt — referenced in transactions, no file present |
| [`RC-019-mismatched.md`](RC-019-mismatched.md) | RC-019 | (linked to nothing in transactions) | Receipt with no matching transaction |

Yes, the last two are deliberate.
