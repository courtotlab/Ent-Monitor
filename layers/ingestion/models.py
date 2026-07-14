from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NormalizedPost:
  post_id: str
  platform: str
  source: str
  creator_id: str
  caption_text: str
  transcript_text: Optional[str] = None
  hashtags: Optional[List[str]] = None
  posted_at: Optional[str] = None
  collected_at: Optional[str] = None
  engagement: Dict[str, Any] = field(default_factory=dict)
  metadata: Dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> Dict[str, Any]:
    return asdict(self)

