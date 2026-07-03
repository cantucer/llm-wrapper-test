from __future__ import annotations


KNOWN_WRAPPERS = {
    "direct_vllm": {
        "category": "baseline",
        "default_port": None,
        "setup": "Already running upstream endpoint.",
        "docs": "vLLM OpenAI-compatible server",
    },
    "litellm_proxy": {
        "category": "service_gateway",
        "default_port": 4000,
        "setup": "Run LiteLLM Proxy with litellm_config.yaml.",
        "supports_local_python_service": True,
        "supports_docker": True,
    },
    "bifrost": {
        "category": "service_gateway",
        "default_port": 8080,
        "setup": "Run Bifrost by Docker or NPX and configure vLLM provider in UI.",
        "supports_docker": True,
        "supports_npx": True,
    },
    "portkey_local": {
        "category": "service_gateway",
        "default_port": 8787,
        "setup": "Run Portkey Gateway by Docker or NPX, then pass custom host headers.",
        "supports_docker": True,
        "supports_npx": True,
    },
    "helicone_gateway": {
        "category": "service_gateway",
        "default_port": 8081,
        "setup": "Run Helicone AI Gateway Docker image or hosted gateway.",
        "supports_docker": True,
    },
    "llm_gateway": {
        "category": "service_gateway",
        "default_port": 3000,
        "setup": "Run LLM Gateway Docker/self-host setup.",
        "supports_docker": True,
    },
    "litellm_sdk": {
        "category": "sdk_wrapper",
        "default_port": None,
        "setup": "Install litellm and call it in-process.",
        "supports_python_sdk": True,
    },
}
