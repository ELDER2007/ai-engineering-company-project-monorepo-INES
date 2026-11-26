// ============================================================
// Nexova — Operaciones de Colecciones
// Filtros y ordenamientos puros para arreglos tipados
// ============================================================

import {
  type AvailabilityStatus,
  type Candidate,
  type CandidateStatus,
  type SeniorityLevel,
} from "../types/models";

export type SortDirection = "asc" | "desc";

export type CandidateSortableField =
  | "fullName"
  | "yearsOfExperience"
  | "expectedSalary"
  | "currentSalary"
  | "englishLevel"
  | "seniority"
  | "status";

export interface CandidateSortRule {
  field: CandidateSortableField;
  direction: SortDirection;
}

export interface CandidateFilterCriteria {
  seniority?: SeniorityLevel;
  availability?: ReadonlyArray<AvailabilityStatus>;
  minimumExpectedSalary?: number;
  maximumExpectedSalary?: number;
  skills?: ReadonlyArray<string>;
  status?: CandidateStatus;
  remoteOnly?: boolean;
}

const ENGLISH_ORDER: ReadonlyArray<Candidate["englishLevel"]> = [
  "A1",
  "A2",
  "B1",
  "B2",
  "C1",
  "C2",
  "Native",
];

const SENIORITY_ORDER: ReadonlyArray<SeniorityLevel> = [
  "Junior",
  "Semi-Senior",
  "Senior",
  "Lead",
  "Executive",
];

const STATUS_ORDER: ReadonlyArray<CandidateStatus> = [
  "Active",
  "In process",
  "Hired",
  "Inactive",
];

function compareStrings(a: string, b: string): number {
  return a.localeCompare(b, "en", { sensitivity: "base" });
}

function compareByField(a: Candidate, b: Candidate, field: CandidateSortableField): number {
  switch (field) {
    case "fullName":
      return compareStrings(a.fullName, b.fullName);
    case "yearsOfExperience":
      return a.yearsOfExperience - b.yearsOfExperience;
    case "expectedSalary":
      return a.expectedSalary - b.expectedSalary;
    case "currentSalary":
      return a.currentSalary - b.currentSalary;
    case "englishLevel":
      return ENGLISH_ORDER.indexOf(a.englishLevel) - ENGLISH_ORDER.indexOf(b.englishLevel);
    case "seniority":
      return SENIORITY_ORDER.indexOf(a.seniority) - SENIORITY_ORDER.indexOf(b.seniority);
    case "status":
      return STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status);
    default:
      return 0;
  }
}

export function filterCandidatesBySkills(
  candidates: ReadonlyArray<Candidate> | null | undefined,
  requiredSkills: ReadonlyArray<string> | null | undefined
): Candidate[] {
  if (!candidates || candidates.length === 0) {
    return [];
  }

  if (!requiredSkills || requiredSkills.length === 0) {
    return [...candidates];
  }

  const normalizedRequired = requiredSkills
    .map((skill) => skill.trim().toLowerCase())
    .filter((skill) => skill.length > 0);

  if (normalizedRequired.length === 0) {
    return [...candidates];
  }

  return candidates.filter((candidate) => {
    const normalizedCandidateSkills = candidate.skills.map((skill) => skill.toLowerCase());
    return normalizedRequired.every((requiredSkill) =>
      normalizedCandidateSkills.includes(requiredSkill)
    );
  });
}

export function filterCandidatesBySeniority(
  candidates: ReadonlyArray<Candidate> | null | undefined,
  seniority: SeniorityLevel | null | undefined
): Candidate[] {
  if (!candidates || candidates.length === 0 || !seniority) {
    return [];
  }
  return candidates.filter((candidate) => candidate.seniority === seniority);
}

export function filterCandidatesByAvailability(
  candidates: ReadonlyArray<Candidate> | null | undefined,
  availability: ReadonlyArray<AvailabilityStatus> | null | undefined
): Candidate[] {
  if (!candidates || candidates.length === 0) {
    return [];
  }

  if (!availability || availability.length === 0) {
    return [...candidates];
  }

  return candidates.filter((candidate) => availability.includes(candidate.availability));
}

export function filterCandidatesByCriteria(
  candidates: ReadonlyArray<Candidate> | null | undefined,
  criteria: CandidateFilterCriteria | null | undefined
): Candidate[] {
  if (!candidates || candidates.length === 0) {
    return [];
  }

  if (!criteria) {
    return [...candidates];
  }

  const normalizedSkills = (criteria.skills ?? [])
    .map((skill) => skill.trim().toLowerCase())
    .filter((skill) => skill.length > 0);

  return candidates.filter((candidate) => {
    if (criteria.seniority && candidate.seniority !== criteria.seniority) {
      return false;
    }

    if (criteria.status && candidate.status !== criteria.status) {
      return false;
    }

    if (typeof criteria.remoteOnly === "boolean" && candidate.remoteOnly !== criteria.remoteOnly) {
      return false;
    }

    if (
      Array.isArray(criteria.availability) &&
      criteria.availability.length > 0 &&
      !criteria.availability.includes(candidate.availability)
    ) {
      return false;
    }

    if (
      Number.isFinite(criteria.minimumExpectedSalary) &&
      candidate.expectedSalary < (criteria.minimumExpectedSalary as number)
    ) {
      return false;
    }

    if (
      Number.isFinite(criteria.maximumExpectedSalary) &&
      candidate.expectedSalary > (criteria.maximumExpectedSalary as number)
    ) {
      return false;
    }

    if (normalizedSkills.length > 0) {
      const candidateSkills = candidate.skills.map((skill) => skill.toLowerCase());
      const hasAllSkills = normalizedSkills.every((skill) => candidateSkills.includes(skill));
      if (!hasAllSkills) {
        return false;
      }
    }

    return true;
  });
}

export function sortCandidatesBySalary(
  candidates: ReadonlyArray<Candidate> | null | undefined,
  order: SortDirection
): Candidate[] {
  if (!candidates || candidates.length === 0) {
    return [];
  }
  return [...candidates].sort((a, b) =>
    order === "asc" ? a.expectedSalary - b.expectedSalary : b.expectedSalary - a.expectedSalary
  );
}

export function sortCandidatesByExperience(
  candidates: ReadonlyArray<Candidate> | null | undefined,
  order: SortDirection
): Candidate[] {
  if (!candidates || candidates.length === 0) {
    return [];
  }
  return [...candidates].sort((a, b) =>
    order === "asc"
      ? a.yearsOfExperience - b.yearsOfExperience
      : b.yearsOfExperience - a.yearsOfExperience
  );
}

export function sortCandidatesByFields(
  candidates: ReadonlyArray<Candidate> | null | undefined,
  rules: ReadonlyArray<CandidateSortRule> | null | undefined
): Candidate[] {
  if (!candidates || candidates.length === 0) {
    return [];
  }

  if (!rules || rules.length === 0) {
    return [...candidates];
  }

  return [...candidates].sort((a, b) => {
    for (const rule of rules) {
      const result = compareByField(a, b, rule.field);
      if (result !== 0) {
        return rule.direction === "asc" ? result : -result;
      }
    }
    return 0;
  });
}