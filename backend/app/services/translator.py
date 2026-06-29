"""Content translation service with database caching and Google Translate backend."""
import hashlib
import asyncio
import logging
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from deep_translator import GoogleTranslator
from app.models.translation_cache import TranslationCache

log = logging.getLogger("translator")

# Language mapping: site lang code → Google Translator code
LANG_MAP = {
    "zh": "zh-CN", "en": "en", "ja": "ja", "ko": "ko",
    "fr": "fr", "de": "de", "es": "es", "pt": "pt",
    "ru": "ru", "ar": "ar", "th": "th", "vi": "vi",
    "id": "id", "it": "it", "tr": "tr", "hi": "hi",
    "ms": "ms", "tl": "tl", "sw": "sw", "fa": "fa",
    "ur": "ur", "bn": "bn", "my": "my",
}

# Maximum text length per translation chunk (Google Translate limits)
CHUNK_SIZE = 4000

# Sentences that should NOT be translated (numbers, code, etc.)
SKIP_PATTERN = re.compile(r"^[\d\s\.\,\-\+\=\:\;\/\\\[\]\{\}\(\)\@\#\$\%\^\&\*\_\~]+$")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def translate_text(
    db: AsyncSession,
    text: str,
    target_lang: str,
    source_lang: str = "zh",
) -> str:
    """Translate *text* to *target_lang*, using cache if available.

    Returns the original text if translation fails or target_lang is Chinese.
    """
    if not text or not text.strip():
        return text

    # No translation needed for Chinese → Chinese
    if target_lang == "zh" or target_lang == "zh-CN":
        return text

    # Skip pure numbers/symbols
    if SKIP_PATTERN.match(text.strip()):
        return text

    # Only translate texts with CJK content from Chinese
    has_cjk = bool(re.search(r"[一-鿿]", text))
    if not has_cjk and source_lang == "zh":
        return text  # Already non-Chinese, skip

    text_hash = _hash(text)
    google_code = LANG_MAP.get(target_lang, target_lang)

    # Check cache
    result = await db.execute(
        select(TranslationCache).where(
            TranslationCache.source_hash == text_hash,
            TranslationCache.target_lang == target_lang,
        )
    )
    cached = result.scalars().first()
    if cached:
        return cached.translated_text

    # Translate in chunks for long text
    try:
        if len(text) > CHUNK_SIZE:
            # Split by paragraphs
            paragraphs = text.split("\n")
            chunks = []
            current = ""
            for p in paragraphs:
                if len(current) + len(p) < CHUNK_SIZE:
                    current += ("\n" if current else "") + p
                else:
                    if current:
                        chunks.append(current)
                    current = p
            if current:
                chunks.append(current)

            translated_chunks = []
            for chunk in chunks:
                translated = await asyncio.to_thread(GoogleTranslator(source="auto", target=google_code).translate, chunk)
                translated_chunks.append(translated)

            translated_text = "\n".join(translated_chunks)
        else:
            translated_text = await asyncio.to_thread(GoogleTranslator(source="auto", target=google_code).translate, text)

        if not translated_text:
            return text

        # Cache the result
        cache_entry = TranslationCache(
            source_hash=text_hash,
            source_lang=source_lang,
            target_lang=target_lang,
            source_text=text[:500],  # truncate for storage
            translated_text=translated_text,
        )
        db.add(cache_entry)
        await db.flush()

        return translated_text

    except Exception as e:
        log.warning(f"Translation failed ({source_lang}→{target_lang}): {e}")
        return text


async def translate_batch(
    db: AsyncSession,
    texts: list[str],
    target_lang: str,
    source_lang: str = "zh",
) -> list[str]:
    """Translate multiple texts concurrently."""
    if target_lang == "zh":
        return texts

    tasks = [translate_text(db, t, target_lang, source_lang) for t in texts]
    return await asyncio.gather(*tasks)


# ---------------------------------------------------------------------------
# Jinja2 filter function (synchronous wrapper — uses a simple in-memory cache)
# ---------------------------------------------------------------------------

