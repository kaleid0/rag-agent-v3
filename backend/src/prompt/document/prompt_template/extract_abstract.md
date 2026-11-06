# Extract Abstract Prompt

## Instructions

1. Locate the abstract (summary) section in the given text.
2. Extract the abstract content.
3. Generate a list of keywords from the abstract.
4. Output the result strictly in the following json format:

```json
{{
    "abstract": "..."
    "keywords": ["keywords1", "keywords2", ...]
}}
```

5. If no abstract or summary exists, output:

```json
"false"
```

## Text

{text}
