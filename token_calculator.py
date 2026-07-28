import sys
import json
import tiktoken
from pathlib import Path

def count_tokens(text: str, model: str = "claude-3-5-sonnet-20240620") -> int:
    """Estimate tokens using tiktoken (works well too)."""
    try:
        encoding = tiktoken.encoding_for_model("gpt-4o")  # Good approximation for Claude
    except:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

def extract_text_from_json(file_path: Path) -> str:
    """Extract conversation text from exported JSON."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    texts = []
    
    # Handle different JSON structures
    if isinstance(data, dict):
        # Common Copilot structure
        if "messages" in data:
            for msg in data["messages"]:
                if isinstance(msg, dict) and "content" in msg:
                    texts.append(str(msg.get("content", "")))
                elif isinstance(msg, str):
                    texts.append(msg)
        else:
            # Fallback: stringify whole thing
            texts.append(json.dumps(data, ensure_ascii=False))
    else:
        texts.append(str(data))
    
    return "\n\n".join(texts)

def main():
    if len(sys.argv) < 2:
        print("Usage: python token_calculator.py <file_path> [model]")
        print("Example: python token_calculator.py chat_export.json")
        sys.exit(1)
    
    file_path = Path(sys.argv[1])
    model = sys.argv[2] if len(sys.argv) > 2 else "claude-3-5-sonnet-20240620"
    
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)
    
    # Extract text
    if file_path.suffix.lower() == '.json':
        text = extract_text_from_json(file_path)
    else:
        # .txt or .md
        text = file_path.read_text(encoding='utf-8')
    
    token_count = count_tokens(text, model)
    
    print(f"Token Calculation")
    print(f"File: {file_path.name}")
    print(f"Size: {len(text):,} characters")
    print(f"Tokens: {token_count:,} (approx. for {model})")
    print(f"Remaining for Claude 200K context: {200_000 - token_count:,}")

if __name__ == "__main__":
    main()