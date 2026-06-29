# CHANGELOG

## SOS Sync - 2026-06-28 22:33:24

## [2026-06-28 22:32:13] 9fe685ab-3044-4562-900a-c42e2a21a083

**Advice**: Run the test suite to ensure:
1. test_security_red_fail.py passes (validates the new guards).
2. test_openviking_native.py and test_openviking_client.py pass (validates no regression in existing 17 tests).
3. Confirm that safe paths (e.g., './local_file.txt') are still accepted.

---

## SOS Sync - 2026-06-28 22:32:54

## [2026-06-28 22:32:13] 2bd5b81b-7b75-47e4-b80d-f1a40067c836

**Advice**: Modify openviking_client.py. 
1. Add the following 4 module-level functions at the top of the file (after imports, before the class):
   - `_is_path_traversal_attempt(path: str) -> bool`: Check for '../' or '..\\'.
   - `_contains_null_bytes(path: str) -> bool`: Check for '\x00'.
   - `_is_valid_path_for_add_resource(path: str) -> bool`: Combine checks, log warning if blocked, return True if safe.
   - `_is_empty_or_whitespace(query: str) -> bool`: Check for None, empty, or whitespace.
2. In `add_resource(self, path)`: Insert the validation check `if not _is_valid_path_for_add_resource(path): return None` immediately after the `self._client is None` check (approx line 97) and BEFORE the `try` block.
3. In `find_resources(self, query)`: Insert the validation check `if _is_empty_or_whitespace(query): return []` immediately after the `self._client is None` check (approx line 141) and BEFORE the `try` block.
4. Ensure logging uses `logger.warning` for security blocks.
5. Do NOT modify any other logic or imports.

---

