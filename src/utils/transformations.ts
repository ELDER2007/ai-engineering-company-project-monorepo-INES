// ============================================================
// Nexova — Transformaciones, Agregaciones y Reportes
// ============================================================

import {
  type Candidate,
  type CandidateRankingItem,
  type CandidateStatus,
  type EnglishLevel,
  type NexovaOperationalReport,
  type NumericSummary,
  type ProcessStage,
  type SelectionProcess,
  type SeniorityLevel,
  type Vacancy,
  type VacancyStatus,
} from "../types/models";

const SENIORITY_ORDER: ReadonlyArray<SeniorityLevel> = [
  "Junior",
  "Semi-Senior",
  "Senior",
  "Lead",
  "Executive",
];

const ENGLISH_ORDER: ReadonlyArray<EnglishLevel> = ["A1", "A2", "B1", "B2", "C1", "C2", "Native"];

function roundTo2(value: number): number {
  return Math.round(value * 100) / 100;
}

function buildNumericSummary(values: ReadonlyArray<number>): NumericSummary {
  if (values.length === 0) {
    return { total: 0, max: 0, min: 0, average: 0 };
  }

  let total = 0;
  let max = values[0];
  let min = values[0];

  for (const value of values) {
    total += value;
    if (value > max) {
      max = value;
    }
    if (value < min) {
      min = value;
    }
  }

  return {
    total: roundTo2(total),
    max: roundTo2(max),
    min: roundTo2(min),
    average: roundTo2(total / values.length),
  };
}

export function countCandidatesByStatus(
  candidates: ReadonlyArray<Candidate> | null | undefined
): Record<CandidateStatus, number> {
  const counts: Record<CandidateStatus, number> = {
    Active: 0,
    "In process": 0,
    Hired: 0,
    Inactive: 0,
  };

  if (!candidates || candidates.length === 0) {
    return counts;
  }

  for (const candidate of candidates) {
    counts[candidate.status] += 1;
  }

  return counts;
}

export function countVacanciesByStatus(
  vacancies: ReadonlyArray<Vacancy> | null | undefined
): Record<VacancyStatus, number> {
  const counts: Record<VacancyStatus, number> = {
    Open: 0,
    "In progress": 0,
    Closed: 0,
    "On hold": 0,
  };

  if (!vacancies || vacancies.length === 0) {
    return counts;
  }

  for (const vacancy of vacancies) {
    counts[vacancy.status] += 1;
  }

  return counts;
}

export function countProcessesByStage(
  processes: ReadonlyArray<SelectionProcess> | null | undefined
): Record<ProcessStage, number> {
  const counts: Record<ProcessStage, number> = {
    Screening: 0,
    Interview: 0,
    "Technical test": 0,
    "Final interview": 0,
    Offer: 0,
    Rejected: 0,
    Hired: 0,
  };

  if (!processes || processes.length === 0) {
    return counts;
  }

  for (const process of processes) {
    counts[process.stage] += 1;
  }

  return counts;
}

export function sumExpectedSalaries(candidates: ReadonlyArray<Candidate> | null | undefined): number {
  if (!candidates || candidates.length === 0) {
    return 0;
  }
  return roundTo2(candidates.reduce((sum, candidate) => sum + candidate.expectedSalary, 0));
}

export function maxExpectedSalary(candidates: ReadonlyArray<Candidate> | null | undefined): number {
  if (!candidates || candidates.length === 0) {
    return 0;
  }
  return Math.max(...candidates.map((candidate) => candidate.expectedSalary));
}

export function minExpectedSalary(candidates: ReadonlyArray<Candidate> | null | undefined): number {
  if (!candidates || candidates.length === 0) {
    return 0;
  }
  return Math.min(...candidates.map((candidate) => candidate.expectedSalary));
}

export function averageExpectedSalary(candidates: ReadonlyArray<Candidate> | null | undefined): number {
  if (!candidates || candidates.length === 0) {
    return 0;
  }
  return roundTo2(sumExpectedSalaries(candidates) / candidates.length);
}

export function calculateCandidateScore(candidate: Candidate, vacancy: Vacancy): number {
  let score = 0;

  const candidateSkillsLower = candidate.skills.map((skill) => skill.toLowerCase());
  const requiredSkillsLower = vacancy.requiredSkills.map((skill) => skill.toLowerCase());
  const preferredSkillsLower = vacancy.preferredSkills.map((skill) => skill.toLowerCase());

  const requiredMatches = requiredSkillsLower.filter((skill) => candidateSkillsLower.includes(skill)).length;
  if (requiredSkillsLower.length > 0) {
    score += (requiredMatches / requiredSkillsLower.length) * 40;
  }

  const preferredMatches = preferredSkillsLower.filter((skill) => candidateSkillsLower.includes(skill)).length;
  score += Math.min(preferredMatches * 10, 20);

  if (
    candidate.yearsOfExperience >= vacancy.minYearsExperience &&
    candidate.yearsOfExperience <= vacancy.maxYearsExperience
  ) {
    score += 20;
  } else if (
    candidate.yearsOfExperience >= vacancy.minYearsExperience - 2 &&
    candidate.yearsOfExperience <= vacancy.maxYearsExperience + 2
  ) {
    score += 10;
  }

  const candidateSeniorityIndex = SENIORITY_ORDER.indexOf(candidate.seniority);
  const vacancySeniorityIndex = SENIORITY_ORDER.indexOf(vacancy.requiredSeniority);
  const seniorityDifference = Math.abs(candidateSeniorityIndex - vacancySeniorityIndex);
  if (seniorityDifference === 0) {
    score += 15;
  } else if (seniorityDifference === 1) {
    score += 7;
  }

  const candidateEnglishIndex = ENGLISH_ORDER.indexOf(candidate.englishLevel);
  const vacancyEnglishIndex = ENGLISH_ORDER.indexOf(vacancy.requiredEnglishLevel);
  if (candidateEnglishIndex >= vacancyEnglishIndex) {
    score += 15;
  }

  if (candidate.expectedSalary >= vacancy.salaryRangeMin && candidate.expectedSalary <= vacancy.salaryRangeMax) {
    score += 10;
  } else if (candidate.expectedSalary <= vacancy.salaryRangeMax * 1.2) {
    score += 5;
  }

  return roundTo2(Math.min(score, 100));
}

export function rankCandidatesForVacancy(
  candidates: ReadonlyArray<Candidate> | null | undefined,
  vacancy: Vacancy
): CandidateRankingItem[] {
  if (!candidates || candidates.length === 0) {
    return [];
  }

  return candidates
    .map((candidate) => ({
      candidate,
      score: calculateCandidateScore(candidate, vacancy),
    }))
    .sort((a, b) => b.score - a.score);
}

export function calculateVacancyFillRate(
  processes: ReadonlyArray<SelectionProcess> | null | undefined
): number {
  if (!processes || processes.length === 0) {
    return 0;
  }

  const hiredCount = processes.filter((process) => process.stage === "Hired").length;
  return roundTo2((hiredCount / processes.length) * 100);
}

export function buildNexovaOperationalReport(
  candidates: ReadonlyArray<Candidate> | null | undefined,
  vacancies: ReadonlyArray<Vacancy> | null | undefined,
  processes: ReadonlyArray<SelectionProcess> | null | undefined
): NexovaOperationalReport {
  const safeCandidates = candidates ?? [];
  const safeVacancies = vacancies ?? [];
  const safeProcesses = processes ?? [];

  return {
    totalCandidates: safeCandidates.length,
    totalVacancies: safeVacancies.length,
    totalProcesses: safeProcesses.length,
    candidatesByStatus: countCandidatesByStatus(safeCandidates),
    vacanciesByStatus: countVacanciesByStatus(safeVacancies),
    processesByStage: countProcessesByStage(safeProcesses),
    expectedSalarySummary: buildNumericSummary(
      safeCandidates.map((candidate) => candidate.expectedSalary)
    ),
    candidateScoreSummary: buildNumericSummary(safeProcesses.map((process) => process.score)),
  };
}