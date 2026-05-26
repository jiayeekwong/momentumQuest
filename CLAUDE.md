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

