"""Content translation with DB caching + LibreTranslate backend."""
import hashlib, logging, re
from typing import Optional
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.translation_cache import TranslationCache

log = logging.getLogger("translator")
from app.config import settings
LIBRETRANSLATE_URL = settings.LIBRETRANSLATE_URL
CHUNK_SIZE = 4000
SKIP_PATTERN = re.compile(r"^[\d\s\.\,\-\+\=\:\;\/\\\[\]\{\}\(\)\@\#\$\%\^\&\*\_\~]+$")
LANG_MAP = {
    "en":"en","ar":"ar","zh":"zh","cs":"cs","da":"da","nl":"nl",
    "fi":"fi","fr":"fr","de":"de","el":"el","he":"he","hi":"hi",
    "hu":"hu","id":"id","ga":"ga","it":"it","ja":"ja","ko":"ko",
    "fa":"fa","pl":"pl","pt":"pt","ru":"ru","sk":"sk","es":"es",
    "sv":"sv","th":"th","tr":"tr","uk":"uk","vi":"vi",
}

def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

async def translate_text(db: AsyncSession, text: str, target_lang: str, source_lang: str = "zh") -> str:
    if not text or not text.strip() or target_lang in ("zh", "zh-CN"):
        return text
    if SKIP_PATTERN.match(text.strip()):
        return text
    has_cjk = bool(re.search(r"[一-鿿]", text))
    if not has_cjk and source_lang == "zh":
        return text

    text_hash = _hash(text)
    target_code = LANG_MAP.get(target_lang, target_lang)

    result = await db.execute(select(TranslationCache).where(
        TranslationCache.source_hash == text_hash,
        TranslationCache.target_lang == target_lang))
    cached = result.scalars().first()
    if cached:
        return cached.translated_text

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(LIBRETRANSLATE_URL, json={
                "q": text[:CHUNK_SIZE], "source": "auto",
                "target": target_code, "format": "text"})
            if resp.status_code != 200:
                return text
            translated = resp.json()["translatedText"]
        if not translated:
            return text
        db.add(TranslationCache(source_hash=text_hash, source_lang=source_lang,
            target_lang=target_lang, source_text=text[:500], translated_text=translated))
        await db.flush()
        return translated
    except Exception as e:
        log.warning("Translation failed: %s", e)
        return text

async def translate_batch(db: AsyncSession, texts: list[str], target_lang: str, source_lang: str = "zh") -> list[str]:
    if target_lang == "zh":
        return texts
    # Serialize to avoid concurrent session mutation (AsyncSession is not thread-safe)
    results = []
    for t in texts:
        results.append(await translate_text(db, t, target_lang, source_lang))
    return results
