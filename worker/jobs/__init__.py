"""RQ job modules for CodeWizard AI.

RQ resolves job callables via attribute lookups, so we import job modules here
to make them available as attributes on `worker.jobs`.
"""

from . import analyze_pr  # noqa: F401

