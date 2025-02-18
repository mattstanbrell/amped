"""Functions for handling export statements in markdown/MDX content."""

import re

def remove_nextjs_exports(content: str) -> str:
    """Remove Next.js-specific exports from the content.
    
    This function removes export blocks for Next.js specific functions like
    getStaticPaths and getStaticProps, while preserving other content.
    
    Args:
        content: The markdown/MDX content to process
        
    Returns:
        The content with Next.js exports removed
        
    Example:
        >>> content = '''
        ... export const getStaticPaths = async () => {
        ...     return { paths: [], fallback: true }
        ... };
        ... Other content
        ... '''
        >>> result = remove_nextjs_exports(content)
        >>> 'getStaticPaths' not in result
        True
        >>> 'Other content' in result
        True
    """
    def find_matching_brace(text: str, start: int) -> int:
        """Find the matching closing brace, handling nested braces.
        
        Args:
            text: The text to search in
            start: The position of the opening brace
            
        Returns:
            The position of the matching closing brace, or -1 if not found
        """
        stack = []
        i = start
        while i < len(text):
            if text[i] == '{':
                stack.append(i)
            elif text[i] == '}':
                if stack:
                    stack.pop()
                    if not stack:  # Found the matching brace
                        return i
            i += 1
        return -1

    # Pattern to find the start of export blocks
    export_start_pattern = re.compile(
        r'^export\s+(?:'
        r'const\s+(?:getStaticPaths|getStaticProps)|'
        r'(?:async\s+)?function\s+(?:getStaticPaths|getStaticProps)'
        r')(?:\s*=\s*(?:async\s+)?\([^)]*\)\s*=>)?\s*(?:\([^)]*\))?\s*{',
        re.MULTILINE
    )

    result = []
    last_end = 0
    
    while True:
        # Find next export block start
        match = export_start_pattern.search(content, last_end)
        if not match:
            break
            
        start_pos = match.start()
        brace_start = match.end() - 1  # Position of the opening brace
        
        # Find matching closing brace
        end_pos = find_matching_brace(content, brace_start)
        if end_pos == -1:
            break
            
        # Add content up to this export block
        result.append(content[last_end:start_pos])
        
        # Skip past this block and any following semicolon
        last_end = end_pos + 1
        while last_end < len(content) and content[last_end].isspace():
            last_end += 1
        if last_end < len(content) and content[last_end] == ';':
            last_end += 1
    
    # Add remaining content
    result.append(content[last_end:])
    
    # Clean up multiple empty lines
    result = ''.join(result)
    result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)
    
    return result 
