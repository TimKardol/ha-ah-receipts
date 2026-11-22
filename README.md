# AH Kassabon

Home Assistant integration that reads Albert Heijn digital receipts (kassabonnen) and tells you which groceries got more expensive.

1. In the AH app, open a receipt under **Mijn kassabonnen** and share it as PDF.
2. Tap **Bon toevoegen** on the AH Kassabon card and pick the PDF (several at once is fine, older ones too).
3. The integration reads every product line, stores it in Home Assistant, and compares each product with the last time you bought it.

Everything stays in your own Home Assistant; nothing is sent anywhere.

## What you get

- **Card** `custom:ah-kassabon-card` (loaded automatically): upload button, basket change, and lists of products that went up or down, with a price history per product.
- **Sensors**: latest receipt (timestamp, total), number of products more expensive than when first seen (top 15 in attributes), and the average basket price change in %.
- **Event** `ah_kassabon_imported` after every new receipt, with `increases` and `decreases`, for notifications.
- **Actions**: `ah_kassabon.import_file` (a PDF already in HA, e.g. in `/media`), `ah_kassabon.set_variable` (mark a product as sold by weight), `ah_kassabon.remove_receipt`.

## How prices are compared

- Product lines on an AH receipt show the regular shelf price; Bonus discounts are separate lines, so Bonus does not count as a price change.
- Deposit lines (`+STATIEGELD`) are ignored.
- Products sold by weight (meat, cheese) have a different price every time. They are marked **wisselend gewicht** and left out of the comparison when the same name has two prices on one receipt, or when the price changed on three purchases in a row. You can switch this per product on the card.
- AH cuts names to about 12 characters. When the price under one short name jumps by more than 30%, it is treated as a different product (shown as "1 van 2"); a **Samenvoegen** button on the card merges them back.

## Full product names

Receipts only have short names ("AH BAKAARDAP"). The integration looks each one up in AH's public product search, the same anonymous search the AH app uses without logging in, and matches on name and price. A clear match is used straight away (you can still correct it); otherwise the card shows a few candidates under **Controleren** to pick from, search again, or skip.

Only the short product name is sent to AH. No receipts, account or personal data leave Home Assistant. This search is not an official API and AH can change it; if it stops working, price tracking keeps working with the short names.

## Install

Marketplace (HACS) → custom repository → this repo, category Integration. Restart, then **Settings → Devices & services → Add integration → AH Kassabon**.
