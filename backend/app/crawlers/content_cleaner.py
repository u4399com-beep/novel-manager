"""
Content cleaner — removes ads, navigation, watermarks, and
anti-theft obfuscation from crawled chapter bodies.

Configurable via the rule JSON ``cleaner`` section.
"""

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Built-in filter profiles
# ---------------------------------------------------------------------------

# Patterns common across Chinese novel sites
BUILTIN_REMOVE_LINES = [
    # Navigation
    r"^.*(上一章|下一章|返回目录|加入书签|推荐本书|投推荐票).*$",
    r"^.*(手机阅读|手机版|移动版|客户端|下载APP|扫码).*$",
    r"^.*(Ctrl\s*\+?\s*[DF]|F5|F11|ALT\s*\+).*$",
    # Site watermarks
    r"^.*(铅笔小说|23qb|笔趣阁|顶点小说|天籁小说|飘天文学).*$",
    r"^.*(www\..*\.(com|net|org|cn)).*$",
    r"^.*(记住本站|收藏本站|网址|域名|地址).*$",
    # Anti-theft garbage
    r"^[\s\.。…]{10,}$",                    # lines of just dots
    r"^[A-Za-z0-9]{20,}$",                 # random alphanumeric
    r"^.*(最新章节|更新最快|最快更新).*$",
    # Empty / whitespace-only
    r"^\s*$",
    # Pure punctuation lines
    r"^[，。！？…、；：""''（）《》\[\]{}【】\-,.!?:;\"'()\s]+$",
]

# Substring patterns to remove inline (within a line)
BUILTIN_INLINE_REMOVE = [
    r"（本章未完[^）]*）",
    r"\(本章未完[^)]*\)",
    r"【[^】]*?(更新|首发|独家)[^】]*?】",
    r"\[[^\]]*?(更新|首发|独家)[^\]]*?\]",
    r"（温馨提示[^）]*）",
]


def clean_content(
    text: str,
    *,
    remove_lines: Optional[list[str]] = None,
    inline_remove: Optional[list[str]] = None,
    min_line_length: int = 2,
    max_repeat_ratio: float = 0.6,
) -> str:
    """Clean crawled chapter content.

    Parameters
    ----------
    text:
        Raw chapter body text.
    remove_lines:
        Additional regex patterns — entire matching lines are dropped.
    inline_remove:
        Additional regex patterns — matching substrings are removed from lines.
    min_line_length:
        Lines shorter than this (after stripping) are dropped.
    max_repeat_ratio:
        If the same character repeats for more than this fraction of a line,
        the line is dropped as garbage.

    Returns
    -------
    Cleaned text.
    """
    if not text:
        return ""

    # Merge built-in + custom patterns
    line_patterns = list(BUILTIN_REMOVE_LINES) + (remove_lines or [])
    inline_patterns = list(BUILTIN_INLINE_REMOVE) + (inline_remove or [])

    # Pre-compile
    line_re = re.compile("|".join(f"({p})" for p in line_patterns)) if line_patterns else None
    inline_re = re.compile("|".join(f"({p})" for p in inline_patterns)) if inline_patterns else None

    lines = text.split("\n")
    cleaned: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            continue

        # Skip too-short lines
        if len(stripped) < min_line_length:
            continue

        # Check repeat ratio (garbage detection)
        if _is_repeat_garbage(stripped, max_repeat_ratio):
            continue

        # Check line-level patterns
        if line_re and line_re.search(stripped):
            continue

        # Apply inline removals
        if inline_re:
            stripped = inline_re.sub("", stripped).strip()
            if not stripped:
                continue

        cleaned.append(stripped)

    return "\n".join(cleaned)


def _is_repeat_garbage(text: str, max_ratio: float) -> bool:
    """Return True if *text* is mostly the same character repeated."""
    if len(text) < 5:
        return False
    from collections import Counter
    counts = Counter(text)
    most_common = counts.most_common(1)[0][1]
    return (most_common / len(text)) >= max_ratio


# ---------------------------------------------------------------------------
# Title cleaner
# ---------------------------------------------------------------------------

# Patterns to REMOVE from titles (aggressive patterns)
TITLE_REMOVE_PATTERNS = [
    r"\s*[-–—]\s*(铅笔小说|23qb|笔趣阁|顶点|天籁|飘天文学|最新章节).*$",
    r"\s*[-–—]\s*(www\..*\.(com|net|org|cn)).*$",
    r"\s*[（(]\s*(求收藏|求推荐|求月票|求订阅|求打赏|第一更|第二更|第三更|补更|加更|爆发|求票|求鲜花|各种求)[^）)]*[）)]",
    r"\s*[（(]\s*本章未完[^）)]*[）)]",
    r"\s*[\[【].*?(求收藏|求推荐|求月票|求订阅|求票|各种求)[^\]】]*[\]】]",
]

# Patterns specifically for novel/book titles (more aggressive)
NOVEL_TITLE_REMOVE = TITLE_REMOVE_PATTERNS + [
    r"\s*[-–—]\s*(免费|全文|全本|精校|无删减|无广告|txt下载|在线阅读).*$",
    r"\s*[（(][^）)]*?(免费|全文|全本|精校|txt|下载|完本|完结|首发|无广告|无删减)[^）)]*[）)]",
    r"\s*[\[【][^\]】]*?(免费|全文|全本|精校|txt|下载|完本|首发)[^\]】]*[\]】]",
    r"\s*[-–—]\s*.*?(小说|作品|著|书).*$",
    r"\s*作者[：:]\s*\S+",                     # trailing "作者：XXX"
]

# Patterns to NORMALIZE in titles (keep content, fix formatting)
TITLE_FIX_PATTERNS = [
    (r"\s+", " "),                     # collapse whitespace
    (r"&nbsp;", " "),                  # HTML entities
    (r"&lt;", "<"),
    (r"&gt;", ">"),
    (r"&amp;", "&"),
    (r"^\s+", ""),                     # leading whitespace
    (r"\s+$", ""),                     # trailing whitespace
]


def clean_title(title: str) -> str:
    """Clean a chapter title.

    Removes ad/noise suffixes, normalises whitespace, and strips
    garbage while preserving legitimate content like （上）（中）（下）.
    """
    if not title:
        return ""

    result = title.strip()

    # Remove known garbage patterns
    for pattern in TITLE_REMOVE_PATTERNS:
        result = re.sub(pattern, "", result).strip()

    # Apply formatting fixes
    for pattern, replacement in TITLE_FIX_PATTERNS:
        result = re.sub(pattern, replacement, result)

    return result.strip() or title.strip()


# ---------------------------------------------------------------------------
# Chapter title quality filter
# ---------------------------------------------------------------------------

# Chapter titles that are clearly garbage (error pages, navigation, ads)
CHAPTER_TITLE_BAD_EXACT = {
    "", "null", "undefined", "None", "错误", "Error",
    "出现错误", "404", "404 Not Found", "403 Forbidden", "500",
    "页面不存在", "找不到页面", "该页面不存在", "访问被拒绝",
    "请稍后重试", "系统繁忙", "服务不可用",
    # Navigation / UI labels that appear in chapter lists
    "加入书签", "推荐本书", "投推荐票", "手机阅读", "返回目录",
    "上一章", "下一章", "全部章节", "下载APP", "手机版",
    "电脑版", "客户端", "扫码阅读", "安装APP",
    "阅读进度", "书签", "目录", "回目录", "回書目",
    "正在加载", "加载中", "Loading", "请稍候",
    "查看更多", "展开全部", "收起", "点击加载更多",
    "确认", "取消", "关闭", "返回",
}

CHAPTER_TITLE_BAD_CONTAINS = [
    "出现错误", "错误页面", "404", "Not Found", "Forbidden",
    "502 Bad Gateway", "503 Service", "系统错误", "服务器内部错误",
    "淘宝", "天猫", "京东", "拼多多",  # shopping ads
    "成人", "色情", "赌博", "博彩",    # spam
    "www.", "http://", "https://",     # URLs
    "<script", "</script", "&lt;script",  # XSS/script artifacts
    "function(", "javascript:",        # JS artifacts
    "{{", "}}", "{%",                  # template artifacts
    # Navigation/common UI strings
    "加入书签", "推荐本书", "投推荐票", "手机阅读",
    "返回目录", "全部章节", "下载APP",
    "扫码阅读", "阅读进度", "点击加载",
]

CHAPTER_TITLE_BAD_PATTERNS = [
    # Pure numbers (too short to be chapter titles)
    r"^\d{1,3}$",
    # Repeated same character (e.g., "aaaaa", "......")
    r"^(.)\1{4,}$",
    # Titles that are entirely punctuation
    r"^[，。！？…、；：""''（）《》\[\]【】\-_,.!?:;\"'()\s]+$",
    # HTML entity noise
    r"^&[a-z]+;$",
    # Garbled text (high ratio of non-CJK, non-ASCII)
    r"^[^一-鿿぀-ゟ゠-ヿa-zA-Z0-9\s]{5,}$",
]


def is_valid_chapter_title(title: str) -> bool:
    """Return True if *title* looks like a legitimate chapter title."""
    if not title or not title.strip():
        return False

    cleaned = title.strip()

    # Too short or too long
    if len(cleaned) < 2:
        return False
    if len(cleaned) > 200:
        return False

    # Exact bad matches
    if cleaned in CHAPTER_TITLE_BAD_EXACT:
        return False

    lower = cleaned.lower()

    # Contains bad keywords
    for bad in CHAPTER_TITLE_BAD_CONTAINS:
        if bad.lower() in lower:
            return False

    # Matches bad patterns
    for pattern in CHAPTER_TITLE_BAD_PATTERNS:
        if re.match(pattern, cleaned):
            return False

    # Heuristic: at least one CJK character or common word character
    has_cjk = bool(re.search(r"[一-鿿]", cleaned))
    has_alpha = bool(re.search(r"[a-zA-Z]{3,}", cleaned))
    has_digit_chapter = bool(re.match(r"^第[零一二三四五六七八九十百千0-9]+[章节回卷]", cleaned))

    if not (has_cjk or has_alpha or has_digit_chapter):
        return False

    return True


def clean_chapter_title(title: str) -> str:
    """Clean and validate a chapter title. Returns '' if the title is garbage.

    This is the main entry point — call it on every crawled chapter title.
    """
    # Step 1: basic cleaning
    result = clean_title(title)

    # Step 2: strip HTML/XML tags
    result = re.sub(r"<[^>]*>", "", result)

    # Step 3: strip leading/trailing garbage chars
    result = result.strip("·…。.!！?？,，;；:：\"")

    # Step 4: validate quality
    if not is_valid_chapter_title(result):
        return ""

    return result


def clean_novel_title(title: str) -> str:
    """Clean a novel/book title — more aggressive than chapter title cleaning.

    Removes site watermarks, ad suffixes, author tags, and formatting
    garbage from book titles extracted from listing pages.
    """
    if not title:
        return ""

    result = title.strip()

    for pattern in NOVEL_TITLE_REMOVE:
        result = re.sub(pattern, "", result).strip()

    # Also apply generic title fixes
    for pattern, replacement in TITLE_FIX_PATTERNS:
        result = re.sub(pattern, replacement, result)

    return result.strip() or title.strip()


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample = """
第一章 测试

加入书签 推荐本书 手机阅读
真正的正文内容开始了，这里是小说正文。
铅笔小说 www.23qb.net 记住本站域名
（本章未完，请点击下一页继续阅读）
【全网首发】第二段正文继续。
。。。。。。。。。。。。。
F5刷新一下
"""
    result = clean_content(sample)
    print("Before:", repr(sample[:200]))
    print("After:", repr(result[:200]))
