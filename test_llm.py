import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from app.api.chat_api import TOOLS
from app.prompts import get_system_prompt
from app.services.rag import get_relevant_context

load_dotenv()
client = OpenAI()

def test_query(query: str, pilar_id: int = None):
    print(f"--- QUERY: {query} (Pilar Context: {pilar_id}) ---")
    
    # 1. First call to LLM with tools
    messages = [
        {"role": "system", "content": get_system_prompt(pilar_id)},
        {"role": "user", "content": query}
    ]
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto"
    )
    
    msg = response.choices[0].message
    
    if msg.tool_calls:
        print(f"🛠️ LLM decided to call tools: {len(msg.tool_calls)}")
        messages.append(msg)
        
        for tool_call in msg.tool_calls:
            if tool_call.function.name == "buscar_informacion":
                args = json.loads(tool_call.function.arguments)
                q = args.get("query", query)
                print(f"🔍 Searching for: {q} (with pilar_id={pilar_id})")
                context = get_relevant_context(q, pilar_id=pilar_id)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": context
                })
        
        # 2. Second call to LLM with tool results
        final_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        print("\n🤖 FINAL RESPONSE:\n")
        print(final_response.choices[0].message.content)
    else:
        print("\n🤖 FINAL RESPONSE (No tools):\n")
        print(msg.content)
    print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    # Test 1: Pilar 3 asking about Pilar 3 stuff
    test_query("¿Cómo debe ser la rutina de un vendedor en mi pilar?", pilar_id=3)
    # Test 2: Pilar 3 asking about Pilar 6 stuff (Cross-query, should it know?)
    test_query("¿Cómo se debe calcular la liquidación de fin de mes de un vendedor?", pilar_id=3)
