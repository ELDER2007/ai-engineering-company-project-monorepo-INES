import {
  filterCandidatesByAvailability,
  filterCandidatesByCriteria,
  filterCandidatesBySeniority,
  filterCandidatesBySkills,
  sortCandidatesByExperience,
  sortCandidatesByFields,
  sortCandidatesBySalary,
} from "./utils/collections";
import {
  binarySearchCandidateByExpectedSalary,
  binarySearchCandidateById,
  linearSearchCandidateByEmail,
  linearSearchCandidateById,
} from "./utils/search";
import {
  averageExpectedSalary,
  buildNexovaOperationalReport,
  calculateCandidateScore,
  calculateVacancyFillRate,
  countCandidatesByStatus,
  countProcessesByStage,
  countVacanciesByStatus,
  maxExpectedSalary,
  minExpectedSalary,
  rankCandidatesForVacancy,
  sumExpectedSalaries,
} from "./utils/transformations";
import {
  isValidEmail,
  validateCandidate,
  validateSelectionProcess,
  validateVacancy,
} from "./utils/validations";
import { testCandidates, testSelectionProcesses, testVacancies } from "./data";

function section(title: string): void {
  console.log(`\n=== ${title} ===`);
}

function printCandidatesTable(title: string, candidates = testCandidates): void {
  console.log(`\n${title}`);
  console.table(
    candidates.map((candidate) => ({
      id: candidate.id,
      name: candidate.fullName,
      seniority: candidate.seniority,
      english: candidate.englishLevel,
      expectedSalary: candidate.expectedSalary,
      availability: candidate.availability,
      remoteOnly: candidate.remoteOnly,
      status: candidate.status,
    }))
  );
}

function showResult<TInput, TOutput>(
  functionName: string,
  input: TInput,
  output: TOutput
): void {
  console.log(`\n${functionName}`);
  console.log("input:", input);
  console.log("output:", output);
}

section("Data inicial");
console.log("Candidates:", testCandidates.length);
console.log("Vacancies:", testVacancies.length);
console.log("Processes:", testSelectionProcesses.length);
printCandidatesTable("Tabla base de candidatos:");

section("Busqueda");
const indexById = linearSearchCandidateById(testCandidates, "C-2026-0102");
const indexByEmail = linearSearchCandidateByEmail(testCandidates, "ana.torres@nexova.example");
showResult(
  "linearSearchCandidateById",
  { id: "C-2026-0102" },
  {
    index: indexById,
    candidate: indexById >= 0 ? testCandidates[indexById].fullName : null,
  }
);
showResult(
  "linearSearchCandidateByEmail",
  { email: "ana.torres@nexova.example" },
  {
    index: indexByEmail,
    candidate: indexByEmail >= 0 ? testCandidates[indexByEmail].fullName : null,
  }
);

const candidatesBySalaryAsc = sortCandidatesBySalary(testCandidates, "asc");
const binaryBySalary = binarySearchCandidateByExpectedSalary(candidatesBySalaryAsc, 4300);
showResult(
  "binarySearchCandidateByExpectedSalary",
  { targetSalary: 4300, sortedSalaryList: candidatesBySalaryAsc.map((c) => c.expectedSalary) },
  {
    index: binaryBySalary,
    candidate: binaryBySalary >= 0 ? candidatesBySalaryAsc[binaryBySalary].fullName : null,
  }
);

const candidatesById = [...testCandidates].sort((a, b) => a.id.localeCompare(b.id));
const binaryById = binarySearchCandidateById(candidatesById, "C-2026-0103");
showResult(
  "binarySearchCandidateById",
  { targetId: "C-2026-0103", sortedIds: candidatesById.map((c) => c.id) },
  {
    index: binaryById,
    candidate: binaryById >= 0 ? candidatesById[binaryById].fullName : null,
  }
);

section("Filtros y ordenamientos");
const bySkills = filterCandidatesBySkills(testCandidates, ["TypeScript", "Node.js"]);
showResult(
  "filterCandidatesBySkills",
  { requiredSkills: ["TypeScript", "Node.js"] },
  bySkills.map((candidate) => candidate.fullName)
);
printCandidatesTable("Resultado filterCandidatesBySkills:", bySkills);

const bySeniority = filterCandidatesBySeniority(testCandidates, "Senior");
showResult(
  "filterCandidatesBySeniority",
  { seniority: "Senior" },
  bySeniority.map((candidate) => candidate.fullName)
);

const byAvailability = filterCandidatesByAvailability(testCandidates, ["Immediate", "2 weeks"]);
showResult(
  "filterCandidatesByAvailability",
  { availability: ["Immediate", "2 weeks"] },
  byAvailability.map((candidate) => candidate.fullName)
);

const byCriteria = filterCandidatesByCriteria(testCandidates, {
  remoteOnly: true,
  minimumExpectedSalary: 2500,
  maximumExpectedSalary: 4500,
  skills: ["Node.js"],
});
showResult(
  "filterCandidatesByCriteria",
  {
    remoteOnly: true,
    minimumExpectedSalary: 2500,
    maximumExpectedSalary: 4500,
    skills: ["Node.js"],
  },
  byCriteria.map((candidate) => candidate.fullName)
);

const experienceDesc = sortCandidatesByExperience(testCandidates, "desc");
showResult(
  "sortCandidatesByExperience",
  { order: "desc" },
  experienceDesc.map((candidate) => `${candidate.fullName} (${candidate.yearsOfExperience}y)`)
);

const sortedByFields = sortCandidatesByFields(testCandidates, [
  { field: "seniority", direction: "desc" },
  { field: "expectedSalary", direction: "asc" },
]);
showResult(
  "sortCandidatesByFields",
  {
    rules: [
      { field: "seniority", direction: "desc" },
      { field: "expectedSalary", direction: "asc" },
    ],
  },
  sortedByFields.map((candidate) => `${candidate.fullName} (${candidate.seniority})`)
);
printCandidatesTable("Resultado sortCandidatesByFields:", sortedByFields);

section("Transformaciones y metricas");
showResult("countCandidatesByStatus", {}, countCandidatesByStatus(testCandidates));
showResult("countVacanciesByStatus", {}, countVacanciesByStatus(testVacancies));
showResult("countProcessesByStage", {}, countProcessesByStage(testSelectionProcesses));
showResult("sumExpectedSalaries", {}, sumExpectedSalaries(testCandidates));
showResult("averageExpectedSalary", {}, averageExpectedSalary(testCandidates));
showResult("maxExpectedSalary", {}, maxExpectedSalary(testCandidates));
showResult("minExpectedSalary", {}, minExpectedSalary(testCandidates));

const score = calculateCandidateScore(testCandidates[0], testVacancies[0]);
showResult(
  "calculateCandidateScore",
  { candidate: testCandidates[0].fullName, vacancy: testVacancies[0].title },
  score
);

const ranking = rankCandidatesForVacancy(testCandidates, testVacancies[0]);
showResult(
  "rankCandidatesForVacancy",
  { vacancy: testVacancies[0].title },
  ranking.slice(0, 3).map((item) => ({
    candidate: item.candidate.fullName,
    score: item.score,
  }))
);

showResult("calculateVacancyFillRate", {}, `${calculateVacancyFillRate(testSelectionProcesses)}%`);

const report = buildNexovaOperationalReport(testCandidates, testVacancies, testSelectionProcesses);
showResult("buildNexovaOperationalReport", {}, {
  totalCandidates: report.totalCandidates,
  totalVacancies: report.totalVacancies,
  totalProcesses: report.totalProcesses,
  expectedSalarySummary: report.expectedSalarySummary,
  candidateScoreSummary: report.candidateScoreSummary,
});

section("Validaciones");
showResult("isValidEmail", { email: "demo@nexova.example" }, isValidEmail("demo@nexova.example"));
showResult("isValidEmail", { email: "demo@bad" }, isValidEmail("demo@bad"));

showResult(
  "validateCandidate (valid)",
  { candidateId: testCandidates[0].id },
  validateCandidate(testCandidates[0])
);
showResult(
  "validateVacancy (valid)",
  { vacancyId: testVacancies[0].id },
  validateVacancy(testVacancies[0])
);
showResult(
  "validateSelectionProcess (valid)",
  { processId: testSelectionProcesses[0].id },
  validateSelectionProcess(testSelectionProcesses[0])
);

const invalidCandidate = {
  ...testCandidates[0],
  email: "correo-sin-formato",
  yearsOfExperience: -1,
  expectedSalary: 0,
};

showResult(
  "validateCandidate (invalid)",
  {
    candidateId: invalidCandidate.id,
    changedFields: {
      email: invalidCandidate.email,
      yearsOfExperience: invalidCandidate.yearsOfExperience,
      expectedSalary: invalidCandidate.expectedSalary,
    },
  },
  validateCandidate(invalidCandidate)
);
