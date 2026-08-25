# SYNTH1: Distributed Debugging

## Goal
Fix 3 reported bugs in the web application so the test suite passes.

## Bug Report 1: "Users can't update their email"
- **Symptom**: `PUT /users/{id}` returns 200 but the `email` field is not updated
- **Steps to reproduce**: Send a PUT request with `{"email": "new@example.com"}` to `/users/{id}`
- **Server logs**: Request is received, handler completes with 200 status, no errors logged
- **Expected**: After a successful PUT, subsequent GET of the same entity must reflect the new `email` value
- **Constraint**: The handler must read the `email` value from the correct field in the JSON request body (not `username`)

## Bug Report 2: "Order totals are wrong after applying discounts"
- **Symptom**: A order for 2 items at $31.0 each with a 20% discount shows a total of $62.0 instead of $49.6
- **Steps to reproduce**: Create a order, apply a 20% discount, then retrieve the total
- **Server logs**: Cache hit rate is high, response times are normal
- **Monitoring data**: The caching layer is returning values that do not reflect recent changes
- **Expected**: The order total after applying a discount must reflect the discounted price
- **Constraint**: The root cause is in the caching layer, not the order calculation logic itself

## Bug Report 3: "Monthly reports show dates in wrong timezone"
- **Symptom**: A report generated for an event that occurred at 11pm EST on 2024-12-31 shows the date as 2025-01-01
- **Steps to reproduce**: Create an event at 2024-12-31 23:00 EST, then generate the monthly report
- **Server logs**: Date formatting is performed in UTC
- **Expected**: Dates displayed in reports must reflect the local timezone (US/Eastern), not UTC
- **Constraint**: The formatting logic must convert timestamps to the correct local timezone before rendering the date string

## Deliverables
- Fix all 3 bugs (minimal changes)
- All 8 tests in `test_app.py` must pass
- Total diff < 25 lines
