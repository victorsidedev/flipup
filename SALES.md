# Sales lifecycle and inventory status

Sales are immutable financial history: `sales(id, item_id, price, kind, sold_at)`.
Each sale has its own primary key; `item_id` is an indexed foreign key and may
appear in multiple history rows. `kind` is `sale` (default) or `loss`; losses are
identified by `kind='loss'`, never inferred from `price=0`. A zero-price sale is
still a sale. Prices must be nonnegative. Timestamps default to database time.

Refunds are append-only credit notes:
`refunds(id, sale_id, amount, refunded_at)`. The indexed `sale_id` references
`sales.id`; amounts must be positive. Financial rows are never updated or deleted.
There are no refund update, delete, or GET endpoints.

For v1, a sale is ACTIVE exactly when it has no refund rows. Active sales are
keyed by item ID for inventory derivation. `SELECT ... FOR UPDATE` row locks
serialize creation, refunds, and deletion; creation rejects an already sold or
included item with 409. Refunded sales remain in history and allow resale when
no active ancestor covers the item. A resale gets a new sale ID.

`GET /purchases` returns every item with backend-owned status:

- `available`: neither the item nor an ancestor has an active sale.
- `sold`: the item has its own active sale, including a loss write-off.
- `included`: the nearest ancestor with an active sale covers the item;
  `sale` is null and `soldWithItemId` identifies that ancestor.

An item's direct active sale takes precedence. A parent sale covers remaining
nested parts without creating extra financial rows. Earlier child sales remain
intact. Ancestors are resolved within each purchase with cycle protection.

`POST /sales` accepts `{ "itemId": 1, "price": "100.00", "kind": "sale" }`
(`kind` may be omitted). An optional `soldDate` in `YYYY-MM-DD` format records
an explicitly selected sale date in the existing `sold_at` column at midnight,
without timezone conversion. If omitted, the database timestamp defaults to now.
The Mark sold dialog defaults this date to the user's local today.
Returns 201 and the updated purchase. Its direct `sale`
contains `id`, `itemId`, `price`, `kind`, and `soldAt`.

`POST /sales/{sale_id}/refund` needs no body and returns 201 with the same updated
purchase shape. It inserts one credit note for the sale's entire price. Missing
sales return 404; duplicate refunds and zero-price refunds return 409 (a credit
note must have a positive amount). Any refund deactivates the sale in v1. The
amount column and sale-addressed endpoint leave room for a future optional
amount body and cumulative partial-refund rules without changing sale identity.

The frontend renders server statuses and labels direct losses distinctly. New
sale creation necessarily targets an item; all later financial-document actions
must target `sale.id`, never `itemId`. The typed `refundSale(saleId)` client is
available, but there is no refund UI yet.

## Revenue

The requested reporting definition is
`SUM(prices of ACTIVE sales WHERE kind='sale') - SUM(refund amounts)`.
This is not net lifecycle revenue under v1's active definition: a refunded sale
has already been excluded, so subtracting its refund counts the reversal twice.
For example, a 100 sale, full refund, and 120 resale yield 20 by that definition.
Net lifecycle revenue is instead `SUM(all sale-kind prices) - SUM(refunds linked
to sale-kind sales)`, yielding 120. Under full refunds this equals the sum of
active sale-kind prices alone. Loss write-offs are excluded from sales revenue.
No reporting calculation is implemented here; use the appropriate definition
explicitly when adding reports. Never sum inventory cards or count bundle parts
as additional revenue.

## Purchase editor and deletion

- `POST /purchases` creates a purchase with its full inventory representation.
- `PUT /purchases/{id}` updates metadata, names/prices, and adds items. Existing
  item IDs and relationships must be retained; omissions or foreign IDs return
  409. Use explicit deletion instead of omitting items.
- `DELETE /items/{id}` removes the subtree only if no affected item has any
  sales history, including refunded sales and losses. Otherwise returns 409.
  Returns the remaining purchase; an empty purchase is retained.
- `DELETE /purchases/{id}` similarly refuses any sales history with 409;
  otherwise removes the purchase and its items and returns 204.

Deletion checks and writes are atomic. Financial history is never deleted.
Alembic manages the database schema. Run `alembic upgrade head` before starting
the application. Startup does not create tables. See README.md for setup and
deployment instructions.
