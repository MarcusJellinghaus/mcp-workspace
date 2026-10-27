"""Disk caches for GitHub data shared across short-lived processes.

Kept import-free on purpose: ``issues`` imports from this package and
``caching.branches`` imports from ``issues``, so any import here would
create a load-time cycle. Import the submodules directly.
"""
