# CR4: API Design Fix (Brief)

## Your Task
The **User Management API** (`app.py`) was flagged during code review for
multiple API design violations.

Fix all the violations so the API conforms to the team's REST API design guidelines.

## What You Know
- The API is implemented in `app.py` (Flask/Python).
- The code review found issues with HTTP methods, route naming, pagination,
  status codes, API versioning, and error response format.
- `tests/test_api.py` must pass without any modification after your fixes.
- Do NOT modify `tests/test_api.py`.
- Install dependencies before running tests:
  ```bash
  pip install -r requirements.txt
  pytest tests/test_api.py -v
  ```

## What the Planner Has
The Planner has the full API review report with every violation, the exact
locations in `app.py`, and the specific fixes required. Follow the Planner's
instructions precisely.
