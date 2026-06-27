"""
Pluggable rule engine for crawler extraction rules.

Rules are stored as JSON files in ``app/crawlers/rules/``.
Each rule file defines CSS selectors, attributes, transforms, and
fallbacks for the four core operations: search, novel_info, catalog, chapter.

This module provides:

- ``load_rule(source_name)`` — load a rule JSON as a dict
- ``save_rule(source_name, data)`` — save updated rule JSON
- ``list_rules()`` — list all available rule files
- ``apply_rule(html, url, field_spec)`` — execute a field spec against HTML
- ``test_rule(url, source_name, section)`` — end-to-end test
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from app.crawlers.content_cleaner import clean_content, clean_title, clean_novel_title

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

RULES_DIR = Path(__file__).resolve().parent / "rules"

# ---------------------------------------------------------------------------
# Rule file management
# ---------------------------------------------------------------------------


def list_rules() -> list[dict[str, Any]]:
    """Return metadata for every available rule file."""
    rules: list[dict[str, Any]] = []
    if not RULES_DIR.is_dir():
        return rules
    for f in sorted(RULES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            rules.append({
                "filename": f.name,
                "source_name": data.get("source_name", f.stem),
                "description": data.get("description", ""),
                "base_url": data.get("base_url", ""),
                "version": data.get("version", "0"),
            })
        except (json.JSONDecodeError, KeyError):
            rules.append({
                "filename": f.name,
                "source_name": f.stem,
                "description": "(parse error)",
                "base_url": "",
                "version": "0",
            })
    return rules


def load_rule(source_name: str) -> Optional[dict[str, Any]]:
    """Load a single rule file by source_name."""
    filepath = RULES_DIR / f"{source_name}.json"
    if not filepath.is_file():
        return None
    return json.loads(filepath.read_text(encoding="utf-8"))


def save_rule(source_name: str, data: dict[str, Any]) -> bool:
    """Save (create or overwrite) a rule file."""
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RULES_DIR / f"{source_name}.json"
    filepath.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


def delete_rule(source_name: str) -> bool:
    """Delete a rule file."""
    filepath = RULES_DIR / f"{source_name}.json"
    if filepath.is_file():
        filepath.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


async def fetch_url(url: str, timeout: int = 60) -> str:
    """GET *url* and return the decoded text."""
    async with httpx.AsyncClient(
        timeout=timeout,
        headers=HEADERS,
        follow_redirects=True,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------


def _clean_text(text: Optional[str]) -> str:
    """Collapse whitespace."""
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _extract_field(
    soup: BeautifulSoup,
    base_url: str,
    field_spec: dict[str, Any],
    context: Optional[dict[str, Any]] = None,
) -> str:
    """Apply a single field spec to *soup* and return the extracted string.

    Field spec keys:
        selector         — CSS selector
        attribute        — "text" | "href" | "content" | "src" | any attr name
        fallback_selector / fallback_attribute — used if primary yields nothing
        fallback         — literal string fallback
        transform         — "absolute_url" | "regex" | "strip_prefix:X" |
                            "strip_suffix:X" | "status_map"
        transform_pattern — regex pattern for "regex" transform
        cleanup           — list of CSS selectors to remove before extraction
        split_pattern     — regex to split text (for author extraction)
        split_index       — which split segment to return
    """
    result = ""
    used_fallback = False

    # Primary selector
    selector = field_spec.get("selector", "")
    attribute = field_spec.get("attribute", "text")

    if selector:
        el = soup.select_one(selector)
        if el is not None:
            result = _get_element_value(el, attribute)

    # Fallback selector
    if not result:
        fb_sel = field_spec.get("fallback_selector", "")
        fb_attr = field_spec.get("fallback_attribute", "text")
        if fb_sel:
            el = soup.select_one(fb_sel)
            if el is not None:
                result = _get_element_value(el, fb_attr)
                used_fallback = True

    # Context-based fallbacks (run BEFORE literal fallback so transforms work)
    if not result and context:
        ctx_url = context.get("url", "")
        if "from_url" in field_spec.get("fallback", ""):
            result = ctx_url
        elif field_spec.get("fallback") == "text_split":
            # For search results: split the full item text to extract author
            pattern = field_spec.get("split_pattern", ".")
            idx = field_spec.get("split_index", 2)
            full_text = soup.get_text(" ", strip=True)
            parts = full_text.split(pattern)
            if len(parts) > idx:
                result = parts[idx].strip()
        elif field_spec.get("fallback") == "text_after_title":
            # Description: everything after the title
            if "title" in context:
                full_text = soup.get_text(" ", strip=True)
                title = context["title"]
                idx_in_text = full_text.find(title)
                if idx_in_text >= 0:
                    after = full_text[idx_in_text + len(title):]
                    # Remove author prefix if present
                    if context.get("author") and after.startswith(context["author"]):
                        after = after[len(context["author"]):]
                    result = after.strip(" .")

    # Literal fallback (runs last, after context fallbacks)
    if not result:
        fb = field_spec.get("fallback", "")
        if fb and fb not in ("from_url", "text_split", "text_after_title"):
            result = fb
            used_fallback = True

    # Transforms
    if used_fallback:
        # When fallback was used, try fallback_transform first,
        # then fall back to the primary transform.
        fb_transform = field_spec.get("fallback_transform", "")
        if fb_transform:
            result = _apply_transform(result, {"transform": fb_transform}, base_url)
        else:
            result = _apply_transform(result, field_spec, base_url)
    else:
        result = _apply_transform(result, field_spec, base_url)

    return result


def _get_element_value(el: Tag, attribute: str) -> str:
    """Get a value from a BeautifulSoup element."""
    if attribute == "text":
        return _clean_text(el.get_text())
    if attribute in ("content",):
        val = el.get("content", "")
        return str(val).strip()
    val = el.get(attribute, "")
    return str(val).strip()


def _apply_transform(value: str, field_spec: dict[str, Any], base_url: str) -> str:
    """Apply post-processing transforms to an extracted value."""
    transform = field_spec.get("transform", "")
    if not transform or not value:
        return value

    if transform == "absolute_url":
        return urljoin(base_url, value)

    if transform == "regex":
        pattern = field_spec.get("transform_pattern", "")
        if pattern:
            m = re.search(pattern, value)
            if m:
                return m.group(1) if m.lastindex else m.group(0)

    if transform.startswith("strip_prefix:"):
        prefix = transform.split(":", 1)[1]
        if value.startswith(prefix):
            return value[len(prefix):]

    if transform.startswith("strip_suffix:"):
        suffix = transform.split(":", 1)[1]
        if value.endswith(suffix):
            return value[:-len(suffix)]

    if transform == "status_map":
        status_map = field_spec.get("status_map", {
            "完结": "completed",
            "连载": "ongoing",
            "连载中": "ongoing",
        })
        return status_map.get(value, value)

    return value


def apply_rule(
    html: str,
    base_url: str,
    field_specs: dict[str, Any],
    container_selector: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
    cleaner_config: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Apply a section's field specs to HTML.

    Args:
        html: Raw HTML string.
        base_url: Base URL for resolving relative links.
        field_specs: Dict of field_name -> field_spec (the "fields" block).
        container_selector: Optional CSS selector for repeating container
                           elements (e.g. search results, catalog rows).
        context: Optional dict passed through to field extractors.
        cleaner_config: Optional ``cleaner`` block from rule JSON;
                        content fields are auto-cleaned when this is provided.

    Returns:
        List of dicts, each dict maps field_name -> extracted_value.
        If *container_selector* is None, returns a single-element list.
    """
    soup = BeautifulSoup(html, "lxml")

    # Apply cleanup to the whole soup
    for selector in field_specs.get("_cleanup", []):
        for el in soup.select(selector):
            el.decompose()

    # Determine whether this is a repeating-container section.
    # "body" and empty-string containers mean single-item extraction
    # (use the whole document soup so <head> meta tags are available).
    is_repeating = bool(
        container_selector
        and container_selector.strip()
        and container_selector.lower() not in ("body", "html")
    )

    if is_repeating:
        # Multiple items (search results / catalog rows)
        items = soup.select(container_selector)
        results: list[dict[str, Any]] = []
        for item in items:
            row: dict[str, Any] = {}
            item_soup = BeautifulSoup(str(item), "lxml")
            row_context = dict(context or {})
            for field_name, field_spec in field_specs.items():
                if field_name.startswith("_"):
                    continue
                val = _extract_field(item_soup, base_url, field_spec, row_context)
                row[field_name] = val
                row_context[field_name] = val
            results.append(row)
        return results
    else:
        # Single item (novel info / chapter) — use whole document
        row: dict[str, Any] = {}
        row_context = dict(context or {})
        for field_name, field_spec in field_specs.items():
            if field_name.startswith("_"):
                continue
            val = _extract_field(soup, base_url, field_spec, row_context)
            row[field_name] = val
            row_context[field_name] = val
        # Apply content + title cleaner if configured
        if cleaner_config and cleaner_config.get("enabled"):
            for field_name in ("content",):
                if field_name in row and row[field_name]:
                    row[field_name] = clean_content(
                        row[field_name],
                        remove_lines=cleaner_config.get("remove_lines"),
                        inline_remove=cleaner_config.get("inline_remove"),
                        min_line_length=cleaner_config.get("min_line_length", 2),
                        max_repeat_ratio=cleaner_config.get("max_repeat_ratio", 0.6),
                    )
            for field_name in ("title",):
                if field_name in row and row[field_name]:
                    row[field_name] = clean_title(row[field_name])
            # Also clean book titles in novel_info / search results
            for field_name in ("title",):
                if field_name in row and row[field_name]:
                    row[field_name] = clean_novel_title(row[field_name])
        return [row]


# ---------------------------------------------------------------------------
# End-to-end test
# ---------------------------------------------------------------------------


async def test_rule(
    source_name: str,
    section: str,
    test_url: Optional[str] = None,
    keyword: Optional[str] = None,
    book_id: Optional[str] = None,
    chapter_url: Optional[str] = None,
) -> dict[str, Any]:
    """Load a rule, fetch the URL, apply the section rules, return the result.

    Args:
        source_name: e.g. "23qb"
        section: "search" | "novel_info" | "catalog" | "chapter"
        test_url: Direct URL override (bypasses rule URL patterns).
        keyword: Search keyword (for section="search").
        book_id: Book ID (for section="catalog").
        chapter_url: Chapter page URL (for section="chapter").
        novel_url: Novel page URL (for section="novel_info").

    Returns:
        {"success": bool, "url": str, "results": [...], "error": ""}
    """
    rule = load_rule(source_name)
    if not rule:
        return {"success": False, "error": f"Rule '{source_name}' not found"}

    selectors = rule.get("selectors", {})
    if section not in selectors:
        return {"success": False, "error": f"Section '{section}' not in rule"}

    section_rule = selectors[section]
    base_url = rule.get("base_url", "")

    # Build URL
    if test_url:
        url = test_url
    elif section == "search":
        kw = keyword or "test"
        url = base_url + section_rule.get("url", "").replace("{keyword}", kw)
    elif section == "novel_info":
        if test_url:
            url = test_url
        else:
            return {"success": False, "error": "Need test_url for novel_info"}
    elif section == "catalog":
        bid = book_id or "1"
        tmpl = section_rule.get("url", "{base_url}/book/{book_id}/catalog")
        url = tmpl.format(base_url=base_url, book_id=bid)
    elif section == "chapter":
        if chapter_url:
            url = chapter_url
        else:
            return {"success": False, "error": "Need chapter_url for chapter"}
    else:
        return {"success": False, "error": f"Unknown section: {section}"}

    try:
        html = await fetch_url(url)
    except Exception as exc:
        return {"success": False, "error": f"Fetch failed: {exc}", "url": url}

    try:
        container = section_rule.get("container", "")
        fields = section_rule.get("fields", {})
        context = {"url": url, "base_url": base_url}

        # Apply chapter-specific cleanup
        if section == "chapter":
            cleanup_selectors = fields.get("content", {}).get("cleanup", [])
            soup = BeautifulSoup(html, "lxml")
            for sel in cleanup_selectors:
                for el in soup.select(sel):
                    el.decompose()
            html = str(soup)

        cleaner_config = rule.get("cleaner")
        results = apply_rule(
            html,
            base_url,
            fields,
            container_selector=container or None,
            context=context,
            cleaner_config=cleaner_config,
        )

        # Limit results for display
        display_results = results[:20] if len(results) > 20 else results

        return {
            "success": True,
            "url": url,
            "total": len(results),
            "displayed": len(display_results),
            "results": display_results,
        }
    except Exception as exc:
        return {"success": False, "error": f"Extraction failed: {exc}", "url": url}
