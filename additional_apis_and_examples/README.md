# Additional APIs and Examples

Place your custom Python drivers, API wrappers, or example scripts in this folder.

LabAutoMate can use these files as additional context when generating code:
- **Python drivers** (`.py`) — custom instrument drivers not included in PyLabDrivers
- **Example scripts** — automation workflows or Dash app examples to use as templates
- **API wrappers** — interfaces for OPC UA servers, REST APIs, or other protocols

## How to use

1. Place your `.py` files in this folder
2. In the LabAutoMate chatbot, use the file upload feature to attach them to your prompt
3. The AI model will use these as reference when generating new code

## Tips

- Include docstrings and type hints in your code for best AI interpretation
- Name files descriptively (e.g., `vapourtec_opcua_client.py` not `test1.py`)
- Include usage examples at the bottom of driver files
