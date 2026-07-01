from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

import build_graph


class BuildGraphParsingTests(unittest.TestCase):
    def make_mention(self, name: str, category: str = "people") -> build_graph.Mention:
        return build_graph.Mention(
            id="m-1",
            entity_id=build_graph.entity_key(build_graph.canonicalize(name, category), category),
            name=name,
            category=category,
            category_label=build_graph.label(category),
            segment_id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            timestamp="00:00:00",
            excerpt=name,
            detector="test",
            confidence=1.0,
            reason="test",
        )

    def test_parse_timestamp_ms(self) -> None:
        self.assertEqual(build_graph.parse_timestamp_ms("00:01:02.500"), 62500)
        self.assertEqual(build_graph.parse_timestamp_ms("01:02,250"), 62250)
        self.assertEqual(build_graph.parse_timestamp_ms("bad"), 0)

    def test_parse_exact_date_uses_only_hard_dates(self) -> None:
        self.assertEqual(build_graph.parse_exact_date("July 8, 1947").iso, "1947-07-08")
        self.assertEqual(build_graph.parse_exact_date("8 July 1947").iso, "1947-07-08")
        self.assertEqual(build_graph.parse_exact_date("7/8/47").iso, "1947-07-08")
        self.assertIsNone(build_graph.parse_exact_date("on April"))
        self.assertIsNone(build_graph.parse_exact_date("early April 1947"))
        self.assertEqual(build_graph.parse_document_date_value("May 2022").precision, "month")
        self.assertEqual(build_graph.parse_document_date_value("May 2022").iso, "2022-05")
        self.assertEqual(build_graph.parse_document_date_value("1947").precision, "year")

    def test_parse_subtitles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.srt"
            path.write_text("1\n00:00:01,000 --> 00:00:02,500\nFirst line.\nSecond line.\n", encoding="utf-8")
            rows = build_graph.parse_subtitles(path)
        self.assertEqual(rows, [{"start_ms": 1000, "end_ms": 2500, "text": "First line. Second line."}])

    def test_parse_json_segments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.json"
            path.write_text(json.dumps({"segments": [{"start": 1.5, "end": 2.25, "text": "Segment text"}]}), encoding="utf-8")
            rows = build_graph.parse_json(path)
        self.assertEqual(rows, [{"start_ms": 1500, "end_ms": 2250, "text": "Segment text"}])

    def test_signal_patterns_reject_numeric_table_fragments(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="See pages 1, 2 and 22, 23. Revision 1.2.3.4 and value 131.882 are table artifacts. Noise was 000 Hz.",
        )
        mentions = build_graph.pattern_mentions(segment)
        self.assertFalse([item for item in mentions if item["category"] in {"gps_coordinates", "ip_addresses", "radio_frequencies", "frequencies"}])

    def test_signal_patterns_keep_contextual_coordinates_and_frequencies(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="GPS coordinates 37.24, -115.81 were logged with VHF radio 131.882, IPv4 203.0.113.10, and a 300 GHz signal.",
        )
        mentions = build_graph.pattern_mentions(segment)
        by_category = {(item["category"], item["name"]) for item in mentions}
        self.assertIn(("gps_coordinates", "37.24, -115.81"), by_category)
        self.assertIn(("radio_frequencies", "131.882"), by_category)
        self.assertIn(("ip_addresses", "203.0.113.10"), by_category)
        self.assertIn(("frequencies", "300 GHz"), by_category)

    def test_signal_patterns_normalize_frequency_units(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text=(
                "Signals included 300 megahertz, 300MHz, 1600MHz, 1.6 GHz, "
                "5000 Hz, 16-190kHz, 1215-1240 MHz, 0.1 to 20 Gigahertz, and 4.76–5.66 terahertz."
            ),
        )
        mentions = build_graph.pattern_mentions(segment)
        names = {item["name"] for item in mentions if item["category"] == "frequencies"}
        self.assertIn("300 MHz", names)
        self.assertIn("1.6 GHz", names)
        self.assertIn("5 kHz", names)
        self.assertIn("16-190 kHz", names)
        self.assertIn("1.215-1.24 GHz", names)
        self.assertIn("0.1-20 GHz", names)
        self.assertIn("4.76-5.66 THz", names)
        self.assertNotIn("300 megahertz", names)
        self.assertNotIn("300MHz", names)
        self.assertNotIn("1600 MHz", names)
        self.assertNotIn("5000 Hz", names)
        self.assertNotIn("190 kHz", names)

    def test_blood_type_patterns_require_blood_context(self) -> None:
        ad_segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="That's Q-U-A-L-I-A-L-I-F-E dot com slash jesse, J-E-S-S-E, for an extra 15% off.",
        )
        blood_segment = build_graph.Segment(
            id="s-2",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=1000,
            end_ms=2000,
            text="The witness described a rare Rh negative blood type, specifically A-.",
        )

        ad_mentions = build_graph.pattern_mentions(ad_segment)
        blood_mentions = build_graph.pattern_mentions(blood_segment)

        self.assertFalse([item for item in ad_mentions if item["category"] == "blood_types"])
        self.assertIn(("blood_types", "A-"), {(item["category"], item["name"]) for item in blood_mentions})

    def test_frequency_category_is_reserved_for_actual_values(self) -> None:
        entities = json.loads(Path("data/entities.json").read_text(encoding="utf-8"))
        value_re = re.compile(r"^\d{1,9}(?:\.\d{1,6})?(?:-\d{1,9}(?:\.\d{1,6})?)?\s(?:Hz|kHz|MHz|GHz|THz)$")
        invalid_names = [entity["name"] for entity in entities if entity["category"] == "frequencies" and not value_re.match(entity["name"])]
        self.assertEqual(invalid_names, [])

    def test_source_documents_become_entities_with_provenance_relationships(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="transcript-one",
            transcript_title="Transcript One",
            source_file="transcript-one.tsv",
            start_ms=0,
            end_ms=1000,
            text="This American Alchemy transcript calls out a 1600MHz signal.",
        )
        mentions: list[build_graph.Mention] = []
        seen: set[tuple[str, str, str]] = set()
        for item in build_graph.pattern_mentions(segment):
            build_graph.add_mention(mentions, seen, segment, **item)

        mentions = build_graph.add_source_provenance_mentions([segment], mentions)
        entities = build_graph.build_entities(mentions)
        relationships = build_graph.build_relationships([segment], mentions, entities, {})

        entity_keys = {(entity.category, entity.name) for entity in entities}
        self.assertIn(("document_names", "Transcript One"), entity_keys)
        self.assertIn(("frequencies", "1.6 GHz"), entity_keys)
        self.assertIn(("newsrooms", "American Alchemy"), entity_keys)

        relationship_keys = {(relationship.source_name, relationship.target_name, relationship.type) for relationship in relationships}
        self.assertIn(("Transcript One", "1.6 GHz", "source_mentions"), relationship_keys)
        self.assertIn(("Transcript One", "American Alchemy", "source_outlet"), relationship_keys)

    def test_source_document_titles_assign_exact_dates(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="roswell-report",
            transcript_title="Roswell Report July 8 1947",
            source_file="roswell-report.tsv",
            start_ms=0,
            end_ms=1000,
            text="The source document discusses Roswell.",
        )
        mentions = build_graph.add_source_provenance_mentions([segment], [])
        entities = build_graph.build_entities(mentions)
        build_graph.assign_entity_dates([segment], mentions, entities)
        relationships = build_graph.build_relationships([segment], mentions, entities, {})

        document = next(entity for entity in entities if entity.category == "document_names")
        self.assertEqual(document.date_iso, "1947-07-08")
        self.assertEqual(document.date_display, "July 8, 1947")
        self.assertEqual(document.date_source, "source_title")
        self.assertIn(("dates_times", "July 8, 1947"), {(entity.category, entity.name) for entity in entities})
        self.assertIn(
            ("Roswell Report July 8 1947", "July 8, 1947", "dated_on"),
            {(relationship.source_name, relationship.target_name, relationship.type) for relationship in relationships},
        )

    def test_source_document_titles_assign_month_precision_dates(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="mission-report",
            transcript_title="Dow Uap D10 Mission Report Middle East May 2022",
            source_file="mission-report.tsv",
            start_ms=0,
            end_ms=1000,
            text="The source document is a mission report.",
        )
        mentions = build_graph.add_source_provenance_mentions([segment], [])
        entities = build_graph.build_entities(mentions)
        build_graph.assign_entity_dates([segment], mentions, entities)

        document = next(entity for entity in entities if entity.category == "document_names")
        self.assertEqual(document.date_iso, "2022-05")
        self.assertEqual(document.date_display, "May 2022")
        self.assertEqual(document.date_precision, "month")

    def test_event_dates_require_same_sentence_exact_date(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="roswell",
            transcript_title="Roswell",
            source_file="roswell.tsv",
            start_ms=0,
            end_ms=1000,
            text="The Roswell Incident happened on July 8, 1947, near Roswell, New Mexico.",
        )
        mentions: list[build_graph.Mention] = []
        seen: set[tuple[str, str, str]] = set()
        for item in build_graph.pattern_mentions(segment):
            build_graph.add_mention(mentions, seen, segment, **item)
        build_graph.add_mention(
            mentions,
            seen,
            segment,
            name="Roswell Incident",
            category="events",
            detector="test:event",
            confidence=1.0,
            reason="test",
            excerpt=segment.text,
        )
        entities = build_graph.build_entities(mentions)
        build_graph.assign_entity_dates([segment], mentions, entities)

        event = next(entity for entity in entities if entity.category == "events")
        self.assertEqual(event.date_iso, "1947-07-08")
        self.assertEqual(event.date_source, "event_sentence")

    def test_broad_duration_events_do_not_get_single_day_dates(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="world-war",
            transcript_title="World War",
            source_file="world-war.tsv",
            start_ms=0,
            end_ms=1000,
            text="The World War reference appeared beside April 6, 1917, in the source.",
        )
        mentions: list[build_graph.Mention] = []
        seen: set[tuple[str, str, str]] = set()
        for item in build_graph.pattern_mentions(segment):
            build_graph.add_mention(mentions, seen, segment, **item)
        build_graph.add_mention(
            mentions,
            seen,
            segment,
            name="World War",
            category="events",
            detector="test:event",
            confidence=1.0,
            reason="test",
            excerpt=segment.text,
        )
        entities = build_graph.build_entities(mentions)
        build_graph.assign_entity_dates([segment], mentions, entities)

        event = next(entity for entity in entities if entity.category == "events")
        self.assertIsNone(event.date_iso)

    def test_event_dates_reject_report_date_wording(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="tic-tac",
            transcript_title="Tic Tac",
            source_file="tic-tac.tsv",
            start_ms=0,
            end_ms=1000,
            text="The January 7, 2009, report on his involvement with Tic Tac was forwarded later.",
        )
        mentions: list[build_graph.Mention] = []
        seen: set[tuple[str, str, str]] = set()
        for item in build_graph.pattern_mentions(segment):
            build_graph.add_mention(mentions, seen, segment, **item)
        build_graph.add_mention(
            mentions,
            seen,
            segment,
            name="Tic Tac",
            category="events",
            detector="test:event",
            confidence=1.0,
            reason="test",
            excerpt=segment.text,
        )
        entities = build_graph.build_entities(mentions)
        build_graph.assign_entity_dates([segment], mentions, entities)

        event = next(entity for entity in entities if entity.category == "events")
        self.assertIsNone(event.date_iso)

    def test_source_titles_are_used_as_relationship_evidence(self) -> None:
        title_segment = build_graph.Segment(
            id=build_graph.source_title_segment_id("bob-lazar-travis-walton-finally-meet-t"),
            transcript_id="bob-lazar-travis-walton-finally-meet-t",
            transcript_title="Bob Lazar Travis Walton Finally Meet T",
            source_file="bob-lazar-travis-walton-finally-meet-t.tsv",
            start_ms=-1,
            end_ms=0,
            text="Bob Lazar Travis Walton Finally Meet T",
        )
        body_segment = build_graph.Segment(
            id="seg-bob-lazar-travis-walton-finally-meet-t-00000",
            transcript_id="bob-lazar-travis-walton-finally-meet-t",
            transcript_title="Bob Lazar Travis Walton Finally Meet T",
            source_file="bob-lazar-travis-walton-finally-meet-t.tsv",
            start_ms=0,
            end_ms=1000,
            text="Travis Walton described the encounter.",
        )
        dictionaries, omit_terms = build_graph.build_dictionaries({"categories": {}, "omit": []})
        mentions = build_graph.extract_mentions([title_segment, body_segment], dictionaries, omit_terms)
        mentions = build_graph.add_source_title_mentions([title_segment, body_segment], mentions, dictionaries, omit_terms)
        mentions = build_graph.resolve_competing_mentions(mentions)
        mentions = build_graph.add_source_provenance_mentions([title_segment, body_segment], mentions)
        entities = build_graph.build_entities(mentions)
        relationships = build_graph.build_relationships([title_segment, body_segment], mentions, entities, {})

        title_mentions = {
            (mention.name, mention.category)
            for mention in mentions
            if mention.detector == build_graph.SOURCE_TITLE_DETECTOR
        }
        self.assertIn(("Bob Lazar", "whistleblowers"), title_mentions)
        self.assertIn(("Travis Walton", "experiencers"), title_mentions)

        bob_travis_relationship = next(
            relationship
            for relationship in relationships
            if {relationship.source_name, relationship.target_name} == {"Bob Lazar", "Travis Walton"}
        )
        self.assertTrue(bob_travis_relationship.id.startswith("rel-title-"))
        self.assertEqual(bob_travis_relationship.evidence[0]["reason"], "Source title names both entities")
        self.assertIn(
            ("Bob Lazar Travis Walton Finally Meet T", "Travis Walton", "source_mentions"),
            {(relationship.source_name, relationship.target_name, relationship.type) for relationship in relationships},
        )

    def test_generated_people_like_categories_do_not_contain_pentagon_or_universal_origin_leaks(self) -> None:
        entities = json.loads(Path("data/entities.json").read_text(encoding="utf-8"))
        people_like = {
            "dangerous_people",
            "experiencers",
            "friendly_people",
            "journalists",
            "people",
            "politicians",
            "professors",
            "whistleblowers",
        }
        leaks = [
            (entity["category"], entity["name"])
            for entity in entities
            if entity["category"] in people_like
            and ("pentagon" in entity["name"].lower() or "universal origin" in entity["name"].lower())
        ]
        self.assertEqual(leaks, [])

    def test_signal_patterns_keep_only_actual_signals_in_signal_categories(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="The report mentioned radio frequencies, radio frequency, guard frequency, ELF waves, ELF wave, UHF band, and extra low frequency.",
        )
        mentions = build_graph.pattern_mentions(segment)
        radio_names = {item["name"] for item in mentions if item["category"] == "radio_frequencies"}
        frequency_names = {item["name"] for item in mentions if item["category"] == "frequencies"}
        key_term_names = {item["name"] for item in mentions if item["category"] == "key_terms"}
        self.assertFalse(radio_names)
        self.assertIn("radio frequency", key_term_names)
        self.assertIn("guard frequency", key_term_names)
        self.assertIn("ELF frequency", key_term_names)
        self.assertIn("UHF frequency", key_term_names)
        self.assertIn("extremely low frequency", key_term_names)
        self.assertNotIn("ELF frequency", frequency_names)
        self.assertNotIn("UHF frequency", frequency_names)
        self.assertNotIn("extremely low frequency", frequency_names)
        self.assertNotIn("ELF waves", frequency_names)

    def test_person_mentions_reject_table_label_phrases(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="The table columns read Date Location Witnesses Description and Location Time Number.",
        )
        mentions = build_graph.person_mentions(segment, set())
        self.assertFalse([item for item in mentions if item["name"] in {"Date Location Witnesses Description", "Location Time Number"}])

    def test_person_mentions_reclassify_named_reports_as_documents(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="The Robertson Panel Report shaped the official response.",
        )
        mentions = build_graph.person_mentions(segment, set())
        self.assertIn(("Robertson Panel Report", "document_names"), {(item["name"], item["category"]) for item in mentions})

    def test_person_mentions_route_generic_aircraft_phrases_to_key_terms(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="The table listed Aircraft Tail Number and Unidentified Aircraft.",
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        self.assertEqual(by_name.get("Aircraft Tail Number"), "key_terms")
        self.assertEqual(by_name.get("Unidentified Aircraft"), "key_terms")

    def test_person_mentions_route_domain_nouns_out_of_people(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text=(
                "Unidentified Flying Objects, Unidienified Aerial Objects, Flying Objects, "
                "Aerial Phenomena Research Organization, Project Blue Book, National Security, "
                "Western Range, and Wide Area Video Surveillance appeared in the source material."
            ),
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        people_like = {
            item["name"]
            for item in mentions
            if item["category"] in build_graph.PERSON_LIKE_CATEGORIES
        }
        self.assertFalse(
            people_like.intersection(
                {
                    "Unidentified Flying Objects",
                    "Unidienified Aerial Objects",
                    "Flying Objects",
                    "Aerial Phenomena Research Organization",
                    "Project Blue Book",
                    "National Security",
                    "Western Range",
                    "Wide Area Video Surveillance",
                }
            )
        )
        self.assertEqual(by_name.get("Unidentified Flying Objects"), "key_terms")
        self.assertEqual(by_name.get("Unidentified Aerial Objects"), "key_terms")
        self.assertEqual(by_name.get("Flying Objects"), "key_terms")
        self.assertEqual(by_name.get("Aerial Phenomena Research Organization"), "research_groups")
        self.assertEqual(by_name.get("Project Blue Book"), "government_project_codenames")
        self.assertEqual(by_name.get("National Security"), "key_terms")
        self.assertEqual(by_name.get("Western Range"), "locations")
        self.assertEqual(by_name.get("Wide Area Video Surveillance"), "key_terms")

    def test_person_mentions_route_force_western_and_group_phrases_out_of_people(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text=(
                "Atr Force, Air Force Lieutenant, Western Europe, Western Union, "
                "Carrier Strike Group Twelve, Sol Foundation Volume, and Organization Communications "
                "were not person names."
            ),
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        people_like = {
            item["name"]
            for item in mentions
            if item["category"] in build_graph.PERSON_LIKE_CATEGORIES
        }
        self.assertFalse(
            people_like.intersection(
                {
                    "Atr Force",
                    "Air Force Lieutenant",
                    "Western Europe",
                    "Western Union",
                    "Carrier Strike Group Twelve",
                    "Sol Foundation Volume",
                    "Organization Communications",
                }
            )
        )
        self.assertEqual(by_name.get("Atr Force"), "government_agencies")
        self.assertEqual(by_name.get("Air Force Lieutenant"), "government_agencies")
        self.assertEqual(by_name.get("Western Europe"), "locations")
        self.assertEqual(by_name.get("Western Union"), "companies")
        self.assertEqual(by_name.get("Carrier Strike Group Twelve"), "government_agencies")
        self.assertEqual(by_name.get("Sol Foundation Volume"), "nonprofits")
        self.assertEqual(by_name.get("Organization Communications"), "nonprofits")

    def test_person_mentions_omit_hard_ocr_non_entities(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="Aircraft Jl, Aircraft Tail Numbenta, Arizona Name, After J., and L. P. were OCR fragments.",
        )
        mentions = build_graph.person_mentions(segment, set())
        names = {item["name"] for item in mentions}
        self.assertFalse(names.intersection({"Aircraft Jl", "Aircraft Tail Numbenta", "Arizona Name", "After J.", "L. P."}))

    def test_person_mentions_route_structured_field_phrases_to_key_terms(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="Mission Impact, Date Written, First Name Unknown, and Number Per Cent appeared as table labels.",
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        self.assertEqual(by_name.get("Mission Impact"), "key_terms")
        self.assertEqual(by_name.get("Date Written"), "key_terms")
        self.assertEqual(by_name.get("First Name Unknown"), "key_terms")
        self.assertNotIn("Number Per Cent", by_name)

    def test_person_mentions_keep_branded_aircraft_orgs_as_contractors(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="Martin Aircraft and Boeing Aircraft Company were both named.",
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        self.assertEqual(by_name.get("Martin Aircraft"), "contractors")
        self.assertEqual(by_name.get("Boeing Aircraft Company"), "companies")

    def test_person_mentions_do_not_make_command_posts_newsrooms(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="The Missile Command Post forwarded the report.",
        )
        mentions = build_graph.person_mentions(segment, set())
        self.assertEqual({item["name"]: item["category"] for item in mentions}.get("Missile Command Post"), "key_terms")

    def test_person_mentions_route_generic_org_descriptors_out_of_people(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="Air Staff, Mission Control, Advanced Systems, and Research Center were listed.",
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        self.assertEqual(by_name.get("Air Staff"), "government_agencies")
        self.assertEqual(by_name.get("Mission Control"), "government_agencies")
        self.assertEqual(by_name.get("Advanced Systems"), "key_terms")
        self.assertEqual(by_name.get("Research Center"), "research_groups")

    def test_person_mentions_route_light_phenomena_ocr_variants_to_key_terms(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="The table rows showed 3-Light Phenoa, Light Phenos, and H-Light Phenow.",
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        names = {item["name"] for item in mentions}
        self.assertEqual(by_name.get("Light Phenomena"), "key_terms")
        self.assertNotIn("Light Phenoa", names)
        self.assertNotIn("Light Phenos", names)
        self.assertNotIn("Light Phenow", names)

    def test_curated_galactic_federation_is_key_term_not_person(self) -> None:
        dictionaries, _ = build_graph.build_dictionaries({})
        self.assertIn("Galactic Federation", dictionaries["key_terms"])

        mention = self.make_mention("Galactic Federation", "people")
        review = {"nameReclassifications": {"galactic federation": "key_terms"}}
        reviewed = build_graph.apply_review_to_mentions([mention], review)
        self.assertEqual(reviewed[0].category, "key_terms")
        self.assertEqual(reviewed[0].entity_id, "key_terms:galactic-federation")

    def test_person_mentions_route_signal_tech_phrases_out_of_people(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="Terahertz Electronics and Terahertz High Power Amplifier appeared in the table.",
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        self.assertEqual(by_name.get("Terahertz Electronics"), "technology")
        self.assertEqual(by_name.get("Terahertz High Power Amplifier"), "technology")

    def test_person_mentions_route_non_signal_frequency_concepts_to_key_terms(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="High Frequency Gravitational Waves and Radiofrequency Electromagnetic Fields were listed.",
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        self.assertEqual(by_name.get("High Frequency Gravitational Waves"), "key_terms")
        self.assertEqual(by_name.get("Radio Frequency Electromagnetic Fields"), "key_terms")

    def test_person_mentions_route_bird_table_ocr_artifacts_to_key_terms(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="Birds Ol, Bords Ol, and Birds Clololeeieelsee were OCR table rows.",
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        names = {item["name"] for item in mentions}
        self.assertEqual(by_name.get("Birds"), "key_terms")
        self.assertNotIn("Birds Ol", names)
        self.assertNotIn("Bords Ol", names)
        self.assertNotIn("Birds Clololeeieelsee", names)

    def test_person_mentions_route_pentagon_phrases_out_of_people(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="Pentagon Washington, Pentagon Special Programs, and Vietnam War Pentagon Papers were listed.",
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        names = {item["name"] for item in mentions}
        self.assertEqual(by_name.get("Pentagon"), "government_agencies")
        self.assertEqual(by_name.get("Pentagon Special Programs"), "key_terms")
        self.assertEqual(by_name.get("Pentagon Papers"), "leaks")
        self.assertNotIn("Pentagon Washington", names)

    def test_person_mentions_route_universal_origin_species_out_of_people(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="Procyonans Universal Origin and Zeta Reticulans Universal Origin appeared in the almanac.",
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        self.assertEqual(by_name.get("Procyonans Universal Origin"), "alien_species")
        self.assertEqual(by_name.get("Zeta Reticulans Universal Origin"), "alien_species")

    def test_person_mentions_route_measurement_codebook_fields_to_key_terms(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="Angular Velocity, Angular Velocity Mota, Angular Acceleration Motion, Appearance Bearing, and Disappearance Bearing were table fields.",
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        names = {item["name"] for item in mentions}
        self.assertEqual(by_name.get("Angular Velocity"), "key_terms")
        self.assertEqual(by_name.get("Angular Acceleration"), "key_terms")
        self.assertEqual(by_name.get("Appearance Bearing"), "key_terms")
        self.assertEqual(by_name.get("Disappearance Bearing"), "key_terms")
        self.assertNotIn("Angular Velocity Mota", names)
        self.assertNotIn("Angular Acceleration Motion", names)

    def test_person_mentions_keep_news_services_as_newsrooms(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="The Pacific News Service published the item.",
        )
        mentions = build_graph.person_mentions(segment, set())
        self.assertEqual({item["name"]: item["category"] for item in mentions}.get("Pacific News Service"), "newsrooms")

    def test_person_mentions_keep_real_report_titles_as_documents(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="The Condon Report and Air Intelligence Report were cited, but Report In was a bad heading.",
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        self.assertEqual(by_name.get("Condon Report"), "document_names")
        self.assertEqual(by_name.get("Air Intelligence Report"), "document_names")
        self.assertEqual(by_name.get("Report In"), "key_terms")

    def test_person_mentions_reject_enumerated_date_and_location_fragments(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="A. Date Birth 8/5/30. Section A. Oct 11, 1989. P. M. Friday was noted.",
        )
        mentions = build_graph.person_mentions(segment, set())
        names = {item["name"] for item in mentions}
        self.assertNotIn("A. Date Birth", names)
        self.assertNotIn("Section A. Oct", names)
        self.assertNotIn("P. M. Friday", names)

    def test_person_mentions_preserve_real_initial_surnames(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="Sam D. Page was listed as a relative.",
        )
        mentions = build_graph.person_mentions(segment, set())
        self.assertIn("Sam D. Page", {item["name"] for item in mentions})

    def test_person_mentions_strip_observer_and_pilot_roles(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="Observer John A. Potter and Pilot Joseph A. Walker both filed reports.",
        )
        mentions = build_graph.person_mentions(segment, set())
        names = {item["name"] for item in mentions}
        self.assertIn("John A. Potter", names)
        self.assertIn("Joseph A. Walker", names)
        self.assertNotIn("Observer John A. Potter", names)
        self.assertNotIn("Pilot Joseph A. Walker", names)

    def test_person_mentions_reclassify_month_context_phrases_as_dates(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="On November the archive changed. Theresa May was also mentioned.",
        )
        mentions = build_graph.person_mentions(segment, set())
        by_name = {item["name"]: item["category"] for item in mentions}
        self.assertEqual(by_name.get("On November"), "dates_times")
        self.assertEqual(by_name.get("Theresa May"), "people")

    def test_review_export_removes_runtime_source_path(self) -> None:
        review = {
            "source_path": "data/reclass.json",
            "reclassifications": {"people:test": "locations"},
        }
        exported = build_graph.export_review(review)
        self.assertNotIn("source_path", exported)
        self.assertEqual(exported["reclassifications"], {"people:test": "locations"})
        self.assertEqual(exported["falsePositives"], {})

    def test_name_reclassifications_are_derived_from_entity_ids(self) -> None:
        review = {"reclassifications": {"people:department-of-energy": "government_agencies"}}
        build_graph.normalize_review(review)
        build_graph.add_name_reclassifications_from_ids(review)
        self.assertEqual(review["nameReclassifications"]["department of energy"], "government_agencies")

    def test_aliases_can_target_entity_ids(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="Department of Energy",
        )
        mention = build_graph.Mention(
            id="m-1",
            entity_id="people:department-of-energy",
            name="Department of Energy",
            category="people",
            category_label="People",
            segment_id=segment.id,
            transcript_id=segment.transcript_id,
            transcript_title=segment.transcript_title,
            source_file=segment.source_file,
            start_ms=0,
            timestamp="00:00:00",
            excerpt="Department of Energy",
            detector="test",
            confidence=1.0,
            reason="test",
        )
        reviewed = build_graph.apply_review_to_mentions([mention], {"aliases": {"people:department-of-energy": "DOE"}})
        self.assertEqual(reviewed[0].name, "DOE")
        self.assertEqual(reviewed[0].entity_id, "people:doe")

    def test_merge_chains_resolve_to_final_target(self) -> None:
        mention = self.make_mention("James Clapper")
        review = {
            "merges": {
                "people:james-clapper": {
                    "sourceId": "people:james-clapper",
                    "sourceName": "James Clapper",
                    "sourceCategory": "people",
                    "targetId": "people:general-clapper",
                    "targetName": "General Clapper",
                    "targetCategory": "people",
                },
                "people:general-clapper": {
                    "sourceId": "people:general-clapper",
                    "sourceName": "General Clapper",
                    "sourceCategory": "people",
                    "targetId": "people:jim-clapper",
                    "targetName": "Jim Clapper",
                    "targetCategory": "people",
                },
            },
            "nameMerges": {
                "james clapper": {
                    "sourceId": "people:james-clapper",
                    "sourceName": "James Clapper",
                    "sourceCategory": "people",
                    "targetId": "people:general-clapper",
                    "targetName": "General Clapper",
                    "targetCategory": "people",
                },
                "general clapper": {
                    "sourceId": "people:general-clapper",
                    "sourceName": "General Clapper",
                    "sourceCategory": "people",
                    "targetId": "people:jim-clapper",
                    "targetName": "Jim Clapper",
                    "targetCategory": "people",
                },
            },
        }
        reviewed = build_graph.apply_review_to_mentions([mention], review)
        self.assertEqual(reviewed[0].name, "Jim Clapper")
        self.assertEqual(reviewed[0].entity_id, "people:jim-clapper")

    def test_merge_chains_do_not_prefer_shorter_intermediate_names(self) -> None:
        mention = self.make_mention("Harry Reid", "politicians")
        review = {
            "nameMerges": {
                "harry reid": {
                    "sourceId": "politicians:harry-reid",
                    "sourceName": "Harry Reid",
                    "sourceCategory": "politicians",
                    "targetId": "politicians:as-reid",
                    "targetName": "As Reid",
                    "targetCategory": "politicians",
                },
                "as reid": {
                    "sourceId": "politicians:as-reid",
                    "sourceName": "As Reid",
                    "sourceCategory": "politicians",
                    "targetId": "politicians:senator-harry-reid",
                    "targetName": "Senator Harry Reid",
                    "targetCategory": "politicians",
                },
            },
        }
        reviewed = build_graph.apply_review_to_mentions([mention], review)
        self.assertEqual(reviewed[0].name, "Senator Harry Reid")
        self.assertEqual(reviewed[0].entity_id, "politicians:senator-harry-reid")

    def test_name_reclassifications_match_normalized_names(self) -> None:
        mention = self.make_mention("UFO of GOD: The Extraordinary True Story of Chris Bledsoe", "people")
        review = {
            "nameReclassifications": {
                "ufo of god: the extraordinary true story of chris bledsoe": "books",
            },
        }
        reviewed = build_graph.apply_review_to_mentions([mention], review)
        self.assertEqual(reviewed[0].category, "books")
        self.assertEqual(reviewed[0].entity_id, "books:ufo-of-god-the-extraordinary-true-story-of-chris-bledsoe")

    def test_merge_target_reclass_survives_display_alias(self) -> None:
        mention = self.make_mention("Las Vegas", "people")
        review = {
            "nameReclassifications": {
                "las vegas strip": "locations",
            },
            "aliases": {
                "las vegas strip": "Las Vegas",
            },
            "nameMerges": {
                "las vegas": {
                    "sourceId": "people:las-vegas",
                    "sourceName": "Las Vegas",
                    "sourceCategory": "people",
                    "targetId": "people:las-vegas-strip",
                    "targetName": "Las Vegas Strip",
                    "targetCategory": "people",
                },
            },
        }
        reviewed = build_graph.apply_review_to_mentions([mention], review)
        self.assertEqual(reviewed[0].name, "Las Vegas")
        self.assertEqual(reviewed[0].category, "locations")
        self.assertEqual(reviewed[0].entity_id, "locations:las-vegas")

    def test_manual_relationships_resolve_reviewed_endpoint_ids(self) -> None:
        def entity(entity_id: str, name: str, category: str) -> build_graph.Entity:
            return build_graph.Entity(
                id=entity_id,
                name=name,
                canonical_name=build_graph.canonicalize(name, category),
                category=category,
                category_label=build_graph.label(category),
            )

        entities = [
            entity("politicians:secretary-of-state-hillary-clinton", "Secretary of State Hillary Clinton", "politicians"),
            entity("politicians:presidents-bill-clinton", "Presidents Bill Clinton", "politicians"),
        ]
        review = {
            "aliases": {
                "politicians:state-hillary-clinton": "Secretary of State Hillary Clinton",
                "people:when-bill-clinton": "Presidents Bill Clinton",
            },
            "nameReclassifications": {
                "presidents bill clinton": "politicians",
            },
            "nameMerges": {
                "hillary clinton": {
                    "sourceId": "people:hillary-clinton",
                    "sourceName": "Hillary Clinton",
                    "sourceCategory": "people",
                    "targetId": "politicians:state-hillary-clinton",
                    "targetName": "State Hillary Clinton",
                    "targetCategory": "politicians",
                },
            },
            "manualRelationships": {
                "people:hillary-clinton--people:when-bill-clinton": {
                    "sourceId": "people:hillary-clinton",
                    "sourceName": "Hillary Clinton",
                    "sourceCategory": "people",
                    "targetId": "people:when-bill-clinton",
                    "targetName": "Presidents Bill Clinton",
                    "targetCategory": "politicians",
                },
            },
        }
        relationships = build_graph.apply_manual_relationships([], entities, build_graph.normalize_review(review))
        self.assertEqual(len(relationships), 1)
        self.assertEqual(relationships[0].source, "politicians:presidents-bill-clinton")
        self.assertEqual(relationships[0].target, "politicians:secretary-of-state-hillary-clinton")

    def test_merge_cycles_prefer_reviewed_non_person_target(self) -> None:
        mention = self.make_mention("Top Secret Operation Paperclip")
        review = {
            "nameReclassifications": {
                "operation paperclip": "government_project_codenames",
            },
            "nameMerges": {
                "top secret operation paperclip": {
                    "sourceId": "people:top-secret-operation-paperclip",
                    "sourceName": "Top Secret Operation Paperclip",
                    "sourceCategory": "people",
                    "targetId": "government_project_codenames:operation-paperclip",
                    "targetName": "Operation Paperclip",
                    "targetCategory": "government_project_codenames",
                },
                "operation paperclip": {
                    "sourceId": "journalists:operation-paperclip",
                    "sourceName": "Operation Paperclip",
                    "sourceCategory": "government_project_codenames",
                    "targetId": "people:top-secret-operation-paperclip",
                    "targetName": "Top Secret Operation Paperclip",
                    "targetCategory": "people",
                },
            },
        }
        reviewed = build_graph.apply_review_to_mentions([mention], review)
        self.assertEqual(reviewed[0].name, "Operation Paperclip")
        self.assertEqual(reviewed[0].category, "government_project_codenames")
        self.assertEqual(reviewed[0].entity_id, "government_project_codenames:operation-paperclip")

    def test_merge_cycles_do_not_fall_back_to_shortest_source_name(self) -> None:
        mention = self.make_mention("Air Force", "government_agencies")
        review = {
            "nameMerges": {
                "air force": {
                    "sourceId": "government_agencies:air-force",
                    "sourceName": "Air Force",
                    "sourceCategory": "government_agencies",
                    "targetId": "government_agencies:u-s-air-force",
                    "targetName": "U.S. Air Force",
                    "targetCategory": "government_agencies",
                },
                "u s air force": {
                    "sourceId": "government_agencies:u-s-air-force",
                    "sourceName": "U.S. Air Force",
                    "sourceCategory": "government_agencies",
                    "targetId": "government_agencies:united-states-air-force",
                    "targetName": "United States Air Force",
                    "targetCategory": "government_agencies",
                },
                "united states air force": {
                    "sourceId": "government_agencies:united-states-air-force",
                    "sourceName": "United States Air Force",
                    "sourceCategory": "government_agencies",
                    "targetId": "government_agencies:u-s-air-force",
                    "targetName": "U.S. Air Force",
                    "targetCategory": "government_agencies",
                },
            },
        }
        reviewed = build_graph.apply_review_to_mentions([mention], review)
        self.assertEqual(reviewed[0].name, "U.S. Air Force")
        self.assertEqual(reviewed[0].entity_id, "government_agencies:u-s-air-force")

        reverse = self.make_mention("United States Air Force", "government_agencies")
        reviewed_reverse = build_graph.apply_review_to_mentions([reverse], review)
        self.assertEqual(reviewed_reverse[0].name, "U.S. Air Force")
        self.assertEqual(reviewed_reverse[0].entity_id, "government_agencies:u-s-air-force")

    def test_name_merges_prefer_aliased_canonical_names(self) -> None:
        mention = self.make_mention("Diana Pasolka", "experiencers")
        review = {
            "aliases": {
                "experiencers:diana-pasolka": "Diana Pasulka",
                "diana pasolka": "Diana Pasulka",
            },
            "nameMerges": {
                "diana pasulka": {
                    "sourceId": "professors:diana-pasulka",
                    "sourceName": "Diana Pasulka",
                    "sourceCategory": "professors",
                    "targetId": "people:diana-pasolka",
                    "targetName": "Diana Pasolka",
                    "targetCategory": "people",
                }
            },
        }
        reviewed = build_graph.apply_review_to_mentions([mention], review)
        self.assertEqual(reviewed[0].name, "Diana Pasulka")
        self.assertEqual(reviewed[0].category, "people")
        self.assertEqual(reviewed[0].entity_id, "people:diana-pasulka")

    def test_person_heuristic_skips_us_service_fragments(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="The U.S. Army and U.S. Navy reviewed the U.S. Air Force report.",
        )
        names = {item["name"] for item in build_graph.person_mentions(segment, set())}
        self.assertNotIn("S. Army", names)
        self.assertNotIn("S. Navy", names)
        self.assertNotIn("S. Air Force", names)

    def test_person_heuristic_skips_single_word_title_fragments(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text=(
                "The Western range security analysis covered The Aliens, "
                "The Flying secret project truth video."
            ),
        )
        people_like = {
            item["name"].lower()
            for item in build_graph.person_mentions(segment, set())
            if item["category"] in build_graph.PERSON_LIKE_CATEGORIES
        }
        for name in {"western", "national", "range", "security", "analysis", "aliens", "flying", "secret", "project", "truth", "video"}:
            self.assertNotIn(name, people_like)

    def test_organization_shaped_names_do_not_become_people(self) -> None:
        segment = build_graph.Segment(
            id="s-1",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
            text="New York Times covered Battelle Memorial Institute and Intelligence Officers in the report.",
        )
        categories = {item["name"]: item["category"] for item in build_graph.person_mentions(segment, set())}
        self.assertEqual(categories["New York Times"], "newsrooms")
        self.assertEqual(categories["Battelle Memorial Institute"], "institutes")
        self.assertEqual(categories["Intelligence Officers"], "government_agencies")

        committee_segment = build_graph.Segment(
            id="s-2",
            transcript_id="t-1",
            transcript_title="Sample",
            source_file="sample.txt",
            start_ms=0,
            end_ms=1000,
        text="The National Advisory Committee and Robertson Panel reviewed the records.",
        )
        committee_categories = {item["name"]: item["category"] for item in build_graph.person_mentions(committee_segment, set())}
        self.assertEqual(committee_categories["National Advisory Committee"], "government_agencies")
        self.assertEqual(committee_categories["Robertson Panel"], "government_agencies")


if __name__ == "__main__":
    unittest.main()
