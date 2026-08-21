import hashlib


def hash_cache_component(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_embedding_cache_key(*, scope: str, text: str) -> str:
    return f"{hash_cache_component(scope)}:{hash_cache_component(text)}"


def build_translation_cache_key(
    *,
    source_language: str,
    target_language: str,
    text: str,
) -> str:
    scope = f"{source_language}:{target_language}"
    return f"{hash_cache_component(scope)}:{hash_cache_component(text)}"


def build_vlm_cache_key(
    *,
    scope: str,
    video_id: str,
    keyframe_id: int,
    question: str,
) -> str:
    payload = f"{video_id.strip()}:{int(keyframe_id)}:{question.strip()}"
    return f"{hash_cache_component(scope)}:{hash_cache_component(payload)}"
