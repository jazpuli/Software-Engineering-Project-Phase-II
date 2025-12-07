"""Lineage detection service for HuggingFace models."""

import re
import requests
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from src.api.db import crud


# Common base model patterns in HuggingFace
BASE_MODEL_PATTERNS = [
    # Direct references in config
    r'"_name_or_path"\s*:\s*"([^"]+)"',
    r'"model_name_or_path"\s*:\s*"([^"]+)"',
    r'"base_model"\s*:\s*"([^"]+)"',
    r'"pretrained_model_name_or_path"\s*:\s*"([^"]+)"',
    # References in model cards
    r'fine-tuned\s+(?:from|on|version of)\s+[`\[]?([a-zA-Z0-9_/-]+)[`\]]?',
    r'based\s+on\s+[`\[]?([a-zA-Z0-9_/-]+)[`\]]?',
    r'trained\s+(?:from|on)\s+[`\[]?([a-zA-Z0-9_/-]+)[`\]]?',
]

# Well-known base models
KNOWN_BASE_MODELS = {
    "gpt2": "openai-community/gpt2",
    "bert-base-uncased": "google-bert/bert-base-uncased",
    "bert-base-cased": "google-bert/bert-base-cased",
    "roberta-base": "FacebookAI/roberta-base",
    "distilbert-base-uncased": "distilbert/distilbert-base-uncased",
    "t5-small": "google-t5/t5-small",
    "t5-base": "google-t5/t5-base",
    "llama": "meta-llama/Llama-2-7b",
    "mistral": "mistralai/Mistral-7B-v0.1",
    "falcon": "tiiuae/falcon-7b",
}


def fetch_model_config(model_id: str) -> Optional[Dict[str, Any]]:
    """Fetch config.json from HuggingFace model."""
    try:
        url = f"https://huggingface.co/{model_id}/raw/main/config.json"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None


def fetch_model_card(model_id: str) -> Optional[str]:
    """Fetch README/model card from HuggingFace model."""
    try:
        url = f"https://huggingface.co/{model_id}/raw/main/README.md"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.text
    except Exception:
        pass
    return None


def extract_base_model_from_config(config: Dict[str, Any]) -> Optional[str]:
    """Extract base model reference from config.json."""
    # Check common fields
    fields_to_check = [
        "_name_or_path",
        "model_name_or_path",
        "base_model",
        "pretrained_model_name_or_path",
        "model_type",
    ]

    for field in fields_to_check:
        if field in config:
            value = config[field]
            if isinstance(value, str) and "/" in value:
                # Looks like a HuggingFace model ID
                return value
            elif isinstance(value, str) and value in KNOWN_BASE_MODELS:
                return KNOWN_BASE_MODELS[value]

    # Check architectures field
    if "architectures" in config:
        arch = config["architectures"]
        if isinstance(arch, list) and arch:
            arch_name = arch[0].lower()
            for base, full_id in KNOWN_BASE_MODELS.items():
                if base in arch_name:
                    return full_id

    return None


def extract_base_model_from_card(card_text: str) -> Optional[str]:
    """Extract base model reference from model card text."""
    if not card_text:
        return None

    # Search for patterns
    for pattern in BASE_MODEL_PATTERNS[4:]:  # Card-specific patterns
        matches = re.findall(pattern, card_text, re.IGNORECASE)
        for match in matches:
            # Validate it looks like a model ID
            if "/" in match and len(match) < 100:
                return match
            elif match in KNOWN_BASE_MODELS:
                return KNOWN_BASE_MODELS[match]

    return None


def detect_parent_models(model_id: str, hf_data: Optional[Dict] = None) -> List[str]:
    """
    Detect parent/base models for a given HuggingFace model.

    Args:
        model_id: HuggingFace model ID (e.g., "org/model-name")
        hf_data: Optional pre-fetched HuggingFace API data

    Returns:
        List of parent model IDs
    """
    parents = set()

    # 1. Check config.json
    config = fetch_model_config(model_id)
    if config:
        base = extract_base_model_from_config(config)
        if base and base != model_id:
            parents.add(base)

    # 2. Check model card
    card = fetch_model_card(model_id)
    if card:
        base = extract_base_model_from_card(card)
        if base and base != model_id:
            parents.add(base)

    # 3. Check HuggingFace API data if provided
    if hf_data:
        # Check tags for base model info
        tags = hf_data.get("tags", []) or []
        for tag in tags:
            if tag.startswith("base_model:"):
                base = tag.replace("base_model:", "")
                if base and base != model_id:
                    parents.add(base)

        # Check card data
        card_data = hf_data.get("cardData", {}) or {}
        if "base_model" in card_data:
            base = card_data["base_model"]
            if isinstance(base, str) and base != model_id:
                parents.add(base)
            elif isinstance(base, list):
                for b in base:
                    if b != model_id:
                        parents.add(b)

    # Filter out self-references and invalid IDs
    parents.discard(model_id)
    parents = {p for p in parents if "/" in p or p in KNOWN_BASE_MODELS}

    # Normalize known models
    normalized = set()
    for p in parents:
        if p in KNOWN_BASE_MODELS:
            normalized.add(KNOWN_BASE_MODELS[p])
        else:
            normalized.add(p)

    return list(normalized)


def create_lineage_for_artifact(
    db: Session,
    artifact_id: str,
    model_id: str,
    hf_data: Optional[Dict] = None,
) -> List[str]:
    """
    Detect and create lineage edges for an artifact.

    Args:
        db: Database session
        artifact_id: ID of the artifact to create lineage for
        model_id: HuggingFace model ID
        hf_data: Optional pre-fetched HuggingFace API data

    Returns:
        List of parent model IDs that were linked
    """
    parent_model_ids = detect_parent_models(model_id, hf_data)
    linked_parents = []

    for parent_model_id in parent_model_ids:
        # Check if parent exists in our registry
        # Search by name (the model ID is stored as name)
        all_artifacts = crud.list_artifacts(db, limit=1000)
        parent_artifact = None

        for artifact in all_artifacts:
            # Match by exact name only to avoid false positives
            # (e.g., "superbert" should NOT match parent "bert")
            if artifact.name == parent_model_id:
                parent_artifact = artifact
                break

        if parent_artifact and parent_artifact.id != artifact_id:
            # Create lineage edge
            try:
                crud.add_lineage_edge(db, parent_artifact.id, artifact_id)
                linked_parents.append(parent_model_id)
            except Exception:
                pass  # Edge might already exist

    return linked_parents

