import pytest
from core.url import parse_url, ParsedURL

def test_parse_hf_model_min():
    p = parse_url("https://huggingface.co/google-bert/bert-base-uncased")
    assert p.kind == "hf_model"
    assert p.owner == "google-bert"
    assert p.name == "bert-base-uncased"

def test_parse_hf_dataset_2_parts():
    p = parse_url("https://huggingface.co/datasets/bookcorpus")
    assert p.kind == "hf_dataset"
    assert p.owner is None
    assert p.name == "bookcorpus"

def test_parse_hf_dataset_3_parts():
    p = parse_url("https://huggingface.co/datasets/bookcorpus/bookcorpus")
    assert p.kind == "hf_dataset"
    assert p.owner == "bookcorpus"
    assert p.name == "bookcorpus"

def test_parse_github():
    p = parse_url("https://github.com/openai/gpt")
    assert p.kind == "github"
    assert p.owner == "openai"
    assert p.name == "gpt"

def test_parse_other():
    p = parse_url("https://example.com/x")
    assert p.kind == "other"
    assert p.owner is None
    assert p.name is None
