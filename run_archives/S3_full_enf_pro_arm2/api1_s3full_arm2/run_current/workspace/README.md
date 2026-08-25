# UserService — README

Flask API service with v1/v2 versioning.

## Running

```bash
pip install -r requirements.txt
python app.py  # runs on port 8000
```

## Testing

```bash
python -m pytest tests/ -v
```

## API Versions

- v1: `/v1/...` — legacy, backward-compatible
- v2: `/v2/...` — canonical, current

See `compat_matrix.md` for the migration status of each endpoint.

## Notes

- Only modify `app.py`
- All tests must pass after changes
