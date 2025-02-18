"""Main entry point for MDX to MD conversion."""

import sys
from pathlib import Path
import traceback

from parsers.platforms import PLATFORMS, extract_platforms_from_file
from parsers.utils import get_workspace_root
from parsers.meta import extract_meta_from_file, convert_meta_to_frontmatter
from parsers.fragments import process_fragments
from parsers.filters import process_inline_filters
from parsers.components import embed_protected_redaction_message
from parsers.imports import remove_imports
from parsers.media import print_media_paths

def process_directory(in_dir: Path, out_dir: Path, platform: str):
    """Process a directory and its subdirectories.
    
    Args:
        in_dir: Input directory containing MDX files
        out_dir: Output directory for MD files
        platform: Current platform to process
    """
    # Skip gen1 and [category] directories
    if "gen1" in in_dir.parts or "[category]" in in_dir.parts:
        return
        
    # Check index.mdx for platform filtering
    index_file = in_dir / "index.mdx"
    if index_file.is_file():
        dir_platforms = extract_platforms_from_file(index_file)
        # If meta.platforms is specified and doesn't include our platform, skip
        if dir_platforms and platform not in dir_platforms:
            return
        
        try:
            # Get workspace root
            workspace_root = get_workspace_root(index_file)
            
            # First get the meta and raw content
            meta, content = extract_meta_from_file(index_file)
            if meta:
                # Process fragments with the current platform
                content = process_fragments(content, index_file, platform, workspace_root)
                
                # Process InlineFilter blocks
                content = process_inline_filters(content, platform)
                
                # Process protected redaction messages
                content = embed_protected_redaction_message(content, workspace_root)
                
                # Remove all imports
                content = remove_imports(content, index_file)
                
                # Create output directory
                out_dir.mkdir(parents=True, exist_ok=True)
                
                # Generate frontmatter
                frontmatter = convert_meta_to_frontmatter(meta)
                
                # Combine content with an extra newline after frontmatter
                final_content = frontmatter + "\n" + content.lstrip()
                
                # Ensure exactly one newline at end of file
                final_content = final_content.rstrip() + '\n'
                
                # Write the output file
                output_path = out_dir / "index.md"
                output_path.write_text(final_content, encoding='utf-8')
                
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
    """Process a single MDX file and output the corresponding MD file.
    
    Args:
        mdx_path: Path to the MDX file to process
        platform: Current platform to process
    """
    # Try different possible locations for the file
    possible_paths = [
        Path(mdx_path),  # Direct path
        Path("llms-docs") / platform / mdx_path,  # In llms-docs/platform/
        Path("src/pages/[platform]") / mdx_path,  # In src/pages/[platform]/
    ]
    
    mdx_file = None
    for path in possible_paths:
        if path.exists():
            mdx_file = path
            break
    
    if mdx_file is None:
        print(f"Error: File not found in any of:")
        for path in possible_paths:
            print(f"  - {path}")
        return
    
    try:
        # Get workspace root for fragment processing
        workspace_root = get_workspace_root(mdx_file)
        
        # Get meta and raw content
        meta, content = extract_meta_from_file(mdx_file)
        
        # Print any media paths found in the content
        print(f"\nMedia paths in {mdx_file}:")
        print_media_paths(content)
            
        # Process fragments with the current platform
        processed_content = process_fragments(content, mdx_file, platform, workspace_root)
        
        # Create output path
        output_path = mdx_file.with_suffix('.md')
        
        # Generate frontmatter
        frontmatter = convert_meta_to_frontmatter(meta)
        
        # Combine content with an extra newline after frontmatter
        final_content = frontmatter + "\n" + processed_content.lstrip()
        
        # Ensure exactly one newline at end of file
        final_content = final_content.rstrip() + '\n'
        
        # Write the output file
        output_path.write_text(final_content, encoding='utf-8')
            
    except Exception as e:
        print(f"Error processing file: {e}")
        traceback.print_exc()

def main() -> None:
    """Main entry point for the script."""
    # Check if specific file and platform are provided
    if len(sys.argv) == 3:
        mdx_path = sys.argv[1]
        platform = sys.argv[2]
        process_single_file(mdx_path, platform)
            
    # Original directory processing mode
    else:
        if len(sys.argv) != 1:
            print("Usage:")
            print("  For directory processing: python main.py")
            print("  For single file: python main.py <mdx_file_path> <platform>")
            print("Example: python main.py src/pages/[platform]/start/connect-to-aws-resources/index.mdx nextjs")
            return
            
        # Process each platform
        src_dir = Path("src/pages/[platform]")
        if not src_dir.exists():
            print(f"Error: Source directory {src_dir} not found!")
            return
            
        for platform in PLATFORMS:
            print(f"Processing platform: {platform}")
            
            # Create output directory for this platform
            out_dir = Path(f"llms-docs/{platform}")
            
            # Process the directory tree
            process_directory(src_dir, out_dir, platform)
            
        print("Processing complete")

if __name__ == "__main__":
    main() 
