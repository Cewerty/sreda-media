export type MaterialKind = "article" | "video" | "podcast" | "post";

export type MaterialStatus =
  | "idea"
  | "in_progress"
  | "in_review"
  | "changes_requested"
  | "approved"
  | "scheduled"
  | "published"
  | "cancelled";

export type EditorialRole =
  | "author"
  | "trusted_author"
  | "editor"
  | "observer"
  | "admin";

export interface ContentPlanAuthor {
  readonly id: string;
  readonly name: string;
  readonly role: EditorialRole;
}

export interface ContentPlanRubric {
  readonly id: string;
  readonly name: string;
}

export interface ContentPlanMaterial {
  readonly id: string;
  readonly title: string;
  readonly kind: MaterialKind;
  readonly status: MaterialStatus;
  readonly rubricId: ContentPlanRubric["id"];
  readonly assigneeId: ContentPlanAuthor["id"];
  readonly coauthorIds: readonly ContentPlanAuthor["id"][];
  readonly plannedDate: string;
  readonly publicationUrl: string | null;
}

export interface ContentPlanData {
  readonly materials: readonly ContentPlanMaterial[];
  readonly rubrics: readonly ContentPlanRubric[];
  readonly authors: readonly ContentPlanAuthor[];
}
