"""Utility functions for MDX processing."""

from pathlib import Path

def get_workspace_root(file_path: Path) -> Path:
    """Find the workspace root by looking for src directory.
    
    Args:
        file_path: Path to start searching from
        
    Returns:
        Path to the workspace root (directory containing src/)
        
    Example:
        >>> from pathlib import Path
        >>> # Create test directory structure
        >>> Path('test/src').mkdir(parents=True)
        >>> Path('test/src/file.mdx').touch()
        >>> root = get_workspace_root(Path('test/src/file.mdx'))
        >>> root.name == 'test'
        True
    """
    current = file_path.resolve()  # Resolve any symlinks and get absolute path
    while current != current.parent:  # Stop at root directory
        if (current / "src").is_dir():  # Check if src exists and is a directory
            return current
        if current.name == "src" and current.parent.is_dir():  # If we're in src, return parent
            return current.parent
        current = current.parent
    # If we can't find src directory, use the directory containing the file
    return file_path.parent 
