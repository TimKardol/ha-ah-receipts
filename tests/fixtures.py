"""Made-up AH receipts in the text layout pypdf extracts from the real PDFs."""

RECEIPT_JAN = """
                       1234

AANTAL   OMSCHRIJVING         PRIJS BEDRAG

         BONUSKAART                  xx0000

1        HALFVOLLE MELK                1,15 B
2        AH PINDAKAAS         2,49     4,98
1        AH KIPFILET                   6,12
1        AH KIPFILET                   5,87
1        AH SPAGHETTI                  0,99
1        COLA ZERO                     2,29
         +STATIEGELD                   0,15
1        AH ROOMBOTER                  2,19
1        AH RUNDERGEH                  4,57BB

8               SUBTOTAAL                                        30,30

BONUS           AHHALFVOLLEM                                      -0,30

TOTAAL                                                         30,00

BTW                          OVER                               EUR
9%                           27,52                             2,48
TOTAAL                       27,52                             2,48

1234                         12                                34
10:15                                                   31-1-2026
"""


def later_receipt(day: int, changes: dict[str, str]) -> str:
    """The January receipt on another date with some prices changed."""
    text = RECEIPT_JAN.replace("31-1-2026", f"{day}-2-2026")
    for old, new in changes.items():
        text = text.replace(old, new)
    return text


# Card payment: weighed product (per kg), a percentage discount glued to the
# amount, and a footer time cut short; the PAYMENT line has the full time.
RECEIPT_CARD = """
                           1234
AANTAL        OMSCHRIJVING                    PRIJS   BEDRAG
              BONUSKAART                               xx0000
0.350KG       BANANEN                           1,89      0,66
1             AH APPELTAART                             6,4925%
2             AH YOGHURT                       1,29      2,58BB
1             AH BROCCOLI                                 1,49  B
5                 SUBTOTAAL                                       11,22
25% K             AH APPELTAART                                    -1,62
TOTAAL                                                           9,60
PAYMENT                              Date                14/02/2026 09:05
BTW                             OVER                             EUR
1234                            12                                 34
9:0                                                      14-2-2026
"""
