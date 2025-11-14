# Security & Data Safety

## Read-Only Guarantee

**All YouTrack integration tools in this project operate in READ-ONLY mode.**

### What This Means

- ✅ **Only fetches data** - All YouTrack tools use HTTP GET requests exclusively
- ✅ **Never modifies issues** - No POST, PUT, PATCH, or DELETE operations
- ✅ **Safe to run** - Cannot accidentally update, delete, or create issues
- ✅ **Audit-friendly** - All operations are non-destructive data reads

### Implementation Details

The `YouTrackIssuesFetcher` class includes multiple layers of protection:

1. **Class-level constant**: `READ_ONLY_MODE = True` enforces read-only operations
2. **Initialization check**: `_ensure_read_only_mode()` validates on startup
3. **Method validation**: `_validate_http_method()` blocks non-GET requests
4. **Documentation**: All methods explicitly state "READ-ONLY operation"

### Protected Tools

The following tools are guaranteed to be read-only:

- `generate-copilot-prompt` - Fetches YouTrack issues to generate Copilot prompts
- `gishant youtrack-summary` - Fetches issues to generate work summaries
- `fetch-issues` - Fetches issue details for export

### Security Validation

You can verify the read-only guarantees programmatically:

```python
from gishant_scripts.youtrack.fetch_issues import YouTrackIssuesFetcher

fetcher = YouTrackIssuesFetcher(url, token)

# This will succeed
fetcher._validate_http_method('GET')

# These will raise ValueError
fetcher._validate_http_method('POST')   # ❌ Blocked
fetcher._validate_http_method('PUT')    # ❌ Blocked
fetcher._validate_http_method('DELETE') # ❌ Blocked
```

### What Can These Tools Do?

✅ **Allowed Operations:**
- Fetch issue details (ID, summary, description, comments, etc.)
- Read custom fields (assignee, state, priority, type, etc.)
- Retrieve user information
- Search for issues based on queries
- Export data to JSON files

❌ **Blocked Operations:**
- Create new issues
- Update existing issues
- Delete issues
- Add or modify comments
- Change issue states
- Update custom fields
- Create or modify tags

### API Token Permissions

While these tools only use read operations, your YouTrack API token may have broader permissions. The tools' code ensures that even if the token has write access, no write operations will be performed.

**Recommendation:** For maximum security, create a dedicated read-only API token in YouTrack:

1. Go to YouTrack Settings → Users → [Your User] → Authentication
2. Create a new Permanent Token
3. Name it descriptively (e.g., "Read-Only Scripts")
4. Use this token specifically for these tools

### Verification

Run the test suite to verify read-only guarantees:

```bash
cd /home/gisi/dev/repos/gishant-scripts
uv run python /tmp/test_readonly.py
```

Expected output:
```
✓ READ_ONLY_MODE: True
✓ GET requests allowed
✓ POST blocked correctly
✓ PUT blocked correctly
✓ DELETE blocked correctly

✅ All read-only guardrails working correctly!
```

## Questions or Concerns?

If you have any questions about data safety or security:

1. Review the source code in `src/gishant_scripts/youtrack/`
2. Look for all `requests.get()` calls (no `post()`, `put()`, `delete()`)
3. Check for the `READ_ONLY_MODE` constant
4. Verify `_validate_http_method()` enforcement

The code is intentionally simple and transparent to enable easy auditing.
