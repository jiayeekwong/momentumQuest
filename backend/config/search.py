"""Searching for words rather than for letters.

DRF's SearchFilter matches substrings. On a field of prose that is close to
useless for the short terms people actually type: a student searching "ai"
matched "tr-ai-ning", "d-ai-ly", "av-ai-lable" and "em-ai-l", which is 96% of
the scraped adverts against the 18% that mention AI. "ui", "qa", "bi", "ml",
"go" and "r" all behave the same way, and they are exactly the terms a
computing student searches for.

So terms are matched at word boundaries. PostgreSQL spells those \\y, which is
what makes this a filter rather than a settings change -- and it is the only
part of this module that is not portable.

Terms are escaped before they are used as a pattern, because whatever someone
types goes into the regex. The boundaries are then applied only where they
could match: a term that begins or ends with punctuation has no word boundary
there, and demanding one would mean "C++" and ".NET" found nothing.
"""

import re

from rest_framework.filters import SearchFilter

#: A word character, for deciding where a boundary can exist at all.
_WORD = re.compile(r"\w")


def boundaried(term):
    """A regex matching `term` as a whole word, as far as that is meaningful.

    "python" becomes \\ypython\\y. "C++" becomes \\yC\\+\\+ -- no boundary
    after the plus signs, because a word boundary needs a word character on
    one side and requiring one there would match nothing at all.
    """
    pattern = re.escape(term)
    if _WORD.match(term[:1]):
        pattern = r"\y" + pattern
    if _WORD.match(term[-1:]):
        pattern = pattern + r"\y"
    return pattern


class WholeWordSearchFilter(SearchFilter):
    """SearchFilter that matches whole words instead of substrings.

    Deliberately without DRF's field prefixes (^ = @ $). They select a lookup
    per field, and this one applies a single lookup to all of them; honouring
    both would mean two rules for the same declaration.
    """

    def construct_search(self, field_name, queryset=None):
        return f"{field_name}__iregex"

    def get_search_terms(self, request):
        return [boundaried(term) for term in super().get_search_terms(request)
                if term]
