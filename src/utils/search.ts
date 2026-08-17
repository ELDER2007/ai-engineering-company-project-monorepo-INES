// ============================================================
// Nexova — Operaciones de Busqueda
// Busqueda lineal para arrays desordenados y binaria para ordenados
// ============================================================

import { type Candidate } from "../types/models";

export function linearSearchCandidateById(
  candidates: ReadonlyArray<Candidate> | null | undefined,
  id: string | null | undefined
): number {
  if (!candidates || candidates.length === 0 || !id) {
    return -1;
  }

  for (let index = 0; index < candidates.length; index += 1) {
    if (candidates[index].id === id) {
      return index;
    }
  }

  return -1;
}

export function linearSearchCandidateByEmail(
  candidates: ReadonlyArray<Candidate> | null | undefined,
  email: string | null | undefined
): number {
  if (!candidates || candidates.length === 0 || !email) {
    return -1;
  }

  const normalizedEmail = email.trim().toLowerCase();
  if (normalizedEmail.length === 0) {
    return -1;
  }

  for (let index = 0; index < candidates.length; index += 1) {
    if (candidates[index].email.toLowerCase() === normalizedEmail) {
      return index;
    }
  }

  return -1;
}

export function binarySearchCandidateByExpectedSalary(
  sortedCandidates: ReadonlyArray<Candidate> | null | undefined,
  targetSalary: number
): number {
  if (!sortedCandidates || sortedCandidates.length === 0) {
    return -1;
  }

  let left = 0;
  let right = sortedCandidates.length - 1;

  while (left <= right) {
    const middle = Math.floor((left + right) / 2);
    const middleSalary = sortedCandidates[middle].expectedSalary;

    if (middleSalary === targetSalary) {
      return middle;
    }

    if (middleSalary < targetSalary) {
      left = middle + 1;
    } else {
      right = middle - 1;
    }
  }

  return -1;
}

export function binarySearchCandidateById(
  sortedCandidatesById: ReadonlyArray<Candidate> | null | undefined,
  targetId: string | null | undefined
): number {
  if (!sortedCandidatesById || sortedCandidatesById.length === 0 || !targetId) {
    return -1;
  }

  let left = 0;
  let right = sortedCandidatesById.length - 1;

  while (left <= right) {
    const middle = Math.floor((left + right) / 2);
    const middleId = sortedCandidatesById[middle].id;
    const comparison = middleId.localeCompare(targetId);

    if (comparison === 0) {
      return middle;
    }

    if (comparison < 0) {
      left = middle + 1;
    } else {
      right = middle - 1;
    }
  }

  return -1;
}