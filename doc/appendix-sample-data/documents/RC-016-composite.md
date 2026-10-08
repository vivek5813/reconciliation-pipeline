# Document

> **Composite scan.** A single PDF/image was uploaded to SharePoint containing several receipts on one page. The transaction line is for USD 189.45 but the scan contains charges adding to a different amount.

```
─────────  RECEIPT 1 (top of scan)  ─────────
QUICK MART CONVENIENCE
Santa Brisa  2026-04-04  09:12
Bottled water (4) ........ 6.00
Granola bars (3) ......... 9.00
Disposable cups (50) .... 18.00
TOTAL ................... 33.00
Cash

─────────  RECEIPT 2 (middle of scan)  ─────────
COASTAL PRINT SHOP
2026-04-04  11:28
Workshop signage (3) .... 64.50
Easel pad (2) ........... 38.00
TOTAL .................. 102.50
PAID VISA *3382

─────────  RECEIPT 3 (bottom of scan, cropped)  ─────────
THE COFFEE BAR
2026-04-04  14:05
Coffee x 6 ............... 27.00
Pastries x 4 ............. 22.00
TOTAL .................... 53.95
   (last digit barely legible)
PAID VISA *3382
```

# Raw OCR

```
QUICK MART CONVENIENCE Santa Brisa 2026-04-04 09:12
Bottled water (4) 6.00  Granola bars (3) 9.00  Disposable cups (50) 18.00  TOTAL 33.00 Cash
COASTAL PRINT SHOP 2026-04-04 11:28
Workshop signage (3) 64.50  Easel pad (2) 38.00  TOTAL 102.50 PAID VISA *3382
THE COFFEE BAR 2026-04-04 14:05
Coffee x 6 27.00  Pastries x 4 22.00  TOTAL 53.9?  PAID VISA *3382
```

# Notes for Analyst

- Transaction TX-2026-04-0049 records USD 189.45 as one expense line.
- Composite scan contains three receipts: 33.00 + 102.50 + 53.95 = **189.45** ✓ (matches if last digit is 5).
- The 33.00 was paid cash (not on a corporate card).
- These are likely all workshop-prep miscellaneous expenses but the transaction line description ("Composite scan - several receipts") doesn't break them out.
- Some employees do this regularly to save submission effort. It is the Analyst's problem to deal with.
