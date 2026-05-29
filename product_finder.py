import json
import logging

import requests
from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL, SERPER_API_KEY


logger = logging.getLogger(__name__)


SERPER_ENDPOINT = "https://google.serper.dev/search"

MAX_RESEARCH_ROUNDS = 6

SYSTEM_PROMPT = (
    "You are a strict, data-driven e-commerce brand strategist working under Mark's EQ Framework.\n"
    "Your objective is to find 3 highly specific product candidates that solve a real problem.\n\n"
    "CRITICAL OPERATIONAL MANDATE:\n"
    "You have access to a live Google search tool. You MUST use it to look up and verify actual data.\n"
    "Research iteratively: search competitors first, read the results, then run follow-up searches\n"
    "for sourcing costs and traffic based on what you found. Run as many searches as you need.\n"
    "1. Search for real competitors in the market to gauge traffic and traction.\n"
    "2. Search for the product on AliExpress or CJ Dropshipping to find real COGS + shipping estimates.\n"
    "Do not guess or make up numbers. If a search returns nothing useful, say so and flag the figure\n"
    "as unverified rather than inventing one.\n\n"
    "When you have gathered enough evidence, stop searching and deliver your final report in clean,\n"
    "scannable Markdown with exact pricing math, shipping footprints, cited source links, and an EQ Score."
)

SEARCH_TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "google_search_tool",
            "description": (
                "Executes a live Google query to pull real snippets regarding competitor "
                "traffic, site metrics, and sourcing costs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "The target search string (e.g., 'dog joint supplement aliexpress "
                            "wholesale price' or 'competitor brand name monthly traffic')"
                        ),
                    }
                },
                "required": ["query"],
            },
        },
    }
]


class LiveResearchEngine:
    def __init__(self):
        if not OPENAI_API_KEY:
            raise RuntimeError("Missing OPENAI_API_KEY in .env.local")
        if not SERPER_API_KEY:
            raise RuntimeError(
                "Missing SERPER_API_KEY in .env.local. Please add it to unlock live web research."
            )
        self.client = OpenAI(api_key=OPENAI_API_KEY)

    def google_search_tool(self, query: str) -> str:
        """Execute a live Google search via Serper and return parsed snippets as text."""
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
        payload = json.dumps({"q": query, "num": 5})

        try:
            response = requests.post(SERPER_ENDPOINT, headers=headers, data=payload, timeout=15)
            response.raise_for_status()
            results = response.json()
        except requests.RequestException as error:
            logger.warning("Serper search failed for %r: %s", query, error)
            return f"Live search connection failure: {error}"
        except ValueError as error:
            return f"Live search returned unparseable response: {error}"

        snippets = []

        answer_box = results.get("answerBox")
        if answer_box:
            answer = answer_box.get("answer") or answer_box.get("snippet")
            if answer:
                snippets.append(f"Answer Box: {answer}")

        for item in results.get("organic", []):
            snippets.append(
                f"Title: {item.get('title')}\n"
                f"Snippet: {item.get('snippet')}\n"
                f"Link: {item.get('link')}"
            )

        return "\n\n".join(snippets) if snippets else "No relevant organic search results found."

    def run_validated_research(
        self,
        seed_market: str,
        exclusions: str,
        skill_lean: str,
    ) -> str:
        """Run an iterative tool-calling loop so the model can research before scoring."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Find winning products for: Market: {seed_market} | "
                    f"Exclusions: {exclusions} | Slider Focus: {skill_lean}"
                ),
            },
        ]

        print("Step 1: Initiating AI strategic analysis...")

        for research_round in range(1, MAX_RESEARCH_ROUNDS + 1):
            try:
                response = self.client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=messages,
                    tools=SEARCH_TOOL_SCHEMA,
                    tool_choice="auto",
                    temperature=0.2,
                )
            except Exception as error:
                logger.exception("OpenAI call failed during research loop.")
                return f"Engine execution failed: {error}"

            assistant_message = response.choices[0].message
            tool_calls = assistant_message.tool_calls

            if not tool_calls:
                return assistant_message.content or "Engine returned an empty response."

            messages.append(assistant_message)

            for tool_call in tool_calls:
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                target_query = arguments.get("query", "")

                print(f"  [Live Web Lookup, round {research_round}] Searching: '{target_query}'")
                search_context = self.google_search_tool(target_query)

                messages.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": tool_call.function.name,
                        "content": search_context,
                    }
                )

        print("Max research rounds reached; generating final report from gathered data...")
        try:
            final_response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0.2,
            )
        except Exception as error:
            logger.exception("OpenAI call failed while generating final report.")
            return f"Engine execution failed: {error}"

        return final_response.choices[0].message.content or "Engine returned an empty response."


if __name__ == "__main__":
    print("Booting up live validation engine for the leg exerciser market...")
    engine = LiveResearchEngine()

    report = engine.run_validated_research(
        seed_market=(
            "Passive leg exerciser machine, seated foot mover for seniors, "
            "circulation foot pedaler"
        ),
        exclusions="heavy gym ellipticals, active under-desk bikes, cheap vibrating massage pads",
        skill_lean="Direct-response advertorial and comfort angles",
    )

    print("\n=== FINAL VERIFIED LEG EXERCISER MARKET REPORT ===")
    print(report)
