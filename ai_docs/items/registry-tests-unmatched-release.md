# registry-tests-unmatched-release — Registry tests acquire leases they never release

**row:** `registry-tests-unmatched-release` · **pri:** `Low` · **size:** `S` · **verified:** `56acf734d43c24c331918b47ac75a7fbe6956ad4`

## Anchors

- `tests/unit/test_workspace_registry.py:224`
- `tests/unit/test_workspace_registry.py:498`
- `tests/unit/test_workspace_registry.py:814`
- `tests/unit/test_workspace_registry.py:950`

## Acceptance

- [ ] Every get_backends call in the file has a matching release, or uses a helper that releases on exit.
- [ ] A teardown assertion fails any test that leaves a nonzero lease count on a live backend.

## Evidence

- Found in the PR #216 review: the tests model requests that never finish, which hides lease-accounting defects. Re-counted on 56acf73: 19 get_backends calls, 2 release calls (lines 817-818).
