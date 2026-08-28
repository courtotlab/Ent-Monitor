from dataclasses import asdict, dataclass, field
from typing import TypedDict

class EngagementDict(TypedDict, total=False):
  likes: int | None
  comments: int | None
  shares: int | None
  views: int | None

class RawPostDict(TypedDict, total=False):
  post_id: str
  platform: str
  source: str
  creator_id: str | None
  caption_text: str | None
  transcript_text: str | None
  hashtags: list[str] | None
  posted_at: str | None
  collected_at: str | None
  engagement: EngagementDict
  metadata: dict[str, object]


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
  engagement: dict[str, object] = field(default_factory=dict)
  metadata: dict[str, object] = field(default_factory=dict)

  def to_dict(self) -> RawPostDict:
    return asdict(self)
