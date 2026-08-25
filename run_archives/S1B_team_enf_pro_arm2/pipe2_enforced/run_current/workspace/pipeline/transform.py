COLUMNS = ['emp_id', 'full_name', 'department', 'notes']
COL_TYPES = ['int', 'str', 'str', 'str']

# Truncation limit per PIPELINE_SPEC.md
TRUNCATION_LIMIT = 255


def transform(rows: list[dict]) -> list[dict]:
    """
    Normalize and truncate string fields.

    BUG: Uses truncation limit of 50 instead of 255.
    """
    result = []
    for row in rows:
        new_row = {}
        for i, col in enumerate(COLUMNS):
            val = row.get(col, "") or ""
            if COL_TYPES[i] == "str":
                val = val.strip()
                if len(val) > TRUNCATION_LIMIT:
                    val = val[:TRUNCATION_LIMIT]
            new_row[col] = val
        result.append(new_row)
    return result
