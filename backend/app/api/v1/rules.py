"""REST API for crawler rule management and testing."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.crawlers import rule_engine
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/rules", tags=["Rules"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RuleTestRequest(BaseModel):
    source_name: str = Field(description="e.g. '23qb'")
    section: str = Field(
        description="search | novel_info | catalog | chapter",
        pattern="^(search|novel_info|catalog|chapter)$",
    )
    test_url: Optional[str] = Field(default=None, description="Direct URL to test")
    keyword: Optional[str] = Field(default=None, description="Search keyword")
    book_id: Optional[str] = Field(default=None, description="Book ID for catalog")
    chapter_url: Optional[str] = Field(default=None, description="Chapter URL")


class RuleSaveRequest(BaseModel):
    source_name: str
    data: dict = Field(description="Full rule JSON")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_rules(current_user: User = Depends(get_current_user)):
    """List all available crawler rules."""
    return rule_engine.list_rules()


@router.get("/{source_name}")
async def get_rule(source_name: str, current_user: User = Depends(get_current_user)):
    """Get a single rule by source name."""
    rule = rule_engine.load_rule(source_name)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule '{source_name}' not found")
    return rule


@router.put("/{source_name}")
async def save_rule(
    source_name: str,
    body: RuleSaveRequest,
    current_user: User = Depends(get_current_user),
):
    """Create or update a crawler rule.

    The rule JSON is validated and saved to ``rules/{source_name}.json``.
    """
    if source_name != body.source_name:
        raise HTTPException(
            status_code=400,
            detail="source_name in path and body must match",
        )
    try:
        rule_engine.save_rule(source_name, body.data)
        return {"message": f"Rule '{source_name}' saved", "source_name": source_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{source_name}", status_code=204)
async def delete_rule(
    source_name: str,
    current_user: User = Depends(get_current_user),
):
    """Delete a crawler rule."""
    if not rule_engine.delete_rule(source_name):
        raise HTTPException(status_code=404, detail=f"Rule '{source_name}' not found")


@router.post("/test")
async def test_rule(
    body: RuleTestRequest,
    current_user: User = Depends(get_current_user),
):
    """Test a crawler rule against a live URL.

    Fetches the target page, applies the rule selectors, and returns
    the extracted results (limited to 20 items for list sections).
    """
    result = await rule_engine.test_rule(
        source_name=body.source_name,
        section=body.section,
        test_url=body.test_url,
        keyword=body.keyword,
        book_id=body.book_id,
        chapter_url=body.chapter_url,
    )
    if not result["success"]:
        raise HTTPException(status_code=422, detail=result.get("error", "Test failed"))
    return result


@router.post("/test-preview")
async def test_preview(
    body: RuleTestRequest,
    current_user: User = Depends(get_current_user),
):
    """Quick preview — same as /test but only returns first 5 results."""
    result = await rule_engine.test_rule(
        source_name=body.source_name,
        section=body.section,
        test_url=body.test_url,
        keyword=body.keyword,
        book_id=body.book_id,
        chapter_url=body.chapter_url,
    )
    if not result["success"]:
        raise HTTPException(status_code=422, detail=result.get("error", "Test failed"))
    result["results"] = result["results"][:5]
    result["displayed"] = min(result["displayed"], 5)
    return result
