"""Acquisition permission is checked before an adapter can run.

The rule these protect: registering an adapter is a capability, and permission
is a separate question. Conflating them is how a policy decision gets quietly
undone by a later refactor -- somebody writes an adapter, registers it, and the
site's robots.txt never enters the conversation again.
"""

from django.test import SimpleTestCase

from .providers.base import CourseProvider, get_provider, register
from .providers.policy import (
    ACQUISITION_POLICY, ALLOWED, BLOCKED, NO_PUBLIC_INTERFACE, PENDING,
    blocked_providers,
    is_permitted, pending_providers, status_for,
)


class AcquisitionPolicyTests(SimpleTestCase):

    def test_sap_learning_is_out_of_scope_entirely(self):
        """Removed from the table, not carried as PENDING.

        A PENDING entry is a to-do item; this is a decision. SAP Learning's
        robots.txt is "user-agent: * / disallow: /", and leaving the name in
        the table would keep inviting an adapter nobody may write. Absence
        already means "not permitted", which is the correct answer.
        """
        self.assertNotIn("SAP Learning", ACQUISITION_POLICY)
        self.assertEqual(status_for("SAP Learning"), PENDING)
        self.assertFalse(is_permitted("SAP Learning"))

    def test_an_unpermitted_provider_cannot_be_constructed(self):
        """Even if somebody writes and registers the adapter anyway."""

        @register
        class OutOfScopeProvider(CourseProvider):
            name = "Some Disallowed Site"

            def search(self, phrase):
                return []

        with self.assertRaises(PermissionError):
            get_provider("Some Disallowed Site")

    def test_a_disallowed_path_is_recorded_with_the_route_that_avoids_it(self):
        """edX permits its sitemap and forbids its search endpoint.

        A route restriction rather than a blanket status: the provider is
        usable, just not by the obvious means.
        """
        edx = ACQUISITION_POLICY["edX"]

        self.assertEqual(edx["status"], ALLOWED)
        self.assertIn("/search?", edx["evidence"])
        self.assertIn("sitemap", edx["route"].lower())
        # And the correction that produced this entry is kept, because the
        # first reading of the same file said the opposite.
        self.assertIn("truncated", edx["correction"].lower())

    def test_pending_is_not_permission(self):
        """An unchecked provider must not become an implemented one by default.

        This is the failure the module exists to prevent: silence reading as
        consent. Asserted against a name nobody has checked, because the real
        table should keep shrinking towards no PENDING entries at all.
        """
        self.assertEqual(status_for("A Provider Nobody Checked"), PENDING)
        self.assertFalse(is_permitted("A Provider Nobody Checked"))

    def test_the_checked_providers_record_their_conditions(self):
        """A permission with a condition attached must state the condition.

        Cisco allows everything and sets Crawl-delay: 10. An adapter that
        honours the first half and not the second is not doing what the site
        asked.
        """
        cisco = ACQUISITION_POLICY["Cisco Networking Academy"]

        self.assertEqual(cisco["status"], ALLOWED)
        self.assertIn("crawl-delay", cisco["evidence"].lower())
        self.assertIn("10", cisco["route"])

    def test_an_unknown_provider_is_not_permitted(self):
        self.assertEqual(status_for("Some New Site"), PENDING)
        self.assertFalse(is_permitted("Some New Site"))

    def test_permitted_providers_cite_what_was_checked(self):
        """An ALLOWED status is a finding with a citation, not an assumption."""
        for name, entry in ACQUISITION_POLICY.items():
            if entry["status"] != ALLOWED:
                continue
            with self.subTest(provider=name):
                self.assertTrue(entry["checked"], f"{name} has no check date")
                self.assertTrue(entry["evidence"])
                self.assertTrue(entry["route"])

    def test_nothing_in_the_table_is_blocked(self):
        """A provider that may not be acquired from is removed, not carried."""
        self.assertEqual(blocked_providers(), {})

    def test_a_permitted_provider_with_nothing_to_read_is_not_implementable(self):
        """Permission and feasibility are different questions.

        Both AWS Skill Builder and Oracle MyLearn permit everything in
        robots.txt and still cannot be acquired from: their catalogues arrive
        over internal calls a browser would have to drive. Recording that as
        ALLOWED would invite an adapter; recording it as BLOCKED would blame
        the site for a decision it did not make.
        """
        for name in ("AWS Skill Builder", "Oracle MyLearn"):
            with self.subTest(provider=name):
                entry = ACQUISITION_POLICY[name]
                self.assertEqual(entry["status"], NO_PUBLIC_INTERFACE)
                self.assertFalse(is_permitted(name))
                # The evidence must say what was actually looked at.
                self.assertIn("sitemap", entry["evidence"].lower())

    def test_every_entry_has_been_checked_or_is_explicitly_pending(self):
        """No entry may sit in the table without a status somebody decided."""
        for name, entry in ACQUISITION_POLICY.items():
            with self.subTest(provider=name):
                self.assertIn(entry["status"],
                              (ALLOWED, BLOCKED, NO_PUBLIC_INTERFACE, PENDING))
                if entry["status"] != PENDING:
                    self.assertTrue(entry["checked"],
                                    f"{name} has a status but no check date")
