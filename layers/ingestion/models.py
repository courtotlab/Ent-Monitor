from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class NormalizedPost:
  post_id: str
  platform: str
  source: str
  creator_id: str
  caption_text: str
  transcript_text: str | None = None
  hashtags: list[str] | None = None
  posted_at: str | None = None
  collected_at: str | None = None
  engagement: dict[str, Any] = field(default_factory=dict)
  metadata: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    return asdict(self)

