import type { DetectedEntity } from "@/lib/api";
import type { AnonymizationMethod, ReviewEntity, ReviewStatus } from "./types";

export type ReviewState = {
  originalText: string;
  entities: ReviewEntity[];
  defaultMethod: AnonymizationMethod;
  categoryFilter: string;
  confidenceThreshold: number;
  search: string;
  anonymizedText: string | null;
  transformStats: {
    transformed_count: number;
    rejected_count: number;
    method_counts: Record<string, number>;
    warnings: string[];
  } | null;
  error: string | null;
};

export type ReviewAction =
  | { type: "LOAD_ANALYSIS"; text: string; detections: DetectedEntity[] }
  | { type: "SET_STATUS"; id: string; status: ReviewStatus }
  | { type: "ACCEPT_VISIBLE"; ids: string[] }
  | { type: "REJECT_VISIBLE"; ids: string[] }
  | { type: "SET_DEFAULT_METHOD"; method: AnonymizationMethod }
  | { type: "SET_ENTITY_METHOD"; id: string; method: AnonymizationMethod }
  | {
      type: "EDIT_ENTITY";
      id: string;
      entity_type: string;
      start: number;
      end: number;
    }
  | { type: "ADD_MANUAL"; entity: ReviewEntity }
  | { type: "DELETE_ENTITY"; id: string }
  | { type: "SET_FILTERS"; categoryFilter?: string; confidenceThreshold?: number; search?: string }
  | {
      type: "SET_RESULT";
      anonymizedText: string;
      stats: ReviewState["transformStats"];
    }
  | { type: "SET_ERROR"; error: string | null }
  | { type: "CLEAR_ALL" }
  | { type: "BACK_TO_REVIEW" };

export function createId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export const initialReviewState: ReviewState = {
  originalText: "",
  entities: [],
  defaultMethod: "replacement",
  categoryFilter: "ALL",
  confidenceThreshold: 0,
  search: "",
  anonymizedText: null,
  transformStats: null,
  error: null,
};

export function reviewReducer(state: ReviewState, action: ReviewAction): ReviewState {
  switch (action.type) {
    case "LOAD_ANALYSIS":
      return {
        ...initialReviewState,
        originalText: action.text,
        defaultMethod: state.defaultMethod,
        entities: action.detections.map((detection) => ({
          id: createId(),
          entity_type: detection.entity_type,
          start: detection.start,
          end: detection.end,
          text: detection.text,
          confidence: detection.confidence,
          detection_source: detection.detection_source,
          recognizer_name: detection.recognizer_name,
          checksum_valid: detection.checksum_valid,
          explanation: detection.explanation,
          review_status: "pending" as const,
          anonymization_method: state.defaultMethod,
          manually_added: false,
        })),
      };
    case "SET_STATUS":
      return {
        ...state,
        entities: state.entities.map((entity) =>
          entity.id === action.id ? { ...entity, review_status: action.status } : entity,
        ),
      };
    case "ACCEPT_VISIBLE":
      return {
        ...state,
        entities: state.entities.map((entity) =>
          action.ids.includes(entity.id)
            ? {
                ...entity,
                review_status:
                  entity.review_status === "manually_added" || entity.review_status === "edited"
                    ? entity.review_status
                    : "accepted",
              }
            : entity,
        ),
      };
    case "REJECT_VISIBLE":
      return {
        ...state,
        entities: state.entities.map((entity) =>
          action.ids.includes(entity.id) ? { ...entity, review_status: "rejected" } : entity,
        ),
      };
    case "SET_DEFAULT_METHOD":
      return {
        ...state,
        defaultMethod: action.method,
        entities: state.entities.map((entity) => ({
          ...entity,
          anonymization_method: action.method,
        })),
      };
    case "SET_ENTITY_METHOD":
      return {
        ...state,
        entities: state.entities.map((entity) =>
          entity.id === action.id ? { ...entity, anonymization_method: action.method } : entity,
        ),
      };
    case "EDIT_ENTITY": {
      if (
        action.start < 0 ||
        action.end <= action.start ||
        action.end > state.originalText.length
      ) {
        return { ...state, error: "Edited span is out of range." };
      }
      const text = state.originalText.slice(action.start, action.end);
      return {
        ...state,
        error: null,
        entities: state.entities.map((entity) =>
          entity.id === action.id
            ? {
                ...entity,
                entity_type: action.entity_type,
                start: action.start,
                end: action.end,
                text,
                review_status: entity.manually_added ? "manually_added" : "edited",
                confidence: null,
              }
            : entity,
        ),
      };
    }
    case "ADD_MANUAL":
      return { ...state, entities: [...state.entities, action.entity], error: null };
    case "DELETE_ENTITY":
      return {
        ...state,
        entities: state.entities.filter((entity) => entity.id !== action.id),
      };
    case "SET_FILTERS":
      return {
        ...state,
        categoryFilter: action.categoryFilter ?? state.categoryFilter,
        confidenceThreshold: action.confidenceThreshold ?? state.confidenceThreshold,
        search: action.search ?? state.search,
      };
    case "SET_RESULT":
      return {
        ...state,
        anonymizedText: action.anonymizedText,
        transformStats: action.stats,
        error: null,
      };
    case "SET_ERROR":
      return { ...state, error: action.error };
    case "BACK_TO_REVIEW":
      return { ...state, anonymizedText: null, transformStats: null };
    case "CLEAR_ALL":
      return { ...initialReviewState, defaultMethod: state.defaultMethod };
    default:
      return state;
  }
}

export function filterEntities(state: ReviewState): ReviewEntity[] {
  const query = state.search.trim().toLowerCase();
  return state.entities
    .filter((entity) =>
      state.categoryFilter === "ALL" ? true : entity.entity_type === state.categoryFilter,
    )
    .filter((entity) =>
      entity.confidence === null ? true : entity.confidence >= state.confidenceThreshold,
    )
    .filter((entity) => {
      if (!query) return true;
      return (
        entity.entity_type.toLowerCase().includes(query) ||
        entity.text.toLowerCase().includes(query) ||
        entity.detection_source.toLowerCase().includes(query)
      );
    })
    .sort((a, b) => a.start - b.start);
}

export function counts(entities: ReviewEntity[]) {
  return {
    total: entities.length,
    accepted: entities.filter((e) =>
      ["pending", "accepted", "edited", "manually_added"].includes(e.review_status),
    ).length,
    rejected: entities.filter((e) => e.review_status === "rejected").length,
    manual: entities.filter((e) => e.manually_added).length,
  };
}
