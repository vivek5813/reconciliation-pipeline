# Appendix A — Synthetic Data Pack

> **All data in this folder is fully synthetic.** Names, project codes, addresses, vendor names, employee names, amounts, and document content are fictional. Do not use real-world data alongside this pack.

This appendix supports [`../participant-brief.md`](../participant-brief.md) for the Meridian Atlas Partners billing reinvention hackathon. It contains a single project's data for a single billing cycle, with deliberately representative messiness.

## A note on document formats

In a real billing cycle, backup documents arrive as PDFs, scanned JPGs, mobile-photo captures, or electronically-issued receipts — some machine-readable, some not. SAP and timecard outputs are typically exported as structured files or printed to PDF.

**All files in this pack are provided as plain-text Markdown for simplicity.** Each backup document in [`documents/`](documents/) includes a `# Raw OCR` section that simulates what a document-intelligence pipeline (e.g. Azure Document Intelligence) would return from an image scan — including noise, partial reads, and ambiguous characters where appropriate. If your prototype requires actual images or PDFs, you may render the Markdown files into those formats. Keep them clearly synthetic.

## What's in here

| Path | What it is |
|---|---|
| [`contracts/contract-001.md`](contracts/contract-001.md) | Excerpt from the engagement contract: parties, scope, rate table, expense rules, invoicing & approval terms. |
| [`transactions/unbilled-2026-04.csv`](transactions/unbilled-2026-04.csv) | Unbilled-transaction extract from SAP for cycle 2026-04 (~50 lines: labour, expenses, holds, classifications). |
| [`sap-outputs/draft-invoice-2026-04.md`](sap-outputs/draft-invoice-2026-04.md) | SAP-generated draft invoice for cycle 2026-04 — the billing proposal produced by the system before any analyst review. Amounts reflect what is in SAP; backup documents may differ. |
| [`sap-outputs/timecards-2026-04.csv`](sap-outputs/timecards-2026-04.csv) | Timecard extract for all labour transactions in cycle 2026-04: employee, task, hours, activity description, submission and approval chain. Two entries are on hold with notes explaining why. |
| [`documents/`](documents/) | Synthetic backup documents in text form — receipts, vendor invoices, hotel folios, mileage logs, per-diem records. Mix of clean, composite, unreadable, mismatched, and missing-backup cases. |
| [`pm-instructions/sample-emails.md`](pm-instructions/sample-emails.md) | Five fictional Project Lead emails representative of the kind of guidance Analysts deal with. |
| [`prior-exceptions/resolutions.csv`](prior-exceptions/resolutions.csv) | A small set of prior exception/resolution pairs from previous cycles on this and similar projects. Use as seed data if helpful. |
| [`restricted/expected-invoice.md`](restricted/expected-invoice.md) | **Facilitators only.** What a perfectly processed invoice looks like for this dataset. |

## How to use

Use this data however you like:

- Process all of it, some of it, or just one document type
- Reformat it (parse the CSV, render the markdown documents into PDFs, etc.)
- Extend it with additional synthetic data if your prototype needs more volume

If your prototype needs document images and you want to render the synthetic documents, you may turn the markdown text in [`documents/`](documents/) into images or PDFs. Keep them clearly synthetic.

## Things to notice

The data has been seeded with deliberate quirks. You don't need to find them all, but a strong prototype will surface or handle several of them. Do not treat this list as exhaustive — there are more than are listed here.

- At least one transaction with a hold flag
- At least one expense without a receipt
- At least one composite document containing more than one item
- At least one document where the amount on the document doesn't match the transaction
- At least one transaction that the contract suggests is non-billable
- At least one Project Lead instruction that conflicts with what the contract literally says
- More than one currency
- At least one receipt where the total matches SAP but contains a line that may not be reimbursable
- At least one vendor invoice where SAP understates the amount and is missing a line entirely
- At least one timecard entry that should not have been coded to this project
- A traveller (E-7702) who has expenses but no timecard entries in this cycle

## What's *not* here

- Any real client name, employee name, project code, address, vendor, amount, or document
- A "correct answer" — for participants. The restricted expected-invoice file exists but is held back until after pitches.
- Coverage of every edge case you might dream up. If your prototype needs an edge case not represented, mock it.

---

*All names, identifiers, and amounts are invented for this exercise.*
