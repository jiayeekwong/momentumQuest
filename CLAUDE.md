# MomentumQuest Project Instructions

## Project Overview

MomentumQuest was built as a comprehensive Career Readiness & Skill-Gap Bridging Platform. The primary directive of the application is to close the feedback loop between education and employment by allowing:

-Students to analyze their skills against industry expectations, study customized training, get validated, and apply directly to matching roles.
-Companies to identify high-potential candidates, list positions detailing exact skills, and sponsor specialized training.
-Admins to oversee the market, regulate learning resources, approve training programs, and endorse official certificate standards.

The system uses:

- Frontend: Next.js with TypeScript
- Backend: Django REST Framework
- Database: PostgreSQL
- Authentication: JWT using SimpleJWT
- Email verification and password reset through Django email backend
- Web scraping module for job market skill extraction
- Learning resource recommendation module
- Certificate validation module


## Architecture of the System

1. The Entry Point
Authentication (/login, /signup):
Users select their role (Student, Company, or Admin) on sign-up/login.
The configuration persists the profile dynamically using AuthContext securely backed by localStorage (mq_user) to safeguard sessions.

2. Student Workflow
Dashboard (/dashboard):
A dashboard containing personalized recommendations, visual skill scores, pending job updates, and ongoing coursework modules.
Skill-Gap Analysis (/skill-gap):
Students choose target fields (e.g., Software Dev, Security Analyst) to run comparisons.
The system highlights skills in high demand and calculates specific deficiencies using dynamic metrics.
Learning Hub (/resources & /profile):
Reordered learning tracks containing courses mapped to the student's specific gaps.
Students go to the profile or validations panel to certify their competencies.
Smart Matching & Application (/jobs & /applications):
The job boards display matching scores showing how well a student's vetted skills align with an employer’s requirements.
Students apply with one-click simplicity and track real-time hiring stages (Pending, Shortlisted, Interviewing, Accepted, Rejected).

3. Company Workflow
Company Dashboard (/company-dashboard):
Overview of hiring pipelines, recruitment metrics, active postings, and applicant tracking.
Profile Setup (/profile):
Customization of corporate bio, industry classifications, and team sizing.
Listing & Program Sponsoring (/post-job & /post-training):
Companies submit job requirements, specifying target skills as mandatory requirements.
To foster stronger talent, they invite users into sponsored curriculum tracks to prep prospective applicants.
Hiring Funnel (/review-applications):
Review candidates sorting by match percentages, change applicant status states, and schedule direct interviews.

4. Admin Control Flow
Overview Main Desk (/admin-dashboard):
Global key performance indicators illustrating overall skills-bridging rates, system activity, and credential volumes.
Curriculum Supervision (/manage-courses & /approvals):
Managing course libraries and auditing company training plans to maintain standard educational value before they are hosted.
Validation Desk (/endorse):
Approval desk where admins vet and issue official stamps on newly earned micro-credentials.
Anouncements (/post-announcement):
Global communication tool to broadcast dates, job fairs, or schedule notices.


## Important Folder Structure

- backend/ = Django backend
- frontend/ = Next.js frontend

## Rules Before Answering or Editing Code

Always inspect the relevant files before suggesting code changes.

Do not modify:

- backend/.env
- frontend/.env.local
- backend/venv/
- frontend/node_modules/
- frontend/.next/

Do not expose secrets, database passwords, email passwords, app passwords, or tokens.

When giving code, clearly state:
1. Which file to open
2. What code to paste
3. What command to run after changes

## Backend Rules

Use Django REST Framework style.

Authentication uses:

- accounts.serializers.py
- accounts.views.py
- accounts.urls.py
- config.settings.py

The backend should use Python 3.12 virtual environment:

- backend/venv/

# MomentumQuest ERD Table Usage

This section explains the purpose of each database table in simple words. Before suggesting backend code changes, always refer to this table usage so the system logic stays consistent.

---

## User

The `User` table stores the main login account for every user in the system.

It contains common account information such as:

- email
- password
- role
- created_time

The `role` field decides whether the user is a Student, Company, or Admin.

Important rule:

- Every Student, Company, and Admin must have one related User account.
- Login and authentication should be handled through this table.
- Role-specific details should not be stored directly in `User`; they should be stored in Student, Company, or Admin tables.

---

## Student

The `Student` table stores student profile details.

It contains student-specific information such as:

- user_id
- student_name
- department

This table is used when the user role is `STUDENT`.

Main usage:

- Store student profile information.
- Link student to skills, certificates, skill gaps, target jobs, and job applications.

Important rule:

- A Student record belongs to one User.
- Student skills should be stored in `Student_skill`, not directly in Student.
- Student certificate records should be stored in `Certificate`.
- The student's career interest is no longer a free-text `desired_job_category`.
  It is now stored in `Student_Target_Job`, which links the student to one or
  more normalized `Job_Title` records.

---

## Company

The `Company` table stores employer/company profile details.

It contains:

- user_id
- company_name

This table is used when the user role is `COMPANY`.

Main usage:

- Store company profile information.
- Allow company users to post job listings.
- Allow company users to create training programmes.
- Allow company users to review student job applications.

Important rule:

- A Company record belongs to one User.
- Company-posted jobs should be stored in `Job_Listing`.
- Company training programmes should be stored in `Training_programme`.

---

## Admin

The `Admin` table stores admin profile details.

It contains:

- user_id
- admin_name

This table is used when the user role is `ADMIN`.

Main usage:

- Store admin profile information.
- Allow admin to approve or validate certificates.
- Allow admin to post announcements.
- Allow admin to manage courses and training programmes.
- Allow admin to review system data.

Important rule:

- An Admin record belongs to one User.
- Admin approval actions should update status fields such as `verified_status` or `approval_status`.

---

## Job_category

The `Job_category` table stores clean job categories used by the system.

It contains:

- category_id
- category_name
- description

Example categories:

- Web Developer
- Software Engineer
- Data Analyst
- Cybersecurity
- DevOps Engineer
- AI/ML Engineer
- Network Engineer
- UI/UX Designer

Main usage:

- Group different job titles into clear career categories.
- Help calculate skill demand by job category.
- Help match students with suitable career paths.
- Help classify scraped jobs from JobStreet.

Important rule:

- `job_title` and `job_category` are not the same.
- `job_title` is the original job name.
- `job_category` is the system’s clean classification.

Example:

- job_title: Junior React Developer
- job_category: Web Developer

---

## Skill

The `Skill` table stores all skills recognized by the system.

It contains:

- skill_id
- skill_name
- skill_category

Example skills:

- Python
- JavaScript
- React
- Django
- SQL
- Power BI
- Cybersecurity
- Git
- Docker
- AWS

Main usage:

- Store a controlled list of technical and soft skills.
- Link skills to students.
- Link skills to scraped jobs.
- Link skills to company job listings.
- Link skills to certificates.
- Link skills to learning resources.
- Link skills to courses and training programmes.

Important rule:

- Skills should be stored once in this table.
- Other tables should refer to skills using `skill_id`.
- Avoid creating duplicate skills such as `JavaScript`, `Javascript`, and `JS`.

---

## Student_skill

The `Student_skill` table stores the skills that a student currently has.

It contains:

- student_skill_id
- student_id
- skill_id
- skill_level

Main usage:

- Record student skill profile.
- Show what skills a student already knows.
- Compare student skills with market-required skills.
- Help calculate student skill gaps.

Example:

A student has:

- Python, Intermediate
- SQL, Beginner
- React, Beginner

Important rule:

- Do not store student skills as plain text in the Student table.
- Always link student skills to the `Skill` table.
- One student can have many skills.
- One skill can belong to many students.

---

## Scraped_job

> NOTE (current implementation): the separate `Scraped_job` table has been
> MERGED into `Job_Listing`. Scraped jobs are now rows in `Job_Listing` with
> `source_type = 'SCRAPED'`, a null `company`, and a populated `source_url`.
> Their extracted skills live in `Job_Skill` (not a separate `Scraped_job_skill`
> table). The scraper writes directly to `Job_Listing`. The sections below
> describe the original design and are kept for historical context.

The `Scraped_job` table stores external job market data collected from JobStreet or other job portals.

It contains:

- scraped_job_id
- category_id
- job_title
- description
- salary_min
- salary_max
- source_portal
- source_url
- scraped_time

Main usage:

- Store job information scraped from external job portals.
- Support skill demand analysis.
- Support skill gap calculation.
- Support job market trend analysis.

Important rule:

- `Scraped_job` is not the same as `Job_Listing`.
- `Scraped_job` is external market data.
- `Job_Listing` is a job posted by companies inside MomentumQuest.
- Students should not directly apply to `Scraped_job` records through MomentumQuest.
- Scraped jobs are used mainly for analysis, not for internal job applications.

Example:

- source_portal: JobStreet
- source_url: original JobStreet job link
- job_title: Data Analyst
- category_id: Data Analyst category

---

## Scraped_job_skill

The `Scraped_job_skill` table connects scraped jobs with extracted skills.

It contains:

- scraped_job_skill_id
- scraped_job_id
- skill_id

Main usage:

- Store which skills are required by each scraped job.
- Support skill demand calculation.
- Help identify what skills are commonly required in the job market.

Example:

A scraped job called `Junior Data Analyst` may contain:

- SQL
- Python
- Power BI
- Excel

These skills are stored as separate records in `Scraped_job_skill`.

Important rule:

- One scraped job can have many skills.
- One skill can appear in many scraped jobs.
- This table acts as a bridge between `Scraped_job` and `Skill`.

Relationship:

- Scraped_job 1 to many Scraped_job_skill
- Skill 1 to many Scraped_job_skill

---

## Skill_Gap

The `Skill_Gap` table stores the missing skills for students based on market demand.

It contains:

- gap_id
- student_id
- skill_id
- total_listings
- demand_percentage
- priority_level
- reviewed_time

Main usage:

- Show which important skills a student is missing.
- Show how demanded each missing skill is.
- Help students decide what to learn next.
- Support learning resource recommendations.

Example:

If a student wants to become a Data Analyst and does not have SQL, while SQL appears in many scraped Data Analyst jobs, the system creates a skill gap record for SQL.

Important rule:

- Skill gap is calculated by comparing:
  - student’s current skills in `Student_skill`
  - market-required skills from `Scraped_job_skill`
- High-demand missing skills should have higher priority.

Example priority logic:

- High priority: demand percentage is high
- Medium priority: demand percentage is moderate
- Low priority: demand percentage is low

---

## Learning_resource

The `Learning_resource` table stores learning materials linked to skills.

It contains:

- resource_id
- skill_id
- title
- platform
- url
- type

Main usage:

- Recommend learning resources to students based on missing skills.
- Help students improve their skill gaps.
- Store course, tutorial, documentation, or certification links.

Example platforms:

- freeCodeCamp
- IBM SkillsBuild
- Microsoft Learn
- Cisco Networking Academy
- Google Cloud Skills Boost
- Coursera
- edX

Important rule:

- Learning resources should link to a skill.
- The system should recommend resources based on the student’s missing skills.
- Certificate-providing resources are preferred because students can submit proof later.

Example:

- skill: JavaScript
- title: JavaScript Algorithms and Data Structures
- platform: freeCodeCamp
- type: Certification
- url: course link

---

## Certificate

The `Certificate` table stores certificates submitted by students.

It contains:

- certificate_id
- student_id
- skill_id
- admin_id
- cert_url
- source
- uploaded_time
- verified_status

Main usage:

- Allow students to submit proof that they completed a course or certification.
- Allow admin to validate the certificate.
- Update or confirm student skills after approval.
- Students are allowed to 

Certificate status examples:

- Pending
- Approved
- Rejected

Important rule:

- A certificate belongs to one student.
- A certificate should be linked to one skill.
- Admin reviews and updates the certificate status.
- If the certificate is approved, the related student skill can be added or confirmed.

Example:

A student completes a freeCodeCamp JavaScript certificate and submits the certificate URL. Admin checks the URL and approves it.

---

## Course

The `Course` table stores courses managed or recommended by the admin.

It contains:

- course_id
- admin_id
- skill_id
- title
- updated_at
- department

Main usage:

- Store learning courses provided by uniersity related to specific skills.
- Allow admin to manage course recommendations.
- Support skill development for students.

Important rule:

- A course should link to a skill.
- Admin is responsible for creating or updating course records.
- Courses are more formal/internal recommendations compared with general learning resources.

---

## Training_programme

The `Training_programme` table stores training programmes submitted or organized by companies/admin.

It contains:

- programme_id
- company_id
- admin_id
- skill_id
- title
- description
- approval_status
- programme_duration
- submission_time

Main usage:

- Allow companies to submit training programmes.
- Allow admin to approve or reject training programmes.
- Link training programmes to specific skills.
- Help students find practical training opportunities.

Important rule:

- A training programme can be submitted by a company.
- Admin can review and approve it.
- The programme should be linked to a skill.
- Only approved training programmes should be shown to students.

Example:

A company submits a “React Web Development Bootcamp”. Admin reviews it. If approved, it can be recommended to students missing React skills.

---

## Job_Listing

The `Job_Listing` table stores jobs posted by companies inside MomentumQuest.

It contains:

- job_id
- company_id
- category_id
- job_title
- description
- salary_min
- salary_max
- closing_date

Main usage:

- Store actual job opportunities posted by companies through the system.
- Allow students to view and apply for jobs.
- Allow companies to manage job postings.

Important rule:

- `Job_Listing` is internal company-posted job data.
- `Scraped_job` is external job market data.
- Students apply to `Job_Listing`, not `Scraped_job`.

Example:

A company posts:

- job_title: Junior Software Engineer
- category: Software Engineer
- salary_min: 3000
- salary_max: 4500

---

## Job_Skill

The `Job_Skill` table connects internal company job listings with required skills.

It contains:

- job_skill_id
- skill_id
- job_id
- importance_level

Main usage:

- Store what skills are required for a company-posted job.
- Show students what skills they need before applying.
- Help compare student skills with job requirements.

Example:

A job listing for Frontend Developer may require:

- JavaScript, High importance
- React, High importance
- CSS, Medium importance
- Git, Medium importance

Important rule:

- One job can require many skills.
- One skill can be required by many jobs.
- `importance_level` explains how important the skill is for that job.

---

## Job_application

The `Job_application` table stores job applications submitted by students.

It contains:

- application_id
- student_id
- job_id
- cv_url
- status
- applied_time
- notif_sent
- is_read

Main usage:

- Store student applications to company job listings.
- Allow company to review applicants.
- Track application status.
- Support notification and read/unread status.

Application status examples:

- Pending
- Reviewed
- Shortlisted
- Accepted
- Rejected

Important rule:

- One student can apply to many jobs.
- One job can receive many applications.
- Applications should only be linked to `Job_Listing`, not `Scraped_job`.

---

## Announcement

The `Announcement` table stores announcements posted by admin.

It contains:

- announ_id
- admin_id
- title
- message
- supporting_doc
- publish_time

Main usage:

- Allow admin to publish system-wide announcements.
- Inform students and companies about important updates.
- Store optional supporting documents.

Example announcements:

- New training programme available
- System maintenance notice
- Career fair announcement
- Certificate submission deadline

Important rule:

- Only admin should create announcements.
- Announcements can be shown on dashboards.

---

# Important System Design Rules

## Do not mix scraped jobs and company-posted jobs

`Scraped_job` and `Job_Listing` serve different purposes.

`Scraped_job` is used for market analysis and allow student to apply through redirect to third party websites.

`Job_Listing` is used for actual student job applications.

If the job appear in both scraped job and job posted by company through system, delete the record in scraped job and maintain the job posted by company.

Students should apply to `Job_Listing`, not `Scraped_job`.

---

## Skills should be centralized

All skills should be stored in the `Skill` table.

Other tables should refer to skills using `skill_id`.

This keeps skill data clean and prevents duplicate skill names.

---

## Job category should be normalized

Different job titles should be grouped under clean job categories.

Example:

- Junior React Developer → Web Developer
- Frontend Engineer → Web Developer
- Data Analyst Intern → Data Analyst
- SOC Analyst → Cybersecurity

This makes skill gap and demand analysis more accurate.

---

## Certificate validation should update student skills

When a student submits a certificate, the admin checks it.

If approved, the system can add or confirm the related skill in `Student_skill`.

This allows the student’s skill gap to improve after completing learning resources.

---

## Scraping should run in the backend only

Web scraping should not run from the frontend.

The scraping module should run through a Django management command such as:

```powershell
python manage.py scrape_jobs