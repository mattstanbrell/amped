"""Functions for handling media components in markdown/MDX content."""

import re
from typing import List, Tuple, Optional
from pathlib import Path
from .media_description import analyze_doc_with_media

def extract_media_paths(content: str) -> List[Tuple[str, str, str, str]]:
    """Extract image and video file paths from markdown/MDX content.
    
    Args:
        content: The markdown/MDX content to process
        
    Returns:
        A list of tuples containing (media_type, file_path, description, full_tag)
        where media_type is either 'image' or 'video'
        
    Example:
        >>> content = '''
        ... ![Alt text](/images/example.png)
        ... <Video src="/videos/demo.mp4" description="Demo video" />
        ... '''
        >>> result = extract_media_paths(content)
        >>> ('image', '/images/example.png', 'Alt text', '![Alt text](/images/example.png)') in result
        True
        >>> ('video', '/videos/demo.mp4', 'Demo video', '<Video src="/videos/demo.mp4" description="Demo video" />') in result
        True
    """
    media_paths = []
    
    # Match markdown image syntax
    # ![Alt text](/path/to/image.png)
    image_pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
    for match in image_pattern.finditer(content):
        alt_text = match.group(1)
        file_path = match.group(2)
        full_tag = match.group(0)
        media_paths.append(('image', file_path, alt_text, full_tag))
    
    # Match Video component
    # Can handle:
    # <Video src="/path.mp4" description="Desc"/>
    # <Video description="Desc" src="/path.mp4"/>
    video_pattern = re.compile(
        r'<Video.*?' +  # Start of Video tag with any attributes
        r'(?:' +  # Start of alternation for src/description order
        r'src="([^"]+)".*?description="([^"]+)"|' +  # src then desc
        r'description="([^"]+)".*?src="([^"]+)"' +  # desc then src
        r')' +  # End of alternation
        r'.*?(?:/>|></Video>|>\s*</Video>)',  # Any remaining attributes and closing, including multi-line
        re.DOTALL
    )
    for match in video_pattern.finditer(content):
        file_path = match.group(1) or match.group(4)  # src from either position
        description = match.group(2) or match.group(3) or ''  # description from either position
        full_tag = match.group(0)
        media_paths.append(('video', file_path, description, full_tag))
    
    return media_paths

def process_media_in_content(
    content: str,
    workspace_root: Path,
    platform: str,
) -> tuple[str, Optional[str]]:
    """Process all media elements in content and add Gemini descriptions.
    
    Args:
        content: The markdown content to process
        workspace_root: Root path for resolving media files
        platform: The platform this doc is for
        
    Returns:
        Tuple of (processed_content, doc_summary)
        where processed_content has Gemini descriptions added under media elements
        and doc_summary is the document summary if media was processed, None otherwise
    """
    # Extract media paths
    media_elements = extract_media_paths(content)
    if not media_elements:
        return content, None
        
    # Get document analysis with media contexts
    doc_analysis = analyze_doc_with_media(content, [(t, p, d) for t, p, d, _ in media_elements], platform)
    if not doc_analysis:
        return content, None
        
    # Process each media file and collect descriptions
    media_descriptions = {}
    
    for media_type, file_path, description, full_tag in media_elements:
        # Find the context for this media
        media_context = next(
            (ctx.description for ctx in doc_analysis.media_contexts 
             if ctx.file_path == file_path),
            None
        )
        
        if media_context:
            # Clean up description and add source URL
            clean_description = media_context.strip()
            url = f"https://docs.amplify.aws{file_path}"
            formatted_description = f"[{clean_description}\nSource: {url}]"
            media_descriptions[full_tag] = formatted_description
        # If we couldn't process the media, just skip it (keeping original tag)
    
    # Insert descriptions under each media element
    for media_element, formatted_description in media_descriptions.items():
        content = content.replace(
            media_element,
            f"{media_element}\n{formatted_description}"
        )
    
    return content, doc_analysis.doc_summary

def print_media_paths(content: str) -> None:
    """Print all media file paths found in the content.
    
    Args:
        content: The markdown/MDX content to process
    """
    media_paths = extract_media_paths(content)
    for media_type, file_path, description, full_tag in media_paths:
        if description:
            print(f"{media_type.capitalize()}: {file_path} ({description})")
        else:
            print(f"{media_type.capitalize()}: {file_path}") 
