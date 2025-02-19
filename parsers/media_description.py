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

class MediaContext(BaseModel):
    """Context for a media file within a document."""
    file_path: str
    context: str

class DocAnalysis(BaseModel):
    """Analysis of a document and its media files."""
    doc_summary: str
    media_contexts: List[MediaContext]

def download_media_file(file_path: str) -> Optional[str]:
    """Download a media file from the Amplify docs website.
    
    Args:
        file_path: Path to the media file (e.g., /images/gen2/manage/user-manager.mp4)
        
    Returns:
        Path to the downloaded file if successful, None if failed
    """
    # First try the optimized .webp version for images
    if file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
        webp_path = file_path.rsplit('.', 1)[0] + '.webp'
        url = f"https://docs.amplify.aws{webp_path}"
    else:
        # For non-image files or if webp fails, use original path
        url = f"https://docs.amplify.aws{file_path}"
    
    print(f"Attempting to download: {url}")
    
    try:
        # Create a temporary directory if it doesn't exist
        temp_dir = Path(tempfile.gettempdir()) / "amplify_media"
        temp_dir.mkdir(exist_ok=True)
        
        # Just use the filename for local storage, with a prefix to avoid collisions
        filename = Path(file_path).name
        if file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            filename = filename.rsplit('.', 1)[0] + '.webp'
        local_path = temp_dir / f"gen2_{filename}"
        
        # Download the file if it doesn't exist
        if not local_path.exists():
            print(f"Downloading {url} to {local_path}")
            response = httpx.get(url)
            response.raise_for_status()
            local_path.write_bytes(response.content)
            
        return str(local_path)
        
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        # If webp failed, try original format as fallback
        if file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            print("Trying original format as fallback...")
            url = f"https://docs.amplify.aws{file_path}"
            try:
                local_path = temp_dir / f"gen2_{filename}"
                print(f"Downloading {url} to {local_path}")
                response = httpx.get(url)
                response.raise_for_status()
                local_path.write_bytes(response.content)
                return str(local_path)
            except Exception as e2:
                print(f"Error downloading original format {url}: {e2}")
        return None

def get_base64_image(image_path: str) -> Optional[tuple[str, str]]:
    """Convert an image file to base64 encoding.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        Tuple of (mime_type, base64_data) if successful, None if file not found
    """
    # First try to download if it's not a local file
    if not os.path.exists(image_path):
        downloaded_path = download_media_file(image_path)
        if not downloaded_path:
            return None
        image_path = downloaded_path
        
    # Get file extension and map to mime type
    ext = Path(image_path).suffix.lower()
    mime_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.webp': 'image/webp',
        '.heic': 'image/heic',
        '.heif': 'image/heif'
    }
    
    mime_type = mime_types.get(ext)
    if not mime_type:
        return None
        
    with open(image_path, 'rb') as img_file:
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
    
    # Define the schema for media contexts
    media_context_schema = content.Schema(
        type=content.Type.OBJECT,
        properties={
            "file_path": content.Schema(type=content.Type.STRING),
            "context": content.Schema(type=content.Type.STRING),
        },
        required=["file_path", "context"]
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
    
    # Create the prompt for document analysis
    prompt = f"""This is documentation for AWS Amplify Gen 2, a code-first development experience that allows developers to use TypeScript to build full-stack applications on AWS, automatically provisioning the cloud infrastructure based on the app's requirements.
This specific document is for the {platform} platform.

Please analyze this documentation and its media elements. Return a JSON object with:
1. A comprehensive summary of the document in the "doc_summary" field
2. For each media element, provide context about how it fits into the document in the "media_contexts" array
3. Each media_contexts array item should have two fields:
   - "file_path": The path of the media file
   - "context": A description of how this media element fits into the document

The media elements are:
{chr(10).join(f'- {typ}: {path} ({desc})' for typ, path, desc in media_elements)}

Document content:
{doc_content}"""

    print("\nSending prompt to Gemini")
    print("Prompt length:", len(prompt))
    print("First 500 chars of prompt:", prompt[:500])
    
    try:
        print("\nCalling Gemini generate_content...")
        response = model.generate_content(prompt)
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
                    context=ctx["context"]
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
                    file_path=path,
                    context=desc or "No context available"
                )
                for _, path, desc in media_elements
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

def generate_media_description(
    file_path: str,
    media_element: str,
    doc_summary: str,
    media_context: str,
    platform: str,
    api_key: Optional[str] = None
) -> Optional[str]:
    """Generate a comprehensive description of a media file using Gemini.
    
    Args:
        file_path: Path to the media file
        media_element: The original media element from the doc (e.g., ![...] or <Video.../>)
        doc_summary: Summary of the document this media appears in
        media_context: Context about this specific media's role in the doc
        platform: The platform this doc is for
        api_key: Optional Gemini API key
        
    Returns:
        Generated description if successful, None if failed
    """
    if api_key:
        genai.configure(api_key=api_key)
    
    print(f"\nProcessing media file: {file_path}")
    
    # First try to download if it's not a local file
    if not os.path.exists(file_path):
        downloaded_path = download_media_file(file_path)
        if not downloaded_path:
            return None
        file_path = downloaded_path
        print(f"Downloaded to: {file_path}")
    
    # Determine if this is an image or video based on extension
    ext = Path(file_path).suffix.lower()
    is_video = ext in ['.mp4', '.mpeg', '.mov', '.avi', '.flv', '.mpg', '.webm', '.wmv', '.3gp']
    print(f"Media type: {'video' if is_video else 'image'}")
    
    context = f"""This media file appears in AWS Amplify Gen 2 documentation for the {platform} platform.

AWS Amplify Gen 2 is a code-first development experience that allows developers to use TypeScript to build full-stack applications on AWS, automatically provisioning the cloud infrastructure based on the app's requirements.

Document summary: {doc_summary}

This specific media element appears as:
{media_element}

Context for this media: {media_context}"""

    print("\nContext for analysis:")
    print("-------------------")
    print(context)
    print("-------------------")

    # Configure the model
    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
        "response_mime_type": "text/plain",
    }

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
    )
    
    if is_video:
        try:
            # Upload the video and wait for processing
            mime_type = f"video/{ext.lstrip('.')}"
            print(f"\nUploading video with MIME type: {mime_type}")
            video_file = upload_to_gemini(file_path, mime_type=mime_type)
            wait_for_files_active([video_file])
            
            # Start chat with video context
            print("\nStarting chat with video context")
            chat = model.start_chat(
                history=[
                    {
                        "role": "user",
                        "parts": [video_file],
                    },
                ]
            )
            
            # Send the analysis prompt
            prompt = f"""{context}

Please provide a concise description of this video that captures the key information a reader needs to understand what it demonstrates. Focus on what actions are shown and their purpose. Keep the description brief but complete."""

            print("\nSending analysis prompt:")
            print("-------------------")
            print(prompt)
            print("-------------------")
            
            response = chat.send_message(prompt)
            print("\nReceived response:")
            print("-------------------")
            print(response.text)
            print("-------------------")
            
            return response.text
            
        except Exception as e:
            print(f"Error processing video {file_path}: {e}")
            return None
            
    else:
        img_data = get_base64_image(file_path)
        if not img_data:
            return None
            
        mime_type, base64_data = img_data
        print(f"\nUploading image with MIME type: {mime_type}")
        
        try:
            # Upload the image and wait for processing
            image_file = upload_to_gemini(file_path, mime_type=mime_type)
            wait_for_files_active([image_file])
            
            # Start chat with image context
            print("\nStarting chat with image context")
            chat = model.start_chat(
                history=[
                    {
                        "role": "user",
                        "parts": [image_file],
                    },
                ]
            )
            
            # Send the analysis prompt
            prompt = f"""{context}

Please provide a concise description of this image that captures the key information a reader needs to understand what it shows. Focus on what is being displayed and its purpose. Keep the description brief but complete."""

            print("\nSending analysis prompt:")
            print("-------------------")
            print(prompt)
            print("-------------------")
            
            response = chat.send_message(prompt)
            print("\nReceived response:")
            print("-------------------")
            print(response.text)
            print("-------------------")
            
            return response.text
            
        except Exception as e:
            print(f"Error processing image {file_path}: {e}")
            return None 
