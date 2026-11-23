# AH Kassabon

Home Assistant integration that reads Albert Heijn digital receipts (kassabonnen) and tells you which groceries got more expensive.

1. In the AH app, open a receipt under **Mijn kassabonnen** and share it as PDF.
2. Tap **Bon toevoegen** on the AH Kassabon card and pick the PDF (several at once is fine, older ones too).
3. The integration reads every product line, stores it in Home Assistant, and compares each product with the last time you bought it.

Everything stays in your own Home Assistant; nothing is sent anywhere.

## What you get

- **Card** `custom:ah-kassabon-card` (loaded automatically): upload button, basket change, and lists of products that went up or down, with a price history per product. Add `link: /boodschappen` to put a button on it that opens the full overview.
- **Overview** `custom:ah-kassabon-overview`: a full-page version for its own dashboard (use a Panel view). Spend per month, the biggest risers, and a sortable, searchable table of every product with its first and current price.
- **Sensors**: latest receipt (timestamp, total), number of products more expensive than when first seen (top 15 in attributes), and the average basket price change in %.
- **Event** `ah_kassabon_imported` after every new receipt, with `increases` and `decreases`, for notifications.
- **Actions**: `ah_kassabon.import_file` (a PDF already in HA, e.g. in `/media`), `ah_kassabon.set_variable` (mark a product as sold by weight), `ah_kassabon.remove_receipt`.

## How prices are compared

- Product lines on an AH receipt show the regular shelf price; Bonus discounts are separate lines, so Bonus does not count as a price change.
- Deposit lines (`+STATIEGELD`) are ignored.
- Products sold by weight (meat, cheese) have a different price every time. They are marked **wisselend gewicht** and left out of the comparison: when AH lists the product by approximate weight ("ca. 280 g"), when the same product has two prices on one receipt, or, for products without a known AH product, when the price changed on three purchases in a row. You can switch this per product on the card.
- With the AH login, products that print the same short name (for example a 0,5 l and a 1,5 l bottle of the same water) are told apart by AH's own product id.
- AH cuts names to about 12 characters. When the price under one short name jumps by more than 30%, it is treated as a different product (shown as "1 van 2"); a **Samenvoegen** button on the card merges them back.

## Full product names

Receipts only have short names ("AH BAKAARDAP"). The integration looks each one up in AH's public product search, the same anonymous search the AH app uses without logging in, and matches on name and price. A clear match is used straight away (you can still correct it); otherwise the card shows a few candidates under **Controleren** to pick from, search again, or skip.

Only the short product name is sent to AH. No receipts, account or personal data leave Home Assistant. This search is not an official API and AH can change it; if it stops working, price tracking keeps working with the short names.

## Optional: log in to your AH account

With a login, Home Assistant fetches the receipts in your AH account itself (the last 12 months, then every 6 hours) and AH tells it the exact product on every line, so there is nothing to pick. Receipts you already uploaded are recognised and not imported twice. Older receipts are imported without a notification.

**Settings → Devices & services → AH Kassabon → Configure**, then follow the steps: open the AH login page on a computer (Chrome or Edge), press F12 → Console, log in, and paste the `appie://login-exit?code=…` link that appears in the console. Home Assistant never sees your password; it keeps a login token in its config entry. **Configure → Log out** removes it. When the login expires, Home Assistant asks you to log in again.

This uses the AH app's own, unofficial API. AH can change or block it; uploading PDFs and the public search keep working either way. Action `ah_kassabon.sync_account` fetches new receipts on demand; the card shows a download button for it.

## Install

Marketplace (HACS) → custom repository → this repo, category Integration. Restart, then **Settings → Devices & services → Add integration → AH Kassabon**.
