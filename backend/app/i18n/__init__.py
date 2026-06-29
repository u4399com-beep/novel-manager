"""i18n translation helper — loads JSON translation files and provides a Jinja2 global."""
import json
import os
from typing import Optional

I18N_DIR = os.path.dirname(os.path.abspath(__file__))
_cache: dict[str, dict] = {}
LANGUAGES = {
    "zh": "中文", "en": "English", "ja": "日本語", "ko": "한국어",
    "fr": "Français", "de": "Deutsch", "es": "Español", "pt": "Português",
    "ru": "Русский", "ar": "العربية", "th": "ภาษาไทย", "vi": "Tiếng Việt",
    "id": "Bahasa Indonesia", "it": "Italiano", "tr": "Türkçe",
    "hi": "हिन्दी", "fa": "فارسی",
    "cs": "Čeština", "da": "Dansk", "nl": "Nederlands", "fi": "Suomi",
    "el": "Ελληνικά", "he": "עברית", "hu": "Magyar", "ga": "Gaeilge",
    "pl": "Polski", "sk": "Slovenčina", "sv": "Svenska",
    "uk": "Українська", "az": "Azərbaycan",
}


def load_translations(lang: str) -> dict:
    """Load translation dict for *lang*, falling back to Chinese."""
    # Validate: only allow known language codes (prevents path traversal)
    if lang not in LANGUAGES and lang not in ("zh-TW",):
        lang = "zh"

    if lang in _cache:
        return _cache[lang]

    path = os.path.join(I18N_DIR, f"{lang}.json")
    if not os.path.isfile(path):
        path = os.path.join(I18N_DIR, "zh.json")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        with open(os.path.join(I18N_DIR, "zh.json"), "r", encoding="utf-8") as f:
            data = json.load(f)

    # Merge with zh as base (fill missing keys)
    if lang != "zh":
        zh_path = os.path.join(I18N_DIR, "zh.json")
        with open(zh_path, "r", encoding="utf-8") as f:
            zh_data = json.load(f)
        for k, v in zh_data.items():
            if k not in data:
                data[k] = v

    _cache[lang] = data
    return data


def t(lang: str, key: str, **kwargs) -> str:
    """Translate *key* to *lang*, with optional format kwargs."""
    data = load_translations(lang)
    text = data.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def get_language_list() -> list[dict]:
    """Return list of {code, name} for UI language selector."""
    return [{"code": k, "name": v} for k, v in LANGUAGES.items()]
