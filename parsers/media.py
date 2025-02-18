"""Functions for handling media components in markdown/MDX content."""

import re
from typing import List, Tuple

def extract_media_paths(content: str) -> List[Tuple[str, str]]:
    """Extract image and video file paths from markdown/MDX content.
    
    Args:
        content: The markdown/MDX content to process
        
    Returns:
        A list of tuples containing (media_type, file_path)
        where media_type is either 'image' or 'video'
        
    Example:
        >>> content = '''
        ... ![Alt text](/images/example.png)
        ... <Video src="/videos/demo.mp4" description="Demo video" />
        ... '''
        >>> result = extract_media_paths(content)
        >>> ('image', '/images/example.png') in result
        True
        >>> ('video', '/videos/demo.mp4') in result
        True
    """
    media_paths = []
    
    # Match markdown image syntax
    # ![Alt text](/path/to/image.png)
    image_pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
    for match in image_pattern.finditer(content):
        file_path = match.group(2)
        media_paths.append(('image', file_path))
    
    # Match Video component
    # <Video src="/path/to/video.mp4" description="Description" />
    video_pattern = re.compile(r'<Video\s+src="([^"]+)"[^>]*/>')
    for match in video_pattern.finditer(content):
        file_path = match.group(1)
        media_paths.append(('video', file_path))
    
    return media_paths

def print_media_paths(content: str) -> None:
    """Print all media file paths found in the content.
    
    Args:
        content: The markdown/MDX content to process
    """
    media_paths = extract_media_paths(content)
    for media_type, file_path in media_paths:
        print(f"{media_type.capitalize()}: {file_path}") 
