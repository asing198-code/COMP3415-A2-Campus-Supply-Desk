# Work log and evidence (Tasks 2, 4, 5, 6)

Raw material for the final report. Rewrite it in your own words. Run the tests with
`python -m unittest discover -s tests -v`.

| Stage | Evidence file | Result |
|---|---|---|
| Baseline (original code + new tests) | `01-baseline-tests.txt` | 39 tests, **3 failures** |
| After the three refactorings | `02-after-refactor-tests.txt` | 39 tests, **the same 3 failures** |
| After the defect fixes | `03-after-defect-fixes-tests.txt` | 39 tests, OK |
| After CR-01 | `04-after-cr01-tests.txt` | 51 tests, OK |

The original `service.py`, `cli.py` and `menu.py` are copied in `evidence/original/` for before/after comparison.

---

## Task 2 – Testing safety net

Files: `tests/helpers.py` (fixture: a fresh temporary save file per test), `tests/test_service.py`,
`tests/test_interfaces.py`. The class names in `test_service.py` match the four categories.

| Category | What is tested | Why it matters | Expected vs actual (baseline) |
|---|---|---|---|
| Normal (`NormalBehaviourTests`, `CommandTests`, `MenuTests`) | Spec price examples (1,000 / 7,800 / 12,000), line details, stock deduction, `ORD-0001`/`ORD-0002` numbering, history order; CLI JSON output and menu quote/placement | The core purpose of the app; also exercises both user interfaces | All pass |
| Boundary (`BoundaryBehaviourTests`) | Student discount at 4,500 / **5,000** / 5,500; free delivery at 9,500 vs 10,000 and after a student discount; half-cent rounding (5,005 → 501 discount) with a custom catalog; quantity 1/99 accepted, 0/−1/100 rejected; ordering exactly the remaining stock | Off-by-one rules are where pricing bugs hide | **Fails at 5,000**: expected discount 500, actual 0 (`subtotal > 5000` defect). All other boundaries pass |
| Invalid (`InvalidBehaviourTests`, `test_service_errors_exit_nonzero_with_message`, `test_parser_rejects_bad_options`) | Bad customer/fulfillment values, bad item lists, `bool`/`float`/`"2"` quantities, over-stock, unknown product/order, malformed save file; every rejection must leave the save file byte-for-byte unchanged; CLI exits non-zero | The spec says invalid requests raise `ValueError` and change nothing | **Fails for duplicate lines**: notebook 15 + 10 with stock 20 is accepted (stock would become −5). All others pass |
| Preserve (`PreservedBehaviourTests`) | Quote equals the order placed after it, `pickup` default, a quote creates no file, reopening keeps orders/stock/numbering, cancel keeps original totals and restores stock, IDs not reused, repeat cancel | These are exactly the behaviors the planned Extract Method refactoring of `quote`/`place_order` could break | **Fails for repeat cancel**: stock goes 4 → 2 → 4 → **6** (expected 4). All others pass |

The failing tests were kept as written. Their expected values come from `FUNCTIONAL_SPEC.md`.

Test-code issue found during development: the first menu tests gave `StopIteration` because the mocked
`input()` ran out of answers. Fixed by making the mock raise `EOFError` after the scripted answers, which is
what a closed terminal does (`tests/test_interfaces.py`, `run_menu_with`).

---

## Task 4 – Refactorings (behavior-preserving)

Verification for all three: `02-after-refactor-tests.txt` has the same 36 passes and the same 3 failures as
the baseline. Each defect was deliberately kept (for example, `>` was still used) so that the refactoring alone
could be verified.

### R1 – Duplicated Code / Long Method → Extract Method (`service.py`)
- **Before:** `quote()` (49 lines) and `place_order()` (58 lines) repeated the same validation, lookup and pricing.
- **Refactoring:** extracted `_price_request()` (validate + price), `_validate_options()`, `_price_line()`,
  `_discount_cents()`, `_delivery_cents()`, `_find_product()`, `_find_order()` and `_format_order_id()`.
  `quote()` is now 2 lines; `place_order()` uses the shared result and only adds ID/status, stock changes and saving.
  `get_order`/`cancel_order` share `_find_order()`.
- **Reason / after:** one source of truth, so quote/order agreement holds by construction, and each rule is a
  small named method. Later evidence: each defect fix touched one place instead of two, and CR-01 changed only
  `_delivery_cents()`.

### R2 – Magic Numbers → Replace Magic Number with Named Constant (`service.py`)
- **Before:** `5000`, `10`, `600`, `10000`, `99`, `1`, `4`, `"ORD-"` as bare literals, each repeated.
- **After:** `STUDENT_DISCOUNT_THRESHOLD_CENTS`, `STUDENT_DISCOUNT_PERCENT`, `DELIVERY_FEE_CENTS`,
  `FREE_DELIVERY_THRESHOLD_CENTS`, `MIN_QUANTITY`, `MAX_QUANTITY`, `ORDER_ID_PREFIX`, `ORDER_NUMBER_DIGITS`.
  The half-up rounding expression now has a comment.

### R3 – Shotgun Surgery (scattered option lists) → shared constants (`service.py`, `cli.py`, `menu.py`)
- **Before:** `("regular","student")` and `("pickup","delivery")` were repeated in the service (twice), the argparse
  `choices` and the menu prompt text.
- **After:** `CUSTOMER_TYPES` and `FULFILLMENT_OPTIONS` are defined once in `service.py`. `cli.py` uses them as
  `choices`, and `menu.py` builds its prompts from them. The prompt text is identical
  (`Fulfillment [pickup/delivery] (Enter = pickup): `), as the menu tests confirm.

### Defect fixes (separate from the refactoring, `03-after-defect-fixes-tests.txt`)
1. Student discount: `>` → `>=` in `_discount_cents()` (spec: "at least 5,000").
2. Duplicate product lines: `_price_line()` now accumulates requested units per product across lines and checks
   the total against stock.
3. Repeat cancellation: `cancel_order()` returns an already-cancelled order unchanged, without restoring stock or saving.

---

## Task 5 – CR-01 Express delivery

### Part A
See `CR-01-part-A-prediction.md` (written before implementation).

### Part B – what changed
- `service.py`: `FULFILLMENT_OPTIONS` gains `"express"`, new `EXPRESS_FEE_CENTS = 1200`, `_delivery_cents()` returns
  it for express before the free-delivery check, and the validation message lists three options.
- `cli.py`: help text for `quote`/`place` and their options (`--fulfillment` describes all three fees). The
  `choices` came from the constant, so no validation code changed.
- `menu.py`: **no change.** The prompt reads `Fulfillment [pickup/delivery/express] (Enter = pickup)` automatically.
- Docs: `FUNCTIONAL_SPEC.md` (validation, price rule 6, three examples), `README.md` (command example, options text,
  test list, expected test count).
- Tests: new `tests/test_express.py` (12 tests): CR-01 examples 2,200 / 8,400 / 13,200; express never waived above
  10,000; discount on merchandise only, including at the 5,000 boundary; `Express`/`EXPRESS`/` express`/`rush`
  still invalid; existing validation and stock rules apply; quote equals order; reopen, cancel, repeat cancel
  and numbering for express orders; CLI example `total_cents` 8400; `--help` mentions express; the menu prompt
  lists express and shows `Delivery: $12.00`; blank fulfillment is still `pickup`.
- Result: 51 tests, OK (`04-after-cr01-tests.txt`). No existing test needed changing. The invalid-fulfillment
  tests had used `courier` rather than `express`.

### Part C – review notes
- Prediction accuracy: correct about `service.py` (constants + `_delivery_cents` only) and about `menu.py` needing
  no code change. `quote()`/`place_order()`/`cancel_order()` and `storage.py` were indeed untouched.
  Slight underestimate: `cli.py` had no help text at all, so meeting requirement 7 meant adding help for every option,
  not just the fulfillment one.
- Effect of the refactoring: it made CR-01 **much easier**. Without R1 the fee logic would have been edited in both
  `quote()` and `place_order()`. Without R3 the new option would have had to be added in four places across three
  files. With them, the code change was about 6 lines in one method plus constants.

---

## Task 6 – candidate AI recommendations from this session

You make the ACCEPT / MODIFY / REJECT decisions and justify them with evidence. Some candidates:

1. **Mock `input()` with a list of answers to test the menu.** The first version caused `StopIteration` errors.
   The AI corrected it to raise `EOFError` after the answers. Evidence: the earlier error, now fixed (a good MODIFY example).
2. **Fix the three defects inside the refactoring step.** Instead, the refactoring kept the defects and the fixes
   were a separate step, as the handout requires. Evidence: identical failures in `01` and `02`, all passing in `03`.
   You could also argue REJECT for "fix while refactoring".
3. **Extract one shared `_price_request()` for quote and order.** Evidence: the CR-01 change touched one method.
4. **Use `courier` rather than `express` as the invalid-fulfillment test value.** This kept the baseline tests valid after CR-01.
5. **Store shared option constants in `service.py` and import them into `cli.py`/`menu.py`.** One possible counter-argument: it couples the UI to
   the service module (an alternative is a separate `options.py`).

Include this conversation (exported transcript) as the AI-use record.
