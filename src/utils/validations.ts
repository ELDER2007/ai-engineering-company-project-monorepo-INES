// ============================================================
// Nexova — Validaciones
// Reglas de campos obligatorios, rangos y coherencia de fechas
// ============================================================

import { type Candidate, type SelectionProcess, type Vacancy } from "../types/models";

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

function buildValidationResult(errors: string[]): ValidationResult {
  return {
    valid: errors.length === 0,
    errors,
  };
}

function isNonEmptyString(value: string | null | undefined): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function hasValidDate(date: Date | null | undefined): boolean {
  if (!date) {
    return false;
  }
  return Number.isFinite(date.getTime());
}

export function isValidEmail(email: string | null | undefined): boolean {
  if (!isNonEmptyString(email)) {
    return false;
  }
  const normalizedEmail = email.trim();
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail);
}

export function validateCandidate(candidate: Candidate | null | undefined): ValidationResult {
  const errors: string[] = [];

  if (!candidate) {
    return buildValidationResult(["Candidate is required"]);
  }

  if (!isNonEmptyString(candidate.id)) {
    errors.push("id is required");
  }

  if (!isNonEmptyString(candidate.fullName)) {
    errors.push("fullName is required");
  }

  if (!isValidEmail(candidate.email)) {
    errors.push("email format is invalid");
  }

  if (!isNonEmptyString(candidate.phone)) {
    errors.push("phone is required");
  }

  if (!Array.isArray(candidate.skills) || candidate.skills.length === 0) {
    errors.push("skills must contain at least one value");
  }

  if (
    !Number.isFinite(candidate.yearsOfExperience) ||
    candidate.yearsOfExperience < 0 ||
    candidate.yearsOfExperience > 50
  ) {
    errors.push("yearsOfExperience must be between 0 and 50");
  }

  if (!Number.isFinite(candidate.currentSalary) || candidate.currentSalary <= 0) {
    errors.push("currentSalary must be greater than 0");
  }

  if (!Number.isFinite(candidate.expectedSalary) || candidate.expectedSalary <= 0) {
    errors.push("expectedSalary must be greater than 0");
  }

  if (!isNonEmptyString(candidate.location)) {
    errors.push("location is required");
  }

  return buildValidationResult(errors);
}

export function validateVacancy(vacancy: Vacancy | null | undefined): ValidationResult {
  const errors: string[] = [];

  if (!vacancy) {
    return buildValidationResult(["Vacancy is required"]);
  }

  if (!isNonEmptyString(vacancy.id)) {
    errors.push("id is required");
  }

  if (!isNonEmptyString(vacancy.title)) {
    errors.push("title is required");
  }

  if (!isNonEmptyString(vacancy.companyName)) {
    errors.push("companyName is required");
  }

  if (!Array.isArray(vacancy.requiredSkills) || vacancy.requiredSkills.length === 0) {
    errors.push("requiredSkills must contain at least one value");
  }

  if (!Number.isFinite(vacancy.minYearsExperience) || vacancy.minYearsExperience < 0) {
    errors.push("minYearsExperience must be greater than or equal to 0");
  }

  if (!Number.isFinite(vacancy.maxYearsExperience) || vacancy.maxYearsExperience < 0) {
    errors.push("maxYearsExperience must be greater than or equal to 0");
  }

  if (
    Number.isFinite(vacancy.minYearsExperience) &&
    Number.isFinite(vacancy.maxYearsExperience) &&
    vacancy.maxYearsExperience < vacancy.minYearsExperience
  ) {
    errors.push("maxYearsExperience must be greater than or equal to minYearsExperience");
  }

  if (!Number.isFinite(vacancy.salaryRangeMin) || vacancy.salaryRangeMin <= 0) {
    errors.push("salaryRangeMin must be greater than 0");
  }

  if (!Number.isFinite(vacancy.salaryRangeMax) || vacancy.salaryRangeMax <= 0) {
    errors.push("salaryRangeMax must be greater than 0");
  }

  if (
    Number.isFinite(vacancy.salaryRangeMin) &&
    Number.isFinite(vacancy.salaryRangeMax) &&
    vacancy.salaryRangeMax < vacancy.salaryRangeMin
  ) {
    errors.push("salaryRangeMax must be greater than or equal to salaryRangeMin");
  }

  if (!isNonEmptyString(vacancy.location)) {
    errors.push("location is required");
  }

  return buildValidationResult(errors);
}

export function validateSelectionProcess(
  process: SelectionProcess | null | undefined
): ValidationResult {
  const errors: string[] = [];

  if (!process) {
    return buildValidationResult(["SelectionProcess is required"]);
  }

  if (!isNonEmptyString(process.id)) {
    errors.push("id is required");
  }

  if (!isNonEmptyString(process.candidateId)) {
    errors.push("candidateId is required");
  }

  if (!isNonEmptyString(process.vacancyId)) {
    errors.push("vacancyId is required");
  }

  if (!isNonEmptyString(process.notes)) {
    errors.push("notes is required");
  }

  if (!Number.isFinite(process.score) || process.score < 0 || process.score > 100) {
    errors.push("score must be between 0 and 100");
  }

  if (!hasValidDate(process.createdAt)) {
    errors.push("createdAt must be a valid date");
  }

  if (!hasValidDate(process.updatedAt)) {
    errors.push("updatedAt must be a valid date");
  }

  if (
    hasValidDate(process.createdAt) &&
    hasValidDate(process.updatedAt) &&
    process.updatedAt.getTime() < process.createdAt.getTime()
  ) {
    errors.push("updatedAt must be greater than or equal to createdAt");
  }

  return buildValidationResult(errors);
}