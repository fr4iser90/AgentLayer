"""Grep tool for AgentLayer - search file contents with regular expressions."""

import re
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Configure logging
logger = logging.getLogger(__name__)

# Tool configuration - matching DeepSeek Harness defaults
GREP_MAX_MATCHES = 250
GREP_MAX_LINE_BYTES = 2000

def grep_handler(args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> str:
    """
    Execute grep search with the given arguments.
    
    Args:
        args: Dictionary containing pattern, path, and include parameters
        context: Optional context dictionary
        
    Returns:
        JSON string with search results or error information
    """
    try:
        pattern = args.get('pattern', '')
        path = args.get('path')
        include = args.get('include')
        
        # Validate input
        if not pattern:
            return json.dumps({
                "ok": False,
                "error": "pattern must be a non-empty string"
            })
        
        # Determine search path
        if path:
            search_path = Path(path)
        else:
            # Default to current working directory
            search_path = Path.cwd()
            
        # Perform the search
        matches = perform_grep_search(search_path, pattern, include)
        
        # Format results for display
        result = format_grep_result_for_ui(matches, len(matches))
        
        # Return structured data for the tool
        return json.dumps({
            "ok": True,
            "result": result,
            "matches": matches
        })
        
    except Exception as e:
        logger.error(f"Grep tool execution failed: {str(e)}")
        return json.dumps({
            "ok": False,
            "error": f"grep search failed: {str(e)}"
        })

def perform_grep_search(search_path: Path, pattern: str, include: str = None) -> List[Dict[str, Any]]:
    """
    Perform the actual grep search in files.
    
    Args:
        search_path: Path to search in
        pattern: Regular expression pattern to search for
        include: Include pattern (file extension filter)
        
    Returns:
        List of matching results
    """
    matches = []
    compiled_pattern = re.compile(pattern)
    
    try:
        # If search_path is a file, search only that file
        if search_path.is_file():
            if include and not matches_include_pattern(search_path.name, include):
                return matches
            
            file_matches = search_file(search_path, compiled_pattern)
            matches.extend(file_matches)
        else:
            # Search all files recursively
            for file_path in search_path.rglob('*'):
                if file_path.is_file():
                    if include and not matches_include_pattern(file_path.name, include):
                        continue
                    
                    file_matches = search_file(file_path, compiled_pattern)
                    matches.extend(file_matches)
    except Exception as e:
        logger.error(f"Error during grep search: {str(e)}")
        raise Exception(f"Error during grep search: {str(e)}")
    
    return matches

def matches_include_pattern(filename: str, include_pattern: str) -> bool:
    """
    Check if filename matches the include pattern.
    
    Args:
        filename: Name of the file to check
        include_pattern: Include pattern (e.g., "*.py", "*.{js,ts}")
        
    Returns:
        True if file matches the pattern
    """
    # For simplicity, we'll handle basic extension matching
    if include_pattern:
        if include_pattern.startswith('*') and include_pattern.endswith('*'):
            # Contains pattern like "*test*"
            return include_pattern[1:-1] in filename
        elif include_pattern.startswith('*'):
            # Ends with pattern like "*.py"
            return filename.endswith(include_pattern[1:])
        elif include_pattern.endswith('*'):
            # Starts with pattern like "src/*"
            return filename.startswith(include_pattern[:-1])
        elif '.' in include_pattern:
            # Exact extension match like "*.py"
            return filename.endswith(include_pattern[1:])
    
    return True  # If no include pattern, match everything

def search_file(file_path: Path, pattern: re.Pattern) -> List[Dict[str, Any]]:
    """
    Search for pattern in a single file.
    
    Args:
        file_path: Path to the file to search
        pattern: Compiled regular expression pattern
        
    Returns:
        List of matching results
    """
    matches = []
    line_number = 0
    
    try:
        with file_path.open('r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_number += 1
                if pattern.search(line):
                    matches.append({
                        'path': str(file_path),
                        'line_number': line_number,
                        'line': line.rstrip('\n')
                    })
    except Exception as e:
        # Log and skip files that can't be read
        logger.debug(f"Could not read file {file_path}: {str(e)}")
        pass
        
    return matches

def format_grep_results(matches: List[Dict[str, Any]]) -> str:
    """
    Format grep results in a readable way.
    
    Args:
        matches: List of matching results
        
    Returns:
        Formatted string of results
    """
    if not matches:
        return "No matches found"
    
    # Group by file
    file_groups = {}
    for match in matches:
        path = match['path']
        if path not in file_groups:
            file_groups[path] = []
        file_groups[path].append(match)
    
    # Format each file group
    formatted_lines = []
    for path, file_matches in file_groups.items():
        formatted_lines.append(path)
        for match in file_matches:
            formatted_lines.append(f"Line {match['line_number']}: {match['line']}")
        formatted_lines.append("")  # Empty line between files
    
    return "\n".join(formatted_lines)

def format_grep_result_for_ui(matches: List[Dict[str, Any]], total_matches: int = None) -> str:
    """
    Format results for UI display (similar to DeepSeek Harness format).
    
    Args:
        matches: List of matching results
        total_matches: Total number of matches (if available)
        
    Returns:
        Formatted string for UI display
    """
    if not matches:
        return "No matches found"
    
    if total_matches and len(matches) < total_matches:
        count_text = f"Found {len(matches)} of {total_matches} matches"
    else:
        count_text = f"Found {len(matches)} matches"
    
    # Group by file
    file_groups = {}
    for match in matches:
        path = match['path']
        if path not in file_groups:
            file_groups[path] = []
        file_groups[path].append(match)
    
    # Format each file group
    formatted_lines = [count_text]
    
    for path, file_matches in file_groups.items():
        formatted_lines.append(path)
        for match in file_matches:
            line_text = match['line']
            # Limit line length for display
            if len(line_text) > GREP_MAX_LINE_BYTES:
                line_text = line_text[:GREP_MAX_LINE_BYTES-3] + "..."
            formatted_lines.append(f"Line {match['line_number']}: {line_text}")
        formatted_lines.append("")  # Empty line between files
    
    return "\n".join(formatted_lines)

# Tool definition - following the structure used by other tools
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search file contents with a regular expression. Returns matching lines with line numbers, grouped by file. "
                          "Returns the first 250 matches inline; a capped result reports where the complete match list was saved. "
                          "Use read on a matched file for surrounding context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regular expression to search for (ripgrep syntax)."
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory to search. Defaults to the current working directory."
                    },
                    "include": {
                        "type": "string",
                        "description": "One glob filter for which files to search (e.g. \"*.ts\", \"*.{js,jsx}\"). Not a list; negation is not supported."
                    }
                },
                "required": ["pattern"]
            }
        },
    }
]

# Handler mapping
HANDLERS = {
    "grep": grep_handler
}

# Tool metadata
TOOL_ID = "agentlayer-grep"
TOOL_DOMAIN = "repository"
TOOL_LABEL = "File Search"
TOOL_DESCRIPTION = "Search for text patterns in files"
TOOL_TAGS = ["file", "search", "grep"]
TOOL_REQUIRES = ["filesystem"]
TOOL_SECRETS_REQUIRED = []