# Synthetic order changes

[`order_changes.json`](order_changes.json) contains the complete seed for the local Gold-rule-to-Silver example. All orders and changes are synthetic.

## Fields

| Key | Contents |
| --- | --- |
| `first_load` | Every change the source sent for orders 1 to 5, in arrival order. Written as version 0 on a new table. |
| `later_arrival` | Order 6, which arrives in the next commit (version 1 on a new table). Shows why comparisons pin one version. |

Each change contains `order_id`, `source_seq`, `op`, `status`, `amount`, and `arrived_at`. `source_seq` is the order of changes inside the source; `arrived_at` is when the pipeline received them. A delete has `null` status and amount.

## The orders

- **Order 1:** one change.
- **Order 2:** the source sent position 1, then 2, then 3 (cancelled). Position 2 arrived late, after position 3.
- **Order 3:** the same change was delivered twice.
- **Order 4:** two different changes carry the same source position 2. That is a conflict.
- **Order 5:** created, then deleted by the source.
- **Order 6:** arrives after the first load.

## Scenario order

1. Replace the demo table's current snapshot with the first batch and run both legacy reports on that pinned version.
2. Compute the shared current state and its review list.
3. Run both reports on the shared state and compare old and new answers on the same pinned version.
4. Append order 6 in a later version and repeat the sales comparison against it.
5. Show what happens to operations if the accepted-only filter moved into Silver.

Reruns retain the Delta table's history, so version numbers increase. `lake/run.json` records the actual pinned and latest versions.
