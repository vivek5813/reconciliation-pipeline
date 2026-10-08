# Document

```
HARBOR FUEL STOP
Santa Brisa, CA
2026-04-02   06:48

Fuel - Regular (12.4 gal) .. 47.32
                              -----
TOTAL ...................... 47.32

PAID  VISA *4471
```

# Raw OCR

```
HARBOR FUEL STOP Santa Brisa CA  2026-04-02 06:48
Fuel - Regular (12.4 gal) 47.32  TOTAL 47.32  PAID VISA *4471
```

# Notes for Analyst

- This receipt is in SharePoint for this project's cycle.
- No transaction line in `unbilled-2026-04.csv` corresponds to a fuel purchase.
- The traveller in question used mileage reimbursement (TX-2026-04-0031, TX-2026-04-0032) — fuel is generally not separately reimbursable when mileage is claimed.
- Likely should be excluded. But this is the kind of document that easily slips into a backup package and confuses reconciliation.
