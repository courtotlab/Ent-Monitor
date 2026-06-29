from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any

@dataclass
class NormalizedPost:
    post_id: str
    platform: str
    source: str
    context: str
    creator_id: str
    caption_text: str
    ocr_text: Optional[str] = None
    transcript_text: Optional[str] = None
    hashtags: Optional[List[str]] = None
    posted_at: Optional[str] = None
    collected_at: Optional[str] = None
    engagement: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
