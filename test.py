import os
import difflib
from pathlib import Path
import sys

def read_file(path):
    """Read file content, return empty string if file doesn't exist."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ""

def compare_files(example_path, generated_path):
    """Compare two files and return a diff if they don't match."""
    example_content = read_file(example_path)
    generated_content = read_file(generated_path)
    
    if not example_content:
        print(f"❌ Example file not found: {example_path}")
        return False
    if not generated_content:
        print(f"❌ Generated file not found: {generated_path}")
        return False
    
    if example_content == generated_content:
        print(f"✅ Files match: {example_path}")
        return True
    
    # Generate diff
    diff = list(difflib.unified_diff(
        example_content.splitlines(keepends=True),
        generated_content.splitlines(keepends=True),
        fromfile=str(example_path),
        tofile=str(generated_path)
    ))
    
    if diff:
        print(f"❌ Files differ: {example_path}")
        print("".join(diff))
        return False
    
    return True

def main():
    # Get the workspace root
    workspace_root = Path(__file__).parent.parent
    
    # Define the paths
    examples_root = workspace_root / "llms/examples"
    generated_root = workspace_root / "llms-docs"
    
    # Track overall success
    all_passed = True
    
    # Walk through the examples directory
    for root, _, files in os.walk(examples_root):
        for file in files:
            if file.endswith('.md'):
                # Get the relative path from examples root
                example_path = Path(root) / file
                rel_path = example_path.relative_to(examples_root)
                
                # Construct the corresponding generated path
                generated_path = generated_root / rel_path
                
                # Compare the files
                if not compare_files(example_path, generated_path):
                    all_passed = False
    
    # Exit with appropriate status code
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main() 
