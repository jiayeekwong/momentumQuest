"""Pagination for the resource catalogue listing.

Scoped to one view rather than configured globally, and that is the whole point
worth recording. This project has ten ListAPIViews returning bare JSON arrays,
and the frontend reads them in 28 places as

    Array.isArray(data) ? data : []

so setting REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"] would hand every one of
them an object instead of a list. Announcements, the public job feed, courses,
certificates, stored skills and training programmes would all quietly render as
empty -- no error, no failing request, just nothing on the page. A global
default is the cheaper edit and the more expensive mistake.
"""

from rest_framework.pagination import PageNumberPagination


class ResourceCataloguePagination(PageNumberPagination):
    """A page of the resource catalogue.

    24 fills the page's three-column grid exactly eight rows deep, and the
    ceiling exists because page_size is caller-supplied: without max_page_size
    a request for ?page_size=20430 reinstates the 5.4MB download this
    pagination was added to stop.
    """

    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 100
