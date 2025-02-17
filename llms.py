import os
import re
import json
from pathlib import Path
import yaml

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

def extract_meta_from_file(file_path: Path) -> tuple[dict, str]:
    """Extract meta information from an MDX file."""
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # First remove Next.js imports and exports
        content = remove_nextjs_imports(content)
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
        return f"---\n{yaml_str}---\n"
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
        
        # Process the index file
        meta, content = extract_meta_from_file(index_file)
        if meta:
            # Create output directory
            out_dir.mkdir(parents=True, exist_ok=True)
            # Generate frontmatter and write to output file
            frontmatter = convert_meta_to_frontmatter(meta)
            output_path = out_dir / "index.md"
            output_path.write_text(frontmatter + content, encoding='utf-8')
    
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

def main():
    # Get the script's directory
    script_dir = Path(__file__).parent
    # Get the workspace root (one level up from script directory)
    workspace_root = script_dir.parent
    
    src_root = workspace_root / "src/pages"
    dest_root = workspace_root / "llms-docs"
    
    if not src_root.exists():
        print(f"Source directory {src_root} does not exist!")
        return
    
    # Create the output root directory
    dest_root.mkdir(exist_ok=True)
    
    for platform in PLATFORMS:
        process_directory(src_root, dest_root / platform, platform)

if __name__ == "__main__":
    main() 
