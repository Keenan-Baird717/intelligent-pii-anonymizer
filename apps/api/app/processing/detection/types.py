"""Entity type constants for Phase 2 detection."""

from enum import StrEnum


class EntityType(StrEnum):
    PERSON = "PERSON"
    EMAIL_ADDRESS = "EMAIL_ADDRESS"
    PHONE_NUMBER = "PHONE_NUMBER"
    STREET_ADDRESS = "STREET_ADDRESS"
    CANADIAN_POSTAL_CODE = "CANADIAN_POSTAL_CODE"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    CREDIT_CARD = "CREDIT_CARD"
    CANADIAN_SIN = "CANADIAN_SIN"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    IP_ADDRESS = "IP_ADDRESS"
    URL = "URL"
    ORGANIZATION = "ORGANIZATION"
    LOCATION = "LOCATION"
    MEDICAL_IDENTIFIER = "MEDICAL_IDENTIFIER"
    CUSTOM_IDENTIFIER = "CUSTOM_IDENTIFIER"


class DetectionSource(StrEnum):
    REGEX = "regex"
    REGEX_CHECKSUM = "regex_checksum"
    PRESIDIO = "presidio"
    SPACY = "spacy"
    CUSTOM = "custom"
    MANUAL = "manual"


ENTITY_SPECIFICITY: dict[str, int] = {
    EntityType.CREDIT_CARD: 100,
    EntityType.CANADIAN_SIN: 100,
    EntityType.EMAIL_ADDRESS: 90,
    EntityType.CANADIAN_POSTAL_CODE: 85,
    EntityType.PHONE_NUMBER: 80,
    EntityType.IP_ADDRESS: 80,
    EntityType.URL: 75,
    EntityType.BANK_ACCOUNT: 70,
    EntityType.MEDICAL_IDENTIFIER: 70,
    EntityType.DATE_OF_BIRTH: 65,
    EntityType.STREET_ADDRESS: 60,
    EntityType.CUSTOM_IDENTIFIER: 55,
    EntityType.PERSON: 50,
    EntityType.ORGANIZATION: 45,
    EntityType.LOCATION: 40,
}

SOURCE_PRIORITY: dict[str, int] = {
    DetectionSource.MANUAL: 100,
    DetectionSource.REGEX_CHECKSUM: 80,
    DetectionSource.REGEX: 60,
    DetectionSource.PRESIDIO: 50,
    DetectionSource.SPACY: 40,
    DetectionSource.CUSTOM: 30,
}

PRESIDIO_TYPE_MAP: dict[str, str] = {
    "PERSON": EntityType.PERSON,
    "EMAIL_ADDRESS": EntityType.EMAIL_ADDRESS,
    "PHONE_NUMBER": EntityType.PHONE_NUMBER,
    "CREDIT_CARD": EntityType.CREDIT_CARD,
    "IBAN_CODE": EntityType.BANK_ACCOUNT,
    "IP_ADDRESS": EntityType.IP_ADDRESS,
    "URL": EntityType.URL,
    "LOCATION": EntityType.LOCATION,
    "DATE_TIME": EntityType.DATE_OF_BIRTH,
    "NRP": EntityType.CUSTOM_IDENTIFIER,
    "MEDICAL_LICENSE": EntityType.MEDICAL_IDENTIFIER,
    "US_SSN": EntityType.CUSTOM_IDENTIFIER,
    "US_BANK_NUMBER": EntityType.BANK_ACCOUNT,
    "US_DRIVER_LICENSE": EntityType.CUSTOM_IDENTIFIER,
    "US_PASSPORT": EntityType.CUSTOM_IDENTIFIER,
    "US_ITIN": EntityType.CUSTOM_IDENTIFIER,
    "CRYPTO": EntityType.CUSTOM_IDENTIFIER,
    "ORG": EntityType.ORGANIZATION,
    "ORGANIZATION": EntityType.ORGANIZATION,
}
