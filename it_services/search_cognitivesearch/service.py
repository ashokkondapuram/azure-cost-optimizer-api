"""IT service entity — public exports for Cognitive Search."""

from __future__ import annotations

SERVICE_ID = "search-cognitivesearch"
CANONICAL_TYPE = "search/cognitivesearch"
ARM_TYPE = "Microsoft.Search/searchServices"
DISPLAY_NAME = "Cognitive Search"
API_SLUG = "cognitivesearch"
COMPONENT = "Search"

from it_services.search_cognitivesearch.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.search_cognitivesearch.engine.sub_engine import SearchSubEngine as SubEngine

