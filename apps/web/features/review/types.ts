export type ReviewStatus = "pending" | "accepted" | "rejected" | "edited" | "manually_added";

export type AnonymizationMethod = "replacement" | "redaction" | "masking" | "pseudonymize";

export const ENTITY_TYPES = [
  "PERSON",
  "EMAIL_ADDRESS",
  "PHONE_NUMBER",
  "STREET_ADDRESS",
  "CANADIAN_POSTAL_CODE",
  "DATE_OF_BIRTH",
  "CREDIT_CARD",
  "CANADIAN_SIN",
  "BANK_ACCOUNT",
  "IP_ADDRESS",
  "URL",
  "ORGANIZATION",
  "LOCATION",
  "MEDICAL_IDENTIFIER",
  "CUSTOM_IDENTIFIER",
] as const;

export type EntityType = (typeof ENTITY_TYPES)[number];

export type ReviewEntity = {
  id: string;
  entity_type: EntityType | string;
  start: number;
  end: number;
  text: string;
  confidence: number | null;
  detection_source: string;
  recognizer_name: string;
  checksum_valid?: boolean | null;
  explanation?: string;
  review_status: ReviewStatus;
  anonymization_method: AnonymizationMethod;
  manually_added: boolean;
};

export type WorkspaceStep = "input" | "review" | "result";
