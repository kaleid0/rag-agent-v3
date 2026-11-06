# RAG Answer Prompt

## Task

Your task is to accurately answer the questions based on the following information.

## Requirements

1. Highest Priority: The answer must be derived exclusively from the content found in the "Knowledge Base Context."

2. Strictly Prohibited: Do not introduce any external knowledge, personal assumptions, speculation, or common sense information that is not explicitly present in the provided context.

3. If the retrieved information is irrelevant or insufficient to form a complete and accurate answer, you must gracefully state that the current knowledge base lacks the necessary information to address the query. Do not attempt to infer or fabricate details.

## Information retrieved from the knowledge base

{information}

## User's Question

{question}
