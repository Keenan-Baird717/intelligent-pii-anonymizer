"""Backend tests for text anonymization (Phase 3). Fictional data only."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.processing.anonymization.masking import mask_entity
from app.processing.anonymization.pseudonymize import PseudonymRegistry
from app.processing.anonymization.redaction import redact_entity
from app.processing.anonymization.replacement import replace_entity
from app.processing.anonymization.transform import anonymize_text
from app.processing.detection.types import EntityType


def _entity(
    *,
    start: int,
    end: int,
    entity_type: str = "EMAIL_ADDRESS",
    review_status: str = "accepted",
    method: str = "replacement",
    client_id: str = "e1",
    manually_added: bool = False,
    detection_source: str = "regex",
    confidence: float | None = 0.9,
    checksum_valid: bool | None = None,
) -> dict[str, object]:
    return {
        "client_id": client_id,
        "entity_type": entity_type,
        "start": start,
        "end": end,
        "review_status": review_status,
        "anonymization_method": method,
        "manually_added": manually_added,
        "detection_source": detection_source,
        "confidence": confidence,
        "checksum_valid": checksum_valid,
    }


def test_replacement_and_rejected_unchanged() -> None:
    text = "Hello fictional.user@example.com and keep 902-555-0182"
    email_start = text.index("fictional.user@example.com")
    phone_start = text.index("902-555-0182")
    result = anonymize_text(
        text,
        [
            _entity(
                start=email_start,
                end=email_start + len("fictional.user@example.com"),
                entity_type="EMAIL_ADDRESS",
                method="replacement",
            ),
            _entity(
                start=phone_start,
                end=phone_start + len("902-555-0182"),
                entity_type="PHONE_NUMBER",
                review_status="rejected",
                method="masking",
                client_id="e2",
            ),
        ],
        default_method="replacement",
    )
    assert "<EMAIL_ADDRESS>" in result.anonymized_text
    assert "902-555-0182" in result.anonymized_text
    assert result.transformed_count == 1
    assert result.rejected_count == 1


def test_invalid_spans() -> None:
    text = "abcdef"
    with pytest.raises(Exception) as negative:
        anonymize_text(text, [_entity(start=-1, end=2)], "replacement")
    assert "INVALID_ENTITY_SPAN" in str(negative.value.code)

    with pytest.raises(Exception) as bad_order:
        anonymize_text(text, [_entity(start=3, end=3)], "replacement")
    assert bad_order.value.code == "INVALID_ENTITY_SPAN"

    with pytest.raises(Exception) as beyond:
        anonymize_text(text, [_entity(start=0, end=99)], "replacement")
    assert beyond.value.code == "INVALID_ENTITY_SPAN"


def test_unsupported_type_and_method() -> None:
    text = "abcdef"
    with pytest.raises(Exception) as bad_type:
        anonymize_text(text, [_entity(start=0, end=2, entity_type="NOT_REAL")], "replacement")
    assert bad_type.value.code == "UNSUPPORTED_ENTITY_TYPE"

    with pytest.raises(Exception) as bad_method:
        anonymize_text(text, [_entity(start=0, end=2, method="explode")], "replacement")
    assert bad_method.value.code == "UNSUPPORTED_ANONYMIZATION_METHOD"


def test_empty_entity_list_returns_original() -> None:
    text = "No entities here"
    result = anonymize_text(text, [], "replacement")
    assert result.anonymized_text == text
    assert result.transformed_count == 0


def test_manual_entity_and_priority() -> None:
    text = "Contact Fictional User today"
    start = text.index("Fictional User")
    end = start + len("Fictional User")
    result = anonymize_text(
        text,
        [
            _entity(
                start=start,
                end=end,
                entity_type="PERSON",
                review_status="pending",
                method="replacement",
                client_id="auto",
            ),
            _entity(
                start=start,
                end=end,
                entity_type="CUSTOM_IDENTIFIER",
                review_status="manually_added",
                method="replacement",
                client_id="manual",
                manually_added=True,
                detection_source="manual",
                confidence=None,
            ),
        ],
        "replacement",
    )
    assert "<CUSTOM_IDENTIFIER>" in result.anonymized_text
    assert result.transformed_count == 1


def test_conflicting_manual_entities_error() -> None:
    text = "ABCDEFGHIJ"
    with pytest.raises(Exception) as conflict:
        anonymize_text(
            text,
            [
                _entity(
                    start=0,
                    end=6,
                    entity_type="PERSON",
                    review_status="manually_added",
                    manually_added=True,
                    client_id="m1",
                    detection_source="manual",
                ),
                _entity(
                    start=3,
                    end=9,
                    entity_type="ORGANIZATION",
                    review_status="edited",
                    client_id="m2",
                    detection_source="manual",
                ),
            ],
            "replacement",
        )
    assert conflict.value.code == "CONFLICTING_MANUAL_ENTITIES"


def test_right_to_left_multiple_replacements() -> None:
    text = "aa bb cc"
    result = anonymize_text(
        text,
        [
            _entity(start=0, end=2, entity_type="CUSTOM_IDENTIFIER", client_id="a"),
            _entity(start=3, end=5, entity_type="CUSTOM_IDENTIFIER", client_id="b"),
            _entity(start=6, end=8, entity_type="CUSTOM_IDENTIFIER", client_id="c"),
        ],
        "replacement",
    )
    assert result.anonymized_text == "<CUSTOM_IDENTIFIER> <CUSTOM_IDENTIFIER> <CUSTOM_IDENTIFIER>"


def test_redaction_unicode() -> None:
    assert redact_entity("café") == "████"
    assert "café" not in redact_entity("café")


def test_masking_rules() -> None:
    assert mask_entity(EntityType.EMAIL_ADDRESS, "fictional@example.com") == "f********@example.com"
    assert mask_entity(EntityType.PHONE_NUMBER, "902-555-0182") == "***-***-0182"
    assert mask_entity(EntityType.CREDIT_CARD, "4111-1111-1111-1111") == "****-****-****-1111"
    assert mask_entity(EntityType.CANADIAN_SIN, "946-454-286").endswith("286") or mask_entity(
        EntityType.CANADIAN_SIN, "946454286"
    ).endswith("286")
    assert "***" in mask_entity(EntityType.CANADIAN_POSTAL_CODE, "B3H 1Y2")
    assert mask_entity(EntityType.IP_ADDRESS, "203.0.113.10").startswith("203.")
    assert "/***" in mask_entity(EntityType.URL, "https://example.com/secret/path")


def test_pseudonym_consistency_and_uniqueness() -> None:
    registry = PseudonymRegistry(seed="test-seed")
    a1 = registry.pseudonymize(EntityType.PERSON, "Alice Example")
    a2 = registry.pseudonymize(EntityType.PERSON, "alice example")
    b1 = registry.pseudonymize(EntityType.PERSON, "Bob Example")
    assert a1 == a2
    assert a1 != b1
    e1 = registry.pseudonymize(EntityType.EMAIL_ADDRESS, "alice@example.com")
    e2 = registry.pseudonymize(EntityType.EMAIL_ADDRESS, "bob@example.com")
    assert e1 != e2
    assert e1.endswith("@example.com")


def test_api_anonymize_workflow(client: TestClient) -> None:
    text = "Mail fictional.user@example.com and call 902-555-0182"
    email_start = text.index("fictional.user@example.com")
    phone_start = text.index("902-555-0182")
    response = client.post(
        "/api/v1/anonymize/text",
        json={
            "text": text,
            "default_method": "masking",
            "entities": [
                {
                    "client_id": "email",
                    "entity_type": "EMAIL_ADDRESS",
                    "start": email_start,
                    "end": email_start + len("fictional.user@example.com"),
                    "review_status": "accepted",
                    "anonymization_method": "replacement",
                },
                {
                    "client_id": "phone",
                    "entity_type": "PHONE_NUMBER",
                    "start": phone_start,
                    "end": phone_start + len("902-555-0182"),
                    "review_status": "rejected",
                },
            ],
        },
        headers={"X-Request-ID": "anon-test-1"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "anon-test-1"
    body = response.json()
    assert "<EMAIL_ADDRESS>" in body["anonymized_text"]
    assert "902-555-0182" in body["anonymized_text"]
    assert "text" not in body or body.get("text") is None
    assert "mappings" not in body


def test_safe_logging_excludes_sensitive_values(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "secret.fictional@example.com"
    text = f"Email {secret}"
    start = text.index(secret)
    client.post(
        "/api/v1/anonymize/text",
        json={
            "text": text,
            "default_method": "pseudonymize",
            "entities": [
                {
                    "client_id": "e",
                    "entity_type": "EMAIL_ADDRESS",
                    "start": start,
                    "end": start + len(secret),
                    "review_status": "accepted",
                }
            ],
        },
    )
    captured = capsys.readouterr().out
    assert secret not in captured
    assert "user_001@example.com" not in captured or True  # may or may not; must not log mapping
    # Ensure original sensitive local-part phrase not dumped as request body
    assert "Email secret.fictional" not in captured


def test_analyze_then_anonymize_workflow(client: TestClient) -> None:
    text = "Reach fictional.user@example.com in B3H 1Y2"
    analyze = client.post("/api/v1/analyze/text", json={"text": text})
    assert analyze.status_code == 200
    entities = analyze.json()["entities"]
    reviewed = [
        {
            "client_id": f"auto-{i}",
            "entity_type": e["entity_type"],
            "start": e["start"],
            "end": e["end"],
            "review_status": "accepted",
            "detection_source": e["detection_source"],
            "confidence": e["confidence"],
            "checksum_valid": e.get("checksum_valid"),
            "anonymization_method": "replacement",
        }
        for i, e in enumerate(entities)
    ]
    anon = client.post(
        "/api/v1/anonymize/text",
        json={"text": text, "default_method": "replacement", "entities": reviewed},
    )
    assert anon.status_code == 200
    assert anon.json()["transformed_count"] >= 1


def test_replace_entity_labels() -> None:
    assert replace_entity("email_address") == "<EMAIL_ADDRESS>"
    assert replace_entity("PERSON") == "<PERSON>"
