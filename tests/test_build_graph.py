from __future__ import annotations

import json
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
            text="The National Advisory Committee reviewed the records.",
        )
        committee_categories = {item["name"]: item["category"] for item in build_graph.person_mentions(committee_segment, set())}
        self.assertEqual(committee_categories["National Advisory Committee"], "government_agencies")


if __name__ == "__main__":
    unittest.main()
