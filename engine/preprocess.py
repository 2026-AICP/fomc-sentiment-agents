"""문장 분할. 작년 preprocess.py의 약어·소수점 오분할 방지 로직을 차용·정리."""
import re
from typing import List

ABBREVIATIONS = [
    "U.S.", "Mr.", "Mrs.", "Ms.", "Dr.", "St.", "No.", "Inc.", "Ltd.",
    "Jr.", "Sr.", "Co.", "vs.", "e.g.", "i.e.",
    "Jan.", "Feb.", "Mar.", "Apr.", "Jun.", "Jul.", "Aug.", "Sep.",
    "Sept.", "Oct.", "Nov.", "Dec.",
]


def _normalize_and_protect(text: str) -> str:
    """문장부호로 오인될 마침표를 임시로 §로 치환해 보호."""
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(?<=\d)\.(?=\d)", "§", text)          # 1.5 → 1§5
    for abbr in ABBREVIATIONS:
        text = text.replace(abbr, abbr.replace(".", "§"))  # U.S. → U§S§
    text = re.sub(r"\b([A-Z])\.(?=\s+[A-Z])", r"\1§", text)  # J. Powell
    return text


def split_sentences(text: str) -> List[str]:
    """텍스트 → 문장 리스트. 보호한 §는 마침표로 복원."""
    p = _normalize_and_protect(text)
    parts = re.split(r"(?<!§)([.!?])\s+", p)
    sents: List[str] = []
    i = 0
    while i < len(parts) - 1:
        sent = (parts[i] + parts[i + 1]).replace("§", ".").strip(" \t\n\"'")
        if sent:
            sents.append(sent)
        i += 2
    if i < len(parts):
        tail = parts[i].replace("§", ".").strip(" \t\n\"'")
        if tail:
            sents.append(tail)
    return sents
