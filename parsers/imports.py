"""Functions for handling import statements in markdown/MDX content."""

import re
from pathlib import Path
from typing import List

from .code_blocks import split_content_and_code_blocks

# Import removal patterns
NEXTJS_IMPORT_PATTERNS = [
    r'^import\s*{\s*getCustomStaticPath\s*}\s*from\s*[\'"]@/utils/getCustomStaticPath[\'"];\s*\n?',
    r'^import\s*{\s*getChildPageNodes\s*}\s*from\s*[\'"]@/utils/getChildPageNodes[\'"];\s*\n?',
    r'^import\s*{\s*getApiStaticPath\s*}\s*from\s*[\'"]@/utils/getApiStaticPath[\'"];\s*\n?',
]

IMPORT_PATTERNS = [
    # Schema imports
    r'^import\s+\w+\s+from\s+[\'"].*?amplify-outputs-schema-v1\.json[\'"];?\s*\n?',
    r'^import\s+schema\s+from\s+[\'"]\.?/.*?amplify-outputs-schema-v1\.json[\'"];?\s*\n?',
    # Icons imports
    r'^import\s*{[^}]+}\s*from\s*[\'"]@/components/Icons/[^\'"]+[\'"];?\s*$\n?',
    # AWS Amplify UI and AI imports
    r'^import\s*.*?\s*from\s*[\'"]@aws-amplify/ui-react[\'"].*?\n',
    r'^import\s*.*?\s*from\s*[\'"]@aws-amplify/ui-react-ai[\'"].*?\n',
    r'^import\s*.*?\s*from\s*[\'"]@/components/AI[^\'"]*[\'"].*?\n',
    # UI Wrapper imports
    r'^import\s*.*?\s*from\s*[\'"]@/components/UIWrapper[\'"].*?\n',
    # Fragment imports
    r'^import\s+[a-zA-Z0-9_]+\s+from\s*[\'"](?:/)?src/fragments/.*?[\'"].*?\n',
    # Protected redaction message imports
    r'^import\s*{\s*ProtectedRedactionGen[12]Message\s*}\s*from\s*[\'"]@/protected/ProtectedRedactionMessage[\'"].*?\n'
]

def extract_string_array(array_str: str) -> List[str]:
    """Extract strings from a JavaScript array string.
    
    Args:
        array_str: A string containing a JavaScript array of strings
        
    Returns:
        A list of strings extracted from the array
        
    Example:
        >>> extract_string_array('["react", "nextjs"]')
        ['react', 'nextjs']
        >>> extract_string_array("['angular', 'vue']")
        ['angular', 'vue']
    """
    matches = re.findall(r'["\']([^"\']*)["\']', array_str)
    return matches

def remove_nextjs_imports(content: str) -> str:
    """Remove Next.js-specific imports from the content.
    
    Args:
        content: The markdown/MDX content to process
        
    Returns:
        The content with Next.js imports removed
        
    Example:
        >>> content = 'import { getCustomStaticPath } from "@/utils/getCustomStaticPath";\nOther content'
        >>> remove_nextjs_imports(content)
        'Other content'
    """
    for pattern in NEXTJS_IMPORT_PATTERNS:
        content = re.sub(pattern, '', content, flags=re.MULTILINE)
    return content

def remove_imports(content: str, file_path: Path | None = None) -> str:
    """Remove specific imports while preserving code blocks.
    
    Args:
        content: The markdown/MDX content to process
        file_path: Optional path to the file being processed, used for logging
        
    Returns:
        The content with specified imports removed
        
    Example:
        >>> content = 'import schema from "./schema.json";\n```js\nimport foo from "bar"\n```\nText'
        >>> result = remove_imports(content)
        >>> '```js\\nimport foo from "bar"\\n```' in result
        True
        >>> 'import schema from "./schema.json"' in result
        False
    """
    parts = split_content_and_code_blocks(content)
    result = []
    
    # Pattern to find all imports for logging
    all_imports_pattern = re.compile(r'^import\s+.*?;?\s*$', re.MULTILINE)
    
    # Collect all unfiltered imports across all non-code blocks
    unfiltered_imports = []
    
    for part, is_code_block in parts:
        if not is_code_block:
            # Get all imports in this non-code block
            imports_to_check = [m.group(0).strip() for m in all_imports_pattern.finditer(part)]
            
            # Remove the imports we know we want to remove
            filtered_part = part
            for pattern in IMPORT_PATTERNS:
                filtered_part = re.sub(pattern, '', filtered_part, flags=re.MULTILINE)
            
            # After removal, check which imports are still present
            remaining_imports = [m.group(0).strip() for m in all_imports_pattern.finditer(filtered_part)]
            
            # Only add to unfiltered_imports if the import wasn't matched by any of our patterns
            for imp in remaining_imports:
                should_log = True
                for pattern in IMPORT_PATTERNS:
                    if re.search(pattern, imp + '\n', re.MULTILINE):
                        should_log = False
                        break
                if should_log:
                    unfiltered_imports.append(imp)
            
            result.append(filtered_part)
        else:
            result.append(part)
    
    # Log all unfiltered imports together if any were found
    if unfiltered_imports and file_path:
        print(f"\nFile: {file_path}")
        print("Unfiltered imports:")
        for imp in unfiltered_imports:
            print(f"  {imp}")
    
    return ''.join(result) 
