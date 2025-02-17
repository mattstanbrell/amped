import os
import re
import json
from pathlib import Path
import yaml
from bs4 import BeautifulSoup
import ast

# List of supported platforms
PLATFORMS = ["angular", "javascript", "nextjs", "react", 
             "react-native", "vue", "android", "swift", "flutter"]

# Regex for extracting meta exports and specific fields
META_REGEX = re.compile(
    r"export\s+const\s+meta\s*=\s*({[\s\S]*?});",
    re.MULTILINE | re.DOTALL
)

TITLE_REGEX = re.compile(r'["\']?title["\']?\s*:\s*["\']([^"\']*)["\']')
DESCRIPTION_REGEX = re.compile(r'["\']?description["\']?\s*:\s*["\']([^"\']*)["\']')
PLATFORMS_REGEX = re.compile(r'["\']?platforms["\']?\s*:\s*\[(.*?)\]', re.DOTALL)

def extract_string_array(array_str: str) -> list[str]:
    """Extract strings from a JavaScript array string."""
    # Find all quoted strings, handling both single and double quotes
    matches = re.findall(r'["\']([^"\']*)["\']', array_str)
    return matches

def remove_nextjs_imports(content: str) -> str:
    """Remove Next.js-specific imports from the content."""
    # List of patterns to remove
    import_patterns = [
        r'^import\s*{\s*getCustomStaticPath\s*}\s*from\s*[\'"]@/utils/getCustomStaticPath[\'"];\s*\n?',
        r'^import\s*{\s*getChildPageNodes\s*}\s*from\s*[\'"]@/utils/getChildPageNodes[\'"];\s*\n?'
    ]
    
    # Remove each pattern
    for pattern in import_patterns:
        content = re.sub(pattern, '', content, flags=re.MULTILINE)
    
    return content

def remove_nextjs_exports(content: str) -> str:
    """Remove Next.js-specific exports from the content."""
    def find_matching_brace(text: str, start: int) -> int:
        """Find the matching closing brace, handling nested braces."""
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
    
    # Join and clean up multiple empty lines
    result = ''.join(result)
    result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)
    
    return result

def find_matching_filter_end(text: str, start: int) -> int:
    """Find the matching closing InlineFilter tag, handling nested filters."""
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
        
        # Debug output for tag matching
        if i % 1000 == 0:  # Print every 1000 characters to avoid spam
            print(f"Current position: {i}, Stack depth: {len(stack)}")
            print(f"Next 20 chars: {text[i:i+20]}")
    
    # If we get here, we didn't find a matching end tag
    print(f"Failed to find closing tag. Stack depth: {len(stack)}")
    if stack:
        context_start = max(0, stack[-1] - 50)
        context_end = min(len(text), stack[-1] + 50)
        print(f"Context around last opening tag:\n{text[context_start:context_end]}")
    
    return -1

def process_inline_filters(content: str, current_platform: str) -> str:
    """Process InlineFilter blocks in MDX content using regex."""
    print(f"\nProcessing inline filters for platform: {current_platform}")
    
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
        indent = "  " * depth
        print(f"{indent}Processing at depth {depth}")
        
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
            print(f"{indent}Found InlineFilter with platforms: {platforms}")
            
            # Find the matching end tag
            content_start = tag_end + 1
            content_end = find_matching_end(text, content_start)
            
            if content_end == -1:
                print(f"{indent}Warning: No matching end tag found")
                pos = start_tag + 1
                continue
            
            # Get the content between tags
            inner_content = text[content_start:content_end - len('</inlinefilter>')]
            
            # Include content if either:
            # 1. No platforms specified (empty filter) - include for all platforms
            # 2. Current platform is in the specified platforms list
            should_include = not platforms or current_platform in platforms
            
            if should_include:
                print(f"{indent}Including content for {current_platform}")
                # Recursively process any nested filters
                processed_content = process_recursive(inner_content, depth + 1)
                result.append(processed_content)
            else:
                print(f"{indent}Excluding content for {current_platform} (not in {platforms})")
            
            # Move past this entire block
            pos = content_end
        
        return ''.join(result).strip()
    
    # Process the content recursively
    result = process_recursive(content)
    
    # Clean up multiple empty lines
    result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)
    
    return result.strip()

def remove_overview_components(content: str) -> str:
    """Remove Overview component tags from the content."""
    return re.sub(
        r'<Overview\s+childPageNodes\s*=\s*{[^}]+}\s*/>\s*\n?',
        '',
        content,
        flags=re.IGNORECASE | re.MULTILINE
    )

def process_fragments(content: str, file_path: Path, platform: str, workspace_root: Path) -> str:
    """Process fragment imports and components in MDX content."""
    # Track imported fragments
    fragment_imports = {}
    
    # Extract and remove imports
    import_pattern = re.compile(
        r'^import\s+([a-zA-Z0-9_]+)\s+from\s+\'(/src/fragments/[^\']+)\';\s*\n?',
        re.MULTILINE
    )
    
    def import_repl(match):
        alias = match.group(1)
        source_path = match.group(2)
        # Convert /src/fragments path to workspace path
        rel_path = source_path.lstrip('/')
        fragment_imports[alias] = workspace_root / rel_path
        return ''  # Remove the import
    
    content = import_pattern.sub(import_repl, content)
    
    # Process Fragments components
    fragments_pattern = re.compile(
        r'<Fragments\s+fragments\s*=\s*({[\s\S]*?})\s*/>\s*\n?'
    )
    
    def fragments_repl(match):
        fragments_str = match.group(1)
        
        # Extract platform to alias mapping using regex
        # Handle both forms: {platform: alias} and {'platform': alias}
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
                return fragment_content.strip()
            except Exception as e:
                print(f"Warning: Error processing fragment {fragment_path}: {e}")
                return ''
        
        return ''  # Remove the Fragments component if no matching content
    
    content = fragments_pattern.sub(fragments_repl, content)
    return content

def extract_meta_from_file(file_path: Path) -> tuple[dict, str]:
    """Extract meta information from an MDX file."""
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # First remove Next.js imports and exports
        content = remove_nextjs_imports(content)
        content = remove_nextjs_exports(content)
        content = remove_overview_components(content)
        
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
                meta_dict['description'] = desc_match.group(1)
            
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

def convert_meta_to_frontmatter(meta: dict) -> str:
    """Convert meta dictionary to YAML frontmatter."""
    # We only want title and description in the frontmatter
    frontmatter = {}
    if 'title' in meta:
        frontmatter['title'] = meta['title']
    if 'description' in meta:
        frontmatter['description'] = meta['description']
    
    if not frontmatter:
        return ""
    
    try:
        # Convert to YAML, preserving order
        yaml_str = yaml.dump(frontmatter, sort_keys=False, allow_unicode=True)
        return f"---\n{yaml_str}---\n\n"
    except Exception as e:
        print(f"Error converting meta to YAML: {e}")
        return ""

def extract_platforms_from_file(file_path: Path) -> list[str] | None:
    """Extract platforms array from index.mdx meta."""
    meta, _ = extract_meta_from_file(file_path)
    if "platforms" in meta and isinstance(meta["platforms"], list):
        return meta["platforms"]
    return None

def process_directory(in_dir: Path, out_dir: Path, platform: str):
    """Process a directory and its subdirectories."""
    # Skip gen1 directory
    if "gen1" in in_dir.parts:
        return
        
    # Check index.mdx for platform filtering
    index_file = in_dir / "index.mdx"
    if index_file.is_file():
        dir_platforms = extract_platforms_from_file(index_file)
        # If meta.platforms is specified and doesn't include our platform, skip
        if dir_platforms and platform not in dir_platforms:
            return
        
        try:
            # First get the meta and raw content
            meta, content = extract_meta_from_file(index_file)
            if meta:
                # Get workspace root for fragment processing
                workspace_root = index_file.parent
                while workspace_root.name != "src" and workspace_root.parent != workspace_root:
                    workspace_root = workspace_root.parent
                workspace_root = workspace_root.parent
                
                # Process fragments with the current platform
                content = process_fragments(content, index_file, platform, workspace_root)
                
                # Process InlineFilter blocks
                content = process_inline_filters(content, platform)
                
                # Create output directory
                out_dir.mkdir(parents=True, exist_ok=True)
                
                # Generate frontmatter and write to output file
                frontmatter = convert_meta_to_frontmatter(meta)
                output_path = out_dir / "index.md"
                output_path.write_text(frontmatter + content, encoding='utf-8')
                
                if not content.strip():
                    print(f"Warning: Empty content after processing {index_file}")
        except Exception as e:
            print(f"Error processing {index_file}: {e}")
    
    # Process subdirectories
    for item in in_dir.iterdir():
        if item.is_dir():
            # Replace [platform] with the actual platform in the output path
            out_subdir = out_dir
            if item.name == "[platform]":
                out_subdir = out_dir
            else:
                out_subdir = out_dir / item.name
            process_directory(item, out_subdir, platform)

def process_single_file(mdx_path: str, platform: str):
    """Process a single MDX file and output the corresponding MD file."""
    mdx_file = Path(mdx_path)
    if not mdx_file.exists():
        print(f"Error: File {mdx_path} does not exist!")
        return

    print(f"\nProcessing {mdx_file} for platform: {platform}")
    
    try:
        # First get the meta and raw content
        print("\nExtracting meta and content...")
        meta, content = extract_meta_from_file(mdx_file)
        
        if not meta:
            print("Warning: No meta information found")
        else:
            print(f"Found meta: {json.dumps(meta, indent=2)}")
            
        # Get workspace root for fragment processing
        workspace_root = mdx_file.parent
        while workspace_root.name != "src" and workspace_root.parent != workspace_root:
            workspace_root = workspace_root.parent
        workspace_root = workspace_root.parent
        
        print(f"\nUsing workspace root: {workspace_root}")
        
        # Process fragments
        print("\nProcessing fragments...")
        content_after_fragments = process_fragments(content, mdx_file, platform, workspace_root)
        
        if content_after_fragments != content:
            print("Content was modified by fragment processing")
        else:
            print("No changes from fragment processing")
        
        # Process InlineFilter blocks
        print("\nProcessing inline filters...")
        final_content = process_inline_filters(content_after_fragments, platform)
        
        if final_content != content_after_fragments:
            print("Content was modified by inline filter processing")
        else:
            print("No changes from inline filter processing")
        
        # Create output path
        output_path = mdx_file.with_suffix('.md')
        print(f"\nWriting output to: {output_path}")
        
        # Generate frontmatter
        frontmatter = convert_meta_to_frontmatter(meta)
        
        # Write the output file
        output_path.write_text(frontmatter + final_content, encoding='utf-8')
        
        if not final_content.strip():
            print("Warning: Output content is empty!")
        else:
            print(f"Successfully wrote {len(final_content)} characters of content")
            
    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback
        traceback.print_exc()

def main():
    import sys
    if len(sys.argv) > 2:
        # Process single file mode
        mdx_path = sys.argv[1]
        platform = sys.argv[2]
        process_single_file(mdx_path, platform)
    else:
        # Original directory processing mode
        script_dir = Path(__file__).parent
        workspace_root = script_dir.parent
        
        src_root = workspace_root / "src/pages"
        dest_root = workspace_root / "llms-docs"
        
        if not src_root.exists():
            print(f"Source directory {src_root} does not exist!")
            return
        
        dest_root.mkdir(exist_ok=True)
        
        for platform in PLATFORMS:
            process_directory(src_root, dest_root / platform, platform)

if __name__ == "__main__":
    main() 
