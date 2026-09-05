"""The MomentumQuest privacy notice, as versioned server-side content.

Kept as a module rather than a database table for two reasons. Version history
is what the spec asks be preserved, and git already preserves it exactly --
a table would need its own admin CRUD to achieve less. And serving the text
from here means a version bump is a backend change: the frontend renders
whatever ``/api/auth/privacy-notice/current/`` returns, so no page has to be
redeployed when the notice changes.

Adding a version:
  1. Add a new entry to NOTICES. Never edit a published one -- a consent row
     points at its version string, and rewriting that text would silently
     change what past users are recorded as having agreed to.
  2. Point CURRENT_VERSION at it.
  3. Decide whether existing users must re-acknowledge.
"""

from datetime import date

from django.conf import settings

# 1.2 removes the administrator review of transcripts and stops keeping the
# file at all. Existing students are not blocked from logging in: every
# document function asks for its acknowledgement at the point of use and
# records it against whatever version is current, so the next upload is itself
# the re-acknowledgement.
CURRENT_VERSION = "1.2"

# Shown on the sign-up screen above the consent checkboxes. Kept short on
# purpose: the full notice is one click away, and a wall of text at the point
# of decision is read by nobody.
SIGNUP_SUMMARY = (
    "MomentumQuest processes your personal and academic information to provide "
    "skill validation, learning recommendations and job-matching functions.\n\n"
    "Certificates or examination results that you upload may contain your name "
    "and NRIC/MyKad or passport number. Authorised administrators may view "
    "these details when verifying that the document belongs to you."
)

# The exact wording a user is agreeing to. Stored here so the checkbox label,
# the consent record and the full notice cannot drift apart.
CONSENT_STATEMENTS = {
    "PRIVACY_NOTICE_ACKNOWLEDGEMENT":
        "I have read and understood the MomentumQuest Personal Data Privacy Notice.",
    "DOCUMENT_VERIFICATION_CONSENT":
        "I understand and consent to the processing of identity information contained "
        "in documents I submit for certificate, qualification and skill verification.",
}

# Shown immediately before a student uploads a document, and acknowledged
# separately from the signup consent.
UPLOAD_NOTICE = {
    "heading": "Certificate Verification Notice",
    "body": (
        "The document you are about to upload may contain personal information, "
        "including your full name and NRIC/MyKad or passport number.\n\n"
        "It is stored privately and can be opened only by you and by authorised "
        "MomentumQuest administrators reviewing it for verification. MomentumQuest "
        "does not extract or store the identification number shown on your document, "
        "and it is never used for job matching, recommendations or skill-gap analysis."
    ),
    "acknowledgement":
        "I understand and consent to the processing of personal information contained "
        "in this document for verification purposes.",
}

# The equivalent for an examination result. Separate from UPLOAD_NOTICE because
# a transcript is parsed automatically rather than reviewed by an administrator,
# so what happens to it differs and the student should be told the truth about
# their own document.
TRANSCRIPT_NOTICE = {
    "heading": "Examination Result Notice",
    "body": (
        "Your transcript may contain personal information, including your full name "
        "and NRIC/MyKad or passport number.\n\n"
        "It is stored privately and can be opened only by you and by authorised "
        "MomentumQuest administrators. MomentumQuest reads only your subject codes "
        "and grades from it, and never extracts or stores the identification number "
        "shown on the document."
    ),
    "acknowledgement":
        "I understand and consent to the processing of personal information contained "
        "in this document for verification purposes.",
}


def _p(text):
    return {"type": "paragraph", "text": text}


def _list(*items):
    return {"type": "list", "items": list(items)}


NOTICES = {
    "1.0": {
        "version": "1.0",
        "effective_date": date(2026, 8, 24),
        "system": "MomentumQuest",
        "sections": [
            {
                "heading": "1. Purpose of This Notice",
                "blocks": [
                    _p("MomentumQuest is a career and learning support platform designed to "
                       "assist students in managing their skills, identifying skill gaps, "
                       "obtaining learning recommendations, exploring job opportunities, "
                       "receiving job recommendations, submitting job applications, and "
                       "tracking application progress."),
                    _p("MomentumQuest also allows students to upload certificates, examination "
                       "results, and other supporting documents for certificate, qualification, "
                       "and skill verification."),
                    _p("This Privacy Notice explains:"),
                    _list("what personal information MomentumQuest collects;",
                          "why the information is collected;",
                          "how the information is used;",
                          "who may access the information; and",
                          "how uploaded documents containing personal information are handled."),
                    _p("Please read this notice before creating your MomentumQuest account."),
                ],
            },
            {
                "heading": "2. Personal Information We May Collect",
                "blocks": [
                    _p("Depending on the MomentumQuest features you use, the system may collect "
                       "the following information."),
                    _p("A. Account and Student Information"),
                    _list("full name;",
                          "email address;",
                          "student or matric number;",
                          "programme or course of study;",
                          "university or educational institution;",
                          "account login and authentication information; and",
                          "other information that you voluntarily provide in your student profile."),
                    _p("B. Academic and Skills Information"),
                    _list("academic qualifications;",
                          "examination results;",
                          "certificates;",
                          "professional or academic achievements;",
                          "skills;",
                          "completed courses;",
                          "training programmes; and",
                          "other supporting academic or professional information submitted by you."),
                    _p("C. Career and Learning Information"),
                    _list("career interests;",
                          "interested job titles;",
                          "skills and identified skill gaps;",
                          "job recommendations;",
                          "learning recommendations;",
                          "selected learning resources;",
                          "job applications; and",
                          "application progress or status."),
                    # The audit log records the acting user and their IP for
                    # sensitive document operations. Collecting it without
                    # saying so would make this notice inaccurate.
                    _p("D. Security and Access Records"),
                    _p("To protect uploaded documents, MomentumQuest keeps a record of "
                       "sensitive actions taken on them -- such as when a document is "
                       "uploaded, opened by an administrator, verified, rejected or "
                       "deleted. Each record identifies the account that performed the "
                       "action, the student the document belongs to, the date and time, "
                       "and the network (IP) address the action came from."),
                    _p("These records exist so that access to private documents can be "
                       "accounted for. They never contain the contents of a document, and "
                       "never contain an NRIC/MyKad or passport number."),
                ],
            },
            {
                "heading": "3. Uploaded Certificates and Examination Results",
                "blocks": [
                    _p("MomentumQuest allows students to voluntarily upload certificates, "
                       "examination results, academic documents, or other supporting documents "
                       "for certificate, qualification, and skill verification."),
                    _p("Depending on the document, it may contain personal information including:"),
                    _list("your full name;",
                          "NRIC/MyKad number;",
                          "passport number;",
                          "student or candidate number;",
                          "educational institution;",
                          "examination results;",
                          "grades;",
                          "qualifications;",
                          "certificates; and",
                          "other information appearing on the original document."),
                    _p("By uploading such a document, you acknowledge that the information "
                       "contained in the document may be viewed by authorised MomentumQuest "
                       "administrators for verification purposes."),
                ],
            },
            {
                "heading": "4. Use of NRIC/MyKad or Passport Information",
                "blocks": [
                    _p("Some certificates or examination documents may display your NRIC/MyKad "
                       "number, passport number, or other identification information."),
                    _p("MomentumQuest does not separately extract or store your NRIC/MyKad or "
                       "passport number as a field in your student profile or database for "
                       "normal system use."),
                    _p("Where identification information appears in an original document uploaded "
                       "by you, it may remain visible within that document."),
                    _p("Authorised MomentumQuest administrators may view the identification "
                       "information shown on the uploaded document as part of the certificate, "
                       "qualification, or skill verification process."),
                    _p("Identification information contained in uploaded documents will not be "
                       "used for:"),
                    _list("job matching;",
                          "job recommendations;",
                          "learning recommendations;",
                          "skill-gap analysis;",
                          "job-demand analysis; or",
                          "other unrelated MomentumQuest functions."),
                    _p("MomentumQuest will not intentionally copy the identification number from "
                       "the uploaded document into other system records unless a new purpose is "
                       "introduced and you are appropriately informed."),
                ],
            },
            {
                "heading": "5. Certificate and Skill Verification",
                "blocks": [
                    _p("When you submit a certificate, examination result, or other supporting "
                       "document, authorised MomentumQuest administrators may review the document "
                       "to determine whether it reasonably supports the certificate, "
                       "qualification, result, achievement, or skill submitted by you."),
                    _p("The administrator may review information such as:"),
                    _list("the student's registered name;",
                          "the name appearing on the document;",
                          "the issuing institution or organisation;",
                          "the qualification or certificate title;",
                          "examination results or grades;",
                          "relevant skills or achievements; and",
                          "whether the uploaded document is readable and appropriate for "
                          "verification."),
                    # MomentumQuest holds no trusted identity record, so there is nothing to
                    # compare an identification number against. Saying the administrator
                    # "verifies your IC" would overstate what the review establishes.
                    _p("MomentumQuest does not hold a separate record of your NRIC/MyKad or "
                       "passport number, so the review does not compare the identification "
                       "number on your document against a stored value. Identification "
                       "information visible on the document is seen only as part of reading the "
                       "original document."),
                    _p("The administrator may mark a submission as Pending, Verified / Approved, "
                       "or Rejected."),
                    _p("The verification result may subsequently be displayed in MomentumQuest to "
                       "indicate that a submitted certificate, qualification, or skill has been "
                       "reviewed by an authorised administrator."),
                    _p("MomentumQuest's verification process confirms the submitted document for "
                       "the purposes of the platform. It should not be interpreted as independent "
                       "legal identity verification by a government authority."),
                ],
            },
            {
                "heading": "6. How MomentumQuest Uses Your Information",
                "blocks": [
                    _p("MomentumQuest may process your personal information for purposes "
                       "including:"),
                    _list("creating and managing your account;",
                          "maintaining your student profile;",
                          "providing system authentication;",
                          "validating submitted certificates, qualifications, and skills;",
                          "recording verification results;",
                          "identifying skill gaps;",
                          "providing personalised learning recommendations;",
                          "providing personalised job recommendations;",
                          "allowing you to search for jobs;",
                          "enabling job applications;",
                          "tracking job-application progress;",
                          "displaying relevant skills and qualifications;",
                          "maintaining system security;",
                          "providing administrative and technical support; and",
                          "supporting other functions directly related to MomentumQuest."),
                    _p("Your information will not intentionally be used for unrelated purposes "
                       "without further notice where appropriate."),
                ],
            },
            {
                "heading": "7. Who May Access Your Information",
                "blocks": [
                    _p("Access to information in MomentumQuest is restricted according to user "
                       "roles."),
                    _p("Students may access information associated with their own account and "
                       "their own submitted documents. Students cannot access another student's "
                       "private documents or personal information."),
                    _p("Authorised administrators may access uploaded certificates, examination "
                       "results, and the information contained in those documents when necessary "
                       "for certificate verification, qualification verification, skill "
                       "validation, reviewing submitted evidence, and authorised system "
                       "administration."),
                    _p("Companies using MomentumQuest may access information relevant to job "
                       "applications or other functions made available to them through the "
                       "platform. Companies are not provided access to a student's NRIC/MyKad "
                       "number, passport number, or original private verification document. "
                       "Where appropriate, companies receive only the relevant verification "
                       "result, for example \"Skill: Verified\", instead of the student's "
                       "identification number."),
                    _p("Other students are not permitted to view another student's identification "
                       "information, private certificates, private examination results, or other "
                       "restricted supporting documents."),
                ],
            },
            {
                "heading": "8. Storage and Security of Uploaded Documents",
                "blocks": [
                    _p("Certificates, examination results, and other supporting documents "
                       "containing personal information are treated as private documents, and "
                       "MomentumQuest takes reasonable measures to restrict access to them."),
                    _p("Uploaded documents are accessible only to the student who uploaded the "
                       "document and to authorised MomentumQuest administrators where required "
                       "for verification. They are stored outside the system's public files "
                       "area, under unpredictable identifiers, and are never exposed through "
                       "publicly accessible links."),
                    _p("Identification information contained in uploaded documents is not "
                       "intentionally:"),
                    _list("copied into unrelated databases;",
                          "included in filenames;",
                          "displayed in public profiles;",
                          "included in system analytics;",
                          "included in ordinary application logs;",
                          "sent to employers through normal job-matching functions; or",
                          "disclosed to other students."),
                ],
            },
            {
                "heading": "9. Data Retention",
                "blocks": [
                    _p("MomentumQuest retains personal information and uploaded documents only "
                       "for as long as reasonably necessary to support the functions described "
                       "in this notice."),
                    # The project policy is "active account only": no grace period. This is
                    # enforced by post_delete receivers in resources/signals.py, which unlink
                    # the stored file -- the promise is code, not just prose.
                    _p("Document retention period: uploaded certificates, examination results "
                       "and transcripts are retained while your MomentumQuest account remains "
                       "active. When your account is deleted, the private documents you uploaded "
                       "are removed from storage at the same time. There is no additional "
                       "retention period."),
                    _p("You may also delete a submitted document yourself while it is still "
                       "awaiting verification."),
                ],
            },
            {
                "heading": "10. Job and Learning Recommendations",
                "blocks": [
                    _p("MomentumQuest may use information such as your skills, qualifications, "
                       "career interests, interested job titles, learning history and identified "
                       "skill gaps to provide personalised job or learning recommendations."),
                    _p("Your NRIC/MyKad number or passport number is not used as an input for "
                       "these recommendation functions."),
                    _p("Recommendations generated by MomentumQuest are intended to assist "
                       "students in exploring career and learning opportunities and should not "
                       "be treated as guaranteed employment or academic outcomes."),
                ],
            },
            {
                "heading": "11. Job Applications and Companies",
                "blocks": [
                    _p("Creating a MomentumQuest account does not automatically give companies "
                       "access to all personal information or documents in your account."),
                    _p("When you choose to submit a job application, relevant information "
                       "required for the application may be made available to the company "
                       "concerned."),
                    _p("Private identification information contained in certificates or "
                       "examination results is not provided to companies as part of the standard "
                       "MomentumQuest job application process."),
                ],
            },
            {
                "heading": "12. Your Choices and Rights",
                "blocks": [
                    _p("You may contact the MomentumQuest administrator to:"),
                    _list("request access to your personal information;",
                          "request correction of inaccurate information;",
                          "report incorrect certificate or skill verification;",
                          "ask how your information is being processed;",
                          "request deletion of information where applicable;",
                          # Withdrawal is handled by the administrator rather
                          # than self-service, so it belongs in this list.
                          "withdraw consent for document processing; or",
                          "ask questions about this Privacy Notice."),
                    _p("Withdrawal of consent for document processing may prevent MomentumQuest "
                       "from providing certificate, qualification, or skill-verification "
                       "functions that require access to uploaded documents."),
                ],
            },
            {
                "heading": "13. Changes to This Privacy Notice",
                "blocks": [
                    _p("MomentumQuest may update this Privacy Notice when changes are made to the "
                       "system or to the way personal information is collected, processed, "
                       "stored, or disclosed."),
                    _p("Each version of the Privacy Notice contains a version number and "
                       "effective date, and your acknowledgement is recorded against the version "
                       "you accepted."),
                    _p("Where a significant change affects how personal information is processed, "
                       "users will be informed and additional acknowledgement or consent will be "
                       "obtained where appropriate."),
                ],
            },
        ],
    },
    "1.1": {
        "version": "1.1",
        "effective_date": date(2026, 8, 31),
        "system": "MomentumQuest",
        # Version 1.1 carries its own wording. The consent statements and
        # document notices moved into the version because 1.1 introduces
        # purposes 1.0 never described -- CV processing and disclosure to
        # employers -- and the text a user agreed to has to travel with the
        # version they agreed to.
        "summary": (
            "MomentumQuest processes your personal and academic information to provide "
            "skill validation, learning recommendations and job-matching functions.\n\n"
            "Documents you submit for verification, such as certificates and examination "
            "results, are stored privately and may be opened by authorised administrators "
            "to confirm that they belong to you.\n\n"
            "When you apply for a job, a CV you upload is read once to prepare your "
            "application and then deleted. The information you confirm is stored with the "
            "application and shared with that employer."
        ),
        "consent_statements": {
            "PRIVACY_NOTICE_ACKNOWLEDGEMENT":
                "I have read and understood the MomentumQuest Privacy Notice.",
            "DOCUMENT_VERIFICATION_CONSENT":
                "I agree to MomentumQuest processing and privately storing documents I "
                "submit for qualification and skill verification.",
            "CV_PROCESSING_CONSENT":
                "I agree to MomentumQuest reading this CV to prepare my application. The "
                "CV file will be deleted after processing.",
            "APPLICATION_DISCLOSURE_ACKNOWLEDGEMENT":
                "By submitting, you agree that the information in this application will "
                "be shared with the employer for recruitment purposes.",
        },
        "upload_notice": {
            "heading": "Document verification",
            "body": (
                "This document is stored privately and can be opened only by you and by "
                "authorised MomentumQuest administrators reviewing it for verification.\n\n"
                "MomentumQuest does not extract or store any identification number shown on "
                "it, and never uses one for job matching, recommendations or skill-gap "
                "analysis."
            ),
            "acknowledgement":
                "I agree to MomentumQuest processing and privately storing this document "
                "for qualification and skill verification.",
        },
        "transcript_notice": {
            "heading": "Examination result verification",
            "body": (
                "Your transcript is stored privately and can be opened only by you and by "
                "authorised MomentumQuest administrators.\n\n"
                "MomentumQuest reads your subject codes and grades from it to recognise "
                "skills, and never extracts or stores any identification number shown on "
                "the document. Skills are added only after an administrator has reviewed "
                "and approved the transcript."
            ),
            "acknowledgement":
                "I agree to MomentumQuest processing and privately storing this document "
                "for qualification and skill verification.",
        },
        "cv_notice": {
            "heading": "How we use your CV",
            "body": (
                "Your CV is read once so that MomentumQuest can suggest the skills, "
                "education and experience to put in your application.\n\n"
                "The file itself is not kept. It is deleted as soon as it has been read, "
                "and no copy is stored. Only the information you review and confirm is "
                "saved, and it is saved with the application you submit.\n\n"
                "You can edit or remove anything that was read from your CV before you "
                "submit. What you confirm is treated as information you have declared, "
                "not as verified evidence."
            ),
            "acknowledgement":
                "I agree to MomentumQuest reading this CV to prepare my application. The "
                "CV file will be deleted after processing.",
        },
        "application_disclosure": (
            "By submitting, you agree that the information in this application will be "
            "shared with the employer for recruitment purposes."
        ),
        "sections": [
            {
                "heading": "1. Purpose of This Notice",
                "blocks": [
                    _p("MomentumQuest is a career and learning support platform that helps "
                       "students manage their skills, identify skill gaps, obtain learning "
                       "recommendations, explore job opportunities, submit job applications "
                       "and track application progress."),
                    _p("This version of the notice (1.1) adds descriptions of two things "
                       "version 1.0 did not cover: how a CV is processed when you apply for "
                       "a job, and what is shared with an employer when you submit an "
                       "application."),
                    _p("Please read this notice before creating your MomentumQuest account."),
                ],
            },
            {
                "heading": "2. Personal Information We May Collect",
                "blocks": [
                    _p("A. Account and student information"),
                    _list("full name;",
                          "email address;",
                          "student or matric number;",
                          "department or programme of study;",
                          "account login and authentication information; and",
                          "other information you voluntarily provide in your student profile."),
                    _p("B. Academic and skills information"),
                    _list("academic qualifications;",
                          "examination results;",
                          "certificates;",
                          "skills and skill levels;",
                          "completed courses and training programmes; and",
                          "other supporting academic or professional information you submit."),
                    _p("C. Career and learning information"),
                    _list("career interests and interested job titles;",
                          "identified skill gaps;",
                          "job and learning recommendations;",
                          "selected learning resources;",
                          "job applications; and",
                          "application progress or status."),
                    _p("D. Technical information"),
                    _list("the IP address from which a consent or a sensitive document "
                          "action was performed, recorded in the privacy audit log so that "
                          "access to identity-bearing documents can be accounted for."),
                ],
            },
            {
                "heading": "3. Document Verification Is a Required Student Function",
                "blocks": [
                    _p("Verifying qualifications and skills is a core part of what "
                       "MomentumQuest does. Skill validation, skill-gap analysis and the "
                       "recommendations built on them depend on evidence you submit."),
                    _p("Consenting to document processing is therefore required to use the "
                       "student features of MomentumQuest. You are not required to upload "
                       "any particular document, and you may use the platform without "
                       "uploading one; but if you choose to submit a certificate or an "
                       "examination result, it will be processed as described here."),
                    _p("You may withdraw this consent later. Doing so stops MomentumQuest "
                       "verifying new documents; it does not delete your account."),
                ],
            },
            {
                "heading": "4. Certificates and Examination Results",
                "blocks": [
                    _p("Certificates, examination results, transcripts and other supporting "
                       "documents you upload are stored privately. They are never placed in "
                       "a publicly reachable location and are never served through a public "
                       "media URL."),
                    _p("Such a document may contain personal information including:"),
                    _list("your full name;",
                          "NRIC/MyKad number;",
                          "passport number;",
                          "student or candidate number;",
                          "educational institution;",
                          "examination results and grades; and",
                          "other information appearing on the original document."),
                    _p("Authorised MomentumQuest administrators may open these documents "
                       "when reviewing them for certificate, qualification or skill "
                       "verification. Every such access is recorded in the privacy audit "
                       "log."),
                    _p("From a transcript, MomentumQuest extracts your subject codes and "
                       "grades, and the skills recognised from them. These are stored so "
                       "that your skills and skill gaps can be calculated."),
                    _p("MomentumQuest does not extract or store your NRIC/MyKad or passport "
                       "number as a field in your profile or database. Where such a number "
                       "appears on a document you upload, it remains inside that document "
                       "and is not copied anywhere else, used for matching or "
                       "recommendations, written into a filename, placed in a URL, recorded "
                       "in logs, or disclosed to companies or other students."),
                    _p("A transcript that has been read is not thereby verified. Skills are "
                       "added to your profile only after an authorised administrator has "
                       "reviewed the document and approved it, or where the issuer has been "
                       "confirmed by a genuine verification mechanism."),
                ],
            },
            {
                "heading": "5. Certificate and Skill Verification",
                "blocks": [
                    _p("An administrator reviewing a submitted document checks that the name "
                       "on it matches your registered name, that it is readable, that the "
                       "issuing institution is identifiable, and that it supports the "
                       "qualification or skill you claimed."),
                    _p("A submission is marked Pending, Verified or Rejected. Where a "
                       "submission is rejected you are given a plain-language reason."),
                    _p("MomentumQuest's verification confirms the submitted document for the "
                       "purposes of this platform. It is not independent legal identity "
                       "verification by a government authority. MomentumQuest holds no "
                       "trusted identity record to compare an identification number "
                       "against, and therefore does not attempt to verify one."),
                ],
            },
            {
                "heading": "6. CV Processing for Job Applications",
                "blocks": [
                    _p("When you apply for a job you may upload a CV so that MomentumQuest "
                       "can prepare your application for you."),
                    _p("The CV is read once, in order to suggest the skills, education and "
                       "experience to include. Reading it requires your consent, which is "
                       "requested at the moment you upload it."),
                    _p("The CV file itself is not stored. It is written to a temporary "
                       "location only for as long as it takes to read it, and is deleted "
                       "immediately afterwards, whether or not reading succeeded. No copy "
                       "is retained, and the file is never placed in public or permanent "
                       "storage."),
                    _p("Only the information you then review and confirm is saved, and it is "
                       "saved as part of the application you submit. You may edit or remove "
                       "anything before submitting."),
                    _p("Information taken from a CV is treated as information you have "
                       "declared, not as verified evidence. It is not the same as a "
                       "certificate an administrator has checked."),
                ],
            },
            {
                "heading": "7. Job Applications and Employers",
                "blocks": [
                    _p("Creating a MomentumQuest account does not give any company access to "
                       "your personal information or your documents."),
                    _p("When you submit an application, the information in that application "
                       "is shared with the employer concerned for recruitment purposes. That "
                       "is the information you confirmed at the time of submitting: the "
                       "skills, education and experience you declared, together with your "
                       "answers on the application form and any contact details you "
                       "provided."),
                    _p("The employer sees the application as you submitted it. Changes you "
                       "make to your profile afterwards do not alter an application already "
                       "sent."),
                    _p("For each skill in an application the employer is shown whether it was "
                       "verified by an administrator at the time of submission. The employer "
                       "receives the verification result only. They do not receive your "
                       "certificates, your transcripts, your examination results, or any "
                       "identification number."),
                ],
            },
            {
                "heading": "8. Who May Access Your Information",
                "blocks": [
                    _p("Students may access their own account and their own submitted "
                       "documents, and may not access another student's."),
                    _p("Authorised administrators may access uploaded documents where "
                       "necessary for verification and authorised system administration. "
                       "Such access is recorded."),
                    _p("Companies may access the applications submitted to their own job "
                       "listings. They cannot access your NRIC/MyKad or passport number, "
                       "your uploaded documents, or any certificate-verification function."),
                ],
            },
            {
                "heading": "9. Storage and Security",
                "blocks": [
                    _p("Uploaded documents are stored outside the public media directory, "
                       "under unpredictable filenames, and are reachable only through an "
                       "authenticated endpoint that checks on every request that the "
                       "requester is the owning student or an authorised administrator."),
                    _p("Uploaded files are validated by their actual content, not their "
                       "filename, and only PDF, JPEG and PNG documents are accepted."),
                    _p("Identification information contained in an uploaded document is not "
                       "copied into other databases, included in filenames, displayed in "
                       "public profiles, included in analytics, written to ordinary "
                       "application logs, sent to employers, or disclosed to other "
                       "students."),
                ],
            },
            {
                "heading": "10. Data Retention",
                "blocks": [
                    _p("CV files are deleted immediately after they are read. They are never "
                       "retained."),
                    _p("Certificates and transcripts are retained while your account is "
                       "active and are deleted when the record or the account is deleted. "
                       "There is no grace period: deleting a document removes the stored "
                       "file as well as the database row."),
                    _p("Consent records are retained as historical evidence of what was "
                       "agreed to and when. Withdrawing a consent records the withdrawal "
                       "against the existing record; it does not erase it, because a record "
                       "that could be erased would not be evidence."),
                    _p("Applications and the information submitted with them are retained "
                       "for the employer's recruitment purposes."),
                ],
            },
            {
                "heading": "11. Withdrawing Consent",
                "blocks": [
                    _p("You may withdraw a consent by contacting the MomentumQuest "
                       "administrator."),
                    _p("Withdrawing document-verification consent means MomentumQuest will "
                       "no longer verify new certificates or academic documents for you, and "
                       "document-verification functions become unavailable. Skills supported "
                       "only by evidence you have withdrawn or deleted are recalculated."),
                    _p("Withdrawing consent does not delete your account, and does not by "
                       "itself withdraw applications you have already submitted to "
                       "employers."),
                    _p("A withdrawn consent cannot authorise any further processing. Past "
                       "processing that took place while the consent was live remains "
                       "lawful and its record is kept."),
                ],
            },
            {
                "heading": "12. Your Choices and Rights",
                "blocks": [
                    _p("You may contact the MomentumQuest administrator to:"),
                    _list("request access to your personal information;",
                          "request correction of inaccurate information;",
                          "report incorrect certificate or skill verification;",
                          "ask how your information is being processed;",
                          "request deletion of information where applicable;",
                          "withdraw a consent; or",
                          "ask questions about this Privacy Notice."),
                ],
            },
            {
                "heading": "13. Changes to This Privacy Notice",
                "blocks": [
                    _p("MomentumQuest may update this Privacy Notice when the system or the "
                       "handling of personal information changes."),
                    _p("Each version carries a version number and effective date, and your "
                       "acknowledgement is recorded against the version you accepted. "
                       "Earlier versions are preserved and earlier acknowledgements are "
                       "never rewritten to refer to a newer version."),
                    _p("Where a change materially affects how your personal information is "
                       "processed, you will be asked to acknowledge the new version the next "
                       "time you use an affected function."),
                ],
            },
        ],
    },
}


def _transcripts_are_not_kept(notice):
    """Version 1.2 from 1.1, with the transcript wording it changed.

    Derived rather than copied. A 300-line duplicate of 1.1 would drift from
    it at the first correction, and the two would then disagree about text
    students have already agreed to. Only the paragraphs that actually changed
    are named here, so the diff *is* the change.

    1.1 itself is untouched -- deep-copied before editing -- because consent
    rows point at a version string, and rewriting that text would silently
    change what past users are recorded as having agreed to.
    """
    import copy

    updated = copy.deepcopy(notice)
    updated["version"] = "1.2"
    updated["effective_date"] = date(2026, 9, 1)

    updated["transcript_notice"] = {
        "heading": "Examination result verification",
        "body": (
            "Your transcript is read once, and the file itself is not kept. It is "
            "deleted as soon as your subject codes and grades have been read from "
            "it, and no copy is stored.\n\n"
            "What is kept is the information read from it: your subject codes, "
            "your grades, and the skills recognised from them. MomentumQuest never "
            "extracts or stores any identification number shown on the document.\n\n"
            "Skills are added to your profile immediately. No administrator reads "
            "your transcript, and no administrator can: by the time the upload "
            "finishes, the document no longer exists."
        ),
        "acknowledgement":
            "I agree to MomentumQuest reading this document to recognise my "
            "skills. I understand the file is deleted immediately afterwards.",
    }

    for section in updated["sections"]:
        blocks = section.get("blocks", [])
        for index, block in enumerate(blocks):
            text = block.get("text", "")

            if text.startswith("A transcript that has been read is not thereby verified."):
                blocks[index] = _p(
                    "A transcript is checked automatically before its skills are "
                    "used: MomentumQuest confirms that the document reads as an "
                    "academic transcript and that any matric number on it matches "
                    "your account. It is not checked by a person, and it is not "
                    "checked with the issuing university. Skills recognised this "
                    "way rest on those automatic checks alone.")

            elif text.startswith("Certificates and transcripts are retained while your account is"):
                blocks[index] = _p(
                    "Transcripts are deleted immediately after they are read, in "
                    "the same way as CV files. Only the subjects, grades and "
                    "skills read from them are kept.")
                blocks.insert(index + 1, _p(
                    "Certificates are retained while your account is active and "
                    "are deleted when the record or the account is deleted. There "
                    "is no grace period: deleting a certificate removes the stored "
                    "file as well as the database row."))

    return updated


NOTICES["1.2"] = _transcripts_are_not_kept(NOTICES["1.1"])


def get_notice(version=None):
    """Return one notice version as a JSON-serialisable dict.

    ``contact_email`` is injected at read time rather than baked into NOTICES:
    it is deployment configuration, not part of the agreed text, so changing it
    must not require publishing a new notice version.
    """
    version = version or CURRENT_VERSION
    notice = NOTICES.get(version)
    if notice is None:
        raise KeyError(f"Unknown privacy notice version: {version}")

    return {
        **notice,
        "effective_date": notice["effective_date"].isoformat(),
        "contact_email": getattr(settings, "PRIVACY_CONTACT_EMAIL", ""),
        # A version may carry its own wording. Where it does not, the original
        # 1.0 text applies -- so publishing 1.1 could not retroactively change
        # what a 1.0 acknowledgement refers to.
        "summary": notice.get("summary", SIGNUP_SUMMARY),
        "consent_statements": notice.get("consent_statements", CONSENT_STATEMENTS),
        "upload_notice": notice.get("upload_notice", UPLOAD_NOTICE),
        "transcript_notice": notice.get("transcript_notice", TRANSCRIPT_NOTICE),
        # 1.0 described neither CV processing nor employer disclosure, so these
        # are empty for it rather than being invented.
        "cv_notice": notice.get("cv_notice"),
        "application_disclosure": notice.get("application_disclosure", ""),
    }
