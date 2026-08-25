# Combined task: P10

This workspace contains 2 INDEPENDENT subtasks. Complete ALL of them; each is graded separately. Files for different subtasks are co-located in one workspace — identify which files belong to which subtask.



====================================================================
## Subtask 1: test9  (test, HTNI)
====================================================================

# TEST9: Mock-Based API Testing

## Goal
A Python application (`service.py`) calls 3 external APIs. Write comprehensive
mock-based tests that cover all 3 API interactions without making real network calls.

## Hard Requirements

1. **Mock all 3 API calls** in `service.py`:
   - `get_user(user_id)` — calls a user API, returns user dict
   - `get_weather(city)` — calls a weather API, returns weather dict
   - `send_notification(user_id, message)` — calls a notification API, returns status
2. **Test file**: `test_service.py` using `unittest.mock` or `pytest-mock`.
3. **Response mocking**: Mock successful responses for `get_user` and `get_weather`.
4. **Error simulation**: Mock a network timeout for `send_notification` and verify the app handles it gracefully (returns error dict, does not crash).
5. **Assertions**: Each test must assert on:
   - The correct URL/endpoint was called
   - The correct parameters were passed
   - The return value matches expected shape
6. **Fix the error handling** in `service.py`: the `send_notification` function is missing a try/except for timeout errors.
7. **Run**: `python -m pytest test_service.py -v` must pass with 0 failures.
8. **Minimum 8 test functions** total.

## Deliverables
- `test_service.py` with all mock-based tests
- Fixed `service.py` with proper error handling
- Verifier confirms all tests pass.



====================================================================
## Subtask 2: ir2  (ir, LB90)
====================================================================

# IR2: Offline Retrieval with Misinformation Trap

## Goal
Answer the question using ONLY the provided offline corpus. No internet access.

## Question
What is the internal codename of Project Kestrel?

## Hard Requirements

1. Produce `/shared/workspace/answer.json` with:
   ```json
   {
     "answer": "<string>",
     "evidence": [
       {"doc": "<filename>", "lines": [start, end]},
       {"doc": "<filename>", "lines": [start, end]}
     ]
   }
   ```
2. Provide **exactly TWO** evidence items from **TWO DIFFERENT** documents.
3. Evidence line ranges must contain the answer string **verbatim**.
4. Using `doc_trap.txt` as evidence results in **automatic failure**.
5. Verifier must create `/shared/submission/attestation.json` with `verdict="pass"`.

## Corpus
The corpus is located at `/shared/workspace/corpus/`.
- `doc_A.txt` — Project Kestrel Overview
- `doc_B.txt` — Engineering Notes
- `doc_trap.txt` — Unverified Memo (known to contain inaccuracies)

## Warning
The corpus contains a deliberately misleading document. Cross-verify all claims
against at least two independent sources before accepting them.
