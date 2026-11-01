"""Re-planner: decides what to do when a step cannot be routed or run."""
OPTIONAL = {"code_execution": "Code running isn't available yet, so the code is delivered without being run.",
            "validation": "No tool was available to check the result, so it was not independently checked."}


def adjust(capability: str, reason: str) -> dict:
    """{'action': 'skip'|'abort', 'note': str}"""
    if capability in OPTIONAL:
        return {"action": "skip", "note": OPTIONAL[capability]}
    return {"action": "abort", "note": reason}
