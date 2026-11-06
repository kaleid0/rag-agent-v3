# Grade Texts Prompt

## Task

Evaluate how relevant each of the five provided texts is to a given query.

## Requirements

1. Carefully read the query and the five texts.

2. Assign a relevance score to each text based on how well it addresses the query.

3. Use the following 0-5 scale for scoring:
    - 0 - Completely irrelevant
    - 1 - Slightly relevant (mentions a related topic but does not address the query meaningfully)
    - 2 - Somewhat relevant (partially related, but lacks depth or specificity)
    - 3 - Moderately relevant (covers the topic in a general way, but not focused)
    - 4 - Highly relevant (directly related, with solid supporting information)
    - 5 - Very relevant and fully focused (directly answers or discusses the core of the query)

4. Return ONLY the scores in the following JSON format without any additional text or explanation:

```json
{{
  "text1": X,
  "text2": X,
  "text3": X,
  "text4": X,
  "text5": X
}}
```

## Query and Texts

- **Query**: {query}

**Text1**:

> {text1}

**Text2**:

> {text2}

**Text3**:

> {text3}

**Text4**:

> {text4}

**Text5**:

> {text5}
