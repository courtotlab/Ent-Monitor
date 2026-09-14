# Preprocessing Database Interactions

- **Location:** [layers/preprocess/queries.py](../../../../layers/preprocess/queries.py)
- **Component Overview:** [Preprocessing Component Overview](overview.md)
- **Authoritative Schema:** For complete table schemas, constraints, and pgvector types for `posts` and `sbert_anchors`, see [Database Schema Reference](../../../database/schema.md).

---

## 1. Fetching Data

### Read: Fetch unprocessed posts
Selects all posts that haven't been scored by SBERT yet.
```sql
SELECT post_id, platform, caption_text, transcript_text, source
FROM posts
WHERE sbert_score IS NULL
```

### Read: Fetch active anchors
Selects the embedding vectors for all active semantic anchors to evaluate relevance.
```sql
SELECT anchor_id, anchor_text, embedding
FROM sbert_anchors
WHERE active = TRUE
```

## 2. Writing Results

### Write: Update post scores (Batch)
Updates the posts table with the calculated SBERT score and the corresponding best anchor match.
```sql
UPDATE posts
SET sbert_score = $score,
    matched_anchor_id = $anchor_id
WHERE post_id = $post_id AND platform = $platform
```

### Write: Increment anchor match counts
Tracks the lifetime number of posts matched against specific anchors.
```sql
UPDATE sbert_anchors
SET match_count = match_count + $increment
WHERE anchor_id = $anchor_id
```
