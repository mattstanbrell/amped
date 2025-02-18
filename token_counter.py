import os
import tiktoken
import argparse
from pathlib import Path

def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count the number of tokens in a text string."""
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))

def count_tokens_in_directory(directory: str, file_pattern: str = "*.md") -> dict:
    """Count tokens in all matching files in a directory recursively."""
    token_counts = {
        'files': {},
        'total_tokens': 0,
        'total_files': 0
    }
    
    # Convert to Path object for better path handling
    dir_path = Path(directory)
    
    # Recursively find all markdown files
    for file_path in dir_path.rglob(file_pattern):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Count tokens in the file
            token_count = count_tokens(content)
            
            # Store relative path and count
            relative_path = str(file_path.relative_to(dir_path))
            token_counts['files'][relative_path] = token_count
            token_counts['total_tokens'] += token_count
            token_counts['total_files'] += 1
            
        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")
    
    return token_counts

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Count tokens in documentation files.')
    parser.add_argument('platform', help='Platform name (e.g., nextjs, android)')
    args = parser.parse_args()
    
    # Directory containing the documentation
    docs_dir = f"../llms-docs/{args.platform}"
    
    # Make the path absolute from the script location
    script_dir = Path(__file__).parent
    docs_dir = (script_dir.parent / f"llms-docs/{args.platform}").resolve()
    
    if not docs_dir.exists():
        print(f"Error: Directory not found: {docs_dir}")
        return
        
    print(f"Scanning directory: {docs_dir}")
    
    # Count tokens in both .md and .mdx files
    md_counts = count_tokens_in_directory(docs_dir, "*.md")
    mdx_counts = count_tokens_in_directory(docs_dir, "*.mdx")
    
    # Combine results
    total_counts = {
        'files': {**md_counts['files'], **mdx_counts['files']},
        'total_tokens': md_counts['total_tokens'] + mdx_counts['total_tokens'],
        'total_files': md_counts['total_files'] + mdx_counts['total_files']
    }
    
    # Print summary
    print(f"\nToken Count Summary")
    print(f"=================")
    print(f"Total files processed: {total_counts['total_files']}")
    print(f"Total tokens: {total_counts['total_tokens']}")
    print(f"\nPer-file breakdown:")
    print("=================")
    
    # Sort files by token count for better visibility
    sorted_files = sorted(total_counts['files'].items(), key=lambda x: x[1], reverse=True)
    for file_path, count in sorted_files:
        print(f"{file_path}: {count} tokens")

if __name__ == "__main__":
    main() 
