# Contributing to MCP File System Server

Thank you for your interest in contributing to the MCP File System Server! This guide will help you set up your development environment and understand the contribution process.

## Development Setup

### Setting up the development environment

```bash
# Clone the repository
git clone https://github.com/MarcusJellinghaus/mcp-workspace.git
cd mcp-workspace

# Create and activate a virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install in development mode with dev dependencies
pip install -e ".[dev,config]"
```

## Running from Source (Development Mode)

For development and testing, you can run the server directly from source without installation:

### Method 1: Module execution
```bash
python -m src.main --project-dir /path/to/project [--log-level LEVEL] [--log-file PATH]
```

### Method 2: Direct script execution
```bash
# On Windows:
set PYTHONPATH=%PYTHONPATH%;.
python .\src\main.py --project-dir /path/to/project

# On macOS/Linux:
export PYTHONPATH=$PYTHONPATH:.
python ./src/main.py --project-dir /path/to/project
```

## Testing with MCP Inspector

MCP Inspector is excellent for debugging and testing during development:

```bash
# Start MCP Inspector
npx @modelcontextprotocol/inspector \
  uv \
  --directory C:\path\to\mcp_workspace \
  run \
  src\main.py
```

In the MCP Inspector web UI, configure:
- **Python interpreter**: `C:\path\to\mcp_workspace\.venv\Scripts\python.exe`
- **Arguments**: `C:\path\to\mcp_workspace\src\main.py --project-dir C:\path\to\your\test\project --log-level DEBUG`
- **Environment variables**:
  - Name: `PYTHONPATH`
  - Value: `C:\path\to\mcp_workspace\`

## Testing

The project includes comprehensive pytest-based unit tests.

### Test Structure
- `tests/` - Main test directory
- `tests/file_tools/` - Tests for file operation tools
- `tests/testdata/` - Test data files
- See [tests/README.md](tests/README.md) for detailed test documentation

### LLM Testing
For LLM-based testing, see [tests/LLM_Test.md](tests/LLM_Test.md) - this contains test instructions you can paste directly to an LLM to verify server functionality.

## Development Tools

The project includes several development utility scripts in the `tools/` directory:

- `run_all_checks.bat` / `.sh` - Run all code quality and architecture checks
- `pylint_check.bat` - Run pylint checks
- `reinstall_local.bat` / `.sh` - Reinstall the package in development mode

## Code Style

The project uses:
- **ruff format** for code formatting (line length: 88)
- **ruff** (`I` rules) for import sorting
- **pylint** for code quality checks

## Troubleshooting Development Setup

### Common Issues
1. **Import errors**: Ensure `PYTHONPATH` includes the repository root
2. **Python path issues**: Verify your virtual environment is activated
3. **Missing dependencies**: Run `pip install -e ".[dev]"` to ensure dev dependencies are installed

### Development Logs
- Server logs are written to `project_dir/logs/mcp_workspace_*.log`
- Use `--log-level DEBUG` for detailed development logging
- Check console output for immediate feedback

## Contribution Guidelines

1. **Fork the repository** and create a feature branch
2. **Write tests** for new functionality
3. **Follow code style** guidelines (ruff, pylint)
4. **Update documentation** as needed
5. **Test thoroughly** including edge cases
6. **Submit a pull request** with a clear description

## Project Structure

```
mcp-workspace/
├── src/                    # Main source code
│   ├── main.py            # Entry point and CLI
│   ├── server.py          # MCP server implementation
│   ├── log_utils.py       # Logging utilities
│   └── file_tools/        # File operation tools
├── tests/                 # Test suite
├── tools/                 # Development utilities
├── pyproject.toml         # Project configuration
└── README.md              # User documentation
```

## Questions or Issues?

- Open an issue on GitHub for bugs or feature requests
- Check existing issues before creating new ones
- Include detailed information about your development environment
