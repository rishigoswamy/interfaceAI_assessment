"""
src/replay/locator.py
Multi-strategy resilient element locator resolver.
Tries semantic/accessibility locators first, then text heuristics, CSS, XPath, and coordinate fallbacks.
"""

from typing import List, Optional, Tuple
from playwright.async_api import Page, Locator
from src.schema.artifact import LocatorStrategy, TargetLocator


class LocatorResolver:
    """Resolves UI elements across prioritized fallback strategies."""

    @classmethod
    async def resolve_element(
        cls,
        page: Page,
        locators: List[TargetLocator],
        timeout_ms: int = 4000
    ) -> Tuple[Optional[Locator], Optional[TargetLocator], Optional[str]]:
        """
        Attempts each locator strategy in priority order.
        Returns: (resolved_playwright_locator, matching_TargetLocator, strategy_name)
        """
        last_error = None

        for loc in locators:
            try:
                scope = page
                if loc.frame_selector:
                    scope = page.frame_locator(loc.frame_selector)

                element = None
                if loc.strategy == LocatorStrategy.ROLE_NAME and loc.role:
                    # Semantic Accessibility Tree targeting
                    element = scope.get_by_role(loc.role, name=loc.name or loc.value)
                elif loc.strategy == LocatorStrategy.TEXT_ANCHOR:
                    # Visible text matching
                    element = scope.get_by_text(loc.value, exact=not loc.is_fuzzy)
                elif loc.strategy == LocatorStrategy.CSS:
                    # CSS selector
                    element = scope.locator(loc.value)
                elif loc.strategy == LocatorStrategy.XPATH:
                    # XPath selector
                    element = scope.locator(f"xpath={loc.value}")
                elif loc.strategy == LocatorStrategy.COORDINATES:
                    # Coordinates do not produce a Locator object, handled by caller
                    return None, loc, loc.strategy.value

                if element is not None:
                    # Verify element exists and is attached
                    count = await element.count()
                    if count > 0:
                        # Wait for visibility within small window
                        first_el = element.first
                        await first_el.wait_for(state="visible", timeout=timeout_ms)
                        return first_el, loc, loc.strategy.value
            except Exception as e:
                last_error = str(e)
                continue

        return None, None, f"All locator strategies failed. Last error: {last_error}"
