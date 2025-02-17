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

def extract_meta_from_file(file_path: Path) -> tuple[dict, str]:
    """Extract meta information from an MDX file."""
    try:
        content = file_path.read_text(encoding='utf-8')
        match = META_REGEX.search(content)
        if match:
            meta_str = match.group(1)
            
            # Extract just the fields we need
            meta_dict = {}
            
            # Extract title
            title_match = TITLE_REGEX.search(meta_str)
            if title_match:
                meta_dict['title'] = title_match.group(1)
                print(f"Found title: {meta_dict['title']}")
            
            # Extract description
            desc_match = DESCRIPTION_REGEX.search(meta_str)
            if desc_match:
                meta_dict['description'] = desc_match.group(1)
                print(f"Found description: {meta_dict['description']}")
            
            # Extract platforms
            platforms_match = PLATFORMS_REGEX.search(meta_str)
            if platforms_match:
                platforms_str = platforms_match.group(1)
                meta_dict['platforms'] = extract_string_array(platforms_str)
                print(f"Found platforms: {meta_dict['platforms']}")
            
            # Remove the meta export from content
            content = META_REGEX.sub('', content)
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
    print(f"Processing directory: {in_dir}")
    
    # Check index.mdx for platform filtering
    index_file = in_dir / "index.mdx"
    if index_file.is_file():
        print(f"Found index.mdx in {in_dir}")
        dir_platforms = extract_platforms_from_file(index_file)
        # If meta.platforms is specified and doesn't include our platform, skip
        if dir_platforms and platform not in dir_platforms:
            print(f"Skipping {in_dir} for platform {platform} (not in platforms list)")
            return
        
        # Process the index file
        meta, content = extract_meta_from_file(index_file)
        if meta:
            print(f"Found meta in {index_file}")
            # Create output directory
            out_dir.mkdir(parents=True, exist_ok=True)
            # Generate frontmatter and write to output file
            frontmatter = convert_meta_to_frontmatter(meta)
            output_path = out_dir / "index.md"
            output_path.write_text(frontmatter + content, encoding='utf-8')
            print(f"Wrote {output_path}")
    
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
    
    print(f"Source directory: {src_root}")
    print(f"Destination directory: {dest_root}")
    
    # Create the output root directory
    dest_root.mkdir(exist_ok=True)
    
    for platform in PLATFORMS:
        print(f"\nProcessing platform: {platform}")
        # Start from the root src/pages directory
        process_directory(src_root, dest_root / platform, platform)

if __name__ == "__main__":
    main() 
