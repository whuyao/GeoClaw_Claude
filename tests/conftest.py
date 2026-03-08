# conftest.py — GeoClaw test configuration
# Legacy standalone test scripts are excluded from pytest auto-collection.
# Run them directly: python tests/test_nl.py
collect_ignore = [
    "test_nl.py",
    "test_memory.py",
    "test_v230_new.py",
    "test_v230_features.py",
    "test_mobility.py",
    "test_sre_phase2.py",
    "test_sre_phase3.py",
    "test_updater.py",
]
