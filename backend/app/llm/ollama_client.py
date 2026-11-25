"""Local Ollama client (127.0.0.1 only). There is no fallback to any hosted AI service."""
import base64

import httpx
import numpy as np

from ..core.config import get_settings


class LocalModelError(RuntimeError):
    pass


class Ollama:
    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        s = get_settings()
        self.base = (base_url or s.ollama_url).rstrip("/")
        host = httpx.URL(self.base).host
        if host not in ("127.0.0.1", "localhost", "::1", "ollama"):
            raise LocalModelError("Ollama must run on this machine or the private Docker network")
        self.timeout = timeout or s.llm_timeout_s

    def _post(self, path: str, body: dict) -> dict:
        try:
            r = httpx.post(f"{self.base}{path}", json=body, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise LocalModelError(f"Ollama not reachable ({type(exc).__name__})") from exc
        if r.status_code >= 300:
            raise LocalModelError(f"Ollama error {r.status_code}: {r.text[:200]}")
        return r.json()

    def version(self) -> str | None:
        try:
            return httpx.get(f"{self.base}/api/version", timeout=3).json().get("version")
        except httpx.HTTPError:
            return None

    def models(self) -> list[dict]:
        try:
            return httpx.get(f"{self.base}/api/tags", timeout=5).json().get("models", [])
        except httpx.HTTPError:
            return []

    def loaded(self) -> list[dict]:
        try:
            return httpx.get(f"{self.base}/api/ps", timeout=5).json().get("models", [])
        except httpx.HTTPError:
            return []

    def embed(self, texts: list[str], model: str | None = None) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1024), dtype=np.float32)
        out = []
        for i in range(0, len(texts), 16):
            data = self._post("/api/embed", {"model": model or get_settings().embed_model,
                                              "input": texts[i:i + 16], "keep_alive": "60m",
                                              "options": {"num_gpu": 0}})   # CPU: keep the GPU for the chat model
            out.extend(data["embeddings"])
        v = np.asarray(out, dtype=np.float32)
        return v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-9, None)

    def chat(self, system: str, user: str, model: str | None = None, images: list[bytes] | None = None,
             max_tokens: int = 400, temperature: float = 0.2) -> dict:
        msg = {"role": "user", "content": user}
        if images:
            msg["images"] = [base64.b64encode(b).decode() for b in images]
        data = self._post("/api/chat", {
            "model": model or get_settings().chat_model, "stream": False, "think": False, "keep_alive": "60m",
            "messages": [{"role": "system", "content": system}, msg],
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 4096},
        })
        return {"text": data["message"]["content"].strip(), "eval_count": data.get("eval_count", 0),
                "eval_ms": data.get("eval_duration", 0) / 1e6, "total_ms": data.get("total_duration", 0) / 1e6}
