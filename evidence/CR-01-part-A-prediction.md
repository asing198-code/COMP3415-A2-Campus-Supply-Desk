# CR-01 Part A – Prediction (recorded before implementation)

Recorded after the refactoring and defect fixes, with all 39 tests passing
(`evidence/03-after-defect-fixes-tests.txt`), and before any CR-01 code was written.

## 1. Behavior / requirements that will change
- Fulfillment accepts a third value, `express`, in the service API, the individual commands and the menu.
  Other unknown values stay invalid.
- Pricing: express charges a flat 1,200 cents that is never waived. The free-delivery threshold
  (10,000 cents after discount) keeps applying only to `delivery`.
- Unchanged: student discount (still only on merchandise), rounding, pickup = free, standard delivery = 600
  unless free, defaults `regular`/`pickup`, validation, stock, numbering, history and cancellation.
- `FUNCTIONAL_SPEC.md` "Requests and validation" and "Prices" sections, plus README usage text, need updating.

## 2. Files / methods expected to change
- `supplydesk/service.py`
  - `FULFILLMENT_OPTIONS`: add `"express"`.
  - New constant `EXPRESS_FEE_CENTS = 1200`.
  - `OrderService._delivery_cents()`: add the express branch.
  - `_validate_options()`: the error message lists the three options.
- `supplydesk/cli.py`: argparse `choices` update automatically from `FULFILLMENT_OPTIONS`.
  I expect to add `help=` text so express shows up in `quote --help` / `place --help` (requirement 7).
- `supplydesk/menu.py`: the fulfillment prompt is built from `FULFILLMENT_OPTIONS`, so I expect
  **no code change** unless the display needs it.
- No change expected to `storage.py`: orders are saved as plain dicts, so express orders persist like any other.
- `quote()`, `place_order()`, `cancel_order()`: **no change expected**, because pricing now lives in
  one shared `_price_request()` (after refactoring 1).

## 3. Tests needed
- New service tests: the three CR-01 examples (2,200 / 8,400 / 13,200 cents), express is never free even
  above the threshold, the student discount applies to merchandise only, express quote equals express order,
  express order survives reopening and cancellation with the same totals, stock is restored.
- Regression: pickup and standard delivery tests stay as they are (no expected values change).
- Invalid fulfillment tests: `courier`, `Express` (wrong case) and `EXPRESS` are still rejected.
- CLI: `quote --customer student --fulfillment express --item hoodie:2` gives `total_cents` 8400, and help text mentions express.
- Menu: the prompt lists express, and an express quote shows a $12.00 delivery charge.
