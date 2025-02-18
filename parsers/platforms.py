"""Functions for handling platform-specific processing in MDX content."""

from pathlib import Path
from typing import List, Optional

from .meta import extract_meta_from_file

# List of supported platforms
PLATFORMS = [
    "angular",
    "javascript",
    "nextjs",
    "react", 
    "react-native",
    "vue",
    "android",
    "swift",
    "flutter"
]

def extract_platforms_from_file(file_path: Path) -> Optional[List[str]]:
    """Extract platforms array from index.mdx meta.
    
    Args:
        file_path: Path to the MDX file to extract platforms from
        
    Returns:
        List of platform strings if found, None otherwise
        
    Example:
        >>> content = '''
        ... export const meta = {
        ...   platforms: ["nextjs", "react"]
        ... };
        ... '''
        >>> Path('test.mdx').write_text(content)
        >>> result = extract_platforms_from_file(Path('test.mdx'))
        >>> result == ["nextjs", "react"]
        True
    """
    meta, _ = extract_meta_from_file(file_path)
    if "platforms" in meta and isinstance(meta["platforms"], list):
        return meta["platforms"]
    return None 
