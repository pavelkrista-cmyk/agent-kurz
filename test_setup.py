import os
from dotenv import load_dotenv
import anthropic

# Načti API klíče z .env souboru
load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

message = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=100,
    messages=[
        {"role": "user", "content": "Odpověz jednou větou česky: Setup funguje?"}
    ]
)

print(message.content[0].text)