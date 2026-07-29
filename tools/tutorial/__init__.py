"""Builder for the bilingual illustrated tutorial/devguide HTML pages.

Content lives in ``content/tutorial`` and ``content/devguide`` as plain
data (see ``model.py``); everything expensive runs once through
``runs.RunContext``; ``render.py`` emits self-contained offline HTML
(math pre-rendered to SVG, figures embedded as base64 PNG, schematics as
schemdraw SVG).  Entry point: ``python tools/build_docs.py``.
"""
