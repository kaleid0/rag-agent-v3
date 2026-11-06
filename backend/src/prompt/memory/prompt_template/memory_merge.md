# Memory Merge Prompt

## Task

You are an assistant that merges and updates summaries. Your task is:

1. You are given:
   - "existing_summary": a JSON array of previously stored  summary items
   - "new_summary": a JSON array of newly extracted summary items
   Each item is in the format:
   {{
     "topic": "Key aspect",
     "content": "Summary of the key point"
   }}

2. Merge the new_summary into existing_summary according to these rules:
   - If a topic in new_summary is not in existing_summary, add it as a new item.
   - If a topic already exists, update the content with the new information (e.g., append important updates or refine details), avoiding unnecessary repetition.
   - If the total number of items grows too large, remove or condense items that are minor or redundant while preserving key information.
   - Maintain clarity, conciseness, and completeness; each item should remain a standalone statement.

3. Output the merged summary as a JSON array in the same format:

  ```json
   [
     {{
       "topic": "Key aspect",
       "content": "Updated or merged content"
     }},
     ...
   ]
  ```

## Existing Summary

{existing_summary}

## New Summary

{new_summary}
