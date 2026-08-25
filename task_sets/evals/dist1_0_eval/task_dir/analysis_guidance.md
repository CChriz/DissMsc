# Analysis Guidance — DIST1_queue_race

## Tools to run
- `cat mqueue/queue.py` — find the TOCTOU and missing ack bugs
- `cat mqueue/priority.py` — find the comparator bug
- `cat mqueue/consumer.py` — understand current consumer interface
- `python -m pytest tests/test_single_thread.py -v` — see which tests pass now
- `python -m pytest tests/test_concurrent.py -v --timeout=30` — see failures

## Bug Analysis

### Bug 1: TOCTOU Capacity Check (mqueue/queue.py, put method)
```python
# CURRENT (BUGGY): two operations, race between them
def put(self, message):
    if len(self._queue) >= self._capacity:  # Step 1: check
        raise QueueFull()
    self._queue.append(message)  # Step 2: add (race here!)
```
**Fix**: Hold a lock for BOTH the check AND the append as one atomic operation:
```python
def put(self, message):
    with self._lock:
        if len(self._queue) >= self._capacity:
            raise QueueFull()
        self._queue.append(message)
```
The lock must cover both steps — adding a lock only around the check or only around
the append does NOT fix the race.

### Bug 2: No Acknowledgment (mqueue/queue.py, get method)
```python
# CURRENT (BUGGY): removes message before processing is confirmed
def get(self):
    with self._lock:
        if not self._queue:
            return None
        return self._queue.popleft()  # BUG: message gone if consumer crashes
```
**Fix**: Two-phase delivery — move to "in-flight" state, confirm on ack:
```python
def get(self):
    with self._lock:
        if not self._pending:
            return None, None
        msg = self._pending.popleft()
        receipt = self._generate_receipt()
        self._in_flight[receipt] = msg  # Hold until acked
        return msg, receipt

def ack(self, receipt):
    with self._lock:
        self._in_flight.pop(receipt, None)  # Now safe to discard

def nack(self, receipt):
    with self._lock:
        msg = self._in_flight.pop(receipt, None)
        if msg:
            self._pending.appendleft(msg)  # Re-queue for retry
```

### Bug 3: Type-Unsafe Priority Comparator (mqueue/priority.py)
```python
# CURRENT (BUGGY): compares message objects by value when priorities are equal
@dataclass(order=True)
class PriorityMessage:
    priority: int
    message: Any  # BUG: When priorities equal, Python compares message field
    # This crashes with TypeError if message is a dict or list
```
**Fix**: Add a monotonic sequence number as tie-breaker:
```python
@dataclass(order=True)
class PriorityMessage:
    priority: int
    seq: int        # Tie-breaker: monotonically increasing (never compared on type)
    message: Any = field(compare=False)  # Exclude from comparison
```

## Tell Executor
Fix bugs in mqueue/queue.py, mqueue/priority.py, and update mqueue/consumer.py
to use the ack/nack pattern in the consumer loop.
