"""Phase 4C — Multi-Timeframe Confluence Framework.

Public API:

    from confluence import (
        ConfluenceResult,
        ConfluenceComponent,
        ConfluenceEngineService,
        TimeframeAlignmentService,
    )
"""
from confluence.confluence_models import ConfluenceComponent, ConfluenceResult
from confluence.confluence_engine import ConfluenceEngineService
from confluence.timeframe_alignment import TimeframeAlignmentService

__all__ = [
    "ConfluenceComponent",
    "ConfluenceResult",
    "ConfluenceEngineService",
    "TimeframeAlignmentService",
]
