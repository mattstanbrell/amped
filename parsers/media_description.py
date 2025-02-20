"""Functions for generating descriptions of media files using Gemini."""

import os
import base64
import tempfile
import httpx
from pathlib import Path
from typing import Optional, Dict, List
from pydantic import BaseModel
import google.generativeai as genai
from google.ai.generativelanguage_v1beta.types import content
import time
import json
from collections import deque
from datetime import datetime, timedelta

# ANSI color codes
GREEN = '\033[32m'
RED = '\033[31m'
YELLOW = '\033[33m'
RESET = '\033[0m'

# Add cache directory constant
CACHE_DIR = Path.home() / ".llms_cache"

# Create cache directory if it doesn't exist
CACHE_DIR.mkdir(exist_ok=True)

class MediaContext(BaseModel):
    """Context for a media file within a document."""
    file_path: str
    description: str

class DocAnalysis(BaseModel):
    """Analysis of a document and its media files."""
    doc_summary: str
    media_contexts: List[MediaContext]

# Rate limiter for Gemini API
class RateLimiter:
    def __init__(self, max_requests: int, time_window: int):
        """Initialize rate limiter.
        
        Args:
            max_requests: Maximum number of requests allowed in the time window
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
    
    def wait_if_needed(self):
        """Wait if we've exceeded our rate limit."""
        now = datetime.now()
        
        # Remove requests older than our time window
        while self.requests and (now - self.requests[0]) > timedelta(seconds=self.time_window):
            self.requests.popleft()
        
        # If we've hit our limit, wait until we can make another request
        if len(self.requests) >= self.max_requests:
            wait_time = (self.requests[0] + timedelta(seconds=self.time_window) - now).total_seconds()
            if wait_time > 0:
                print(f"\nRate limit reached. Waiting {wait_time:.1f} seconds...")
                time.sleep(wait_time)
                # After waiting, clean up old requests again
                now = datetime.now()
                while self.requests and (now - self.requests[0]) > timedelta(seconds=self.time_window):
                    self.requests.popleft()
        
        # Add this request to our tracking
        self.requests.append(now)

# Global rate limiter: 15 requests per minute
RATE_LIMITER = RateLimiter(max_requests=15, time_window=60)

def download_media_file(src: str) -> Optional[str]:
    """Download a media file from the Amplify docs website.
    
    Args:
        src: The src URL from markdown (e.g., /images/example.png)
        
    Returns:
        Path to the downloaded file if successful, None if failed
    """
    print("\n=== download_media_file ===")
    print(f"Input src: {src!r}")
    
    # VALIDATE: Must be a markdown src URL starting with /images or /videos
    if not src.startswith(('/images/', '/videos/')):
        print(f"{RED}❌ ERROR: Invalid src URL format - must start with /images/ or /videos/: {src!r}{RESET}")
        return None
        
    # VALIDATE: Must not contain Desktop or absolute paths
    if 'Desktop' in src or src.startswith('/Users/'):
        print(f"{RED}❌ ERROR: Received file path instead of markdown src URL: {src!r}")
        print(f"This is likely a bug - we should only receive the src from markdown!{RESET}")
        return None
    
    # Check if this is an image that needs to be converted to WEBP
    if src.lower().endswith(('.png', '.jpg', '.jpeg')):
        # Extract the path components
        path_parts = src.rsplit('/', 1)  # Split on last /
        if len(path_parts) == 2:
            directory = path_parts[0]  # e.g. /images/auth/examples
            filename = path_parts[1].rsplit('.', 1)[0]  # Remove extension
            print(f"Image file detected:")
            print(f"  Directory: {directory!r}")
            print(f"  Filename: {filename!r}")
            # Insert nextImageExportOptimizer in the same directory
            media_path = f"{directory}/nextImageExportOptimizer/{filename}-opt-1920.WEBP"
        else:
            print(f"{RED}❌ Invalid image path format{RESET}")
            return None
    else:
        # For non-image files (e.g., videos), use the original path
        print("Non-image file, using original path")
        media_path = src
    
    print(f"Final media_path: {media_path!r}")
    url = f"https://docs.amplify.aws{media_path}"
    print(f"Final URL: {url}")
    
    try:
        # Create a sanitized filename for caching
        safe_filename = src.replace('/', '_').lstrip('_')
        cache_path = CACHE_DIR / safe_filename
        print(f"Cache path: {cache_path}")
        
        # Check if file exists in cache
        if cache_path.exists():
            print(f"{GREEN}✅ Cache HIT - File found in cache{RESET}")
            return str(cache_path)
            
        # If not in cache, download and store
        print(f"{YELLOW}🔄 Cache MISS - Downloading {url} to {cache_path}{RESET}")
        response = httpx.get(url)
        response.raise_for_status()
        cache_path.write_bytes(response.content)
        print(f"{GREEN}✅ Download successful{RESET}")
            
        return str(cache_path)
        
    except Exception as e:
        print(f"{RED}❌ Error downloading {url}: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        print("Traceback:")
        traceback.print_exc()
        print(RESET)
        return None

def get_base64_image(src: str) -> Optional[tuple[str, str]]:
    """Convert an image from the docs site to base64 encoding.
    
    Args:
        src: The src URL from markdown (e.g., /images/example.png)
        
    Returns:
        Tuple of (mime_type, base64_data) if successful, None if download fails
    """
    # Download the image
    downloaded_path = download_media_file(src)
    if not downloaded_path:
        return None
        
    # Get file extension and map to mime type
    ext = downloaded_path.lower().split('.')[-1]
    mime_types = {
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'webp': 'image/webp',
        'heic': 'image/heic',
        'heif': 'image/heif'
    }
    
    mime_type = mime_types.get(ext)
    if not mime_type:
        return None
        
    with open(downloaded_path, 'rb') as img_file:
        img_data = img_file.read()
        base64_data = base64.b64encode(img_data).decode('utf-8')
        return (mime_type, base64_data)

def analyze_doc_with_media(
    doc_content: str,
    media_elements: List[tuple[str, str, str]],  # (type, path, description)
    platform: str,
    api_key: Optional[str] = None
) -> Optional[DocAnalysis]:
    """Analyze a document and its media elements using Gemini.
    
    Args:
        doc_content: The processed markdown content
        media_elements: List of (media_type, file_path, description) tuples
        platform: The platform this doc is for (e.g., 'android', 'flutter')
        api_key: Optional Gemini API key
        
    Returns:
        DocAnalysis object if successful, None if failed
    """
    print("\n=== Starting document analysis ===")
    print(f"Platform: {platform}")
    print(f"Number of media elements: {len(media_elements)}")
    for typ, path, desc in media_elements:
        print(f"- {typ}: {path} ({desc})")
    
    if not media_elements:
        print("No media elements found, returning empty analysis")
        return DocAnalysis(
            doc_summary="No media elements to analyze",
            media_contexts=[]
        )

    if api_key:
        print("Configuring Gemini with provided API key")
        genai.configure(api_key=api_key)

    print("Creating Gemini model instance")
    
    # Download and prepare all media files first
    media_files = []
    for media_type, src, description in media_elements:
        downloaded_path = download_media_file(src)
        if not downloaded_path:
            print(f"Warning: Failed to download {src}")
            continue
            
        is_video = src.lower().endswith(('.mp4', '.mpeg', '.mov', '.avi', '.flv', '.mpg', '.webm', '.wmv', '.3gp'))
        if is_video:
            mime_type = f"video/{src.split('.')[-1]}"
        else:
            mime_type = f"image/{downloaded_path.lower().split('.')[-1]}"
            
        try:
            media_file = upload_to_gemini(downloaded_path, mime_type=mime_type)
            media_files.append((src, media_file, description))
        except Exception as e:
            print(f"Warning: Failed to upload {src} to Gemini: {e}")
            continue
    
    if not media_files:
        print("No media files could be processed")
        return None
        
    # Wait for all files to be ready
    print("\nWaiting for all media files to be processed...")
    wait_for_files_active([f for _, f, _ in media_files])
    
    # Check rate limit before making Gemini request
    RATE_LIMITER.wait_if_needed()
    
    # Define the schema for media contexts
    media_context_schema = content.Schema(
        type=content.Type.OBJECT,
        properties={
            "file_path": content.Schema(type=content.Type.STRING),
            "description": content.Schema(type=content.Type.STRING),
        },
        required=["file_path", "description"]
    )
    
    # Define the full response schema
    response_schema = content.Schema(
        type=content.Type.OBJECT,
        properties={
            "doc_summary": content.Schema(type=content.Type.STRING),
            "media_contexts": content.Schema(
                type=content.Type.ARRAY,
                items=media_context_schema
            ),
        },
        required=["doc_summary", "media_contexts"]
    )
    
    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
        "response_schema": response_schema,
        "response_mime_type": "application/json",
    }
    
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
    )
    
    # Start chat with all media files
    print("\nStarting chat with all media files")
    chat = model.start_chat(
        history=[
            {
                "role": "user",
                "parts": [f for _, f, _ in media_files],
            },
        ]
    )
    
    # Create the prompt for document analysis
    prompt = f"""This is documentation for AWS Amplify Gen 2, a code-first development experience that allows developers to use TypeScript to build full-stack applications on AWS, automatically provisioning the cloud infrastructure based on the app's requirements.

Please analyze these media elements in the context of this {platform} platform documentation. For each image/video, write a SINGLE PARAGRAPH that:
- Describes what the media shows (UI elements, code, diagrams)
- Explains the key concepts or features being demonstrated
- Notes any important steps or details a developer needs to understand

Keep each description focused and clear. Aim for concise but comprehensive paragraphs - only go into detail if the media content requires it.

Return a JSON object with:
1. A brief doc_summary field (we'll use this later)
2. A media_contexts array where each item has:
   - file_path: The path of the media file 
   - description: Your single-paragraph description of what the media shows and explains

The media elements to analyze are:
{chr(10).join(f'- {src} ({desc})' for src, _, desc in media_files)}

Document content for context:
{doc_content}"""

    print("\nSending prompt to Gemini")
    print("Full prompt:")
    print("------------------------")
    print(prompt)
    print("------------------------")
    
    try:
        print("\nCalling Gemini generate_content...")
        response = chat.send_message(prompt)
        print("Got response from Gemini")
        
        print("\nRaw response from Gemini:")
        print("------------------------")
        print(response.text)
        print("------------------------")
        
        print("\nParsing JSON response...")
        result = json.loads(response.text)
        
        # Convert the raw JSON into our Pydantic model
        analysis = DocAnalysis(
            doc_summary=result["doc_summary"],
            media_contexts=[
                MediaContext(
                    file_path=ctx["file_path"],
                    description=ctx["description"]
                )
                for ctx in result["media_contexts"]
            ]
        )
        print("Successfully created DocAnalysis object")
        
        return analysis
        
    except Exception as e:
        print(f"\nError during document analysis: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        print("Traceback:")
        traceback.print_exc()
        
        print("\nReturning fallback analysis")
        return DocAnalysis(
            doc_summary="Error analyzing document",
            media_contexts=[
                MediaContext(
                    file_path=src,
                    description=desc or "No context available"
                )
                for _, src, desc in media_files
            ]
        )

def upload_to_gemini(path: str, mime_type: Optional[str] = None):
    """Uploads the given file to Gemini.
    
    Args:
        path: Path to the file to upload
        mime_type: Optional MIME type of the file
    """
    file = genai.upload_file(path, mime_type=mime_type)
    print(f"Uploaded file '{file.display_name}' as: {file.uri}")
    return file

def wait_for_files_active(files: List) -> None:
    """Waits for the given files to be active.
    
    Some files uploaded to the Gemini API need to be processed before they can be
    used as prompt inputs.
    """
    print("Waiting for file processing...")
    for name in (file.name for file in files):
        file = genai.get_file(name)
        while file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(10)
            file = genai.get_file(name)
        if file.state.name != "ACTIVE":
            raise Exception(f"File {file.name} failed to process")
    print("...all files ready")
    print() 
