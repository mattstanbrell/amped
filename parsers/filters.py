"""Functions for handling InlineFilter tags in markdown/MDX content."""

import re
from typing import List, Tuple

from .code_blocks import split_content_and_code_blocks

def find_matching_filter_end(text: str, start: int) -> int:
    """Find the matching closing InlineFilter tag, handling nested filters.
    
    Args:
        text: The text to search in
        start: The position of the opening tag
        
    Returns:
        The position of the matching closing tag, or -1 if not found
    """
    stack = []
    i = start
    in_quotes = False
    quote_char = None
    
    # Push the initial opening tag onto the stack
    stack.append(start)
    
    while i < len(text):
        # Skip over quoted sections
        if text[i] in ['"', "'"] and (i == 0 or text[i-1] != '\\'):
            if not in_quotes:
                in_quotes = True
                quote_char = text[i]
            elif text[i] == quote_char:
                in_quotes = False
                quote_char = None
        
        if not in_quotes:
            # Look for opening tags
            if i + len('<inlinefilter') <= len(text):
                next_chunk = text[i:i+len('<inlinefilter')].lower()
                if next_chunk == '<inlinefilter':
                    stack.append(i)
                    i += len('<inlinefilter') - 1
            
            # Look for closing tags
            elif i + len('</inlinefilter>') <= len(text):
                next_chunk = text[i:i+len('</inlinefilter>')].lower()
                if next_chunk == '</inlinefilter':
                    stack.pop()
                    if not stack:  # Found the matching end tag
                        return i
                    i += len('</inlinefilter') - 1
        
        i += 1
    
    return -1

def process_inline_filters(content: str, current_platform: str) -> str:
    """Process InlineFilter blocks in MDX content using regex.
    
    This function processes InlineFilter tags that conditionally include content
    based on the current platform. It handles nested filters and preserves
    code blocks.
    
    Args:
        content: The markdown/MDX content to process
        current_platform: The platform to filter content for (e.g. 'nextjs', 'react')
        
    Returns:
        The processed content with platform-specific sections included/excluded
        
    Example:
        >>> content = '''
        ... <InlineFilter filters={['nextjs']}>
        ... Next.js specific content
        ... </InlineFilter>
        ... Common content
        ... '''
        >>> result = process_inline_filters(content, 'nextjs')
        >>> 'Next.js specific content' in result
        True
        >>> result = process_inline_filters(content, 'react')
        >>> 'Next.js specific content' not in result
        True
        >>> 'Common content' in result
        True
    """
    def find_matching_end(text: str, start: int) -> int:
        """Find the matching closing InlineFilter tag, handling nested tags."""
        count = 1  # We start after an opening tag
        pos = start
        
        while count > 0 and pos < len(text):
            # Find next opening or closing tag (case insensitive)
            open_tag = -1
            close_tag = -1
            
            # Look for next tags after current position
            text_lower = text.lower()
            temp_pos = pos
            while temp_pos < len(text):
                next_open = text_lower.find('<inlinefilter', temp_pos)
                next_close = text_lower.find('</inlinefilter>', temp_pos)
                
                if next_open == -1 and next_close == -1:
                    break
                    
                if next_open != -1 and (next_close == -1 or next_open < next_close):
                    open_tag = next_open
                    temp_pos = next_open + len('<inlinefilter')
                    break
                    
                if next_close != -1:
                    close_tag = next_close
                    temp_pos = next_close + len('</inlinefilter>')
                    break
            
            # No more tags found
            if open_tag == -1 and close_tag == -1:
                return -1
                
            # Found a closing tag first
            if (close_tag != -1 and open_tag == -1) or (close_tag != -1 and close_tag < open_tag):
                count -= 1
                pos = close_tag + len('</inlinefilter>')
            # Found an opening tag first
            elif open_tag != -1:
                count += 1
                pos = open_tag + len('<inlinefilter')
        
        return pos if count == 0 else -1
    
    def process_recursive(text: str, depth: int = 0) -> str:
        result = []
        pos = 0
        
        while pos < len(text):
            # Find next InlineFilter start (case insensitive)
            start_tag = text.lower().find('<inlinefilter', pos)
            if start_tag == -1:
                # No more filters, add remaining content
                result.append(text[pos:])
                break
            
            # Add content up to the tag
            result.append(text[pos:start_tag])
            
            # Find the filters attribute
            filters_start = text.lower().find('filters=', start_tag)
            if filters_start == -1:
                pos = start_tag + 1
                continue
                
            # Find the end of the opening tag
            tag_end = text.find('>', filters_start)
            if tag_end == -1:
                pos = start_tag + 1
                continue
                
            # Extract platforms string
            platforms_str = text[filters_start:tag_end]
            platforms = re.findall(r'["\']([a-zA-Z0-9-]+)["\']', platforms_str)
            
            # Find the matching end tag
            content_start = tag_end + 1
            content_end = find_matching_end(text, content_start)
            
            if content_end == -1:
                pos = start_tag + 1
                continue
            
            # Get the content between tags
            inner_content = text[content_start:content_end - len('</inlinefilter>')]
            
            # Include content if either:
            # 1. No platforms specified (empty filter) - include for all platforms
            # 2. Current platform is in the specified platforms list
            should_include = not platforms or current_platform in platforms
            
            if should_include:
                # Recursively process any nested filters
                processed_content = process_recursive(inner_content, depth + 1)
                result.append(processed_content)
            
            # Move past this entire block
            pos = content_end
        
        return ''.join(result).strip()
    
    # Process the content recursively
    result = process_recursive(content)
    
    # Clean up multiple empty lines
    result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)
    
    return result.strip() 
