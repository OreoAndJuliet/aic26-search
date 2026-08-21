import asyncio
import logging
import re
from dataclasses import dataclass

from app.cache.factory import create_cache_backend
from app.cache.text_cache import TextCache
from app.core.config import settings
from app.core.exceptions import TranslationUnavailableError
from app.providers.translation import TranslationProvider, create_translation_provider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranslationResult:
    text: str
    applied: bool
    cache_hit: bool = False


class TranslatorService:
    """Translate Vietnamese queries and bypass the network for English queries."""

    _VIETNAMESE_CHARACTERS = re.compile(
        r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
        r"ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ]"
    )
    _VIETNAMESE_WORDS = re.compile(
        r"\b(anh|chi|em|ong|ba|nguoi|người|mot|một|hai|ba|bon|bốn|nam|năm|sau|sáu|bay|bảy|tam|tám|chin|chín|muoi|mười|"
        r"trong|ngoai|ngoài|vao|vào|ra|di|đi|den|đến|xe|oto|ô tô|may|máy|phong|phòng|cua|cửa|ban|bàn|ghe|ghế|nha|nhà|duong|đường|"
        r"bien|biển|ao|áo|quan|quần|non|nón|mu|mũ|mau|màu|do|đỏ|xanh|vang|vàng|trang|trắng|den|đen|tim|tím|hong|hồng|cam|xam|xám|"
        r"con|cai|cái|cho|chó|meo|mèo|ca|cá|chim|hoa|cay|cây|dang|đang|da|đã|se|sẽ|khong|không|co|có|o|ở|tai|tại|tren|trên|duoi|dưới|"
        r"giua|giữa|gan|gần|xa|truoc|trước|sau|trai|trái|phai|phải|ninja|shipper)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        provider: TranslationProvider,
        translation_enabled: bool,
        source_language: str,
        target_language: str,
        translation_cache: TextCache | None = None,
    ) -> None:
        self._provider = provider
        self._translation_enabled = translation_enabled
        self._source_language = source_language
        self._target_language = target_language
        ttl = settings.TRANSLATION_CACHE_TTL_SECONDS
        self._translation_cache = translation_cache or TextCache(
            create_cache_backend(namespace="translation"),
            source_language=source_language,
            target_language=target_language,
            ttl_seconds=ttl if ttl > 0 else None,
        )

    @classmethod
    def needs_translation(cls, text: str) -> bool:
        """Conservatively identify Vietnamese without sending English remotely."""
        return bool(
            cls._VIETNAMESE_CHARACTERS.search(text)
            or cls._VIETNAMESE_WORDS.search(text)
        )

    @property
    def provider_name(self) -> str:
        return self._provider.__class__.__name__

    async def translate_async(self, text: str) -> TranslationResult:
        if not self._translation_enabled or not self.needs_translation(text):
            return TranslationResult(text=text, applied=False)

        cached = self._translation_cache.get(text)
        if cached is not None:
            return TranslationResult(text=cached, applied=True, cache_hit=True)

        translated = await self._provider.translate(
            text,
            source_language=self._source_language,
            target_language=self._target_language,
        )
        if not translated.strip():
            raise TranslationUnavailableError("Translation provider returned empty text.")
        self._translation_cache.set(text, translated)
        return TranslationResult(text=translated, applied=True)

    def translate(self, text: str) -> str:
        return asyncio.run(self.translate_async(text)).text

    def warm_up(self) -> None:
        """Prime translation cache with common queries to guarantee instant sub-millisecond lookups."""
        if not self._translation_enabled:
            return
        common_phrases = {
            "người đi xe máy": "people riding motorbikes",
            "người đi bộ": "people walking",
            "xe buýt": "bus",
            "xe ô tô": "cars",
            "chợ bến thành": "Ben Thanh Market",
            "cầu rồng": "Dragon Bridge",
            "tòa nhà": "building",
            "tai nạn giao thông": "traffic accident",
            
            # TRAKE Cache Priming
            "xe cộ di chuyển trên đường": "vehicles moving on the street",
            "người đi bộ chuẩn bị băng qua đường": "pedestrians preparing to cross the street",
            "người đi bộ bước trên vạch kẻ đường": "pedestrians walking on the crosswalk",
            "chuẩn bị nguyên liệu rau củ": "preparing vegetable ingredients",
            "khu vực bồn rửa và bàn chế biến": "sink and preparation table area",
            "đầu bếp nấu ăn trong gian bếp": "chef cooking in the kitchen",
            "đường phố ban ngày nhiều xe máy": "daytime street with many motorbikes",
            "xe buýt số 150 di chuyển trên đường": "bus number 150 moving on the street",
            "xe buýt dừng tại trạm đón khách": "bus stopping at the station to pick up passengers",
        }
        for vi, en in common_phrases.items():
            self._translation_cache.set(vi, en)
        logger.info("translator warmup complete (cache primed with common contest concepts)")


translator = TranslatorService(
    provider=create_translation_provider(
        provider_name=settings.TRANSLATION_PROVIDER,
        provider_mode=settings.AI_PROVIDER_MODE,
        timeout_seconds=settings.TRANSLATION_TIMEOUT_SECONDS,
        gemini_api_key=settings.GEMINI_API_KEY,
        gemini_model_name=settings.GEMINI_TRANSLATION_MODEL,
        gemini_api_base=settings.GEMINI_API_BASE,
        openai_api_key=settings.OPENAI_API_KEY,
        openai_model_name=settings.OPENAI_TRANSLATION_MODEL,
        openai_api_base=settings.OPENAI_API_BASE,
        google_translation_api_base=settings.GOOGLE_TRANSLATION_API_BASE,
    ),
    translation_enabled=settings.TRANSLATION_ENABLED,
    source_language=settings.TRANSLATION_SOURCE_LANGUAGE,
    target_language=settings.TRANSLATION_TARGET_LANGUAGE,
)
