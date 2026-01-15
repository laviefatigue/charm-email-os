"""
AI-powered domain name generator.

Uses LLMs to generate professional, brand-aligned domain name
candidates based on client context (industry, keywords, audience).

Supports multiple LLM backends:
- OpenAI (GPT-4)
- Anthropic (Claude)
- Local (Ollama)

Example:
    config = DomainGeneratorConfig(model="gpt-4")
    request = DomainRequest(
        client_name="Acme Corp",
        industry="SaaS",
        brand_keywords=["outreach", "connect"],
        required_entra_domains=6,
    )
    candidates = await generate_domain_candidates(request, config)
"""

from typing import Optional
from datetime import datetime
from decimal import Decimal
import asyncio
import json
import os
import re
import logging

from pydantic import BaseModel, Field

from .models import DomainRequest, DomainCandidate, DomainStatus

logger = logging.getLogger(__name__)


class DomainGeneratorConfig(BaseModel):
    """Configuration for domain generation."""
    model: str = Field(default="gpt-4", description="LLM model to use")
    provider: str = Field(default="openai", description="LLM provider (openai, anthropic, ollama)")
    temperature: float = Field(default=0.8, ge=0.0, le=2.0, description="Creativity level")
    extra_variations: int = Field(default=2, ge=1, le=5, description="Multiplier for domain suggestions")

    # Provider-specific settings
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"


def _build_generation_prompt(request: DomainRequest) -> str:
    """
    Build the prompt for domain name generation.

    The prompt guides the LLM to generate professional, brand-appropriate
    domain names suitable for cold email infrastructure.
    """
    count = request.generation_count
    tlds = ", ".join([f".{p.tld}" for p in request.preferred_tlds[:4]])
    avoid_list = ", ".join(request.avoid_words) if request.avoid_words else "none"

    prompt = f"""You are a domain name strategist for cold email infrastructure. Generate {count} professional domain name suggestions for a client.

## CLIENT CONTEXT
- Company Name: {request.client_name}
- Industry: {request.industry}
- Brand Keywords: {", ".join(request.brand_keywords) if request.brand_keywords else "general professional"}
- Target Audience: {request.target_audience or "B2B professionals"}
- Words to Avoid: {avoid_list}

## REQUIREMENTS
1. Domain names should look like legitimate business domains (for email deliverability)
2. Avoid spammy patterns (no numbers, excessive hyphens, or keyword stuffing)
3. Prefer short, memorable names (ideally 8-15 characters before TLD)
4. Mix these patterns:
   - Brand variations: [keyword]-[company derivative]
   - Industry signals: [action verb]-[industry term]
   - Professional suffixes: [brand]hq, [brand]team, [brand]group
   - Clean combinations: [adjective]-[noun]

## PREFERRED TLDs
{tlds}

## OUTPUT FORMAT
Return a JSON array of domain objects. Each object should have:
- "name": the domain without TLD (e.g., "outreach-acme")
- "tld": preferred TLD (e.g., "com")
- "rationale": brief explanation (10-15 words)
- "legitimacy_score": 0.0-1.0 rating of how professional it looks

Example:
```json
[
  {{"name": "growthforge", "tld": "com", "rationale": "Evokes business growth, professional sound", "legitimacy_score": 0.9}},
  {{"name": "acme-connect", "tld": "io", "rationale": "Brand + action verb, tech-friendly TLD", "legitimacy_score": 0.85}}
]
```

Generate exactly {count} unique domain suggestions. Prioritize quality and variety.
Return ONLY the JSON array, no other text."""

    return prompt


async def _call_openai(prompt: str, config: DomainGeneratorConfig) -> str:
    """Call OpenAI API for domain generation."""
    try:
        import httpx

        api_key = config.openai_api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key not configured")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": config.temperature,
                    "max_tokens": 4000,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        raise


async def _call_anthropic(prompt: str, config: DomainGeneratorConfig) -> str:
    """Call Anthropic API for domain generation."""
    try:
        import httpx

        api_key = config.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Anthropic API key not configured")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2024-01-01",
                },
                json={
                    "model": config.model if "claude" in config.model else "claude-3-sonnet-20240229",
                    "max_tokens": 4000,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]
    except Exception as e:
        logger.error(f"Anthropic API error: {e}")
        raise


async def _call_ollama(prompt: str, config: DomainGeneratorConfig) -> str:
    """Call local Ollama for domain generation."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{config.ollama_base_url}/api/generate",
                json={
                    "model": config.model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["response"]
    except Exception as e:
        logger.error(f"Ollama API error: {e}")
        raise


def _parse_llm_response(response: str, request_id: str) -> list[DomainCandidate]:
    """
    Parse LLM response into DomainCandidate objects.

    Handles various response formats and extracts JSON array.
    """
    candidates = []

    # Try to extract JSON from response
    try:
        # Find JSON array in response (handles markdown code blocks)
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            json_str = json_match.group()
            domains = json.loads(json_str)

            for d in domains:
                if isinstance(d, dict) and "name" in d:
                    name = d["name"].lower().strip()
                    tld = d.get("tld", "com").lower().strip().lstrip(".")

                    # Validate domain name format
                    if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$', name) and len(name) > 2:
                        # Try to clean it
                        name = re.sub(r'[^a-z0-9-]', '', name.lower())
                        if not name:
                            continue

                    candidate = DomainCandidate(
                        request_id=request_id,
                        domain_name=f"{name}.{tld}",
                        base_name=name,
                        tld=tld,
                        generation_rationale=d.get("rationale", ""),
                        legitimacy_score=float(d.get("legitimacy_score", 0.7)),
                        status=DomainStatus.GENERATED,
                    )
                    candidates.append(candidate)

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
        # Fallback: try to extract domain-like patterns
        domain_pattern = r'[a-z0-9][a-z0-9-]*[a-z0-9]\.(com|io|co|ai|net|org)'
        matches = re.findall(domain_pattern, response.lower())
        for match in matches:
            parts = match.rsplit('.', 1)
            if len(parts) == 2:
                name, tld = parts
                candidates.append(DomainCandidate(
                    request_id=request_id,
                    domain_name=match,
                    base_name=name,
                    tld=tld,
                    generation_rationale="Extracted from response",
                    legitimacy_score=0.5,
                    status=DomainStatus.GENERATED,
                ))

    return candidates


async def generate_domain_candidates(
    request: DomainRequest,
    config: Optional[DomainGeneratorConfig] = None,
) -> list[DomainCandidate]:
    """
    Generate domain name candidates using AI.

    Args:
        request: Domain sourcing request with client context
        config: Optional generator configuration

    Returns:
        List of DomainCandidate objects

    Example:
        >>> request = DomainRequest(
        ...     client_name="Acme Corp",
        ...     industry="SaaS",
        ...     brand_keywords=["growth", "scale"],
        ...     required_entra_domains=6,
        ...     required_google_domains=5,
        ... )
        >>> candidates = await generate_domain_candidates(request)
        >>> print(f"Generated {len(candidates)} candidates")
        Generated 33 candidates
    """
    if config is None:
        config = DomainGeneratorConfig()

    # Build the prompt
    prompt = _build_generation_prompt(request)

    # Call appropriate LLM provider
    try:
        if config.provider == "openai":
            response = await _call_openai(prompt, config)
        elif config.provider == "anthropic":
            response = await _call_anthropic(prompt, config)
        elif config.provider == "ollama":
            response = await _call_ollama(prompt, config)
        else:
            raise ValueError(f"Unknown provider: {config.provider}")

        # Parse response into candidates
        candidates = _parse_llm_response(response, request.id)

        logger.info(f"Generated {len(candidates)} domain candidates for {request.client_name}")
        return candidates

    except Exception as e:
        logger.error(f"Domain generation failed: {e}")
        raise


def generate_fallback_candidates(request: DomainRequest) -> list[DomainCandidate]:
    """
    Generate fallback domain candidates without AI.

    Uses simple pattern-based generation as a backup when LLM is unavailable.
    """
    candidates = []

    # Derive base from client name
    base = re.sub(r'[^a-z0-9]', '', request.client_name.lower())[:10]

    # Common patterns
    prefixes = ["get", "try", "use", "go", "my", "the", "hello", "hi"]
    suffixes = ["hq", "team", "group", "app", "hub", "io", "co", "inc"]
    action_words = ["reach", "connect", "grow", "scale", "outreach", "engage"]

    tlds = [p.tld for p in request.preferred_tlds[:3]]
    count = 0
    max_count = request.generation_count

    # Pattern 1: prefix-base
    for prefix in prefixes:
        for tld in tlds:
            if count >= max_count:
                break
            name = f"{prefix}{base}"
            candidates.append(DomainCandidate(
                request_id=request.id,
                domain_name=f"{name}.{tld}",
                base_name=name,
                tld=tld,
                generation_rationale=f"Prefix pattern: {prefix} + brand",
                legitimacy_score=0.6,
                status=DomainStatus.GENERATED,
            ))
            count += 1

    # Pattern 2: base-suffix
    for suffix in suffixes:
        for tld in tlds:
            if count >= max_count:
                break
            name = f"{base}{suffix}"
            candidates.append(DomainCandidate(
                request_id=request.id,
                domain_name=f"{name}.{tld}",
                base_name=name,
                tld=tld,
                generation_rationale=f"Suffix pattern: brand + {suffix}",
                legitimacy_score=0.65,
                status=DomainStatus.GENERATED,
            ))
            count += 1

    # Pattern 3: keyword combinations
    for keyword in request.brand_keywords[:3]:
        for tld in tlds:
            if count >= max_count:
                break
            name = f"{keyword}-{base}"
            candidates.append(DomainCandidate(
                request_id=request.id,
                domain_name=f"{name}.{tld}",
                base_name=name,
                tld=tld,
                generation_rationale=f"Keyword pattern: {keyword} + brand",
                legitimacy_score=0.7,
                status=DomainStatus.GENERATED,
            ))
            count += 1

    # Pattern 4: action words
    for action in action_words:
        for tld in tlds:
            if count >= max_count:
                break
            name = f"{action}-{base}"
            candidates.append(DomainCandidate(
                request_id=request.id,
                domain_name=f"{name}.{tld}",
                base_name=name,
                tld=tld,
                generation_rationale=f"Action pattern: {action} + brand",
                legitimacy_score=0.7,
                status=DomainStatus.GENERATED,
            ))
            count += 1

    logger.info(f"Generated {len(candidates)} fallback candidates for {request.client_name}")
    return candidates[:max_count]
