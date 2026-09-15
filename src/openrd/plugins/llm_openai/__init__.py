from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from openrd.core.context import Context
from openrd.db.store import Store, get_store
from openrd.engine.bus import get_bus
from openrd.util.embed import token_estimate


@dataclass
class LLMResult:
    text: str
    model: str
    role: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_rub: float | None = None
    cost_usd: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LLMService:
    def __init__(self, store: Store | None = None) -> None:
        self.store = store or get_store()
        self.provider_id: str | None = None
        self.project_id: str | None = None
        self._pricing_cache: dict[str, dict[str, Any]] = {}

    def bind(self, provider_id: str, project_id: str | None = None) -> None:
        self.provider_id = provider_id
        self.project_id = project_id

    def _provider(self) -> dict[str, Any]:
        if not self.provider_id:
            raise RuntimeError("LLM provider is not bound")
        p = self.store.get_provider(self.provider_id)
        if not p:
            raise RuntimeError("provider not found")
        return p

    def model_for(self, role: str) -> str:
        p = self._provider()
        roles = p.get("roles") or {}
        return roles.get(role) or roles.get("orchestrator") or roles.get("coder") or ""

    async def list_remote_models(self) -> list[dict[str, Any]]:
        p = self._provider()
        key = self.store.get_provider_key(p["id"]) or ""
        url = p["base_url"].rstrip("/") + "/models"
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
        models = data.get("data") or data.get("models") or []
        for m in models:
            mid = m.get("id")
            pricing = (m.get("top_provider") or {}).get("pricing") or m.get("pricing") or {}
            if mid:
                self._pricing_cache[mid] = pricing
        return models

    def _estimate_cost(self, model: str, prompt_t: int, completion_t: int) -> tuple[float | None, float | None]:
        pricing = self._pricing_cache.get(model) or {}
        # Polza uses prompt_per_million / completion_per_million in RUB
        ppm = pricing.get("prompt_per_million")
        cpm = pricing.get("completion_per_million")
        currency = (pricing.get("currency") or "RUB").upper()
        if ppm is None and cpm is None:
            return None, None
        try:
            cost = (prompt_t / 1_000_000) * float(ppm or 0) + (completion_t / 1_000_000) * float(cpm or 0)
        except (TypeError, ValueError):
            return None, None
        if currency == "RUB":
            return cost, None
        return None, cost

    async def complete(
        self,
        role: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float = 0.4,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> LLMResult:
        p = self._provider()
        model = self.model_for(role)
        if not model:
            raise RuntimeError(f"no model configured for role '{role}'")
        key = self.store.get_provider_key(p["id"]) or ""
        payload_messages = list(messages)
        if system:
            payload_messages = [{"role": "system", "content": system}, *payload_messages]
        body: dict[str, Any] = {
            "model": model,
            "messages": payload_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        url = p["base_url"].rstrip("/") + "/chat/completions"
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
        choice = (data.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content")) or ""
        usage = data.get("usage") or {}
        pt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or token_estimate(json.dumps(payload_messages)))
        ct = int(usage.get("completion_tokens") or usage.get("output_tokens") or token_estimate(text))
        # Polza may return cost_rub on usage
        cost_rub = usage.get("cost_rub") or usage.get("cost")
        cost_usd = usage.get("cost_usd")
        if cost_rub is None and cost_usd is None:
            cost_rub, cost_usd = self._estimate_cost(model, pt, ct)
        try:
            cost_rub_f = float(cost_rub) if cost_rub is not None else None
        except (TypeError, ValueError):
            cost_rub_f = None
        try:
            cost_usd_f = float(cost_usd) if cost_usd is not None else None
        except (TypeError, ValueError):
            cost_usd_f = None
        result = LLMResult(
            text=text,
            model=model,
            role=role,
            prompt_tokens=pt,
            completion_tokens=ct,
            cost_rub=cost_rub_f,
            cost_usd=cost_usd_f,
            raw=data,
        )
        if self.project_id:
            self.store.add_cost(
                {
                    "project_id": self.project_id,
                    "model": model,
                    "role": role,
                    "prompt_tokens": pt,
                    "completion_tokens": ct,
                    "cost_rub": cost_rub_f,
                    "cost_usd": cost_usd_f,
                    "meta": {"id": data.get("id")},
                }
            )
            await get_bus().emit(
                self.project_id,
                "llm.cost",
                {
                    "model": model,
                    "role": role,
                    "prompt_tokens": pt,
                    "completion_tokens": ct,
                    "cost_rub": cost_rub_f,
                    "cost_usd": cost_usd_f,
                },
                agent_id=role,
            )
        return result


class Plugin:
    id = "llm.openai_compat"
    provides = ["llm"]
    requires: list[str] = []

    def apply(self, ctx: Context) -> None:
        ctx.provide("llm", LLMService())
