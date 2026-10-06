"""Scaffolding check: the package installs and imports.

This exists so CI has a real test to run before the first ticket lands
(pytest exits non-zero when it collects nothing). Replace or extend it freely.
"""

import lit_vault_tools


def test_package_imports_with_a_version():
    assert lit_vault_tools.__version__
