"""Functions for handling metadata and schema processing in MDX files."""

import re
import json
from pathlib import Path
from typing import Dict, Tuple

from .imports import remove_nextjs_imports, extract_string_array
from .exports import remove_nextjs_exports
from .components import embed_schema

# Regex for extracting meta exports and specific fields
META_REGEX = re.compile(
    r"export\s+const\s+meta\s*=\s*({[\s\S]*?});",
    re.MULTILINE | re.DOTALL
)

TITLE_REGEX = re.compile(r'["\']?title["\']?\s*:\s*["\']([^"\']*)["\']')
DESCRIPTION_REGEX = re.compile(r'["\']?description["\']?\s*:\s*(["\'])((?:(?!\1).)*)\1')
PLATFORMS_REGEX = re.compile(r'["\']?platforms["\']?\s*:\s*\[(.*?)\]', re.DOTALL)

def convert_meta_to_frontmatter(meta: Dict) -> str:
    """Convert meta dictionary to frontmatter format.
    
    Args:
        meta: Dictionary containing metadata fields (title, description)
        
    Returns:
        YAML frontmatter string with title and description
        
    Example:
        >>> meta = {"title": "My Page", "description": "A test page"}
        >>> print(convert_meta_to_frontmatter(meta))
        ---
        title: My Page
        description: A test page
        ---
        <BLANKLINE>
    """
    if not meta:
        return ""
    
    lines = ["---"]
    if 'title' in meta:
        lines.append(f"title: {meta['title']}")
    if 'description' in meta:
        lines.append(f"description: {meta['description']}")
    lines.append("---")
    lines.append("")  # Add an empty line after the frontmatter
    
    return "\n".join(lines)

def extract_meta_from_file(file_path: Path) -> Tuple[Dict, str]:
    """Extract meta information from an MDX file.
    
    This function reads an MDX file, processes its content to extract metadata,
    and returns both the metadata and the processed content.
    
    Args:
        file_path: Path to the MDX file to process
        
    Returns:
        A tuple containing:
        - Dictionary with metadata (title, description, platforms)
        - The processed content with meta exports removed
        
    Example:
        >>> content = '''
        ... export const meta = {
        ...   title: "My Page",
        ...   description: "A test page",
        ...   platforms: ["nextjs", "react"]
        ... };
        ... Other content
        ... '''
        >>> # Write test file
        >>> Path('test.mdx').write_text(content)
        >>> meta, processed = extract_meta_from_file(Path('test.mdx'))
        >>> meta['title']
        'My Page'
        >>> 'Other content' in processed
        True
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # First embed any schemas - do this BEFORE removing imports
        content = embed_schema(content, file_path)
        
        # Only remove Next.js specific imports and exports at this stage
        content = remove_nextjs_imports(content)  # Only removes specific Next.js imports
        content = remove_nextjs_exports(content)
        
        match = META_REGEX.search(content)
        if match:
            meta_str = match.group(1)
            
            # Extract just the fields we need
            meta_dict = {}
            
            # Extract title
            title_match = TITLE_REGEX.search(meta_str)
            if title_match:
                meta_dict['title'] = title_match.group(1)
            
            # Extract description
            desc_match = DESCRIPTION_REGEX.search(meta_str)
            if desc_match:
                meta_dict['description'] = desc_match.group(2)
            
            # Extract platforms
            platforms_match = PLATFORMS_REGEX.search(meta_str)
            if platforms_match:
                platforms_str = platforms_match.group(1)
                meta_dict['platforms'] = extract_string_array(platforms_str)
            
            # Remove the meta export from content
            content = META_REGEX.sub('', content)
            
            # Clean up any remaining empty lines
            content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
            
            return meta_dict, content
        return {}, content
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return {}, "" 
