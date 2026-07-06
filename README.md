# MCP File System Server

A simple Model Context Protocol (MCP) server providing file system operations. This server offers a clean API for performing file system operations within a specified project directory, following the MCP protocol design.

## Overview

This MCP server enables AI assistants like Claude (via Claude Desktop) or other MCP-compatible systems to interact with your local file system. With these capabilities, AI assistants can:

- Read your existing code and project files
- Write new files with generated content
- Update and modify existing files with precision using exact string matching
- Make selective edits to code without rewriting entire files
- Delete files when needed
- Review repositories to provide analysis and recommendations
- Debug and fix issues in your codebase
- Generate complete implementations based on your specifications

All operations are securely contained within your specified project directory, giving you control while enabling powerful AI collaboration on your local files.

By connecting your AI assistant to your filesystem, you can transform your workflow from manual coding to a more intuitive prompting approach - describe what you need in natural language and let the AI generate, modify, and organize code directly in your project files.

## Features

- `list_directory`: List all files and directories in the project directory
- `read_file`: Read the contents of a file
- `save_file`: Write content to a file atomically
- `append_file`: Append content to the end of a file
- `delete_this_file`: Delete a specified file from the filesystem
- `edit_file`: Make selective edits using exact string matching
- `move_file`: Move or rename files and directories within the project
- `get_reference_projects`: Discover available reference projects
- `list_reference_directory`: List files in reference projects
- `read_reference_file`: Read files from reference projects
- `Structured Logging`: Comprehensive logging system with both human-readable and JSON formats

## Installation

```bash
# Clone the repository
git clone https://github.com/MarcusJellinghaus/mcp-workspace.git
cd mcp_workspace

# Create and activate a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies using pip with pyproject.toml
pip install -e .
```

## Running the Server

Once installed, you can use the `mcp-workspace` command directly:

```bash
mcp-workspace --project-dir /path/to/project [--reference-project NAME=/path/to/reference]... [--log-level LEVEL] [--log-file PATH] [--file-size-limit N]
```

### Command Line Arguments:

- `--project-dir`: (Required) Directory to serve files from
- `--reference-project`: (Optional) Add reference project in format name=/path/to/dir (repeatable, auto-renames duplicates)
- `--log-level`: (Optional) Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `--log-file`: (Optional) Path for structured JSON logs. If not specified, logs to mcp_workspace_{timestamp}.log in project_dir/logs/.
- `--file-size-limit`: (Optional) Default line limit for `check_file_size` when `max_lines` is omitted; must be > 0. Falls back to 600 when not set.

The server uses FastMCP for operation. The project directory parameter (`--project-dir`) is **required** for security reasons. All file operations will be restricted to this directory. Attempts to access files outside this directory will result in an error.

## Structured Logging

The server provides flexible logging options:

- Standard human-readable logs to console
- Structured JSON logs to file (default: `project_dir/logs/mcp_workspace_{timestamp}.log` or custom path with `--log-file`)
- Function call tracking with parameters, timing, and results
- Automatic error context capture
- Configurable log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Use `--console-only` to disable file logging

## Reference Projects

Reference projects allow you to provide AI assistants with read-only access to additional codebases or directories for context and reference. This feature enables the LLM to browse and read files from multiple projects while maintaining write access only to the main project directory.

### Features

- **Read-only access**: Reference projects can only be browsed and read from, never modified
- **Multiple projects**: Configure multiple reference projects simultaneously
- **Auto-discovery**: LLM can discover available reference projects
- **Security**: Same path validation and gitignore filtering as main project
- **Flexible paths**: Supports both relative and absolute paths

### Configuration

Use the `--reference-project` argument to add reference projects:

```bash
# Single reference project
mcp-workspace --project-dir ./my-project --reference-project docs=./documentation

# Multiple reference projects
mcp-workspace --project-dir ./my-project \
  --reference-project docs=./documentation \
  --reference-project examples=/home/user/examples \
  --reference-project libs=../shared-libraries

# Absolute paths
mcp-workspace --project-dir /path/to/main/project \
  --reference-project utils=/usr/local/utils \
  --reference-project config=/etc/myapp
```

### Auto-Rename Behavior

If you specify duplicate reference project names, they are automatically renamed with numeric suffixes:

```bash
# This configuration:
mcp-workspace --project-dir ./project \
  --reference-project docs=./docs1 \
  --reference-project docs=./docs2 \
  --reference-project docs=./docs3

# Results in these reference project names:
# - docs (points to ./docs1)
# - docs_2 (points to ./docs2)  
# - docs_3 (points to ./docs3)
```

### Startup Validation

The server validates reference projects at startup:

- **Valid references**: Added successfully and available to the LLM
- **Invalid references**: Logged as warnings, but server continues with valid ones
- **Path resolution**: Relative paths are resolved relative to the current working directory

### Use Cases

- **Documentation browsing**: Give the LLM access to project documentation or wikis
- **Code examples**: Reference example projects or templates
- **Shared libraries**: Browse common utility libraries or frameworks
- **Configuration files**: Access system or application configuration directories
- **Multi-project development**: Work on one project while referencing related projects

### Security Notes

- Reference projects are **strictly read-only** - no write, edit, or delete operations are possible
- All paths are validated to prevent directory traversal attacks
- Gitignore filtering is automatically applied to hide irrelevant files
- Path access is restricted to the specified reference project directories

## Integration Options

This server can be integrated with different Claude interfaces. Each requires a specific configuration.

## Claude Desktop App Integration

The Claude Desktop app can also use this file system server.

### Configuration Steps for Claude Desktop

1. **Locate the Claude Desktop configuration file**:
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

2. **Add the MCP server configuration** (create the file if it doesn't exist):

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "mcp-workspace",
      "args": [
        "--project-dir",
        "C:\\path\\to\\your\\specific\\project",
        "--reference-project",
        "docs=C:\\path\\to\\documentation",
        "--reference-project",
        "examples=C:\\path\\to\\examples",
        "--log-level",
        "INFO"
      ]
    }
  }
}
```

3. **Configuration notes**:
   - The `mcp-workspace` command should be available in your PATH after installation
   - You must specify an explicit project directory path in `--project-dir`
   - Replace the project directory path with your actual project path
   - The project directory should be the folder you want Claude to access

4. **Restart the Claude Desktop app** to apply changes

### Troubleshooting Claude Desktop Integration

- Check logs at: `%APPDATA%\Claude\logs` (Windows) or `~/Library/Application Support/Claude/logs` (macOS)
- Verify the `mcp-workspace` command is available in your PATH (run `mcp-workspace --help` to test)
- Ensure the specified project directory exists and is accessible
- Verify all paths in your configuration are correct

## Contributing

For development setup, testing, and contribution guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Available Tools

The server exposes the following MCP tools:

| Operation | Description | Example Prompt |
|-----------|-------------|----------------|
| `list_directory` | Lists files and directories in the project directory | "List all files in the src directory" |
| `read_file` | Reads the contents of a file | "Show me the contents of main.js" |
| `save_file` | Creates or overwrites files atomically | "Create a new file called app.js" |
| `append_file` | Adds content to existing files | "Add a function to utils.js" |
| `delete_this_file` | Removes files from the filesystem | "Delete the temporary.txt file" |
| `edit_file` | Makes selective edits using exact string matching | "Fix the bug in the fetch function" |
| `move_file` | Moves or renames files and directories | "Rename config.js to settings.js" |
| `get_reference_projects` | Lists available reference projects | "What reference projects are available?" |
| `list_reference_directory` | Lists files in a reference project | "List files in the docs reference project" |
| `read_reference_file` | Reads files from reference projects | "Show me the README from the examples project" |

### Tool Details

#### List Directory
- Returns a list of file and directory names
- By default, results are filtered based on .gitignore patterns and .git folders are excluded

#### Read File
- Parameters:
  - `file_path` (string): Path to the file to read (relative to project directory)
  - `start_line` (integer, optional): First line to return (1-based, inclusive). Must be provided together with `end_line`.
  - `end_line` (integer, optional): Last line to return (1-based, inclusive). Must be provided together with `start_line`.
  - `with_line_numbers` (boolean, optional): Prefix each line with its line number. Defaults to `True` when a line range is specified, `False` for full reads.
- Returns the content of the file as a string

#### Save File
- Parameters:
  - `file_path` (string): Path to the file to write to
  - `content` (string): Content to write to the file
- Returns a boolean indicating success

#### Append File
- Parameters:
  - `file_path` (string): Path to the file to append to
  - `content` (string): Content to append to the file
- Returns a boolean indicating success
- Note: The file must already exist; use `save_file` to create new files

#### Delete This File
- Parameters: `file_path` (string): Path to the file to delete
- Returns a boolean indicating success
- Note: This operation is irreversible and will permanently remove the file

#### Edit File
Makes precise edits to files using exact string matching. This tool is designed for reliability and predictability.

**Parameters:**
- `file_path` (string): File to edit (relative to project directory)
- `edits` (array): List of edit operations, each containing:
  - `old_text` (string): Exact text to find and replace (must match exactly)
  - `new_text` (string): Replacement text
- `dry_run` (boolean, optional): Preview changes without applying (default: False)
- `options` (object, optional): Formatting settings
  - `preserve_indentation` (boolean, default: False): Apply indentation from old_text to new_text

**Key Characteristics:**
- **Exact string matching only** - The `old_text` must match exactly (case-sensitive, whitespace-sensitive)
- **No fuzzy or partial matching** - For maximum reliability and predictability
- **First occurrence replacement** - Only replaces the first match of each `old_text` pattern
- **Sequential processing** - Edits are applied in order, with each edit seeing the results of previous edits
- **Already-applied detection** - Automatically detects when edits are already applied (no-op optimization)
- **Git-style diff output** - Shows exactly what changed in unified diff format
- **Clear error reporting** - Specific messages when text patterns are not found

**Examples:**
```python
# Basic text replacement
edit_file("config.py", [
    {"old_text": "DEBUG = False", "new_text": "DEBUG = True"}
])

# Multiple edits in one operation
edit_file("app.py", [
    {"old_text": "def old_function():", "new_text": "def new_function():"},
    {"old_text": "old_function()", "new_text": "new_function()"}
])

# Preview changes without applying
edit_file("code.py", edits, dry_run=True)

# With indentation preservation
edit_file("indented.py", [
    {"old_text": "    old_code()", "new_text": "new_code()"}
], options={"preserve_indentation": True})
```

**Important Notes:**
- The text in `old_text` must match exactly - including spacing, capitalization, and line breaks
- Use `\n` for line breaks in multi-line replacements
- If `old_text` appears multiple times, only the first occurrence is replaced
- Consider using `dry_run=True` to preview changes before applying them

#### Move File
Moves or renames files and directories within the project directory. Automatically preserves git history when applicable.

**Parameters:**
- `source_path` (string): Source file/directory path (relative to project)
- `destination_path` (string): Destination path (relative to project)

**Returns:** Boolean (true for success)

**Features:**
- Automatically creates parent directories if they don't exist
- Preserves git history when moving tracked files (uses git mv internally)
- Falls back to filesystem operations if git is unavailable
- Works for both files and directories
- Simple, clear error messages for LLMs

**Examples:**
```python
# Rename a file
move_file("old_name.py", "new_name.py")

# Move a file to a different directory
move_file("src/temp.py", "archive/temp.py")

# Rename a directory
move_file("old_folder", "new_folder")

# Move with automatic parent directory creation
move_file("file.txt", "new_dir/sub_dir/file.txt")  # Creates new_dir/sub_dir if needed
```

**Error Handling:**
- Returns simplified error messages suitable for AI assistants:
  - "File not found" - when source doesn't exist
  - "Destination already exists" - when target path is occupied
  - "Permission denied" - for access issues
  - "Invalid path" - for security violations
  - "Move operation failed" - for unexpected errors

#### Get Reference Projects
Discovery tool for LLMs to find available reference projects.

**Parameters:** None

**Returns:** Dictionary containing:
- `count`: Number of available projects
- `projects`: List of project names
- `usage`: Instructions for next steps

**Example:**
```python
get_reference_projects()
# Returns: {
#   "count": 3,
#   "projects": ["docs", "examples", "utils"],
#   "usage": "Use these 3 projects with list_reference_directory() and read_reference_file()"
# }
```

**Use Cases:**
- LLM discovers what reference projects are available
- Initial exploration of additional codebases
- Dynamic selection of reference projects to browse

#### List Reference Directory
Lists files and directories in a reference project, with the same gitignore filtering as the main project.

**Parameters:**
- `reference_name` (string): Name of the reference project

**Returns:** List of strings containing file and directory names

**Examples:**
```python
# List root directory of reference project (shows subdirectories)
list_reference_directory("docs")

# Then read files from subdirectories using read_reference_file
read_reference_file("examples", "src/components/Button.tsx")
```

**Features:**
- Automatic gitignore filtering (same as main project)
- Excludes .git directories
- Returns relative paths within the reference project
- Validates reference project exists

#### Read Reference File
Reads the contents of a file from a reference project.

**Parameters:**
- `reference_name` (string): Name of the reference project
- `file_path` (string): Path to the file within the reference project (relative to reference project root)
- `start_line` (integer, optional): First line to return (1-based, inclusive). Must be provided together with `end_line`.
- `end_line` (integer, optional): Last line to return (1-based, inclusive). Must be provided together with `start_line`.
- `with_line_numbers` (boolean, optional): Prefix each line with its line number. Defaults to `True` when a line range is specified, `False` for full reads.

**Returns:** String containing the file contents

**Examples:**
```python
# Read README from docs reference project
read_reference_file("docs", "README.md")

# Read source file from examples project
read_reference_file("examples", "src/app.py")

# Read specific lines with line numbers
read_reference_file("examples", "src/app.py", start_line=10, end_line=20)

# Read config file
read_reference_file("config", "settings/production.yml")
```

**Features:**
- Read-only access (no modification possible)
- Same path validation as main project files
- Supports any text-based file format
- Returns raw file contents as string

**Error Handling:**
- "Reference project not found" - when reference_name doesn't exist
- "File not found" - when file doesn't exist in reference project
- "Invalid path" - for security violations or path traversal attempts
- "Permission denied" - for access issues

## Security Features

- All paths are normalized and validated to ensure they remain within the project directory
- Reference projects use the same path validation and security measures
- Path traversal attacks are prevented for both main project and reference projects
- Files are written atomically to prevent data corruption
- Delete operations are restricted to the project directory for safety
- Reference projects are strictly read-only to prevent accidental modifications

### MCP Configuration Management Tool

For easy configuration and installation of this MCP server, you can use the **mcp-config** development tool. This CLI tool simplifies the process of managing MCP server configurations across multiple clients (Claude Desktop, VS Code, etc.).

#### Installation

```bash
# Install mcp-config
pip install git+https://github.com/MarcusJellinghaus/mcp-config.git
```

#### Quick Setup

```bash
# Setup for Claude Desktop with automatic configuration
mcp-config setup mcp-workspace "Filesystem Server" --project-dir /path/to/your/project

# Setup with reference projects
mcp-config setup mcp-workspace "Filesystem Server" \
  --project-dir /path/to/your/project \
  --reference-project docs=/path/to/documentation \
  --reference-project examples=/path/to/examples

# Setup with custom log configuration
mcp-config setup mcp-workspace "Filesystem Server" \
  --project-dir /path/to/your/project \
  --reference-project utils=/shared/utilities \
  --log-level DEBUG \
  --log-file /custom/path/server.log
```

**Learn more:** [mcp-config on GitHub](https://github.com/MarcusJellinghaus/mcp-config)

This tool eliminates the manual configuration steps and reduces setup errors by handling path resolution, environment detection, and client-specific configuration formats automatically.



## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

The MIT License is a permissive license that allows reuse with minimal restrictions. It permits use, copying, modification, and distribution with proper attribution.

## Links

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Tools Py](https://github.com/MarcusJellinghaus/mcp-tools-py)
- [MCP Configuration Tool](https://github.com/MarcusJellinghaus/mcp-config)
- [Cline MCP Servers Documentation](https://docs.cline.bot/mcp-servers/configuring-mcp-servers)
- [Cline Extension for VSCode](https://github.com/saoudrizwan/claude-dev)
- [Model Context Protocol Documentation](https://modelcontextprotocol.io/)
