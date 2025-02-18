import argparse
from pathlib import Path
import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List
import tiktoken

# Get the directory containing this script and the docs directory
script_dir = Path(__file__).parent.parent
docs_dir = script_dir.parent / 'llms-docs'  # Go up one more level to find llms-docs

# Load environment variables from .env.local in the llms directory
load_dotenv(script_dir / '.env.local')

# Initialize OpenAI client and tokenizer
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
tokenizer = tiktoken.get_encoding("cl100k_base")  # OpenAI's default tokenizer

class Split(BaseModel):
    line: int
    context: str

class ChunkingResponse(BaseModel):
    splits: List[Split]

def create_chunking_prompt(document_content: str, filepath: str) -> str:
    """Create a prompt for the LLM to suggest document chunking points."""
    prompt = """You are a document chunking assistant for AWS Amplify Gen 2 documentation. AWS Amplify Gen 2 is a code-first development experience that allows developers to use TypeScript to build full-stack applications on AWS, automatically provisioning the cloud infrastructure based on the app's requirements.

You are currently processing the documentation file: {filepath}

Your task is to analyze the given markdown document and identify optimal splitting points that:
1. Maintain semantic coherence
2. Keep related concepts together
3. Don't split code blocks
4. Keep headings with their related content

Pay special attention to markdown heading patterns:
- Use heading levels (# vs ## vs ###) to identify major and minor section boundaries
- Major section breaks (# or ## headings) are often good splitting points
- Chunks should start with a heading where natural

For the document enclosed in <document></document> tags, return a JSON array of line numbers where splits should occur. Each number represents the line AFTER which a split should happen.

Rules:
- Don't split in the middle of paragraphs
- Don't split in the middle of code blocks
- Keep headings with their related content
- Prefer splitting at major section boundaries (# or ## headings)
- For each split point, please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk

Example of good context:
Original chunk: "The company's revenue grew by 3% over the previous quarter." (our chunks should be much larger than this, this is just an example)
Context to add: "SEC filing, ACME corp Q2 2023 performance, following Q1 revenue of $314M"

<document>
{content}
</document>"""

    return prompt.format(filepath=filepath, content=document_content.strip())

def count_tokens(text: str) -> int:
    """Count the number of tokens in a text string."""
    return len(tokenizer.encode(text))

def process_markdown_file(file_path: Path) -> None:
    """Process a single markdown file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Count tokens in the content
        token_count = count_tokens(content)
        
        # If file is small, create empty splits JSON
        if token_count < 500:
            json_path = file_path.with_suffix('.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump({"splits": []}, f, indent=2, ensure_ascii=False)
            
            print(f"\nProcessing: {file_path.relative_to(docs_dir)}")
            print("-" * 80)
            print(f"File has {token_count} tokens. Skipping chunking and creating empty splits.")
            print(f"Saved empty chunks to: {json_path.name}")
            print("-" * 80)
            return 0, 0
            
        # Add line numbers to content for chunking
        lines = content.splitlines()
        numbered_content = ''.join(f"{i+1}: {line}\n" for i, line in enumerate(lines))
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return 0, 0

    # Get clean relative path for display and context
    relative_path = str(file_path.relative_to(docs_dir))
    
    # Create prompt
    prompt = create_chunking_prompt(numbered_content, relative_path)

    # Print the prompt
    print(f"\nProcessing: {relative_path}")
    print("-" * 80)
    print("Prompt:")
    print(prompt)
    print("-" * 80)

    # Call OpenAI API
    try:
        completion = client.beta.chat.completions.parse(
            model="o3-mini",
            messages=[
                {"role": "system", "content": "You are a document chunking assistant for AWS Amplify Gen 2 documentation."},
                {"role": "user", "content": prompt}
            ],
            response_format=ChunkingResponse
        )
        
        # Save JSON response next to the markdown file
        json_path = file_path.with_suffix('.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(
                completion.choices[0].message.parsed.model_dump(),
                f,
                indent=2,
                ensure_ascii=False
            )
        
        print("\nResponse:")
        # Print the parsed response
        print(completion.choices[0].message.parsed.model_dump_json(indent=2))
        
        # Print token usage and cost
        input_tokens = completion.usage.prompt_tokens
        output_tokens = completion.usage.completion_tokens
        
        # Calculate costs (o3-mini pricing: $1.10 per 1M input tokens, $4.40 per 1M output tokens)
        input_cost = (input_tokens / 1_000_000) * 1.10
        output_cost = (output_tokens / 1_000_000) * 4.40
        total_cost = input_cost + output_cost
        
        print(f"\nToken Usage:")
        print(f"Input tokens:  {input_tokens:,}")
        print(f"Output tokens: {output_tokens:,}")
        print(f"\nCost:")
        print(f"Input cost:  ${input_cost:.4f}")
        print(f"Output cost: ${output_cost:.4f}")
        print(f"Total cost:  ${total_cost:.4f}")
        print(f"Saved chunks to: {json_path.name}")
        print("-" * 80)
        
        return input_cost, output_cost
        
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
        return 0, 0

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Generate chunking prompts for documentation files')
    parser.add_argument('dir_path', type=str, help='Path to the directory relative to llms-docs/')
    args = parser.parse_args()

    # Construct full path
    dir_path = docs_dir / args.dir_path

    # Validate directory exists
    if not dir_path.exists() or not dir_path.is_dir():
        print(f"Error: Directory not found: {dir_path}")
        return

    # Process all markdown files in the directory
    md_files = list(dir_path.glob('**/*.md'))
    if not md_files:
        print(f"No markdown files found in {dir_path}")
        return

    print(f"Found {len(md_files)} markdown files to process")
    
    # Track total costs
    total_input_cost = 0
    total_output_cost = 0
    
    # Process each file
    for file_path in md_files:
        input_cost, output_cost = process_markdown_file(file_path)
        total_input_cost += input_cost
        total_output_cost += output_cost
    
    print(f"\nProcessed {len(md_files)} files")
    print(f"Total input cost:  ${total_input_cost:.4f}")
    print(f"Total output cost: ${total_output_cost:.4f}")
    print(f"Total cost:        ${(total_input_cost + total_output_cost):.4f}")

if __name__ == "__main__":
    main()
