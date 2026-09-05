"""
Seeds SubjectSkillMapping with Universiti Malaya computer science modules.

Run once after migrating:
    python manage.py seed_subject_skill_mappings

Safe to re-run — existing rows are left alone. General-education modules
(GIG/GLT/GKS/GQA/GQX/GBX/GKP) are deliberately absent: they map to no
technical skill, and a transcript showing them as "unrecognised" is correct
behaviour rather than a gap in this table.
"""

from django.core.management.base import BaseCommand

from scrape_jobs.models import Skill
from resources.models import SubjectSkillMapping


# (module code, module name, [skill names])
MAPPINGS = [
    ("WIA1001", "INFORMATION SYSTEMS",                     ["Information Systems"]),
    ("WIA1002", "DATA STRUCTURE",                          ["Data Structures", "Java"]),
    ("WIA1003", "COMPUTER SYSTEM ARCHITECTURE",            ["Computer Architecture"]),
    ("WIA1005", "NETWORK TECHNOLOGY FOUNDATION",           ["Networking"]),
    ("WIA1006", "MACHINE LEARNING",                        ["Machine Learning"]),
    ("WIA2001", "DATABASE",                                ["SQL", "Database Design"]),
    ("WIA2003", "PROBABILITY AND STATISTICS",              ["Statistics"]),
    ("WIA2004", "OPERATING SYSTEMS",                       ["Operating Systems"]),
    ("WIA2005", "ALGORITHM DESIGN AND ANALYSIS",           ["Algorithms"]),
    ("WIA2006", "SYSTEMS ANALYSIS AND DESIGN",             ["Systems Analysis"]),
    ("WIA2007", "MOBILE APPLICATION DEVELOPMENT",          ["Mobile Development"]),
    ("WIA3002", "ACADEMIC PROJECT I",                      ["Research"]),
    ("WIE2001", "TRENDS IN INFORMATION SYSTEMS",           ["Information Systems"]),
    ("WIE2003", "INTRODUCTION TO DATA SCIENCE",            ["Data Analysis"]),
    ("WIE2005", "INFORMATION RETRIEVAL AND WEB SEARCH",    ["Information Retrieval"]),
    ("WIE3002", "ELECTRONIC COMMERCE",                     ["E-Commerce"]),
    ("WIE3003", "INFORMATION SYSTEM CONTROL AND SECURITY", ["Cybersecurity"]),
    ("WIE3005", "KNOWLEDGE MANAGEMENT AND ENGINEERING",    ["Knowledge Management"]),
    ("WIF2003", "WEB PROGRAMMING",                         ["HTML", "CSS", "JavaScript"]),
    ("WIX1001", "COMPUTING MATHEMATICS I",                 ["Mathematics"]),
    ("WIX1002", "FUNDAMENTALS OF PROGRAMMING",             ["Programming", "Java"]),
    ("WIX1003", "COMPUTER SYSTEMS AND ORGANIZATION",       ["Computer Architecture"]),
    ("WIX2001", "THINKING AND COMMUNICATION SKILLS",       ["Communication"]),
    ("WIX2002", "PROJECT MANAGEMENT",                      ["Project Management"]),
]


class Command(BaseCommand):
    help = "Seed SubjectSkillMapping with UM computer science module codes."

    def handle(self, *args, **options):
        created_mappings = 0
        created_skills = 0

        for code, name, skill_names in MAPPINGS:
            for skill_name in skill_names:
                skill = Skill.objects.filter(skill_name__iexact=skill_name).first()
                if not skill:
                    skill = Skill.objects.create(skill_name=skill_name)
                    created_skills += 1

                _, created = SubjectSkillMapping.objects.get_or_create(
                    subject_code=code,
                    skill=skill,
                    defaults={"subject_name": name},
                )
                if created:
                    created_mappings += 1

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {created_mappings} mapping(s); created {created_skills} new skill(s). "
            f"Total mappings: {SubjectSkillMapping.objects.count()}."
        ))
