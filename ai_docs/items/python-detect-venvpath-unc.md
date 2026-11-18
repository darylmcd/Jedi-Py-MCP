# python-detect-venvpath-unc — python_detect probes UNC venvPath and VIRTUAL_ENV values

**row:** `python-detect-venvpath-unc` · **pri:** `Low` · **size:** `M` · **verified:** `56acf734d43c24c331918b47ac75a7fbe6956ad4`

## Anchors

- `src/python_refactor_mcp/util/python_detect.py:53`
- `src/python_refactor_mcp/util/python_detect.py:57`
- `src/python_refactor_mcp/util/python_detect.py:62`
- `src/python_refactor_mcp/util/python_detect.py:64`
- `src/python_refactor_mcp/util/shared.py:140`

## Acceptance

- [ ] A UNC or device value in either source is skipped before any is_dir or exists call, asserted with spies on Path methods.
- [ ] Non-network absolute values still resolve as before (existing tests stay green).

## Evidence

- Found in the PR #219 review: ADR 0011 guards caller-supplied tool strings, not values read from the workspace pyproject or the environment.
