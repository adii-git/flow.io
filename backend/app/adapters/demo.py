"""Demo adapter: deterministic, clearly labelled simulated outputs so the full flow runs with no keys."""
import base64
import json
from .base import Adapter, AdapterResult

TAG = "[Simulated output] "


class DemoAdapter(Adapter):
    def run(self, pkg, tool, api_key, capability):
        obj = pkg.objective[:120]
        if capability == "validation":
            return AdapterResult(json.dumps({"passed": True, "issues": []}), simulated=True)
        if capability == "web_research":
            src = [{"title": f"Example source {i} (simulated)", "url": f"https://example.com/source-{i}",
                    "description": "Placeholder text. No search was performed."} for i in (1, 2, 3)]
            return AdapterResult(TAG + "Three placeholder sources.", {"sources": src}, simulated=True)
        if capability == "image_generation":
            svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400"><rect width="640" height="400" fill="#E3E8EA"/>'
                   '<text x="320" y="200" text-anchor="middle" font-family="sans-serif" font-size="24" fill="#12181B">Simulated image</text></svg>')
            n = getattr(pkg, "image_count", 1)
            img = {"mime": "image/svg+xml", "b64": base64.b64encode(svg.encode()).decode()}
            return AdapterResult(TAG + f"{n} placeholder image(s).", {"images": [img] * n}, simulated=True)
        if capability == "code_generation":
            return AdapterResult(TAG + "Placeholder code for: " + obj + "\n\n```python main.py\n# Simulated: no model wrote this.\n"
                                 "def main():\n    print('placeholder')\n\n\nif __name__ == '__main__':\n    main()\n```", simulated=True)
        names = ", ".join(f["name"] for f in pkg.files)
        body = {"writing": "A placeholder piece of writing for the objective.",
                "reasoning": "A placeholder analysis of the objective, with a sample chart below.",
                "long_context_documents": "A placeholder summary of the supplied material" + (f" ({names})." if names else "."),
                "file_processing": "Placeholder notes on the attached files" + (f": {names}." if names else "."),
                }.get(capability, "Placeholder output.")
        chart = '\n\n```json\n{"title": "Sample comparison (simulated)", "labels": ["A", "B", "C"], "values": [3, 5, 2]}\n```' if capability == "reasoning" else ""
        return AdapterResult(f"{TAG}{body} Objective: {obj}{chart}", simulated=True)
