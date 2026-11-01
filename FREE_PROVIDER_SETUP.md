# Free-first provider setup

Flow.io can run in live mode without Anthropic, Brave Search, or OpenAI by using the providers below.

## 1. Google Gemini

Create a Gemini API key in Google AI Studio and save it in **Flow.io → Tools** under **Google Gemini**.

Flow.io uses:

- `gemini-3.8-flash` for general reasoning, documents, coding and validation.
- `gemini-3.5-flash-lite` for fast/light work.
- `gemini-2.5-flash-lite` + `google_search` for web research.

The exact model availability and free-tier limits are controlled by Google. Google currently documents a free developer tier for selected Gemini models. Search grounding has separate quotas and may depend on model/account access.

## 2. Groq

Create a Groq API key and save it under **Groq** in Flow.io → Tools.

Flow.io uses `openai/gpt-oss-120b` through Groq's OpenAI-compatible API.

Groq maintains a Free tier with rate limits; upgrading to the Developer tier is optional.

## 3. Hugging Face

Create a Hugging Face token with **Inference Providers** permission and save it under **Hugging Face** in Flow.io → Tools.

Flow.io uses the OpenAI-compatible Hugging Face router with `openai/gpt-oss-120b:fastest`.

Hugging Face currently gives Free users a small monthly Inference Providers credit. This is useful as a fallback/testing provider, not an unlimited free service.

## 4. Local/open-source image generation

The `Local Stable Diffusion` tool uses an Automatic1111/Forge-compatible local API. No cloud API key is needed.

1. Install/run an Automatic1111/Forge-compatible Stable Diffusion WebUI locally.
2. Launch it with its API enabled.
3. Confirm the API endpoint is:

   `http://127.0.0.1:7860/sdapi/v1/txt2img`

4. In `.env`, configure this for Docker Desktop on Mac:

   `LOCAL_IMAGE_API_URL=http://host.docker.internal:7860/sdapi/v1/txt2img`

5. Rebuild Flow.io:

   `docker compose down`

   `docker compose up --build`

The local image tool remains unavailable until `LOCAL_IMAGE_API_URL` is set, so normal text workflows are unaffected.

## Live mode

After saving at least one provider key in Tools, switch:

`EXECUTION_MODE=live`

Then rebuild/restart the stack.

The router prefers connected providers over providers whose API key is missing.

## Original providers

Anthropic, Brave Search and OpenAI remain available as optional providers. They were not removed from the architecture.
