"""Universal Real-World VQA Question Categorization, Intent-Tailored Prompting, and Normalization."""

from __future__ import annotations

import json
import re
from typing import Any

MAX_VQA_ANSWER_LENGTH = 100

# ── 1. Comprehensive Multi-Lingual Intent Pattern Definitions ───────────────────

# Action & Activity
ACTION_PATTERNS = [
    r"\bdoing\b",
    r"\baction\b",
    r"\bactivity\b",
    r"\bhappening\b",
    r"\bperforming\b",
    r"\bgesture\b",
    r"\bbehavior\b",
    r"\bmovement\b",
    r"\bmotion\b",
    r"\bholding\b",
    r"\bwearing\b",
    r"\bplaying\b",
    r"\bworking\b",
    r"\blàm gì\b",
    r"\bhành động\b",
    r"\bhoạt động\b",
    r"\bdiễn ra\b",
    r"\bđang làm\b",
]

# Choice / Alternative (X or Y / X hay Y)
CHOICE_PATTERNS = [
    r"\b\w+\s+or\s+\w+\b",
    r"\b\w+\s+hay\s+\w+\b",
    r"\b\w+\s+hay là\s+\w+\b",
]

# Text Reading / OCR / Signage
OCR_PATTERNS = [
    r"\b(?:what|which)\s+(?:text|word|words|letter|letters|number|numbers|digit|digits|characters?)\b",
    r"\b(?:written|printed|inscribed|displayed|shown)\s+on\b",
    r"\b(?:say|read|reads|spell|spells)\b",
    r"\b(?:sign|billboard|banner|screen|shirt|plate|license plate|license|logo|title|headline|caption)\b",
    r"\bchữ\b",
    r"\bviết gì\b",
    r"\bbiển số\b",
    r"\btiêu đề\b",
    r"\bđọc được gì\b",
]

# Time of Day & Weather / Environment
ENVIRONMENT_PATTERNS = [
    r"\b(?:time of day|day or night|daytime|nighttime|season)\b",
    r"\b(?:weather|temperature|climate|sunny|rainy|snowy|cloudy|foggy)\b",
    r"\b(?:lighting|indoor or outdoor|inside or outside)\b",
    r"\bthời tiết\b",
    r"\bban ngày\b",
    r"\bban đêm\b",
    r"\btrong nhà hay ngoài trời\b",
    r"\bmùa gì\b",
]

# Emotion & Facial Expression
EMOTION_PATTERNS = [
    r"\b(?:emotion|feeling|mood|facial expression|expression|sentiment)\b",
    r"\b(?:happy|sad|angry|smiling|crying|laughing|surprised|serious|bored)\b",
    r"\bcảm xúc\b",
    r"\bbiểu cảm\b",
    r"\bvui hay buồn\b",
    r"\btâm trạng\b",
]

# Role / Profession / Identity
ROLE_PATTERNS = [
    r"\b(?:profession|job|occupation|role|career|title|identity)\b",
    r"\b(?:doctor|nurse|police|officer|chef|cook|driver|teacher|student|anchor|presenter|journalist|host|athlete|singer|actor)\b",
    r"\bnghề nghiệp\b",
    r"\bvai trò\b",
    r"\bngười này làm nghề gì\b",
    r"\blà ai\b",
]

# Material & Composition
MATERIAL_PATTERNS = [
    r"\b(?:material|made of|composed of|texture|substance)\b",
    r"\b(?:wood|wooden|metal|metallic|glass|plastic|leather|fabric|cotton|paper|concrete|stone|gold|silver|ceramic)\b",
    r"\bchất liệu\b",
    r"\blàm bằng gì\b",
    r"\bvật liệu\b",
]

# Object State & Condition
STATE_PATTERNS = [
    r"\b(?:open or closed|on or off|turned on|turned off|empty or full|broken|intact)\b",
    r"\b(?:state of|condition of|status of)\b",
    r"\bmở hay đóng\b",
    r"\bbật hay tắt\b",
    r"\bđầy hay vơi\b",
    r"\bhỏng hay còn dùng được\b",
]

# Spatial Position & Direction
SPATIAL_PATTERNS = [
    r"\b(?:which side|left or right|top or bottom|above or under|in front or behind|foreground or background|relative position)\b",
    r"\bphía nào\b",
    r"\bbên trái hay bên phải\b",
    r"\bở trên hay ở dưới\b",
    r"\bphía trước hay phía sau\b",
]


# ── 2. Intent Detection Helper Functions ─────────────────────────────────────────

def is_action_question(question: str) -> bool:
    q_lower = question.lower()
    return any(re.search(pat, q_lower) for pat in ACTION_PATTERNS)


def is_choice_question(question: str) -> bool:
    q_lower = question.lower()
    return any(re.search(pat, q_lower) for pat in CHOICE_PATTERNS)


def is_ocr_question(question: str) -> bool:
    q_lower = question.lower()
    return any(re.search(pat, q_lower) for pat in OCR_PATTERNS)


def is_environment_question(question: str) -> bool:
    q_lower = question.lower()
    return any(re.search(pat, q_lower) for pat in ENVIRONMENT_PATTERNS)


def is_emotion_question(question: str) -> bool:
    q_lower = question.lower()
    return any(re.search(pat, q_lower) for pat in EMOTION_PATTERNS)


def is_role_question(question: str) -> bool:
    q_lower = question.lower()
    return any(re.search(pat, q_lower) for pat in ROLE_PATTERNS)


def is_material_question(question: str) -> bool:
    q_lower = question.lower()
    return any(re.search(pat, q_lower) for pat in MATERIAL_PATTERNS)


def is_state_question(question: str) -> bool:
    q_lower = question.lower()
    return any(re.search(pat, q_lower) for pat in STATE_PATTERNS)


def is_spatial_question(question: str) -> bool:
    q_lower = question.lower()
    return any(re.search(pat, q_lower) for pat in SPATIAL_PATTERNS)


# ── 3. High-Accuracy VQA Prompt Builder ─────────────────────────────────────────

def build_vqa_prompt(question: str, ocr_context: str = "") -> str:
    """Build optimized VQA prompt tailored specifically to the real-world question intent."""
    clean_q = question.strip()
    q_lower = clean_q.lower()
    words = re.findall(r"\b\w+\b", q_lower)
    first_word = words[0] if words else ""
    
    context = f"\nHint (Extracted OCR Text): {ocr_context}\n" if ocr_context else " "

    # 1. Count / Quantity
    if any(phrase in q_lower for phrase in ["how many", "number of", "count", "quantity", "bao nhiêu", "mấy", "số lượng"]):
        return (
            "Answer using only the image. Count the requested objects accurately. "
            "Return JSON only in this exact shape: "
            '{"answer": "<number> or \"0\" if none"}. '
            "Be precise - return only the integer count as a string (e.g. '1', '2', '0'). "
            f"Question: {clean_q}{context}"
        )

    # 2. Text Reading / OCR / Signage
    if is_ocr_question(clean_q):
        return (
            "Answer using only the image. Read and transcribe the exact text, words, digits, or characters visible. "
            "Return JSON only in this exact shape: "
            '{"answer": "<exact transcribed text or words>"}. '
            "Preserve original case and spelling as shown in the image. "
            f"Question: {clean_q}{context}"
        )

    # 3. Choice / Alternative (e.g. "Is he cooking or cleaning?", "red or blue?")
    if is_choice_question(clean_q):
        return (
            "Answer using only the image. Choose the single most accurate option from the choices given in the question. "
            "Return JSON only in this exact shape: "
            '{"answer": "<chosen option or accurate phrase>"}. '
            "Do NOT answer with yes/no. Directly state the correct choice. "
            f"Question: {clean_q}{context}"
        )

    # 4. Action / Activity / Verbs
    if is_action_question(clean_q):
        return (
            "Answer using only the image. Identify the primary ACTION or ACTIVITY being performed. "
            "Describe the action using an active verb phrase in present continuous tense "
            "(e.g. 'chopping vegetables', 'stirring soup in pan', 'riding bicycle', 'walking down stairs', "
            "'speaking to audience', 'driving car', 'washing dishes', 'pouring water', 'reading book'). "
            "Do NOT answer with static nouns alone — focus specifically on the action/verb. "
            "Return JSON only in this exact shape: "
            '{"answer": "<active verb phrase>"}. '
            f"Question: {clean_q}{context}"
        )

    # 5. Emotion & Facial Expression
    if is_emotion_question(clean_q):
        return (
            "Answer using only the image. Identify the facial expression or emotional state of the subject accurately. "
            "Return JSON only in this exact shape: "
            '{"answer": "<emotion name, e.g. smiling, serious, happy, angry, surprised, neutral>"}. '
            f"Question: {clean_q}{context}"
        )

    # 6. Role / Profession / Identity
    if is_role_question(clean_q):
        return (
            "Answer using only the image. Identify the specific profession, role, or occupation of the person. "
            "Return JSON only in this exact shape: "
            '{"answer": "<concise job title or role, e.g. news anchor, chef, police officer, athlete, doctor, driver>"}. '
            f"Question: {clean_q}{context}"
        )

    # 7. Material & Composition
    if is_material_question(clean_q):
        return (
            "Answer using only the image. Identify the primary material or composition of the object. "
            "Return JSON only in this exact shape: "
            '{"answer": "<material name, e.g. wood, metal, glass, plastic, leather, ceramic, concrete>"}. '
            f"Question: {clean_q}{context}"
        )

    # 8. Object State & Status
    if is_state_question(clean_q):
        return (
            "Answer using only the image. Identify the current operational or physical state/condition of the object. "
            "Return JSON only in this exact shape: "
            '{"answer": "<concise state, e.g. open, closed, turned on, turned off, empty, full, broken>"}. '
            f"Question: {clean_q}{context}"
        )

    # 9. Spatial Position & Direction
    if is_spatial_question(clean_q):
        return (
            "Answer using only the image. Identify the relative spatial location or direction accurately. "
            "Return JSON only in this exact shape: "
            '{"answer": "<spatial position, e.g. on the left, on the right, in the center, in foreground, in background, under the table>"}. '
            f"Question: {clean_q}{context}"
        )

    # 10. Time of Day & Weather / Lighting
    if is_environment_question(clean_q):
        return (
            "Answer using only the image. Identify the time of day, lighting, weather, or environmental setting. "
            "Return JSON only in this exact shape: "
            '{"answer": "<descriptor, e.g. daytime, night, sunset, sunny, rainy, cloudy, indoor, outdoor>"}. '
            f"Question: {clean_q}{context}"
        )

    # 11. Color
    if any(phrase in q_lower for phrase in ["what color", "which color", "color of", "colour", "màu gì", "màu sắc"]):
        return (
            "Answer using only the image. Identify the primary color accurately. "
            "Return JSON only in this exact shape: "
            '{"answer": "<color name>"}. '
            "Use standard color names (e.g. red, blue, green, white, black, silver, yellow, orange, gray, purple). "
            f"Question: {clean_q}{context}"
        )

    # 12. Location / Setting / Place
    if first_word in ("where",) or any(phrase in q_lower for phrase in ["where is", "located at", "what place", "ở đâu", "nơi nào", "địa điểm"]):
        return (
            "Answer using only the image. Describe the specific location or setting concisely. "
            "Return JSON only in this exact shape: "
            '{"answer": "<location description>"}. '
            "Keep it brief (under 50 characters, e.g., 'in modern kitchen', 'on city highway', 'in TV studio', 'in supermarket'). "
            f"Question: {clean_q}{context}"
        )

    # 13. Object / Entity / Text / Name (What, Which, Who, Name)
    if first_word in ("what", "which", "who", "whom", "whose", "name", "cái", "ai", "vật"):
        return (
            "Answer using only the image. Identify the specific object(s), person, text, or entity accurately. "
            "Return JSON only in this exact shape: "
            '{"answer": "<concise answer naming the object, entity, or item>"}. '
            "Do NOT answer with yes/no. Give the specific item name (e.g., 'laptop and cup', 'strawberries', 'microphone', 'police car'). "
            f"Question: {clean_q}{context}"
        )

    # 14. Polar Yes/No Verification (strictly auxiliary verbs, no 'or')
    if first_word in ("is", "are", "do", "does", "did", "can", "could", "will", "would", "has", "have", "had", "was", "were"):
        return (
            "Answer using only the image. Provide a yes or no answer. "
            "Return JSON only in this exact shape: "
            '{"answer": "yes" or "no"}. '
            "Answer strictly 'yes' or 'no' based on the image. "
            f"Question: {clean_q}{context}"
        )

    # 15. General fallback
    return (
        "Answer using only the image. Provide a concise, accurate answer naming the specific item or action. "
        "Return JSON only in this exact shape: "
        '{"answer": "<short answer>"}. '
        "Keep the answer short and suitable for CSV export (max 100 characters). "
        f"Question: {clean_q}{context}"
    )


# ── 4. Answer Extraction & Normalization ─────────────────────────────────────────

def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    return cleaned.strip()


def _extract_answer_from_json(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("answer", "response", "text", "result"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                extracted = _extract_answer_from_json(value)
                if extracted:
                    return extracted
        return None

    if isinstance(payload, list):
        for item in payload:
            extracted = _extract_answer_from_json(item)
            if extracted:
                return extracted
    return None


def clean_action_answer(answer: str) -> str:
    """Strip unnecessary filler boilerplate from VLM output to leave crisp answers."""
    cleaned = answer.strip().rstrip(".").strip()
    # Strip common sentence starter boilerplate
    boilerplate_patterns = [
        r"^(?:the\s+)?(?:person|man|woman|child|chef|worker|subject|people|camera)\s+(?:is\s+|are\s+|appears\s+to\s+be\s+)",
        r"^(?:he|she|they|it)\s+(?:is\s+|are\s+|seems\s+to\s+be\s+)",
        r"^(?:there\s+is\s+|there\s+are\s+)",
        r"^(?:the\s+image\s+shows\s+|this\s+shows\s+|i\s+can\s+see\s+)",
    ]
    for pat in boilerplate_patterns:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def parse_vqa_answer(raw_text: str, *, max_length: int = MAX_VQA_ANSWER_LENGTH) -> str:
    """Parse provider output as JSON when possible, clean boilerplate, and normalize."""
    text = _strip_code_fence(raw_text)
    if not text:
        return ""

    try:
        payload = json.loads(text)
        extracted = _extract_answer_from_json(payload)
        if extracted:
            text = extracted
    except json.JSONDecodeError:
        pass

    text = clean_action_answer(text)
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[:max_length].rstrip()
