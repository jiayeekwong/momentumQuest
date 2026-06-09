export type UserRole = 'student' | 'company' | 'admin';

export interface TargetJob {
  id: number;
  title_name: string;
}

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  avatar?: string;
  department?: string;
  targetJobs?: TargetJob[];
  companyName?: string;
  createdAt?: string;
  updatedAt?: string;
}

// Student-specific types
export interface StudentProfile extends User {
  department: string;
  graduationYear?: number;
  currentSkills: Skill[];
  targetJobTitle?: string;
  appliedJobs: string[];
  certifications?: Certificate[];
}

// Company-specific types
export interface CompanyProfile extends User {
  companyName: string;
  industry?: string;
  size?: 'startup' | 'scale-up' | 'enterprise';
  website?: string;
  hq?: string;
  activeListings: number;
  applications: number;
}

// Admin-specific types
export interface AdminProfile extends User {
  department?: string;
  permissions?: string[];
}

// Skill and training types
export interface Skill {
  id: string;
  name: string;
  category: string;
  proficiency: 'beginner' | 'intermediate' | 'advanced' | 'expert';
  verifiedBy?: string;
  verifiedDate?: string;
}

export interface Course {
  id: string;
  title: string;
  description: string;
  provider: string;
  duration: string;
  skillsTaught: string[];
  difficulty: 'beginner' | 'intermediate' | 'advanced';
  cost?: number;
  certificateIncluded: boolean;
  url?: string;
}

export interface Certificate {
  id: string;
  name: string;
  issuer: string;
  issuedDate: string;
  expiryDate?: string;
  skillVerified?: string[];
  status: 'pending' | 'approved' | 'rejected';
}

// Job and application types
export interface JobListing {
  id: string;
  title: string;
  company: string;
  companyLogo?: string;
  description: string;
  category: string;
  salary: string;
  salaryMin?: number;
  salaryMax?: number;
  location?: string;
  closingDate: string;
  requiredSkills: string[];
  matchScore?: number;
  applicants?: number;
  postedDate?: string;
  status?: 'open' | 'closed' | 'filled';
}

export interface JobApplication {
  id: string;
  jobId: string;
  studentId: string;
  jobTitle: string;
  companyName: string;
  submittedDate: string;
  status: 'pending' | 'shortlisted' | 'interview' | 'accepted' | 'rejected';
  lastUpdated: string;
  notes?: string;
}

export interface Candidate {
  id: string;
  name: string;
  email: string;
  matchScore: number;
  skills: string[];
  appliedDate: string;
  status: 'pending' | 'shortlisted' | 'interview' | 'accepted' | 'rejected';
  avatar?: string;
}

// Training and workshop types
export interface TrainingWorkshop {
  id: string;
  title: string;
  company: string;
  description: string;
  skills: string[];
  targetAudience: string;
  startDate: string;
  endDate: string;
  maxParticipants?: number;
  registered?: number;
  status: 'pending' | 'approved' | 'rejected' | 'active' | 'completed';
  cost?: number;
  certificateIncluded: boolean;
  content?: string;
}

// Skill gap analysis types
export interface SkillGapAnalysis {
  jobTitle: string;
  requiredSkills: SkillRequirement[];
  acquiredSkills: SkillRequirement[];
  gapCount: number;
  matchPercentage: number;
  recommendations: CourseRecommendation[];
}

export interface SkillRequirement {
  skill: string;
  proficiency: 'beginner' | 'intermediate' | 'advanced' | 'expert';
  acquired: boolean;
}

export interface CourseRecommendation {
  courseId: string;
  courseTitle: string;
  skill: string;
  provider: string;
  priority: 'high' | 'medium' | 'low';
  estimatedDays: number;
}

// Announcement types
export interface Announcement {
  id: string;
  title: string;
  content: string;
  author: string;
  publishedDate: string;
  priority: 'high' | 'medium' | 'low';
  audience: 'all' | 'students' | 'companies' | 'admins';
  status: 'draft' | 'published' | 'archived';
}

// Dashboard stats types
export interface StudentDashboardStats {
  skillsAcquired: number;
  skillGaps: number;
  jobsApplied: number;
  certifications: number;
  streak?: number;
}

export interface CompanyDashboardStats {
  activeListings: number;
  totalApplications: number;
  shortlisted: number;
  interviews: number;
  conversionRate?: number;
}

export interface AdminDashboardStats {
  totalUsers: number;
  activeListings: number;
  pendingApprovals: number;
  certificationsApproved: number;
  activeTrainings: number;
}

// API Response types
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

// Pagination types
export interface PaginationParams {
  page: number;
  limit: number;
  sortBy?: string;
  order?: 'asc' | 'desc';
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

// Filter and search types
export interface JobFilter {
  category?: string;
  salaryMin?: number;
  salaryMax?: number;
  skills?: string[];
  location?: string;
  status?: string;
}

export interface StudentFilter {
  skills?: string[];
  experience?: string;
  location?: string;
  availability?: string;
}

// Form types
export interface LoginFormData {
  email: string;
  password: string;
}

export interface SignUpFormData {
  name: string;
  email: string;
  password: string;
  confirmPassword: string;
  role: UserRole;
}

// Status badges
export const StatusVariants = {
  pending: 'warning',
  shortlisted: 'info',
  interview: 'primary',
  accepted: 'success',
  rejected: 'danger',
  approved: 'success',
  completed: 'success',
  active: 'success',
  open: 'success',
  closed: 'danger',
  filled: 'warning',
  draft: 'neutral',
  published: 'success',
  archived: 'neutral',
} as const;

// Color mappings
export const CategoryColors: Record<string, string> = {
  'Data Science': 'bg-purple-50 text-purple-700',
  'Web Development': 'bg-blue-50 text-blue-700',
  'Cloud Computing': 'bg-sky-50 text-sky-700',
  'DevOps': 'bg-orange-50 text-orange-700',
  'Cybersecurity': 'bg-red-50 text-red-700',
  'AI/ML': 'bg-violet-50 text-violet-700',
  'Analytics': 'bg-indigo-50 text-indigo-700',
  'Mobile Development': 'bg-green-50 text-green-700',
};

// Mock data constants
export const MOCK_SKILLS = [
  'Python', 'JavaScript', 'TypeScript', 'React', 'Next.js',
  'SQL', 'PostgreSQL', 'MongoDB', 'Docker', 'Kubernetes',
  'AWS', 'GCP', 'Azure', 'Terraform', 'Jenkins',
  'Machine Learning', 'Deep Learning', 'NLP', 'TensorFlow', 'PyTorch'
];

export const MOCK_JOB_CATEGORIES = [
  'Data Science', 'Web Development', 'Cloud Computing',
  'DevOps', 'Cybersecurity', 'AI/ML', 'Analytics', 'Mobile Development'
];

export const MOCK_COMPANIES = [
  'Nexus AI', 'FinTrack', 'CloudTech', 'DataVault',
  'SecureNet', 'DevOps Pro', 'WebFlow', 'AI Solutions'
];

export const JOB_DEMAND_SKILLS = [
  'Data Analysis', 'Cloud Computing', 'AI', 'Cybersecurity', 'DevOps'
];
