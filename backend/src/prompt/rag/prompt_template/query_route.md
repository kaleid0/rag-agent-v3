# Query Route Prompt

## Instructions

Estimate how relevant each collection is to the question using its title and keywords. Give each collection an integer score from 0 (unrelated) to 5 (very relevant).

Return one JSON object. Include every supplied collection_id exactly once as a key and use the corresponding score as its value. Keep collection IDs unchanged and include scores of zero. Titles may repeat, so use the IDs to distinguish collections.

For two collections with IDs `collection-A` and `collection-B`, a valid response is

```json
{{"collection-A": 5, "collection-B": 0}}
```

## Collections

{collections}

## Question

{question}
