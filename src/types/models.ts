// ============================================================
// Nexova — Modelos de Datos (RRHH y Talent Acquisition)
// ============================================================

export type EnglishLevel = "A1" | "A2" | "B1" | "B2" | "C1" | "C2" | "Native";

export type SeniorityLevel = "Junior" | "Semi-Senior" | "Senior" | "Lead" | "Executive";

export type AvailabilityStatus = "Immediate" | "2 weeks" | "1 month" | "Not available";

export type CandidateStatus = "Active" | "In process" | "Hired" | "Inactive";

export type VacancyStatus = "Open" | "In progress" | "Closed" | "On hold";

export type ProcessStage =
  | "Screening"
  | "Interview"
  | "Technical test"
  | "Final interview"
  | "Offer"
  | "Rejected"
  | "Hired";

export interface Candidate {
  id: string;
  fullName: string;
  email: string;
  phone: string;
  yearsOfExperience: number;
  skills: string[];
  englishLevel: EnglishLevel;
  seniority: SeniorityLevel;
  currentSalary: number;
  expectedSalary: number;
  availability: AvailabilityStatus;
  location: string;
  remoteOnly: boolean;
  status: CandidateStatus;
}

export interface Vacancy {
  id: string;
  title: string;
  companyName: string;
  requiredSkills: string[];
  preferredSkills: string[];
  minYearsExperience: number;
  maxYearsExperience: number;
  requiredEnglishLevel: EnglishLevel;
  requiredSeniority: SeniorityLevel;
  salaryRangeMin: number;
  salaryRangeMax: number;
  isRemote: boolean;
  location: string;
  status: VacancyStatus;
}

export interface SelectionProcess {
  id: string;
  candidateId: string;
  vacancyId: string;
  stage: ProcessStage;
  score: number;
  notes: string;
  createdAt: Date;
  updatedAt: Date;
}

export interface CandidateRankingItem {
  candidate: Candidate;
  score: number;
}

export interface NumericSummary {
  total: number;
  max: number;
  min: number;
  average: number;
}

export interface NexovaOperationalReport {
  totalCandidates: number;
  totalVacancies: number;
  totalProcesses: number;
  candidatesByStatus: Record<CandidateStatus, number>;
  vacanciesByStatus: Record<VacancyStatus, number>;
  processesByStage: Record<ProcessStage, number>;
  expectedSalarySummary: NumericSummary;
  candidateScoreSummary: NumericSummary;
}

export const sampleCandidate: Candidate = {
  id: "C-2026-0001",
  fullName: "Maria Gonzalez",
  email: "maria.gonzalez@nexova.example",
  phone: "+56912345678",
  yearsOfExperience: 6,
  skills: ["TypeScript", "React", "Node.js", "PostgreSQL"],
  englishLevel: "C1",
  seniority: "Senior",
  currentSalary: 3400,
  expectedSalary: 4300,
  availability: "2 weeks",
  location: "Santiago, Chile",
  remoteOnly: false,
  status: "Active",
};

export const sampleVacancy: Vacancy = {
  id: "V-2026-0010",
  title: "Senior Full Stack Developer",
  companyName: "Nexova",
  requiredSkills: ["TypeScript", "React", "Node.js"],
  preferredSkills: ["PostgreSQL", "Docker"],
  minYearsExperience: 4,
  maxYearsExperience: 8,
  requiredEnglishLevel: "B2",
  requiredSeniority: "Senior",
  salaryRangeMin: 3800,
  salaryRangeMax: 5200,
  isRemote: true,
  location: "Santiago, Chile",
  status: "Open",
};

export const sampleSelectionProcess: SelectionProcess = {
  id: "P-2026-0300",
  candidateId: "C-2026-0001",
  vacancyId: "V-2026-0010",
  stage: "Interview",
  score: 82,
  notes: "Strong backend profile with good communication.",
  createdAt: new Date("2026-07-01T10:00:00.000Z"),
  updatedAt: new Date("2026-07-02T15:30:00.000Z"),
};

export const sampleCandidates: Candidate[] = [
  sampleCandidate,
  {
    id: "C-2026-0002",
    fullName: "Juan Perez",
    email: "juan.perez@nexova.example",
    phone: "+5491155566677",
    yearsOfExperience: 3,
    skills: ["JavaScript", "Vue", "Node.js"],
    englishLevel: "B2",
    seniority: "Semi-Senior",
    currentSalary: 2400,
    expectedSalary: 3000,
    availability: "Immediate",
    location: "Buenos Aires, Argentina",
    remoteOnly: true,
    status: "In process",
  },
  {
    id: "C-2026-0003",
    fullName: "Camila Rojas",
    email: "camila.rojas@nexova.example",
    phone: "+56999888777",
    yearsOfExperience: 9,
    skills: ["Python", "Django", "AWS", "PostgreSQL"],
    englishLevel: "C2",
    seniority: "Lead",
    currentSalary: 5100,
    expectedSalary: 6200,
    availability: "1 month",
    location: "Santiago, Chile",
    remoteOnly: false,
    status: "Active",
  },
];

export const sampleVacancies: Vacancy[] = [
  sampleVacancy,
  {
    id: "V-2026-0011",
    title: "Data Analyst",
    companyName: "Nexova",
    requiredSkills: ["SQL", "Python"],
    preferredSkills: ["Power BI", "Pandas"],
    minYearsExperience: 2,
    maxYearsExperience: 5,
    requiredEnglishLevel: "B1",
    requiredSeniority: "Semi-Senior",
    salaryRangeMin: 2200,
    salaryRangeMax: 3200,
    isRemote: false,
    location: "Buenos Aires, Argentina",
    status: "In progress",
  },
];

export const sampleSelectionProcesses: SelectionProcess[] = [
  sampleSelectionProcess,
  {
    id: "P-2026-0301",
    candidateId: "C-2026-0002",
    vacancyId: "V-2026-0011",
    stage: "Technical test",
    score: 74,
    notes: "Solid SQL and analytics foundations.",
    createdAt: new Date("2026-07-03T11:00:00.000Z"),
    updatedAt: new Date("2026-07-05T08:00:00.000Z"),
  },
];