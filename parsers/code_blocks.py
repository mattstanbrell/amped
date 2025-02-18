"""Functions for handling code blocks in markdown/MDX content."""

import re
from typing import List, Tuple

def split_content_and_code_blocks(content: str) -> List[Tuple[str, bool]]:
    """Split content into alternating non-code and code blocks.
    
    Args:
        content: The markdown/MDX content to split
        
    Returns:
        A list of tuples where each tuple contains:
        - The content section (str)
        - A boolean indicating if it's a code block (True) or not (False)
        
    Example:
        >>> content = "Some text\\n```python\\nprint('hello')\\n```\\nMore text"
        >>> result = split_content_and_code_blocks(content)
        >>> len(result)
        3
        >>> result[0] == ("Some text\\n", False)
        True
        >>> result[1] == ("```python\\nprint('hello')\\n```", True)
        True
        >>> result[2] == ("\\nMore text", False)
        True
    """
    parts = []
    current_pos = 0
    
    # Match code blocks that may have an optional language specifier
    # e.g. ```python, ```ts, ```json, or just ```
    code_block_pattern = re.compile(
        r'(```(?:[a-zA-Z]+\s*\n|[a-zA-Z]*\s*\n|)\s*[\s\S]*?```)',
        re.DOTALL
    )
    
    for match in code_block_pattern.finditer(content):
        # Add non-code content before this block
        if match.start() > current_pos:
            parts.append((content[current_pos:match.start()], False))
        
        # Add the code block
        parts.append((match.group(0), True))
        current_pos = match.end()
    
    # Add any remaining non-code content
    if current_pos < len(content):
        parts.append((content[current_pos:], False))
    
    return parts 
