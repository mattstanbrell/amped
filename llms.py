import os
import re
import json
from pathlib import Path
import yaml
from bs4 import BeautifulSoup
import ast

# List of supported platforms
PLATFORMS = ["angular", "javascript", "nextjs", "react", 
             "react-native", "vue", "android", "swift", "flutter"]

# Regex for extracting meta exports and specific fields
META_REGEX = re.compile(
    r"export\s+const\s+meta\s*=\s*({[\s\S]*?});",
    re.MULTILINE | re.DOTALL
)

TITLE_REGEX = re.compile(r'["\']?title["\']?\s*:\s*["\']([^"\']*)["\']')
DESCRIPTION_REGEX = re.compile(r'["\']?description["\']?\s*:\s*["\']([^"\']*)["\']')
PLATFORMS_REGEX = re.compile(r'["\']?platforms["\']?\s*:\s*\[(.*?)\]', re.DOTALL)

def extract_string_array(array_str: str) -> list[str]:
    """Extract strings from a JavaScript array string."""
    # Find all quoted strings, handling both single and double quotes
    matches = re.findall(r'["\']([^"\']*)["\']', array_str)
    return matches

def remove_nextjs_imports(content: str) -> str:
    """Remove Next.js-specific imports from the content."""
    # List of patterns to remove
    import_patterns = [
        r'^import\s*{\s*getCustomStaticPath\s*}\s*from\s*[\'"]@/utils/getCustomStaticPath[\'"];\s*\n?',
        r'^import\s*{\s*getChildPageNodes\s*}\s*from\s*[\'"]@/utils/getChildPageNodes[\'"];\s*\n?'
    ]
    
    # Remove each pattern
    for pattern in import_patterns:
        content = re.sub(pattern, '', content, flags=re.MULTILINE)
    
    return content

def remove_nextjs_exports(content: str) -> str:
    """Remove Next.js-specific exports from the content."""
    def find_matching_brace(text: str, start: int) -> int:
        """Find the matching closing brace, handling nested braces."""
        stack = []
        i = start
        while i < len(text):
            if text[i] == '{':
                stack.append(i)
            elif text[i] == '}':
                if stack:
                    stack.pop()
                    if not stack:  # Found the matching brace
                        return i
            i += 1
        return -1

    # Pattern to find the start of export blocks
    export_start_pattern = re.compile(
        r'^export\s+(?:'
        r'const\s+(?:getStaticPaths|getStaticProps)|'
        r'(?:async\s+)?function\s+(?:getStaticPaths|getStaticProps)'
        r')(?:\s*=\s*(?:async\s+)?\([^)]*\)\s*=>)?\s*(?:\([^)]*\))?\s*{',
        re.MULTILINE
    )

    result = []
    last_end = 0
    
    while True:
        # Find next export block start
        match = export_start_pattern.search(content, last_end)
        if not match:
            break
            
        start_pos = match.start()
        brace_start = match.end() - 1  # Position of the opening brace
        
        # Find matching closing brace
        end_pos = find_matching_brace(content, brace_start)
        if end_pos == -1:
            break
            
        # Add content up to this export block
        result.append(content[last_end:start_pos])
        
        # Skip past this block and any following semicolon
        last_end = end_pos + 1
        while last_end < len(content) and content[last_end].isspace():
            last_end += 1
        if last_end < len(content) and content[last_end] == ';':
            last_end += 1
    
    # Add remaining content
    result.append(content[last_end:])
    
    # Join and clean up multiple empty lines
    result = ''.join(result)
    result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)
    
    return result

def find_matching_filter_end(text: str, start: int) -> int:
    """Find the matching closing InlineFilter tag, handling nested filters."""
    stack = []
    i = start
    in_quotes = False
    quote_char = None
    
    # Push the initial opening tag onto the stack
    stack.append(start)
    
    while i < len(text):
        # Skip over quoted sections
        if text[i] in ['"', "'"] and (i == 0 or text[i-1] != '\\'):
            if not in_quotes:
                in_quotes = True
                quote_char = text[i]
            elif text[i] == quote_char:
                in_quotes = False
                quote_char = None
        
        if not in_quotes:
            # Look for opening tags
            if i + len('<inlinefilter') <= len(text):
                next_chunk = text[i:i+len('<inlinefilter')].lower()
                if next_chunk == '<inlinefilter':
                    stack.append(i)
                    i += len('<inlinefilter') - 1
            
            # Look for closing tags
            elif i + len('</inlinefilter>') <= len(text):
                next_chunk = text[i:i+len('</inlinefilter>')].lower()
                if next_chunk == '</inlinefilter':
                    stack.pop()
                    if not stack:  # Found the matching end tag
                        return i
                    i += len('</inlinefilter') - 1
        
        i += 1
        
        # Debug output for tag matching
        # if i % 1000 == 0:  # Print every 1000 characters to avoid spam
            # print(f"Current position: {i}, Stack depth: {len(stack)}")
            # print(f"Next 20 chars: {text[i:i+20]}")
    
    # If we get here, we didn't find a matching end tag
    # print(f"Failed to find closing tag. Stack depth: {len(stack)}")
    # if stack:
        # context_start = max(0, stack[-1] - 50)
        # context_end = min(len(text), stack[-1] + 50)
        # print(f"Context around last opening tag:\n{text[context_start:context_end]}")
    
    return -1

def process_inline_filters(content: str, current_platform: str) -> str:
    """Process InlineFilter blocks in MDX content using regex."""
    # print(f"\nProcessing inline filters for platform: {current_platform}")
    
    def find_matching_end(text: str, start: int) -> int:
        """Find the matching closing InlineFilter tag, handling nested tags."""
        count = 1  # We start after an opening tag
        pos = start
        
        while count > 0 and pos < len(text):
            # Find next opening or closing tag (case insensitive)
            open_tag = -1
            close_tag = -1
            
            # Look for next tags after current position
            text_lower = text.lower()
            temp_pos = pos
            while temp_pos < len(text):
                next_open = text_lower.find('<inlinefilter', temp_pos)
                next_close = text_lower.find('</inlinefilter>', temp_pos)
                
                if next_open == -1 and next_close == -1:
                    break
                    
                if next_open != -1 and (next_close == -1 or next_open < next_close):
                    open_tag = next_open
                    temp_pos = next_open + len('<inlinefilter')
                    break
                    
                if next_close != -1:
                    close_tag = next_close
                    temp_pos = next_close + len('</inlinefilter>')
                    break
            
            # No more tags found
            if open_tag == -1 and close_tag == -1:
                return -1
                
            # Found a closing tag first
            if (close_tag != -1 and open_tag == -1) or (close_tag != -1 and close_tag < open_tag):
                count -= 1
                pos = close_tag + len('</inlinefilter>')
            # Found an opening tag first
            elif open_tag != -1:
                count += 1
                pos = open_tag + len('<inlinefilter')
        
        return pos if count == 0 else -1
    
    def process_recursive(text: str, depth: int = 0) -> str:
        indent = "  " * depth
        # print(f"{indent}Processing at depth {depth}")
        
        result = []
        pos = 0
        
        while pos < len(text):
            # Find next InlineFilter start (case insensitive)
            start_tag = text.lower().find('<inlinefilter', pos)
            if start_tag == -1:
                # No more filters, add remaining content
                result.append(text[pos:])
                break
            
            # Add content up to the tag
            result.append(text[pos:start_tag])
            
            # Find the filters attribute
            filters_start = text.lower().find('filters=', start_tag)
            if filters_start == -1:
                pos = start_tag + 1
                continue
                
            # Find the end of the opening tag
            tag_end = text.find('>', filters_start)
            if tag_end == -1:
                pos = start_tag + 1
                continue
                
            # Extract platforms string
            platforms_str = text[filters_start:tag_end]
            platforms = re.findall(r'["\']([a-zA-Z0-9-]+)["\']', platforms_str)
            # print(f"{indent}Found InlineFilter with platforms: {platforms}")
            
            # Find the matching end tag
            content_start = tag_end + 1
            content_end = find_matching_end(text, content_start)
            
            if content_end == -1:
                # print(f"{indent}Warning: No matching end tag found")
                pos = start_tag + 1
                continue
            
            # Get the content between tags
            inner_content = text[content_start:content_end - len('</inlinefilter>')]
            
            # Include content if either:
            # 1. No platforms specified (empty filter) - include for all platforms
            # 2. Current platform is in the specified platforms list
            should_include = not platforms or current_platform in platforms
            
            if should_include:
                # print(f"{indent}Including content for {current_platform}")
                # Recursively process any nested filters
                processed_content = process_recursive(inner_content, depth + 1)
                result.append(processed_content)
            # else:
                # print(f"{indent}Excluding content for {current_platform} (not in {platforms})")
            
            # Move past this entire block
            pos = content_end
        
        return ''.join(result).strip()
    
    # Process the content recursively
    result = process_recursive(content)
    
    # Clean up multiple empty lines
    result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)
    
    return result.strip()

def remove_overview_components(content: str) -> str:
    """Remove Overview component tags from the content."""
    return re.sub(
        r'<Overview\s+childPageNodes\s*=\s*{[^}]+}\s*/>\s*\n?',
        '',
        content,
        flags=re.IGNORECASE | re.MULTILINE
    )

def embed_schema(content: str, file_path: Path) -> str:
    """Embed JSON schema from an imported file into the markdown content."""
    # Find schema imports
    schema_import_pattern = re.compile(r'import\s+(\w+)\s+from\s+[\'"]([^\'\"]+\.json)[\'"]')
    matches = schema_import_pattern.finditer(content)
    
    for match in matches:
        var_name = match.group(1)
        schema_path = match.group(2)
        
        # Resolve the schema path relative to the file
        schema_file = file_path.parent / schema_path
        if not schema_file.exists():
            # print(f"Warning: Schema file not found: {schema_file}")
            continue
            
        try:
            # Read and parse the schema
            schema_content = schema_file.read_text(encoding='utf-8')
            schema_json = json.loads(schema_content)
            formatted_schema = json.dumps(schema_json, indent=2)
            
            # Create markdown code block
            schema_block = f"```json\n{formatted_schema}\n```"
            
            # Replace the JSX-style schema embedding with markdown
            content = re.sub(
                r'<pre><code[^>]*>\s*{JSON\.stringify\(' + var_name + r'[^}]+}\s*</code></pre>',
                schema_block,
                content
            )
            
            # Remove the schema import
            content = re.sub(r'import\s+' + var_name + r'\s+from\s+[\'"]' + re.escape(schema_path) + r'[\'"];\s*\n?', '', content)
            
        except Exception as e:
            print(f"Error processing schema file {schema_file}: {e}")
            
    return content

def convert_ui_table_to_markdown(content: str) -> str:
    """Convert @aws-amplify/ui-react Table components to markdown tables."""
    # First find all Table components
    table_pattern = re.compile(
        r'<Table[^>]*>.*?</Table>',
        re.DOTALL
    )
    
    def process_table(table_match: str) -> str:
        # Extract caption if present
        caption = ''
        caption_match = re.search(r'caption="([^"]*)"', table_match)
        if caption_match:
            caption = caption_match.group(1)
        
        # Process header
        header_pattern = re.compile(
            r'<TableHead>.*?<TableRow>(.*?)</TableRow>.*?</TableHead>',
            re.DOTALL
        )
        header_match = header_pattern.search(table_match)
        if not header_match:
            return table_match  # Return original if no header found
            
        # Extract header cells
        header_cells = []
        for cell in re.finditer(r'<TableCell[^>]*>(.*?)</TableCell>', header_match.group(1), re.DOTALL):
            cell_content = cell.group(1).strip()
            header_cells.append(cell_content)
            
        # Process body
        body_pattern = re.compile(
            r'<TableBody>(.*?)</TableBody>',
            re.DOTALL
        )
        body_match = body_pattern.search(table_match)
        if not body_match:
            return table_match  # Return original if no body found
            
        # Build markdown table
        markdown_rows = []
        
        # Add caption if present
        if caption:
            markdown_rows.append(f"\n{caption}\n")
            
        # Add header
        markdown_rows.append('| ' + ' | '.join(header_cells) + ' |')
        markdown_rows.append('|' + '---|' * len(header_cells))
        
        # Process each row in body
        row_pattern = re.compile(r'<TableRow[^>]*>(.*?)</TableRow>', re.DOTALL)
        for row_match in row_pattern.finditer(body_match.group(1)):
            row_cells = []
            for cell in re.finditer(r'<TableCell[^>]*>(.*?)</TableCell>', row_match.group(1), re.DOTALL):
                cell_content = cell.group(1)
                
                # Handle links
                cell_content = re.sub(
                    r'<a href="([^"]+)"[^>]*>(.*?)</a>',
                    r'[\2](\1)',
                    cell_content
                )
                
                # Handle strong tags
                cell_content = re.sub(
                    r'<strong>(.*?)</strong>',
                    r'**\1**',
                    cell_content
                )
                
                # Clean up any remaining HTML-like tags
                cell_content = re.sub(r'<[^>]+>', '', cell_content)
                cell_content = cell_content.strip()
                row_cells.append(cell_content)
                
            markdown_rows.append('| ' + ' | '.join(row_cells) + ' |')
            
        return '\n'.join(markdown_rows)
    
    # Replace each table with its markdown equivalent
    return table_pattern.sub(lambda m: process_table(m.group(0)), content)

def convert_cards_to_markdown(content: str) -> str:
    """Convert Card components to markdown format with frontmatter."""
    # First check if we're inside an AIConversation component
    ai_conversation_pattern = re.compile(
        r'<AIConversation[^>]*>.*?</AIConversation>',
        re.DOTALL
    )
    
    # Split content into AIConversation and non-AIConversation parts
    parts = []
    last_end = 0
    
    for match in ai_conversation_pattern.finditer(content):
        # Add non-AIConversation content before this match
        if match.start() > last_end:
            parts.append((content[last_end:match.start()], False))
        
        # Add AIConversation content
        parts.append((match.group(0), True))
        last_end = match.end()
    
    # Add remaining content
    if last_end < len(content):
        parts.append((content[last_end:], False))
    
    # Process each part
    result = []
    for part_content, is_ai_conversation in parts:
        if is_ai_conversation:
            # Preserve AIConversation content as is
            result.append(part_content)
        else:
            # Process cards in non-AIConversation content
            processed = part_content
            
            # Remove the Card import
            processed = re.sub(
                r'import\s*{\s*Card\s*}\s*from\s*[\'"]@aws-amplify/ui-react[\'"];\s*\n?',
                '',
                processed,
                flags=re.MULTILINE
            )
            
            # Handle column layouts first (outer wrapper)
            columns_pattern = re.compile(
                r'<Columns\s+columns=\{(\d+)\}>\s*([\s\S]*?)\s*</Columns>',
                re.DOTALL
            )
            
            def process_columns(match: str) -> str:
                columns_content = match.group(2).strip()
                
                # Process any cards within the columns
                card_pattern = re.compile(
                    r'<Card\s+variation="outlined">\s*([\s\S]*?)\s*</Card>',
                    re.DOTALL
                )
                
                def process_card(card_match: str) -> str:
                    card_content = card_match.group(1).strip()
                    
                    # Check for link pattern (Simple Link Cards)
                    link_pattern = re.compile(r'\[(.*?)\]\((.*?)\)([\s\S]*)', re.DOTALL)
                    link_match = link_pattern.search(card_content)
                    
                    if link_match:
                        title = link_match.group(1).strip()
                        link = link_match.group(2).strip()
                        description = link_match.group(3).strip()
                        return f"> [{title}]({link})\n>\n> {description}"
                    
                    # If no pattern matches, preserve as is
                    return f"> {card_content}"
                
                processed_content = card_pattern.sub(lambda m: process_card(m), columns_content)
                return processed_content
            
            # Process columns first
            processed = columns_pattern.sub(process_columns, processed)
            
            # Then process any remaining cards outside columns
            card_pattern = re.compile(
                r'<Card\s+variation="outlined">\s*([\s\S]*?)\s*</Card>',
                re.DOTALL
            )
            
            def process_remaining_card(match: str) -> str:
                card_content = match.group(1).strip()
                
                # Check for Feature Cards pattern
                feature_pattern = re.compile(
                    r'<Flex[^>]*>\s*<Heading[^>]*>(.*?)</Heading>\s*<Text>(.*?)</Text>\s*</Flex>',
                    re.DOTALL
                )
                feature_match = feature_pattern.search(card_content)
                
                if feature_match:
                    title = feature_match.group(1).strip()
                    description = feature_match.group(2).strip()
                    return f"> ### {title}\n>\n> {description}"
                
                # Check for Welcome Message Cards
                text_pattern = re.compile(r'<Text>(.*?)</Text>', re.DOTALL)
                text_match = text_pattern.search(card_content)
                
                if text_match:
                    content = text_match.group(1).strip()
                    return f"> {content}"
                
                # If no pattern matches, preserve as is
                return f"> {card_content}"
            
            processed = card_pattern.sub(process_remaining_card, processed)
            result.append(processed)
    
    return ''.join(result)

def process_fragments(content: str, file_path: Path, platform: str, workspace_root: Path) -> str:
    """Process fragment imports and components in MDX content."""
    # First embed any JSON schemas
    content = embed_schema(content, file_path)
    
    # Convert UI tables to markdown
    content = convert_ui_table_to_markdown(content)
    
    # Convert Cards to markdown
    content = convert_cards_to_markdown(content)
    
    # Track imported fragments
    fragment_imports = {}
    
    # Extract and remove imports
    import_pattern = re.compile(
        r'^import\s+([a-zA-Z0-9_]+)\s+from\s+[\'"](?:/)?([^\'\"]+)[\'"]\s*;\s*\n?',
        re.MULTILINE
    )
    
    def import_repl(match):
        alias = match.group(1)
        source_path = match.group(2)
        # Handle both absolute and relative paths
        if source_path.startswith('src/'):
            fragment_imports[alias] = workspace_root / source_path
        else:
            # For absolute paths starting with /, strip the leading /
            fragment_imports[alias] = workspace_root / source_path.lstrip('/')
        return ''  # Remove the import
    
    content = import_pattern.sub(import_repl, content)
    
    # Process Fragments components
    fragments_pattern = re.compile(
        r'<Fragments\s+fragments\s*=\s*({[\s\S]*?})\s*/>\s*\n?'
    )
    
    def fragments_repl(match):
        fragments_str = match.group(1)
        
        # Extract platform to alias mapping using regex
        # Handle both forms: {platform: alias} and {'platform': alias}
        mapping_pattern = re.compile(r'[\'"]?([\w-]+)[\'"]?\s*:\s*(\w+)')
        mappings = mapping_pattern.findall(fragments_str)
        
        # Find the matching fragment for current platform
        fragment_path = None
        fragment_content = ''
        
        for frag_platform, alias in mappings:
            if frag_platform == platform and alias in fragment_imports:
                fragment_path = fragment_imports[alias]
                break
        
        if fragment_path and fragment_path.exists():
            try:
                print(f"Processing fragment: {fragment_path}")
                # Read and process the fragment file
                fragment_content = fragment_path.read_text(encoding='utf-8')
                # Process any nested fragments in the fragment
                fragment_content = process_fragments(
                    fragment_content, 
                    fragment_path, 
                    platform,
                    workspace_root
                )
                # Process any inline filters in the fragment
                fragment_content = process_inline_filters(fragment_content, platform)
                return fragment_content.strip()
            except Exception as e:
                # print(f"Warning: Error processing fragment {fragment_path}: {e}")
                return ''
        # else:
        #     if fragment_path:
        #         # print(f"Warning: Fragment file not found: {fragment_path}")
        #     else:
        #         # print(f"Warning: No matching fragment found for platform {platform}")
        
        return ''  # Remove the Fragments component if no matching content
    
    content = fragments_pattern.sub(fragments_repl, content)
    return content

def split_content_and_code_blocks(content: str) -> list[tuple[str, bool]]:
    """Split content into alternating non-code and code blocks.
    Returns a list of (content, is_code_block) tuples."""
    parts = []
    current_pos = 0
    
    # Match code blocks that may have an optional language specifier
    # e.g. ```python, ```ts, ```json, or just ```
    code_block_pattern = re.compile(
        r'(```(?:[a-zA-Z]+\s*\n|[a-zA-Z]*\s*\n|)\s*[\s\S]*?```)',
        re.DOTALL
    )
    
    for match in code_block_pattern.finditer(content):
        # Add non-code content before this block
        if match.start() > current_pos:
            parts.append((content[current_pos:match.start()], False))
        
        # Add the code block
        parts.append((match.group(0), True))
        current_pos = match.end()
    
    # Add any remaining non-code content
    if current_pos < len(content):
        parts.append((content[current_pos:], False))
    
    return parts

def remove_imports(content: str, file_path: Path | None = None) -> str:
    """Remove specific imports while preserving code blocks."""
    parts = split_content_and_code_blocks(content)
    result = []
    
    # List of specific import patterns to remove
    import_patterns = [
        # Next.js specific imports
        r'^import\s*{\s*getCustomStaticPath\s*}\s*from\s*[\'"]@/utils/getCustomStaticPath[\'"];\s*\n?',
        r'^import\s*{\s*getChildPageNodes\s*}\s*from\s*[\'"]@/utils/getChildPageNodes[\'"];\s*\n?',
        r'^import\s*{\s*getApiStaticPath\s*}\s*from\s*[\'"]@/utils/getApiStaticPath[\'"];\s*\n?',
        # Schema imports - updated to handle both formats with optional semicolon
        r'^import\s+\w+\s+from\s+[\'"].*?amplify-outputs-schema-v1\.json[\'"];?\s*\n?',
        r'^import\s+schema\s+from\s+[\'"]\.?/.*?amplify-outputs-schema-v1\.json[\'"];?\s*\n?',
        # All imports from Icons directory
        r'^import\s*{[^}]+}\s*from\s*[\'"]@/components/Icons/[^\'"]+[\'"];?\s*$\n?',
        # AWS Amplify UI and AI imports - handle all variations with flexible whitespace
        r'^import\s*.*?\s*from\s*[\'"]@aws-amplify/ui-react[\'"].*?\n',
        r'^import\s*.*?\s*from\s*[\'"]@aws-amplify/ui-react-ai[\'"].*?\n',
        r'^import\s*.*?\s*from\s*[\'"]@/components/AI[^\'"]*[\'"].*?\n',
        # UI Wrapper imports
        r'^import\s*.*?\s*from\s*[\'"]@/components/UIWrapper[\'"].*?\n',
        # Fragment imports
        r'^import\s+[a-zA-Z0-9_]+\s+from\s*[\'"](?:/)?src/fragments/.*?[\'"].*?\n',
        # Protected redaction message imports - updated pattern
        r'^import\s*{\s*ProtectedRedactionGen[12]Message\s*}\s*from\s*[\'"]@/protected/ProtectedRedactionMessage[\'"].*?\n'
    ]
    
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
            for pattern in import_patterns:
                filtered_part = re.sub(pattern, '', filtered_part, flags=re.MULTILINE)
            
            # After removal, check which imports are still present
            remaining_imports = [m.group(0).strip() for m in all_imports_pattern.finditer(filtered_part)]
            
            # Only add to unfiltered_imports if the import wasn't matched by any of our patterns
            for imp in remaining_imports:
                should_log = True
                for pattern in import_patterns:
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

def remove_jsx_comments(content: str) -> str:
    """Remove JSX-style comments while preserving code blocks."""
    parts = split_content_and_code_blocks(content)
    result = []
    
    for part, is_code_block in parts:
        if not is_code_block:
            # Remove JSX comments outside code blocks
            part = re.sub(r'{/\*.*?\*/}', '', part, flags=re.DOTALL)
            # Clean up empty lines
            part = re.sub(r'\n\s*\n\s*\n', '\n\n', part)
        result.append(part)
    
    return ''.join(result).strip()

def extract_meta_from_file(file_path: Path) -> tuple[dict, str]:
    """Extract meta information from an MDX file."""
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # First embed any schemas - do this BEFORE removing imports
        content = embed_schema(content, file_path)
        
        # Then remove imports and exports
        content = remove_imports(content, file_path)
        content = remove_nextjs_exports(content)
        content = remove_overview_components(content)
        content = remove_jsx_comments(content)
        
        match = META_REGEX.search(content)
        if match:
            meta_str = match.group(1)
            
            # Extract just the fields we need
            meta_dict = {}
            
            # Extract title
            title_match = TITLE_REGEX.search(meta_str)
            if title_match:
                meta_dict['title'] = title_match.group(1)
            
            # Extract description
            desc_match = DESCRIPTION_REGEX.search(meta_str)
            if desc_match:
                meta_dict['description'] = desc_match.group(1)
            
            # Extract platforms
            platforms_match = PLATFORMS_REGEX.search(meta_str)
            if platforms_match:
                platforms_str = platforms_match.group(1)
                meta_dict['platforms'] = extract_string_array(platforms_str)
            
            # Remove the meta export from content
            content = META_REGEX.sub('', content)
            
            # Clean up any remaining empty lines
            content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
            
            return meta_dict, content
        return {}, content
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return {}, ""

def convert_meta_to_frontmatter(meta: dict) -> str:
    """Convert meta dictionary to YAML frontmatter."""
    # We only want title and description in the frontmatter
    frontmatter = {}
    if 'title' in meta:
        frontmatter['title'] = meta['title']
    if 'description' in meta:
        frontmatter['description'] = meta['description']
    
    if not frontmatter:
        return ""
    
    try:
        # Convert to YAML, preserving order
        yaml_str = yaml.dump(frontmatter, sort_keys=False, allow_unicode=True)
        return f"---\n{yaml_str}---\n\n"
    except Exception as e:
        print(f"Error converting meta to YAML: {e}")
        return ""

def extract_platforms_from_file(file_path: Path) -> list[str] | None:
    """Extract platforms array from index.mdx meta."""
    meta, _ = extract_meta_from_file(file_path)
    if "platforms" in meta and isinstance(meta["platforms"], list):
        return meta["platforms"]
    return None

def process_directory(in_dir: Path, out_dir: Path, platform: str):
    """Process a directory and its subdirectories."""
    # Skip gen1 directory
    if "gen1" in in_dir.parts:
        return
        
    # Check index.mdx for platform filtering
    index_file = in_dir / "index.mdx"
    if index_file.is_file():
        dir_platforms = extract_platforms_from_file(index_file)
        # If meta.platforms is specified and doesn't include our platform, skip
        if dir_platforms and platform not in dir_platforms:
            return
        
        try:
            # First get the meta and raw content
            meta, content = extract_meta_from_file(index_file)
            if meta:
                # Get workspace root for fragment processing
                workspace_root = index_file.parent
                while workspace_root.name != "src" and workspace_root.parent != workspace_root:
                    workspace_root = workspace_root.parent
                workspace_root = workspace_root.parent
                
                # Process fragments with the current platform
                content = process_fragments(content, index_file, platform, workspace_root)
                
                # Process InlineFilter blocks
                content = process_inline_filters(content, platform)
                
                # Create output directory
                out_dir.mkdir(parents=True, exist_ok=True)
                
                # Generate frontmatter and write to output file
                frontmatter = convert_meta_to_frontmatter(meta)
                output_path = out_dir / "index.md"
                output_path.write_text(frontmatter + content, encoding='utf-8')
                
                # if not content.strip():
                    # print(f"Warning: Empty content after processing {index_file}")
        except Exception as e:
            print(f"Error processing {index_file}: {e}")
    
    # Process subdirectories
    for item in in_dir.iterdir():
        if item.is_dir():
            # Replace [platform] with the actual platform in the output path
            out_subdir = out_dir
            if item.name == "[platform]":
                out_subdir = out_dir
            else:
                out_subdir = out_dir / item.name
            process_directory(item, out_subdir, platform)

def process_single_file(mdx_path: str, platform: str):
    """Process a single MDX file and output the corresponding MD file."""
    mdx_file = Path(mdx_path)
    if not mdx_file.exists():
        print(f"Error: File {mdx_path} does not exist!")
        return
    
    try:
        # Get meta and raw content
        meta, content = extract_meta_from_file(mdx_file)
            
        # Get workspace root for fragment processing
        workspace_root = mdx_file.parent
        while workspace_root.name != "src" and workspace_root.parent != workspace_root:
            workspace_root = workspace_root.parent
        workspace_root = workspace_root.parent
        
        # Process fragments with the current platform
        processed_content = process_fragments(content, mdx_file, platform, workspace_root)
        
        # Create output path
        output_path = mdx_file.with_suffix('.md')
        
        # Generate frontmatter
        frontmatter = convert_meta_to_frontmatter(meta)
        
        # Write the output file
        output_path.write_text(frontmatter + processed_content, encoding='utf-8')
            
    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback
        traceback.print_exc()

def main():
    import sys
    
    # Check if specific file and platform are provided
    if len(sys.argv) == 3:
        mdx_path = sys.argv[1]
        platform = sys.argv[2]
        process_single_file(mdx_path, platform)
            
    # Original directory processing mode
    else:
        if len(sys.argv) != 1:
            print("Usage:")
            print("  For directory processing: python llms.py")
            print("  For single file: python llms.py <mdx_file_path> <platform>")
            print("Example: python llms.py src/pages/[platform]/start/connect-to-aws-resources/index.mdx nextjs")
            return
            
        # Process each platform
        src_dir = Path("src/pages/[platform]")
        if not src_dir.exists():
            print(f"Error: Source directory {src_dir} not found!")
            return
            
        for platform in PLATFORMS:
            print(f"Processing platform: {platform}")
            
            # Create output directory for this platform
            out_dir = Path(f"llms-docs/{platform}")
            
            # Process the directory tree
            process_directory(src_dir, out_dir, platform)
            
        print("Processing complete")

if __name__ == "__main__":
    main() 
