# Document

```
LE CAFÉ DU PORT
Vancouver, BC
2026-04-02   12:34

Cobb salad .............. CAD 18.00
Sparkling water .........  CAD 4.50
Coffee ..................  CAD 4.50
                           --------
Subtotal ................ CAD 27.00
Tax (5% GST) ............ CAD 1.35
Tip ..................... CAD 23.65
                           --------
TOTAL ................... CAD 52.00

PAID  VISA *4471 (in CAD)
```

# Raw OCR

```
LE CAFE DU PORT Vancouver BC  2026-04-02 12:34
Cobb salad CAD 18.00  Sparkling water CAD 4.50  Coffee CAD 4.50
Subtotal CAD 27.00  Tax (5% GST) CAD 1.35  Tip CAD 23.65  TOTAL CAD 52.00
PAID VISA *4471 (in CAD)
```

# Notes for Analyst

- Transaction TX-2026-04-0048 records CAD 52.00.
- Project is billed in USD. Conversion at receipt-date FX needed.
- Indicative FX 2026-04-02: CAD 1.00 = USD 0.74 (synthetic — your prototype may use any reasonable rate).
- Tip is unusually high relative to subtotal — possibly a punch-error during expense submission; possibly correct if tip was rounded up to a flat amount. Worth noticing.
