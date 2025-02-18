"""Functions for handling fragment imports and processing in MDX content."""

import re
from pathlib import Path
from typing import Dict

from .code_blocks import split_content_and_code_blocks
from .filters import process_inline_filters
from .components import (
    embed_schema,
    embed_protected_redaction_message,
    convert_ui_table_to_markdown,
    convert_cards_to_markdown,
    remove_jsx_comments,
    remove_overview_components
)

def process_fragments(content: str, file_path: Path, platform: str, workspace_root: Path) -> str:
    """Process fragment imports and components in MDX content.
    
    This function handles:
    - Schema embedding
    - Inline filter processing
    - Protected redaction messages
    - UI table conversion
    - Card conversion
    - Fragment imports and processing
    
    Args:
        content: The markdown/MDX content to process
        file_path: Path to the current file
        platform: The current platform (e.g. 'nextjs', 'react')
        workspace_root: Path to the workspace root
        
    Returns:
        The processed content with all fragments and components handled
    """
    # First embed any schemas
    content = embed_schema(content, file_path)
    
    # Process InlineFilter blocks BEFORE protected redaction messages
    content = process_inline_filters(content, platform)
    
    # Now process protected redaction messages
    content = embed_protected_redaction_message(content, workspace_root)
    
    # Convert UI tables to markdown
    content = convert_ui_table_to_markdown(content)
    
    # Convert Cards to markdown
    content = convert_cards_to_markdown(content)
    
    # Remove Overview components
    content = remove_overview_components(content)
    
    # Remove JSX comments
    content = remove_jsx_comments(content)
    
    # Track imported fragments - collect ALL imports first
    fragment_imports = {}
    import_pattern = re.compile(
        r'(?:^|\n|```.*?\n)(?:\s*)(import\s+([a-zA-Z0-9_]+)\s+from\s+[\'"](?:/)?([^\'\"]+)[\'"]\s*;\s*\n?)',
        re.MULTILINE | re.DOTALL
    )
    
    # First pass: collect all imports without removing them
    for match in import_pattern.finditer(content):
        alias = match.group(2)
        source_path = match.group(3)
        if source_path.startswith('/'):
            fragment_imports[alias] = workspace_root / source_path.lstrip('/')
        elif source_path.startswith('src/'):
            fragment_imports[alias] = workspace_root / source_path
        else:
            fragment_imports[alias] = file_path.parent / source_path
    
    # Split content into sections to preserve code blocks
    sections = split_content_and_code_blocks(content)
    processed_sections = []
    
    # Process each section
    for section_content, is_code_block in sections:
        if is_code_block:
            processed_sections.append(section_content)
            continue
        
        # Process Fragments components in non-code sections
        fragments_pattern = re.compile(
            r'<Fragments\s+fragments\s*=\s*({[\s\S]*?})\s*/>\s*\n?',
            re.MULTILINE
        )
        
        def fragments_repl(match):
            fragments_str = match.group(1)
            
            # Extract platform to alias mapping using regex
            mapping_pattern = re.compile(r'[\'"]?([\w-]+)[\'"]?\s*:\s*(\w+)')
            mappings = mapping_pattern.findall(fragments_str)
            
            # Find the matching fragment for current platform
            fragment_path = None
            fragment_content = ''
            
            for frag_platform, alias in mappings:
                if frag_platform == platform and alias in fragment_imports:
                    fragment_path = fragment_imports[alias]
                    break
            
            if fragment_path and fragment_path.exists():
                try:
                    # Read and process the fragment file
                    fragment_content = fragment_path.read_text(encoding='utf-8')
                    
                    # Process any nested fragments in the fragment
                    fragment_content = process_fragments(
                        fragment_content, 
                        fragment_path, 
                        platform,
                        workspace_root
                    )
                    
                    # Process any inline filters in the fragment
                    fragment_content = process_inline_filters(fragment_content, platform)
                    
                    # Ensure proper spacing around headings
                    # First ensure there's a newline before any heading
                    fragment_content = re.sub(r'([^\n])\n(\#{1,6}\s+[^\n]+)', r'\1\n\n\2', fragment_content)
                    # Then ensure there's a newline after any heading
                    fragment_content = re.sub(r'(\#{1,6}\s+[^\n]+)\n([^\n])', r'\1\n\n\2', fragment_content)
                    
                    # Add newlines to ensure proper separation between fragments
                    return "\n\n" + fragment_content.strip() + "\n\n"
                except Exception as e:
                    print(f"Error processing fragment {fragment_path}: {e}")
                    return ''
            
            return ''
        
        # Process fragments first
        section_content = fragments_pattern.sub(fragments_repl, section_content)
        
        # Add the processed section if it's not empty
        if section_content.strip():
            processed_sections.append(section_content)
    
    # Join sections with proper spacing and remove imports
    result = []
    current_section = []
    
    for section in processed_sections:
        # If this is a code block (starts with ```), add it as is
        if section.strip().startswith('```'):
            if current_section:
                # Process and add the current non-code section
                non_code_content = '\n'.join(current_section)
                # Remove imports only from non-code sections, with more precise pattern
                non_code_content = re.sub(
                    r'^\s*import\s+[a-zA-Z0-9_]+\s+from\s+[\'"](?:/)?[^\'\"]+[\'"]\s*;\s*\n?',
                    '',
                    non_code_content,
                    flags=re.MULTILINE
                )
                if non_code_content.strip():
                    result.append(non_code_content.strip())
                current_section = []
            result.append(section.strip())
        else:
            # Add to current non-code section
            if section.strip():
                current_section.append(section.strip())
    
    # Process any remaining non-code section
    if current_section:
        non_code_content = '\n'.join(current_section)
        # Remove imports only from non-code sections, with more precise pattern
        non_code_content = re.sub(
            r'^\s*import\s+[a-zA-Z0-9_]+\s+from\s+[\'"](?:/)?[^\'\"]+[\'"]\s*;\s*\n?',
            '',
            non_code_content,
            flags=re.MULTILINE
        )
        if non_code_content.strip():
            result.append(non_code_content.strip())
    
    # Join all sections with proper spacing and ensure consistent line endings
    content = '\n\n'.join(result)
    
    # Clean up multiple empty lines but preserve double newlines
    content = re.sub(r'\n{3,}', '\n\n', content)
    
    # Ensure file ends with exactly one newline
    content = content.rstrip() + '\n'
    
    return content 
