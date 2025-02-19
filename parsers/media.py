"""Functions for handling media components in markdown/MDX content."""

import re
from typing import List, Tuple
from pathlib import Path
from .media_description import analyze_doc_with_media, generate_media_description

def extract_media_paths(content: str) -> List[Tuple[str, str, str]]:
    """Extract image and video file paths from markdown/MDX content.
    
    Args:
        content: The markdown/MDX content to process
        
    Returns:
        A list of tuples containing (media_type, file_path, description)
        where media_type is either 'image' or 'video'
        
    Example:
        >>> content = '''
        ... ![Alt text](/images/example.png)
        ... <Video src="/videos/demo.mp4" description="Demo video" />
        ... '''
        >>> result = extract_media_paths(content)
        >>> ('image', '/images/example.png', 'Alt text') in result
        True
        >>> ('video', '/videos/demo.mp4', 'Demo video') in result
        True
    """
    media_paths = []
    
    # Match markdown image syntax
    # ![Alt text](/path/to/image.png)
    image_pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
    for match in image_pattern.finditer(content):
        alt_text = match.group(1)
        file_path = match.group(2)
        media_paths.append(('image', file_path, alt_text))
    
    # Match Video component
    # <Video src="/path/to/video.mp4" description="Description" />
    video_pattern = re.compile(r'<Video\s+src="([^"]+)"(?:\s+description="([^"]*)")?\s*/>')
    for match in video_pattern.finditer(content):
        file_path = match.group(1)
        description = match.group(2) or ''  # Use empty string if no description
        media_paths.append(('video', file_path, description))
    
    return media_paths

def process_media_in_content(
    content: str,
    workspace_root: Path,
    platform: str,
) -> str:
    """Process all media elements in content and add Gemini descriptions.
    
    Args:
        content: The markdown content to process
        workspace_root: Root path for resolving media files
        platform: The platform this doc is for
        
    Returns:
        Content with Gemini descriptions added under media elements
    """
    # Extract media paths
    media_paths = extract_media_paths(content)
    if not media_paths:
        return content
        
    # Get document analysis with media contexts
    doc_analysis = analyze_doc_with_media(content, media_paths, platform)
    if not doc_analysis:
        return content
        
    # Process each media file and collect descriptions
    media_descriptions = {}
    
    for media_type, file_path, description in media_paths:
        # Find the original media element in the content
        if media_type == 'image':
            media_element = f'![{description}]({file_path})'
        else:
            media_element = f'<Video src="{file_path}" description="{description}" />'
        
        # Find the context for this media
        media_context = next(
            (ctx.context for ctx in doc_analysis.media_contexts 
             if ctx.file_path == file_path),
            "No specific context found"
        )
        
        # Convert the relative media path to absolute
        abs_media_path = workspace_root / file_path.lstrip('/')
        
        # Generate comprehensive description
        gemini_description = generate_media_description(
            str(abs_media_path),
            media_element,
            doc_analysis.doc_summary,
            media_context,
            platform
        )
        
        if gemini_description:
            media_descriptions[media_element] = gemini_description
    
    # Insert descriptions under each media element
    for media_element, description in media_descriptions.items():
        content = content.replace(
            media_element,
            f"{media_element}\n[{description}]"
        )
    
    return content

def print_media_paths(content: str) -> None:
    """Print all media file paths found in the content.
    
    Args:
        content: The markdown/MDX content to process
    """
    media_paths = extract_media_paths(content)
    for media_type, file_path, description in media_paths:
        if description:
            print(f"{media_type.capitalize()}: {file_path} ({description})")
        else:
            print(f"{media_type.capitalize()}: {file_path}") 
