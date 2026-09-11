import re

from .models import Skill, SkillAlias

#: Skill names that are also ordinary English words, abbreviations of
#: something else, or single letters. A word-boundary match alone says nothing
#: about them: "go" appears in "go live" and "go-to person", "R" in "R&D",
#: "Swift" in "swift resolution of customer issues" and in SWIFT the banking
#: network. Left unguarded these produced most of their own matches -- "Go"
#: was tagged on 40 adverts and "R" on 23, and a SAP consultant's skill gap
#: told the student to learn Go and Swift.
#:
#: A name listed here is only accepted when the surrounding text also reads as
#: technical, and never when one of its known idioms is what matched.
AMBIGUOUS_SKILLS = {"go", "r", "c", "swift", "rust", "dart", "scala", "spark",
                    "math", "excel", "jest", "solid", "bert", "keras", "vite",
                    # Added after the Phase 10 shadow run: "SDN" matched the
                    # company suffix "Sdn Bhd" in 53 of 53 adverts, and "GIS"
                    # is Group Information Security in Malaysian banking.
                    "sdn", "gis"}

#: How much text either side of a match is inspected for context.
CONTEXT_WINDOW = 70

#: Phrases that are the *reason* an ambiguous name matched, and are not the
#: skill. Checked against the matched term plus its immediate surroundings.
NEGATIVE_CONTEXT = (
    r"\bgo[-\s]?live\b", r"\bgo[-\s]to\b", r"\bgo\s+the\s+extra\b",
    r"\bgo\s+through\b", r"\bgo\s+beyond\b", r"\bgo\s+above\b",
    r"\bon\s+the\s+go\b", r"\bready\s+to\s+go\b", r"\bgo\s+into\b",
    r"\br\s*&\s*d\b", r"\br\.\s*i\.\s*v\.\s*e\.\s*r\b",
    r"\bswift\s+(?:resolution|response|action|turnaround|manner|delivery)\b",
    r"\bswift\s+(?:message|payment|network|code|mt\d)", r"\biso\s*20022\b",
    r"\bexcel(?:s|led|lent|ling)?\s+(?:in|at)\b",
    r"\bsolid\s+(?:understanding|knowledge|experience|grasp|background|foundation)\b",
    r"\bspark\s+(?:interest|joy|innovation|creativity)\b",
    r"\bc\s*-?\s*level\b", r"\bcertificate\s+in\s+c\b",
    # "Sdn Bhd" -- Sendirian Berhad -- ends the name of virtually every
    # Malaysian company. It is not Software Defined Networking, and without
    # this it produced 53 false SDN detections out of 53.
    r"\bsdn\.?\s*bhd\b",
    # "Solid SQL Server skills", "2 solid years" -- the adjective, not the
    # design principles. SOLID the acronym sits next to "principles".
    r"\bsolid\s+(?!principles?\b|design\b)\w+",
    r"\b\d+\s+solid\b",
    # "solid, practical knowledge" -- the comma escapes the rule above.
    r"\bsolid\s*[,;]",
    # Solid.js is a JavaScript framework, not the SOLID principles.
    r"\bsolid\.js\b",
    # In Malaysian banking adverts GIS is routinely Group Information
    # Security, a policy function, not geographic information systems.
    r"\bgis\s+(?:strategy|guideline|policy|standard|framework)\b",
)
NEGATIVE_PATTERN = re.compile("|".join(NEGATIVE_CONTEXT), re.IGNORECASE)

#: Per-term homonym guards: what a term must be near, and what rules it out.
#:
#: The global POSITIVE_CONTEXT below is deliberately broad -- it only has to
#: separate a requirements paragraph from prose about attitude -- and that is
#: exactly why it cannot police these. A data-centre cabling advert says
#: "engineer", "infrastructure" and "network", so a generic context gate on
#: "backbone" passes it and still files the advert under a JavaScript library.
#: These terms need to be judged against their own domain, not against
#: technology in general.
#:
#: ``reject`` wins over ``require``: the whole point is that the term has a
#: common non-skill meaning, and finding that meaning settles it.
TERM_GUARDS = {
    # "backbone" is structured-cabling vocabulary. Observed in advert 269,
    # "Project Engineer - IT/Fiber Optic (Data Center)": "Coordinate fiber
    # optic, backbone, and horizontal cabling scope across all areas".
    "backbone": {
        "require": r"\b(?:javascript|js|jquery|underscore|node|npm|spa|mvc|"
                   r"front[- ]?end|web\s+app\w*|single[- ]page|marionette|"
                   r"ember|angular|react|framework|library)\b",
        "reject": r"\b(?:fib(?:re|er)|cabl\w*|containment|patch\s+panel|"
                  r"mdf|idf|mmr|data\s+hall|riser|conduit|copper|"
                  r"backbone\s+(?:cabling|link|circuit|network|switch)|"
                  r"network\s+backbone|lan|wan|switch\w*|router\w*)\b",
    },
    # "charts" is ordinary reporting vocabulary. Observed on a Coursera card:
    # "Skills you'll gain: Microsoft Excel, Pivot Tables And Charts".
    "charts": {
        "require": r"\b(?:chart\.js|chartjs|javascript|js|d3|canvas|npm|"
                   r"front[- ]?end|web\s+app\w*|library|plugin)\b",
        "reject": r"\b(?:excel|pivot|spreadsheet|powerpoint|report\w*|"
                  r"dashboard|org\w*\s+chart|gantt|flow\s*chart|"
                  r"pie\s+chart|bar\s+chart|tableau|power\s?bi)\b",
    },
    # "Sage" is accounting software, a herb, a publisher and an adjective.
    # Observed on a Coursera card: "Sage Publications Advanced Project
    # Management". Canonical rather than an alias, so requires_context cannot
    # reach it -- membership here is what gates it.
    # "Apache" alone is the Apache Software Foundation's name, worn by
    # hundreds of unrelated projects. The canonical skill is the HTTP Server
    # (its aliases are httpd, apache 2.2, apache 2.4), but the bare word
    # matched "Apache Spark", "Apache Kafka", "Apache Flink", "Apache Polaris"
    # and "Dubbo (Apache or Alibaba)": 43 of 44 corpus occurrences were some
    # other project, the worst rate found in the exposure sweep.
    #
    # Tomcat is rejected too. It is an Apache project and a web server, but it
    # is a servlet container with its own skill identity -- an advert asking
    # for Tomcat is not asking for httpd.
    "apache": {
        "require": r"\b(?:httpd|apache\s*(?:http|web\s*server|2\.[24])|"
                   r"web\s+server|virtual\s+host|mod_\w+|\.htaccess|"
                   r"reverse\s+proxy|nginx|lamp\s+stack|"
                   # Siblings in a web/application server list. Advert 549
                   # reads "PHP, Apache, Redhat Jboss, Websphere, Weblogic,
                   # IIS" -- unmistakably the HTTP server, and rejected by the
                   # first version of this rule because none of its own
                   # vocabulary appears.
                   r"iis|jboss|websphere|weblogic|xampp|wamp|php)\b",
        "reject": r"\bapache\s+(?:spark|kafka|flink|hadoop|airflow|cassandra|"
                  r"hive|beam|nifi|solr|lucene|maven|tomcat|camel|pulsar|"
                  r"iceberg|polaris|superset|zookeeper|storm|druid|arrow|"
                  r"parquet|dubbo|struts|groovy|ant|poi|jmeter|mesos|kylin|"
                  r"ignite|geode|couchdb|activemq|karaf|ranger|atlas|oozie|"
                  r"sqoop|impala|drill|phoenix|accumulo)\b",
    },
    # "REST" is REST API in 84 of 89 corpus occurrences and ordinary English in
    # the other five: "rest day given in lieu", "Rest assured, we handle every
    # application", "trainable for the rest".
    #
    # The idioms are rejected narrowly and everything else leans on the
    # require list, because a broad reject would also swallow "REST Assured",
    # which is a real Java testing library.
    "rest": {
        "require": r"\b(?:api|apis|ful|endpoint\w*|http|https|json|xml|soap|"
                   r"web\s*service\w*|microservice\w*|crud|swagger|openapi|"
                   r"postman|graphql|payload|request\w*|"
                   # Integration vocabulary. Advert 279 reads "REST,
                   # event-driven, and protocol-based integrations", which
                   # names the API style without ever saying "API".
                   r"integration\w*|architecture|protocol\w*|"
                   r"event[- ]driven|soa)\b",
        "reject": r"\b(?:rest\s+(?:day|period|break)|the\s+rest\b|"
                  r"rest\s+of\s+the|rest\s+and\s+recreation)",
    },
    "sage": {
        "require": r"\b(?:accounting|account\w*\s+software|payroll|ledger|"
                   r"bookkeep\w*|erp|invoic\w*|sage\s*(?:50|100|200|300|x3|"
                   r"intacct|one)|financial\s+software)\b",
        "reject": r"\b(?:publication\w*|publish\w*|journal|press|handbook|"
                  r"sage\s+(?:advice|green|leaf|tea)|herb\w*)\b",
    },
}

#: The AI assistant products, which are evidence for "AI Coding Assistants"
#: only where the advert is talking about building software.
#:
#: One guard shared by all of them, because the question is identical for each:
#: is this advert using the tool to write code, or to draft an email, generate
#: marketing copy, or build against an API? The last is a different competence
#: the catalogue already carries as LLM / GenAI / OpenAI API.
#:
#: Every rule below came from a shadow run over the 30 adverts that mention one
#: of these products, not from guesswork:
#:
#:   * bare "develop" is absent from the trigger -- it fired on "application
#:     development" in a Power Platform advert and "AI developments" in a
#:     corporate-communications one;
#:   * Power BI is absent from the reject -- it looked like a business-stack
#:     signal until two adverts showed it beside genuine assistant-assisted
#:     development, so it is not a reliable anti-signal;
#:   * Copilot Studio and Copilot agents are rejected, because Microsoft uses
#:     the same brand for a low-code bot builder.
AI_ASSISTANT_PRODUCTS = (
    "chatgpt", "github copilot", "copilot", "cursor", "claude", "claude code",
    "codex", "amazon q", "gemini",
)

#: Phrases that contain a trigger word while meaning something else, or the
#: opposite. "No-Code Development" contains "Code" and is a promise that you
#: will not write any; "Application Programming Interface" contains
#: "Programming" and names an integration boundary; "Infrastructure as Code"
#: and "Code Reusability" are about neither an assistant nor application code.
#:
#: Negated at the trigger itself rather than across the window, which matters:
#: a course may mention no-code tooling in passing and still teach
#: assistant-assisted programming, so a window-wide reject would be too blunt.
#: Ordered alternation covers the overlap -- "such as code review" still
#: matches on the code_review alternative after cod(?:e|ing) is refused here.
_NOT_WRITING_CODE = r"(?<!no-)(?<!no\s)(?<!low-)(?<!low\s)(?<!as\s)"

AI_CODING_REQUIRE = (
    r"\b(?:" + _NOT_WRITING_CODE + r"cod(?:e|ing)(?!\s+reusability)|"
    r"debug\w*|programming(?!\s+interface)|software\s+develop\w*|"
    r"software\s+engineer\w*|refactor\w*|unit\s+test\w*|test\s+case\w*|"
    r"code\s+review|pull\s+request|ide|pair[- ]programming|boilerplate|"
    r"backend|back[- ]end|frontend|front[- ]end|full[- ]?stack|"
    r"source\s+code|codebase|troubleshoot\w*)\b"
)

AI_CODING_REJECT = (
    r"\b(?:content\s+(?:generation|creation|creator|writer)|copywrit\w*|"
    r"marketing|social\s+media|design\s+tool|figma|firefly|midjourney|canva|"
    r"business\s+operation\w*|"
    r"power\s+(?:apps|automate|platform)|sharepoint|microsoft\s+fabric|"
    r"purview|copilot\s+(?:agent|studio)|microsoft\s+365|m365|"
    r"corporate\s+communication\w*|data\s+loss\s+prevention|dlp|"
    r"(?:integrat\w+|consum\w+|call\w*)\s+(?:the\s+)?(?:llm|openai|claude|"
    r"gemini)?\s*apis?|llm\s+api|gemini\s+enterprise)\b"
)

TERM_GUARDS.update({
    product: {"require": AI_CODING_REQUIRE, "reject": AI_CODING_REJECT}
    for product in AI_ASSISTANT_PRODUCTS
})

TERM_GUARD_PATTERNS = {
    term: (re.compile(rule["require"], re.IGNORECASE),
           re.compile(rule["reject"], re.IGNORECASE))
    for term, rule in TERM_GUARDS.items()
}

#: Signals that the surrounding text is discussing technology, so an
#: ambiguous name in it plausibly means the skill. Deliberately broad: the
#: negative list above is what does the precise work, and this only has to
#: separate a requirements paragraph from prose about attitude.
POSITIVE_CONTEXT = re.compile(
    r"\b(?:programming|language|framework|library|developer|development|"
    r"engineer|engineering|software|backend|back[- ]end|frontend|front[- ]end|"
    r"full[- ]?stack|script|scripting|code|coding|codebase|api|sdk|stack|"
    r"proficien\w*|hands[- ]on|familiar\w*|knowledge\s+of|experience\s+(?:with|in)|"
    r"python|java|javascript|typescript|kotlin|flutter|ios|android|xcode|swift|"
    r"golang|node|react|angular|vue|django|flask|spring|\.net|sql|linux|docker|"
    r"kubernetes|aws|azure|gcp|git|matlab|sas|tableau|power\s?bi|statistic\w*|"
    r"data\s+(?:analysis|science|engineering)|machine\s+learning)\b",
    re.IGNORECASE,
)


def _accepted_in_context(text, match):
    """Whether an ambiguous match is really the skill, given its surroundings."""
    start = max(0, match.start() - CONTEXT_WINDOW)
    window = text[start:match.end() + CONTEXT_WINDOW]

    # A term with its own guard is judged by that guard alone. The generic
    # positive list would pass a cabling advert on the word "engineer", which
    # is the failure these exist to stop.
    guard = TERM_GUARD_PATTERNS.get(match.group(0).strip().lower())
    if guard is not None:
        require, reject = guard
        if reject.search(window):
            return False
        return bool(require.search(window))

    # An idiom that explains the match rules it out, wherever it sits.
    if NEGATIVE_PATTERN.search(window):
        return False
    return bool(POSITIVE_CONTEXT.search(window))


#: How a term was matched, recorded per job_skill link so a questionable
#: detection can be traced back to the exact string that produced it.
DIRECT_CANONICAL = "DIRECT_CANONICAL"
ALIAS = "ALIAS"
CONTEXTUAL_ALIAS = "CONTEXTUAL_ALIAS"


def _terms_by_skill():
    """Every term that may match, with how it should be treated.

    Inactive skills and aliases are excluded rather than deleted: an imported
    name awaiting review must stay recoverable, but it must not create job
    links in the meantime. Phase 9 showed what happens otherwise -- an
    inactive alias "xml" pointing at the Python library lxml very nearly
    filed Malaysian XML demand under a parser.
    """
    terms = {}
    for skill in Skill.objects.filter(is_active=True):
        terms[skill] = [(skill.skill_name, DIRECT_CANONICAL)]
    for alias in (SkillAlias.objects
                  .filter(is_active=True, skill__is_active=True)
                  .select_related("skill")):
        entry = terms.setdefault(alias.skill,
                                 [(alias.skill.skill_name, DIRECT_CANONICAL)])
        entry.append((alias.alias_name,
                      CONTEXTUAL_ALIAS if alias.requires_context else ALIAS))
    return terms


# Characters that continue a technology token. A term must not be glued to one
# of these, which is what \b means for ordinary words and what it fails to mean
# for terms whose own edge is punctuation.
#
# The two sides differ by the dot, and not arbitrarily. On the left it must
# block a match: ".NET" inside "ASP.NET" is the web framework, a different
# catalogue entry. On the right it must not, because a dot after a term is
# usually the end of a sentence -- "Java/C#. Understanding of REST APIs"
# was the whole reason two adverts still missed C# after the boundary fix.
_LEFT_TOKEN_CHARS = r'\w#+.'
_RIGHT_TOKEN_CHARS = r'\w#+'


def _term_pattern(term):
    """A boundary-anchored pattern that also works for C#, C++ and .NET.

    ``\\b`` is the edge between a word character and a non-word one, so
    ``\\bC#\\b`` cannot match "C# developer": after the '#' comes a space,
    and two non-word characters have no boundary between them. The same defeats
    C++ and .NET. It was not a near miss -- 64 adverts mentioned C# and not one
    produced a skill link, and .NET appeared in 57 with no catalogue row at all.

    Where the term's own edge is punctuation, the assertion is replaced with
    the one \\b was standing in for: not adjacent to more of the same token.
    So "C#" matches in "C# developer" but not in "C##", and ".NET" matches on
    its own but not inside "ASP.NET", which is a different skill.
    """
    left = (r'\b' if (term[:1].isalnum() or term[:1] == '_')
            else rf'(?<![{_LEFT_TOKEN_CHARS}])')
    right = (r'\b' if (term[-1:].isalnum() or term[-1:] == '_')
             else rf'(?![{_RIGHT_TOKEN_CHARS}])')
    return re.compile(left + re.escape(term) + right, re.IGNORECASE)


def extract_skill_matches(text):
    """Every skill the text asks for, with the evidence for each.

    Returns a list of ``(skill, matched_text, match_method)``. The method
    matters downstream: a CONTEXTUAL_ALIAS hit survived a look at its
    surroundings, an ALIAS hit did not need to, and a reviewer reading a
    suspicious link needs to know which.

    Three gates, in order of how much they are trusted:

      * a canonical name in AMBIGUOUS_SKILLS ("Go", "R", "Swift") must survive
        the context check -- these are ordinary English words;
      * an alias marked ``requires_context`` must survive the same check --
        that flag exists for short or overloaded strings like "Mac", which is
        macOS in one advert and a MAC address in another;
      * everything else matches on a word boundary alone.
    """
    if not text:
        return []

    terms_by_skill = _terms_by_skill()

    # A catalogue of two thousand skills makes the naive "compile a pattern
    # per skill and scan the text" loop the dominant cost of every extraction.
    # This containment test is a pure filter, not a second matching rule: the
    # patterns below are anchored on both sides, so they can only match where
    # the term already occurs as a substring.
    lowered = text.lower()

    matches = []
    for skill, terms in terms_by_skill.items():
        if not any(term.lower() in lowered for term, _ in terms):
            continue

        ambiguous_name = skill.skill_name.strip().lower() in AMBIGUOUS_SKILLS
        best = None
        for term, method in terms:
            if term.lower() not in lowered:
                continue
            pattern = _term_pattern(term)
            # A guarded term is gated however it matched. "Sage" is a
            # canonical name, so requires_context cannot reach it and
            # AMBIGUOUS_SKILLS would subject it to the generic gate it needs
            # to bypass.
            gated = (method == CONTEXTUAL_ALIAS
                     or (method == DIRECT_CANONICAL and ambiguous_name)
                     or term.strip().lower() in TERM_GUARD_PATTERNS)

            for found in pattern.finditer(text):
                if gated and not _accepted_in_context(text, found):
                    continue
                candidate = (found.group(0), method)
                # An ungated canonical hit is the strongest evidence there is;
                # take it and stop looking.
                if not gated and method == DIRECT_CANONICAL:
                    best = candidate
                    break
                best = best or candidate
            if best and best[1] == DIRECT_CANONICAL:
                break

        if best is not None:
            matches.append((skill, best[0], best[1]))

    return matches


def extract_skills_from_text(text):
    """The skills a text asks for.

    Thin wrapper over :func:`extract_skill_matches`, kept because most callers
    only want the skills and should not have to unpack match provenance.
    """
    return [skill for skill, _, _ in extract_skill_matches(text)]
