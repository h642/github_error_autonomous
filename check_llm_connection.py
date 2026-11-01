"""Diagnostic script to verify live LLM API credentials before running repairs."""

import os
import sys
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def test_connection():
    print("======================================================================")
    print("  AUTONOMOUS REPAIR PIPELINE - LLM CONNECTIVITY CHECK")
    print("======================================================================")

    provider = os.getenv("LLM_PROVIDER", "").lower()
    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if not provider:
        if gemini_key:
            provider = "gemini"
        elif openai_key:
            provider = "openai"
        elif anthropic_key:
            provider = "anthropic"
        else:
            provider = "mock"

    print(f"Selected Provider: {provider.upper()}")

    if provider == "mock":
        print("\n[INFO] No API keys configured. Pipeline will run in deterministic benchmark mode.")
        print("To connect a live LLM:")
        print("  1. Copy .env.example to .env:  cp .env.example .env")
        print("  2. Add your GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY")
        print("  3. Re-run this check:  python3 check_llm_connection.py")
        return 0

    print(f"Testing live API handshake with provider '{provider}'...")

    if provider == "gemini":
        if not gemini_key:
            print("✗ Error: GEMINI_API_KEY is not set.")
            return 1
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
            print(f"Sending test probe to model: {model_name}...")
            res = client.models.generate_content(
                model=model_name,
                contents="Ping. Respond with 'PONG' and nothing else.",
            )
            print(f"✓ Success! Gemini API responded: {res.text.strip()}")
            return 0
        except Exception as exc:
            print(f"✗ Gemini connection failed: {exc}")
            return 1

    elif provider == "openai":
        if not openai_key:
            print("✗ Error: OPENAI_API_KEY is not set.")
            return 1
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            model_name = os.getenv("LLM_MODEL", "gpt-4o")
            print(f"Sending test probe to model: {model_name}...")
            res = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "Ping. Respond with 'PONG' and nothing else."}],
                max_tokens=10,
            )
            reply = res.choices[0].message.content or ""
            print(f"✓ Success! OpenAI API responded: {reply.strip()}")
            return 0
        except Exception as exc:
            print(f"✗ OpenAI connection failed: {exc}")
            return 1

    elif provider == "anthropic":
        if not anthropic_key:
            print("✗ Error: ANTHROPIC_API_KEY is not set.")
            return 1
        try:
            import httpx
            model_name = os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022")
            print(f"Sending test probe to model: {model_name}...")
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model_name,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "Ping. Respond with 'PONG' and nothing else."}],
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            print(f"✓ Success! Anthropic API responded: {data['content'][0]['text'].strip()}")
            return 0
        except Exception as exc:
            print(f"✗ Anthropic connection failed: {exc}")
            return 1

    else:
        print(f"Unknown provider: {provider}")
        return 1


if __name__ == "__main__":
    sys.exit(test_connection())
