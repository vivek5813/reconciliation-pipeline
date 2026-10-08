# Document

```
══════════════════════════════════════════════
       MARINA EVENTS COMPANY, LLC
       82 Pier Road, Santa Brisa, CA
       Tax ID: 88-XXXXXXX
══════════════════════════════════════════════

INVOICE  #ME-2026-04-129
Date:     2026-04-04
Bill to:  Meridian Atlas Partners
          Attn: Accounts Payable
          Project: Coastal Greenway Phase 2 / PRJ-NS-7421

DESCRIPTION                          AMOUNT
─────────────────────────────────────────────
Workshop room rental
  half-day, 2026-04-03 ............. 490.00

Catering for stakeholder workshop
  20 attendees, lunch + breaks ..... 612.00

AV / projector setup & teardown
  incl. screen, clicker, HDMI hub ..  45.00
─────────────────────────────────────────────
Subtotal ............................ 1,147.00
Tax (n/a) ...........................     0.00
─────────────────────────────────────────────
TOTAL DUE ........................... USD 1,147.00

Payment terms: Net 30
Remit to: Marina Events Company, LLC
══════════════════════════════════════════════
```

# Raw OCR

```
MARINA EVENTS COMPANY LLC  82 Pier Road Santa Brisa CA  Tax ID 88-XXXXXXX
INVOICE #ME-2026-04-129  Date 2026-04-04
Bill to Meridian Atlas Partners Attn Accounts Payable Project Coastal Greenway Phase 2 / PRJ-NS-7421
DESCRIPTION AMOUNT
Workshop room rental half-day 2026-04-03 490.00
Catering for stakeholder workshop 20 attendees lunch + breaks 612.00
AV / projector setup & teardown incl screen clicker HDMI hub 45.00
Subtotal 1147.00  Tax (n/a) 0.00  TOTAL DUE USD 1147.00
Payment terms Net 30  Remit to Marina Events Company LLC
```

# Notes for Analyst

- SAP maps TX-2026-04-0033 (485.00 room) and TX-2026-04-0034 (612.00 catering) to this invoice — but the vendor invoice shows room at **490.00** and includes a third line, **AV setup at 45.00**, with no corresponding SAP transaction.
- Mismatches to resolve: (a) room is USD 5.00 understated in SAP (490 vs 485); (b) AV/projector line (USD 45.00) was never entered — determine whether it is billable and, if so, add a new transaction in SAP before billing.
- Vendor invoice total is USD 1,147.00; SAP transactions total USD 1,097.00. Difference: USD 50.00.
- This is not a subcontractor — no markup applies. Pass-through at cost.
