import os
from dotenv import load_dotenv
import anthropic
from tavily import TavilyClient

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# Definice toolu — Claude vidí jen toto
tools = [{
    "name": "search_web",
    "description": (
        "Vyhledá aktuální zprávy a informace na internetu. "
        "Použij vždy, když potřebuješ aktuální data, novinky nebo fakta."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Vyhledávací dotaz v češtině nebo angličtině"
            }
        },
        "required": ["query"]
    }
}]

# Skutečná implementace toolu — Claude toto nevidí
def search_web(query: str) -> str:
    print(f"  [tool] Hledám: {query}")
    results = tavily.search(query=query, max_results=5)
    # Převeď výsledky na čitelný text pro Claudea
    output = []
    for r in results["results"]:
        output.append(f"Zdroj: {r['url']}\nNadpis: {r['title']}\nShrnutí: {r['content']}\n")
    return "\n---\n".join(output)

# System prompt — instrukce pro agenta
system = """Jsi novinářský asistent. Vyhledáš aktuální zprávy na zadané téma
a vrátíš přehledné shrnutí v Markdownu. Struktura výstupu:
- Nadpis s tématem
- 3–5 hlavních bodů (každý s odkazem na zdroj)
- Krátký závěr"""

# Vstup od uživatele
topic = input("Zadej téma pro přehled zpráv: ")
messages = [{"role": "user", "content": f"Připrav přehled aktuálních zpráv na téma: {topic}"}]

# Agentic loop
while True:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=system,
        
        tools=tools,
        messages=messages
    )
    messages.append({"role": "assistant", "content": response.content})

    if response.stop_reason == "end_turn":
        digest = response.content[0].text

        from datetime import date
        filename = f"digest_{date.today()}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# Digest: {topic}\n")
            f.write(f"_Vygenerováno: {date.today()}_\n\n")
            f.write(digest)

        print(f"\nUloženo do: {filename}")
        print("="*50)
        print(digest)
        break

    elif response.stop_reason == "tool_use":
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = search_web(**block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })
        messages.append({"role": "user", "content": tool_results})