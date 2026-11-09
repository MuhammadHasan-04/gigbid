from rag.retriever import get_retriever
from rag.verify import apply, entities, is_claim, verify


def test_claim_detection():
    assert is_claim("I built a churn model with XGBoost for a fintech client.")
    assert not is_claim("I would start with a discovery call.")
    assert not is_claim("Which part is most urgent?")


def test_entities_strip_skill_names():
    e = entities("I used LLM fine-tuning and R for Cedar Health.")
    assert "Cedar Health" in e["names"] and "LLM" not in e["names"] and "R" in e["skills"]


def test_fabrications_removed():
    r = get_retriever("ai_ml", "v0")
    text = "I have 12 years of Kubernetes experience. I delivered a Swift iOS app for Northwind. I would start next week."
    claims = verify(text, r, use_llm=False)
    assert all(c.verdict == "unsupported" for c in claims)
    assert apply(text, claims) == "I would start next week."
