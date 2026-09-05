# Derived IMDA ICT career hierarchy

The files in this directory are a MomentumQuest-reviewed transcription of the
eight visual master career-map pages in the IMDA and SkillsFuture Singapore
*Skills Framework for Infocomm Technology: Consolidated Career Maps*.

- `imda_ict_career_hierarchy.csv` is the flat, import-friendly table.
- `imda_ict_career_hierarchy.json` contains the same relationships plus dataset
  metadata and provenance.

Current derived scope:

- 8 career tracks;
- 33 sub-tracks;
- 173 track/sub-track/role relationships;
- 124 unique role labels.

This is not an official IMDA CSV or an official taxonomy release. IMDA publishes
the source hierarchy visually in a PDF. Every relationship retains its source
master-page number and source URL so it can be reviewed. Shared roles are
repeated under the sub-tracks they visually span and marked with
`is_cross_subtrack=true`.

The dataset deliberately excludes role descriptions, tasks, competencies,
proficiency levels, feeder roles, lateral moves and direct progression edges.
Those need a separate extraction and review stage before they can be treated as
authoritative project data.

Official source:

https://www.imda.gov.sg/-/media/imda/images/programmes/skills-framework-for-ict/consolidated-career-maps.pdf

Regenerate and validate the files from the downloaded source PDF:

```powershell
cd backend
python manage.py prepare_imda_career_hierarchy `
  --pdf scrape_jobs\data\official\IMDA_SFw_ICT_Consolidated_Career_Maps.pdf `
  --output-dir ..\docs\data
```

Before redistributing the derived dataset outside an academic/project context,
review the current IMDA source-use and attribution terms.
