"""Functions for handling component and JSX processing in markdown/MDX content."""

import re
import json
from pathlib import Path
from bs4 import BeautifulSoup
from .code_blocks import split_content_and_code_blocks

def embed_schema(content: str, file_path: Path) -> str:
    """Embed JSON schema from an imported file into the markdown content.
    
    This function finds schema imports in the content, reads the referenced JSON files,
    and embeds their content directly in markdown code blocks.
    
    Args:
        content: The markdown/MDX content to process
        file_path: Path to the current file, used to resolve relative schema paths
        
    Returns:
        The content with schema imports replaced by embedded JSON
        
    Example:
        >>> content = '''
        ... import schema from './schema.json';
        ... <pre><code>{JSON.stringify(schema, null, 2)}</code></pre>
        ... '''
        >>> # Assuming schema.json exists and contains {"foo": "bar"}
        >>> result = embed_schema(content, Path('test.mdx'))
        >>> '```json\\n{\\n  "foo": "bar"\\n}\\n```' in result
        True
    """
    # Find schema imports
    schema_import_pattern = re.compile(r'import\s+(\w+)\s+from\s+[\'"]([^\'\"]+\.json)[\'"]')
    matches = schema_import_pattern.finditer(content)
    
    for match in matches:
        var_name = match.group(1)
        schema_path = match.group(2)
        
        # Resolve the schema path relative to the file
        schema_file = file_path.parent / schema_path
        if not schema_file.exists():
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

def remove_overview_components(content: str) -> str:
    """Remove Overview component tags from the content.
    
    Args:
        content: The markdown/MDX content to process
        
    Returns:
        The content with Overview components removed
        
    Example:
        >>> content = '<Overview childPageNodes={nodes} />\nOther content'
        >>> remove_overview_components(content)
        'Other content'
    """
    return re.sub(
        r'<Overview\s+childPageNodes\s*=\s*{[^}]+}\s*/>\s*\n?',
        '',
        content,
        flags=re.IGNORECASE | re.MULTILINE
    )

def convert_ui_table_to_markdown(content: str) -> str:
    """Convert @aws-amplify/ui-react Table components to markdown tables.
    
    Args:
        content: The markdown/MDX content to process
        
    Returns:
        The content with UI tables converted to markdown format
        
    Example:
        >>> content = '''
        ... <Table>
        ...   <TableHead>
        ...     <TableRow>
        ...       <TableCell>Header</TableCell>
        ...     </TableRow>
        ...   </TableHead>
        ...   <TableBody>
        ...     <TableRow>
        ...       <TableCell>Data</TableCell>
        ...     </TableRow>
        ...   </TableBody>
        ... </Table>
        ... '''
        >>> result = convert_ui_table_to_markdown(content)
        >>> '| Header |' in result
        True
        >>> '| Data |' in result
        True
    """
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
    """Convert Card components to markdown format with frontmatter.
    
    Args:
        content: The markdown/MDX content to process
        
    Returns:
        The content with Card components converted to markdown format
        
    Example:
        >>> content = '''
        ... <Card variation="outlined">
        ...   <Flex>
        ...     <Heading>Title</Heading>
        ...     <Text>Description</Text>
        ...   </Flex>
        ... </Card>
        ... '''
        >>> result = convert_cards_to_markdown(content)
        >>> '> ### Title' in result
        True
        >>> '> Description' in result
        True
    """
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

def embed_protected_redaction_message(content: str, workspace_root: Path) -> str:
    """Embed protected redaction messages directly in markdown format.
    
    Args:
        content: The markdown/MDX content to process
        workspace_root: Path to the workspace root for resolving imports
        
    Returns:
        The content with protected redaction messages embedded as markdown
    """
    # First check if we need to process any redaction messages
    if not re.search(r'<ProtectedRedactionGen[12]Message\s*/>', content):
        return content

    # Try to read the message component file
    message_file = workspace_root / "src/protected/ProtectedRedactionMessage/index.tsx"
    if not message_file.exists():
        return content

    try:
        # Read the message component file
        message_content = message_file.read_text(encoding='utf-8')
        
        # Extract Gen1 and Gen2 message components
        message_components = {}
        for gen in ['1', '2']:
            component_pattern = re.compile(
                rf'export\s+const\s+ProtectedRedactionGen{gen}Message\s*=\s*\(\)\s*=>\s*\(\s*'
                r'<Callout\s+warning[^>]*>\s*([\s\S]*?)\s*</Callout>\s*\)',
                re.DOTALL
            )
            match = component_pattern.search(message_content)
            if match:
                # Extract the content and convert to markdown
                callout_content = match.group(1)
                
                # Convert paragraph tags to newlines
                md_content = re.sub(r'<p>(.*?)</p>', r'\1\n', callout_content)
                
                # Convert code tags
                md_content = re.sub(r'<code>(.*?)</code>', r'`\1`', md_content)
                
                # Convert list items
                md_content = re.sub(r'<ul>\s*([\s\S]*?)\s*</ul>', lambda m: '\n' + re.sub(r'<li>(.*?)</li>', r'- \1', m.group(1)), md_content)
                
                # Clean up any remaining HTML tags
                md_content = re.sub(r'<[^>]+>', '', md_content)
                
                # Clean up whitespace and empty lines
                md_content = re.sub(r'\n\s*\n\s*\n', '\n\n', md_content)
                md_content = md_content.strip()
                
                # Format as GitHub-flavored markdown warning with proper quoting
                lines = md_content.split('\n')
                quoted_lines = [f"> {line}" if line.strip() else ">" for line in lines]
                formatted_message = f"\n\n> [!WARNING]\n" + "\n".join(quoted_lines) + "\n\n"
                
                message_components[f'Gen{gen}'] = formatted_message
        
        # First remove the imports
        content = re.sub(
            r'^import\s*{\s*ProtectedRedactionGen[12]Message\s*}\s*from\s*[\'"]@/protected/ProtectedRedactionMessage[\'"].*?\n',
            '',
            content,
            flags=re.MULTILINE
        )
        
        # Then replace each component usage with its markdown
        for gen, message in message_components.items():
            content = re.sub(
                rf'<ProtectedRedaction{gen}Message\s*/>\s*\n?',
                message,
                content,
                flags=re.MULTILINE
            )
        
        return content
            
    except Exception as e:
        print(f"Error processing protected redaction messages: {e}")
        return content 

def remove_jsx_comments(content: str) -> str:
    """Remove JSX-style comments while preserving code blocks.
    
    Args:
        content: The markdown/MDX content to process
        
    Returns:
        The content with JSX comments removed
        
    Example:
        >>> content = 'Some text\n{/* A comment */}\nMore text'
        >>> remove_jsx_comments(content)
        'Some text\nMore text'
    """
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
