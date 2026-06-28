#!/usr/bin/env python3
"""
Build a reproducible transcript intelligence report.

This pipeline prioritizes structured data, transcript evidence, reclassification
rules, and graph exports. It uses only the Python standard library so it can run
immediately in this repository.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PROJECT_ID = "relationship-graph"
RELATIONSHIP_WINDOW_RADIUS = 4
RELATIONSHIP_WINDOW_MENTION_LIMIT = 30
RELATIONSHIP_OUTPUT_LIMIT = 8000
DATA_DIR = ROOT / "data"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
REGISTRY_PATH = TRANSCRIPTS_DIR / "entity-registry.json"
RECLASS_INPUT = DATA_DIR / "reclass.json"
LEGACY_ROOT_RECLASS_INPUT = ROOT / "reclass.json"
LEGACY_REVIEW_INPUT = DATA_DIR / "review-decisions.json"
DATA_REVIEW_INPUT = DATA_DIR / "review-decisions.json"
LEGACY_ROOT_REVIEW_INPUT = ROOT / "review-decisions.json"
REPORT_RECLASS_INPUT = ROOT / "report" / "data" / "reclass.json"
REPORT_REVIEW_INPUT = ROOT / "report" / "data" / "review-decisions.json"
LEGACY_V2_REVIEW_INPUT = ROOT / "report-v2" / "review-decisions.json"
LEGACY_V2_DATA_REVIEW_INPUT = ROOT / "report-v2" / "data" / "review-decisions.json"
DATA_EXPORT_INPUT = DATA_DIR / "relationship-graph-data.json"
LEGACY_DATA_EXPORT_INPUTS = [
    DATA_DIR / "uap-relationship-graph-data.json",
    ROOT / "uap-relationship-graph-data.json",
    DATA_DIR / "transcript-intelligence-v2.json",
    ROOT / "transcript-intelligence-v2.json",
]

SOURCE_EXTENSIONS = [".tsv", ".srt", ".vtt", ".json", ".txt"]
PREFERRED_EXTENSIONS = [".tsv", ".srt", ".vtt", ".json", ".txt"]
NON_TRANSCRIPT_FILES = {
    "entity-registry.json",
    "generate-report.js",
    "build_report_v2.py",
    "reclass.json",
    "review-decisions.json",
    "transcript-intelligence-v2.json",
    "uap-relationship-graph-data.json",
    "relationship-graph-data.json",
    "README.md",
    "README_V2.md",
}

CATEGORY_LABELS = {
    "research_groups": "Active research groups",
    "patents": "Patents",
    "white_papers": "White papers",
    "books": "Books",
    "authors": "Authors",
    "journalists": "Journalists",
    "newsrooms": "Newsrooms",
    "frequencies": "Frequencies",
    "locations": "Locations",
    "people": "People",
    "experiencers": "Experiencers",
    "government_project_codenames": "Government project codenames",
    "military_bases": "Military bases",
    "professors": "Professors",
    "universities": "Universities",
    "university_departments": "Departments at Universities",
    "government_agencies": "Government agencies",
    "contractors": "Contractors",
    "document_names": "Document names",
    "whistleblowers": "Whistleblowers",
    "companies": "Companies",
    "politicians": "Politicians",
    "tv_shows": "TV shows",
    "movies": "Hollywood-produced movies",
    "directors": "Directors",
    "producers": "Producers",
    "blood_types": "Blood types",
    "medical_conditions": "Medical conditions",
    "dates_times": "Dates and times",
    "dumbs": "DUMBs (Deep Underground Military Bases)",
    "events": "Events",
    "hoaxers": "Hoaxers",
    "confirmed_hoaxes": "Confirmed hoaxes",
    "key_terms": "Key terms",
    "websites": "Websites",
    "technology": "Technology",
    "chemicals": "Chemicals",
    "chemical_elements": "Chemical elements",
    "materials": "Materials",
    "stars": "Stars",
    "planets": "Planets",
    "constellations": "Constellations",
    "star_systems": "Star systems",
    "galaxies": "Galaxies",
    "theories": "Theories",
    "gps_coordinates": "GPS coordinates",
    "ip_addresses": "IP addresses",
    "financiers": "Financiers",
    "symbols": "Symbols",
    "religious_texts": "Religious texts",
    "emerging_terminology": "Emerging terminology",
    "taxonomies": "Taxonomies",
    "secret_societies": "Secret societies",
    "leaks": "Leaks",
    "watchdog_groups": "Watchdog groups",
    "nonprofits": "Nonprofits",
    "institutes": "Institutes",
    "dangerous_people": "Dangerous people",
    "friendly_people": "Friendly people",
    "likely_spies": "Likely spies",
    "alien_species": "Alien species",
    "radio_frequencies": "Radio frequencies",
}

TOP_CATEGORY_LABELS = {
    "people": "People",
    "news_media": "News Media",
    "institutions_programs": "Institutions & Programs",
    "places": "Places",
    "documents_media": "Documents & Media",
    "events_claims": "Events & Claims",
    "science_technology": "Science & Technology",
    "signals": "Signals",
    "terms_references": "Terms & References",
    "needs_review": "Needs Review",
}

CATEGORY_TO_TOP = {
    "people": "people",
    "whistleblowers": "people",
    "experiencers": "people",
    "professors": "people",
    "journalists": "news_media",
    "newsrooms": "news_media",
    "politicians": "people",
    "directors": "people",
    "producers": "people",
    "authors": "people",
    "hoaxers": "people",
    "dangerous_people": "people",
    "friendly_people": "people",
    "likely_spies": "people",
    "government_agencies": "institutions_programs",
    "contractors": "institutions_programs",
    "companies": "institutions_programs",
    "nonprofits": "institutions_programs",
    "watchdog_groups": "institutions_programs",
    "secret_societies": "institutions_programs",
    "institutes": "institutions_programs",
    "research_groups": "institutions_programs",
    "universities": "institutions_programs",
    "university_departments": "institutions_programs",
    "government_project_codenames": "institutions_programs",
    "financiers": "institutions_programs",
    "locations": "places",
    "military_bases": "places",
    "dumbs": "places",
    "document_names": "documents_media",
    "patents": "documents_media",
    "white_papers": "documents_media",
    "books": "documents_media",
    "leaks": "documents_media",
    "tv_shows": "documents_media",
    "movies": "documents_media",
    "religious_texts": "documents_media",
    "events": "events_claims",
    "dates_times": "events_claims",
    "confirmed_hoaxes": "events_claims",
    "theories": "events_claims",
    "emerging_terminology": "events_claims",
    "taxonomies": "events_claims",
    "technology": "science_technology",
    "chemicals": "science_technology",
    "chemical_elements": "science_technology",
    "materials": "science_technology",
    "medical_conditions": "science_technology",
    "blood_types": "science_technology",
    "stars": "science_technology",
    "planets": "science_technology",
    "constellations": "science_technology",
    "star_systems": "science_technology",
    "galaxies": "science_technology",
    "alien_species": "science_technology",
    "frequencies": "signals",
    "radio_frequencies": "signals",
    "gps_coordinates": "signals",
    "ip_addresses": "signals",
    "key_terms": "terms_references",
    "symbols": "terms_references",
    "websites": "terms_references",
}

DEFAULT_TERMS = {
    "research_groups": [
        "Advanced Aerospace Threat Identification Program",
        "AATIP",
        "Advanced Aerospace Weapon System Applications Program",
        "AAWSAP",
        "All-domain Anomaly Resolution Office",
        "AARO",
        "Galileo Project",
        "Scientific Coalition for UAP Studies",
        "MUFON",
        "National Institute for Discovery Science",
    ],
    "government_agencies": [
        "CIA",
        "Central Intelligence Agency",
        "NSA",
        "National Security Agency",
        "NASA",
        "DIA",
        "Defense Intelligence Agency",
        "DoD",
        "Department of Defense",
        "DOE",
        "Department of Energy",
        "FBI",
        "DARPA",
        "NRO",
        "NGA",
        "Pentagon",
        "ODNI",
        "U.S. Army",
        "US Army",
        "United States Army",
        "U.S. Navy",
        "US Navy",
        "United States Navy",
        "U.S. Air Force",
        "US Air Force",
        "United States Air Force",
        "Air Force Research Laboratory",
        "Air Force Research Lab",
        "Army Futures Command",
        "Army Corps of Engineers",
    ],
    "government_project_codenames": [
        "Project Blue Book",
        "Project Sign",
        "Project Grudge",
        "Project Mogul",
        "Project Stargate",
        "MKUltra",
        "MK Ultra",
        "Kona Blue",
        "Immaculate Constellation",
        "Zodiac",
        "Sentient",
        "Operation Paperclip",
        "Operation Highjump",
    ],
    "military_bases": [
        "Area 51",
        "S-4",
        "S4",
        "Groom Lake",
        "Papoose Lake",
        "Dulce Base",
        "Wright-Patterson Air Force Base",
        "Nellis Air Force Base",
        "Kirtland Air Force Base",
        "Eglin Air Force Base",
        "Vandenberg",
    ],
    "contractors": [
        "Lockheed Martin",
        "Skunk Works",
        "EG&G",
        "Battelle",
        "Raytheon",
        "Northrop Grumman",
        "Boeing",
        "BAASS",
        "Bigelow Aerospace",
        "Hughes Aircraft",
    ],
    "universities": [
        "MIT",
        "Massachusetts Institute of Technology",
        "Harvard",
        "Stanford",
        "Caltech",
        "University of Virginia",
        "University of Arizona",
        "University of Texas",
        "UCLA",
        "Berkeley",
        "Cornell",
        "Stanford University",
    ],
    "university_departments": [
        "Department of Physics",
        "Physics Department",
        "Department of Electrical Engineering",
        "Department of Materials Science",
        "Department of Aerospace Engineering",
        "Department of Psychology",
    ],
    "whistleblowers": [
        "Bob Lazar",
        "Robert Lazar",
        "David Grusch",
        "Luis Elizondo",
        "Lue Elizondo",
        "Ryan Graves",
        "David Fravor",
        "Alex Dietrich",
        "Kevin Day",
        "Gary Voorhis",
        "Karl Nell",
        "Michael Herrera",
        "Jason Sands",
        "Robert Salas",
        "Edward Snowden",
        "Chelsea Manning",
        "Daniel Ellsberg",
    ],
    "journalists": [
        "George Knapp",
        "Jeremy Corbell",
        "Leslie Kean",
        "Ralph Blumenthal",
        "Ross Coulthart",
        "James Fox",
        "Michael Shellenberger",
        "Steven Greenstreet",
        "Christopher Sharp",
        "Tim McMillan",
    ],
    "newsrooms": [
        "The Wall Street Journal",
        "Wall Street Journal",
        "The New York Times",
        "New York Times",
        "The Washington Post",
        "Washington Post",
        "Reuters",
        "Associated Press",
        "AP News",
        "Al Jazeera",
        "Russia Today",
        "CNN",
        "Fox News",
        "NewsNation",
        "Politico",
        "The Debrief",
        "Liberation Times",
        "Daily Mail",
        "The Guardian",
        "BBC",
    ],
    "professors": [
        "Eric Weinstein",
        "Garry Nolan",
        "Avi Loeb",
        "Hal Puthoff",
        "Jacques Vallee",
        "Jacques Vallée",
        "Diana Pasulka",
        "Jim Segala",
    ],
    "politicians": [
        "Tim Burchett",
        "Anna Paulina Luna",
        "Marco Rubio",
        "Kirsten Gillibrand",
        "Harry Reid",
        "Chuck Schumer",
        "Mike Rounds",
    ],
    "document_names": [
        "Wilson-Davis memo",
        "UAP Disclosure Act",
        "Schumer amendment",
        "Nimitz report",
        "Tic Tac report",
        "Condon Report",
        "Cometa Report",
        "Majestic 12",
        "MJ-12",
    ],
    "books": [
        "The Day After Roswell",
        "Communion",
        "The Hunt for Zero Point",
        "Skinwalkers at the Pentagon",
        "Imminent",
        "The 37th Parallel",
        "Passport to Magonia",
        "The New Science of UFOs",
        "The Shadow of Time",
    ],
    "locations": [
        "Nevada",
        "Los Alamos",
        "Dulce",
        "Roswell",
        "New Mexico",
        "Utah",
        "Skinwalker Ranch",
        "Florida",
        "California",
        "Afghanistan",
        "Peru",
        "Brazil",
        "Russia",
        "China",
        "Antarctica",
        "Las Vegas",
        "Washington",
        "Capitol Hill",
    ],
    "medical_conditions": [
        "cancer",
        "radiation burns",
        "autoimmune",
        "bursitis",
        "dysbiosis",
        "PTSD",
        "memory loss",
        "radiation sickness",
    ],
    "materials": [
        "graphene",
        "bismuth",
        "magnesium",
        "zinc",
        "aluminum",
        "metamaterial",
        "isotope",
        "aerogel",
    ],
    "chemicals": [
        "DMT",
        "N,N-Dimethyltryptamine",
        "Dimethyltryptamine",
    ],
    "technology": [
        "anti-gravity",
        "antigravity",
        "gravity control",
        "zero point energy",
        "field propulsion",
        "inertial mass reduction",
        "warp drive",
        "reactionless drive",
        "electrogravitics",
        "magnetohydrodynamics",
        "MHD",
        "directed energy",
        "laser weapon",
        "sensor fusion",
        "radar spoofing",
        "stealth technology",
        "microchip technology",
        "semiconductor technology",
        "reverse engineering",
    ],
    "chemical_elements": [
        "hydrogen",
        "helium",
        "lithium",
        "carbon",
        "oxygen",
        "silicon",
        "iron",
        "copper",
        "zinc",
        "bismuth",
        "magnesium",
        "aluminum",
        "element 115",
        "moscovium",
    ],
    "key_terms": [
        "non-human intelligence",
        "NHI",
        "crash retrieval",
        "reverse engineering",
        "metamaterials",
        "antigravity",
        "consciousness",
        "noetics",
        "remote viewing",
        "zero point energy",
    ],
    "theories": [
        "interdimensional hypothesis",
        "extraterrestrial hypothesis",
        "ultraterrestrial hypothesis",
        "simulation hypothesis",
        "holographic universe",
        "many worlds",
        "time travel",
        "noetics",
    ],
    "star_systems": ["Zeta Reticuli", "Alpha Centauri", "Sirius", "Pleiades", "Orion"],
    "stars": ["Sirius", "Vega", "Betelgeuse", "Arcturus", "Proxima Centauri"],
    "planets": ["Mars", "Venus", "Jupiter", "Saturn", "Mercury", "Neptune"],
    "constellations": ["Orion", "Pleiades", "Ursa Major", "Cygnus", "Draco"],
    "galaxies": ["Milky Way", "Andromeda"],
    "alien_species": ["Grey", "Greys", "Reptilian", "Nordic", "Tall Whites", "Mantid"],
    "secret_societies": ["Illuminati", "Freemasons", "Bilderberg", "Bohemian Grove"],
    "leaks": ["WikiLeaks", "Snowden leaks", "Panama Papers"],
    "nonprofits": ["Doctors Without Borders", "MUFON", "SCU"],
    "institutes": ["Institute of Noetic Sciences", "National Institute for Discovery Science"],
}

PATTERN_CATEGORIES = {
    "websites",
    "ip_addresses",
    "gps_coordinates",
    "radio_frequencies",
    "frequencies",
    "dates_times",
    "blood_types",
    "patents",
}

URL_RE = re.compile(r"\b(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s)]*)?", re.I)
IP_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
GPS_RE = re.compile(r"\b[-+]?(?:[1-8]?\d(?:\.\d+)?|90(?:\.0+)?),\s*[-+]?(?:(?:1[0-7]\d|\d?\d)(?:\.\d+)?|180(?:\.0+)?)\b")
FREQ_RE = re.compile(
    r"\b\d{1,5}(?:\.\d{1,4})?\s?(?:Hz|kHz|MHz|GHz|THz|hertz|kilohertz|megahertz|gigahertz|terahertz)\b",
    re.I,
)
FREQ_RANGE_RE = re.compile(
    r"\b\d{1,5}(?:\.\d{1,4})?\s*(?:to|-|–)\s*\d{1,5}(?:\.\d{1,4})?\s*"
    r"(?:Hz|kHz|MHz|GHz|THz|hertz|kilohertz|megahertz|gigahertz|terahertz)\b",
    re.I,
)
FREQ_BAND_RE = re.compile(
    r"\b(?:(?:extremely|extra|very|ultra)\s+low\s+frequency|very\s+high\s+frequency|ultra\s+high\s+frequency|"
    r"(?:ELF|SLF|ULF|VLF|LF|MF|HF|VHF|UHF|SHF|EHF)\s+(?:frequency|frequencies|band|signal|wave|waves))\b",
    re.I,
)
RADIO_TERM_RE = re.compile(r"\b(?:radio frequenc(?:y|ies)|VHF radio|UHF radio|CB radio|guard frequency)\b", re.I)
RADIO_RE = re.compile(r"\b(?:1[3-7]\d|4[0-9]\d|8[0-9]\d)\.\d{3,4}\b")
DATE_RE = re.compile(
    r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},?\s+\d{2,4}|"
    r"\d{1,2}:\d{2}(?:\s?[ap]\.?m\.?)?)\b",
    re.I,
)
BLOOD_RE = re.compile(r"\b(?:A|B|AB|O)[+-]\b")
PATENT_RE = re.compile(r"\b(?:US\s*)?(?:Patent|patent)\s*(?:No\.?\s*)?(?:\d{4,}[A-Z0-9-]*)?\b", re.I)
PERSON_RE = re.compile(r"\b(?:Dr\.|Mr\.|Ms\.|Sen\.|Rep\.)?\s*(?:[A-Z][a-z]+|[A-Z]\.)\s+(?:[A-Z][a-z]+|[A-Z]\.)(?:\s+(?:[A-Z][a-z]+|[A-Z]\.)){0,2}\b")
MALFORMED_SERVICE_FRAGMENT_RE = re.compile(r"^S\.\s+(?:Army|Navy|Air\s+Force|Airforce|Aircraft)$", re.I)
MILITARY_BASE_NAME_RE = re.compile(r"\b(?:Air\s+Force|Army|Naval|Navy)\s+Base\b", re.I)
MILITARY_ORG_NAME_RE = re.compile(r"\b(?:Army|Navy|Air\s+Force|Marine\s+Corps|Coast\s+Guard)\b", re.I)
MILITARY_PERSON_ROLE_RE = re.compile(r"\b(?:Admiral|Brigadier|Captain|Chief|Colonel|General|Lieutenant|Minister|Sergeant)\b", re.I)
NEWSROOM_NAME_RE = re.compile(
    r"\b(?:Journal|Times|Post|News|Network|Press|Reuters|Associated\s+Press|BBC|CNN|Guardian|Jazeera|Politico|Debrief|Mail)\b",
    re.I,
)
INSTITUTE_NAME_RE = re.compile(r"\b(?:Institute|Institutes)\b", re.I)
UNIVERSITY_NAME_RE = re.compile(r"\b(?:University|College|School)\b", re.I)
RESEARCH_ORG_NAME_RE = re.compile(r"\b(?:Laboratory|Laboratories|Labs?|Research\s+Center|Research\s+Institute)\b", re.I)
GOVERNMENT_ORG_NAME_RE = re.compile(
    r"\b(?:Department|Agency|Administration|Bureau|Office|Ministry|Command|Secretary|Forest\s+Service|Geological\s+Service|"
    r"Health\s+Service|Selective\s+Service|Strategic\s+Services|Technical\s+Services)\b",
    re.I,
)
COMPANY_ORG_NAME_RE = re.compile(r"\b(?:Corporation|Company|Companies|Inc\.?|LLC|Ltd\.?|Limited|Aerospace|Aircraft|Technologies|Systems)\b", re.I)
GOVERNMENT_ROLE_GROUP_RE = re.compile(r"\b(?:Officers|Officials|Agents|Postal\s+Service|Secret\s+Service)\b", re.I)
RESEARCH_ROLE_GROUP_RE = re.compile(r"\b(?:Scientists|Researchers|Technicians|Engineers)\b", re.I)
GENERAL_ORG_NAME_RE = re.compile(r"\b(?:Service|Services|Division|Center|Centre|Staff)\b", re.I)
NON_PERSON_TOP_CATEGORIES = {
    "companies",
    "contractors",
    "government_agencies",
    "institutes",
    "newsrooms",
    "research_groups",
    "universities",
}
PERSON_LIKE_CATEGORIES = {
    "people",
    "whistleblowers",
    "experiencers",
    "professors",
    "journalists",
    "politicians",
    "directors",
    "producers",
    "authors",
    "hoaxers",
    "dangerous_people",
    "friendly_people",
    "likely_spies",
}

PERSON_STOPWORDS = {
    "United States",
    "New Mexico",
    "Las Vegas",
    "Los Alamos",
    "Capitol Hill",
    "American Alchemy",
    "American Alchemists",
    "Air Force",
    "All Rights",
    "National Security",
    "Department Defense",
    "New Science",
    "You Tube",
    "Thank You",
    "Wall Street Journal",
    "The Wall Street Journal",
    "New York Times",
    "The New York Times",
    "Washington Post",
    "The Washington Post",
    "Associated Press",
    "AP News",
    "Al Jazeera",
    "Russia Today",
    "Fox News",
    "Daily Mail",
    "The Guardian",
    "The Debrief",
    "Liberation Times",
}

CLASSIFY_HINTS = {
    "whistleblowers": ["whistleblower", "came forward", "testified", "claims", "revealed", "former official", "former intelligence"],
    "journalists": ["journalist", "reporter", "investigative", "wrote about", "interviewed by"],
    "professors": ["professor", "physicist", "scientist", "researcher", "university", "dr."],
    "politicians": ["senator", "representative", "congress", "committee", "amendment"],
    "experiencers": ["abducted", "experience", "encounter", "taken", "witness", "saw a light"],
    "likely_spies": ["spy", "asset", "agent", "intelligence officer", "case officer", "station"],
    "dangerous_people": ["dangerous", "threat", "killed", "murder", "violent"],
    "friendly_people": ["helped", "trusted", "friendly", "ally", "supportive"],
}

RELATION_RULES = [
    (("people", "government_agencies"), "affiliated_with"),
    (("whistleblowers", "government_agencies"), "formerly_inside"),
    (("people", "universities"), "associated_with"),
    (("professors", "universities"), "teaches_or_researches_at"),
    (("government_agencies", "government_project_codenames"), "operates_or_oversees"),
    (("contractors", "government_agencies"), "contracts_with"),
    (("document_names", "people"), "mentions_or_authored_by"),
    (("journalists", "newsrooms"), "reports_for_or_published_by"),
    (("military_bases", "locations"), "located_near"),
]


@dataclass
class Segment:
    id: str
    transcript_id: str
    transcript_title: str
    source_file: str
    start_ms: int
    end_ms: int
    text: str


@dataclass
class Mention:
    id: str
    entity_id: str
    name: str
    category: str
    category_label: str
    segment_id: str
    transcript_id: str
    transcript_title: str
    source_file: str
    start_ms: int
    timestamp: str
    excerpt: str
    detector: str
    confidence: float
    reason: str


@dataclass
class Entity:
    id: str
    name: str
    canonical_name: str
    category: str
    category_label: str
    count: int = 0
    confidence: float = 0.0
    transcripts: list[str] = field(default_factory=list)
    significance: str = ""
    detectors: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class Relationship:
    id: str
    source: str
    target: str
    source_name: str
    target_name: str
    type: str
    weight: int
    evidence_segment_ids: list[str]
    evidence: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0


def main() -> None:
    review = read_review_input()
    registry = read_registry()
    sources = select_transcript_sources()
    segments = load_segments(sources)
    dictionaries, omit_terms = build_dictionaries(registry)
    mentions = resolve_competing_mentions(extract_mentions(segments, dictionaries, omit_terms))
    mentions = apply_review_to_mentions(mentions, review)
    entities = build_entities(mentions)
    relationships = build_relationships(segments, mentions, entities, review)
    graph = build_graph(entities, relationships)
    manifest = build_manifest(sources, segments, mentions, entities, relationships, review)
    write_report(segments, mentions, entities, relationships, graph, manifest, review)
    print("Generated index.html")
    print(
        f"Indexed {len(sources)} transcript sources, {len(segments)} segments, "
        f"{len(entities)} entities, {len(mentions)} mentions, {len(relationships)} relationships."
    )


def read_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"categories": {}, "omit": []}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def read_review_input() -> dict[str, Any]:
    for path in (
        RECLASS_INPUT,
        LEGACY_ROOT_RECLASS_INPUT,
        LEGACY_REVIEW_INPUT,
        DATA_REVIEW_INPUT,
        LEGACY_ROOT_REVIEW_INPUT,
        REPORT_RECLASS_INPUT,
        REPORT_REVIEW_INPUT,
        LEGACY_V2_DATA_REVIEW_INPUT,
        LEGACY_V2_REVIEW_INPUT,
    ):
        if not path.exists():
            continue
        try:
            review = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"reclassifications": {}, "nameReclassifications": {}, "falsePositives": {}, "omissions": {}, "aliases": {}, "merges": {}, "nameMerges": {}}
        normalize_review(review)
        add_name_reclassifications_from_ids(review)
        persist_generated_review(path, review)
        review["source_path"] = str(path.relative_to(ROOT))
        return review
    review = read_review_from_data_export()
    persist_generated_review(Path(), review)
    return review


def normalize_review(review: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "reclassifications",
        "nameReclassifications",
        "falsePositives",
        "removedFalsePositives",
        "omissions",
        "aliases",
        "merges",
        "nameMerges",
        "removedMerges",
        "removedNameMerges",
        "removedManualRelationships",
        "manualRelationships",
    ):
        if not isinstance(review.get(key), dict):
            review[key] = {}
    normalize_manual_relationships(review)
    apply_review_removals(review)
    return review


def apply_review_removals(review: dict[str, Any]) -> None:
    for entity_id in review.get("removedFalsePositives", {}):
        review.get("falsePositives", {}).pop(entity_id, None)
    for source_id in review.get("removedMerges", {}):
        review.get("merges", {}).pop(source_id, None)
    for source_name in review.get("removedNameMerges", {}):
        review.get("nameMerges", {}).pop(source_name, None)
    for relationship_id in review.get("removedManualRelationships", {}):
        review.get("manualRelationships", {}).pop(relationship_id, None)


def canonical_manual_relationship_key(source_id: str, target_id: str) -> str:
    return "--".join(sorted([source_id, target_id]))


def normalize_manual_relationships(review: dict[str, Any]) -> None:
    normalized: dict[str, Any] = {}
    for key, item in sorted((review.get("manualRelationships") or {}).items()):
        if not isinstance(item, dict):
            continue
        source_id = item.get("sourceId")
        target_id = item.get("targetId")
        if not source_id or not target_id or source_id == target_id:
            continue
        canonical_key = canonical_manual_relationship_key(str(source_id), str(target_id))
        normalized[canonical_key] = item
    review["manualRelationships"] = normalized

    normalized_removed: dict[str, Any] = {}
    for key, item in sorted((review.get("removedManualRelationships") or {}).items()):
        if isinstance(item, dict) and item.get("sourceId") and item.get("targetId"):
            normalized_removed[canonical_manual_relationship_key(str(item["sourceId"]), str(item["targetId"]))] = item
        elif key:
            normalized_removed[str(key)] = item
    review["removedManualRelationships"] = normalized_removed


def export_review(review: dict[str, Any]) -> dict[str, Any]:
    exported = normalize_review(dict(review))
    exported.pop("source_path", None)
    return exported


def persist_generated_review(path: Path, review: dict[str, Any]) -> None:
    if path == RECLASS_INPUT:
        return
    persisted = export_review(review)
    RECLASS_INPUT.write_text(json.dumps(persisted, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def add_name_reclassifications_from_ids(review: dict[str, Any]) -> None:
    name_reclassifications = review.setdefault("nameReclassifications", {})
    for entity_id, category in review.get("reclassifications", {}).items():
        if not category or category not in CATEGORY_LABELS or ":" not in entity_id:
            continue
        slug = entity_id.split(":", 1)[1]
        name_reclassifications.setdefault(normalize_name(slug.replace("-", " ")), category)


def read_review_from_data_export() -> dict[str, Any]:
    review = {
        "reclassifications": {},
        "nameReclassifications": {},
        "falsePositives": {},
        "removedFalsePositives": {},
        "omissions": {},
        "aliases": {},
        "merges": {},
        "nameMerges": {},
        "removedMerges": {},
        "removedNameMerges": {},
        "removedManualRelationships": {},
        "manualRelationships": {},
    }
    export_path = next((path for path in [DATA_EXPORT_INPUT, *LEGACY_DATA_EXPORT_INPUTS] if path.exists()), None)
    if not export_path:
        return review
    try:
        exported = json.loads(export_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return review
    for entity in exported.get("entities", []):
        entity_id = entity.get("id")
        category = entity.get("category")
        if not entity_id or not category or ":" not in entity_id:
            continue
        original_category = entity_id.split(":", 1)[0]
        if original_category != category and category in CATEGORY_LABELS:
            review["reclassifications"][entity_id] = category
            review["nameReclassifications"][normalize_name(entity.get("name", ""))] = category
    if review["reclassifications"]:
        review["note"] = f"Derived from {export_path.relative_to(ROOT)} because no reclass.json was present."
    return normalize_review(review)


def select_transcript_sources() -> list[Path]:
    candidates: dict[str, list[Path]] = defaultdict(list)
    if not TRANSCRIPTS_DIR.exists():
        return []
    for path in TRANSCRIPTS_DIR.iterdir():
        if path.is_dir() or path.name.startswith("."):
            continue
        if path.name in NON_TRANSCRIPT_FILES:
            continue
        if path.suffix.lower() in SOURCE_EXTENSIONS:
            candidates[path.stem].append(path)

    selected = []
    order = {ext: i for i, ext in enumerate(PREFERRED_EXTENSIONS)}
    for _, paths in sorted(candidates.items()):
        selected.append(sorted(paths, key=lambda p: order.get(p.suffix.lower(), 99))[0])
    return selected


def load_segments(paths: list[Path]) -> list[Segment]:
    segments: list[Segment] = []
    for path in paths:
        rows = parse_source(path)
        transcript_id = slugify(path.stem)
        title = titleize(path.stem)
        for index, row in enumerate(rows):
            text = clean_text(row["text"])
            if not text:
                continue
            segment_id = f"seg-{transcript_id}-{index:05d}"
            segments.append(
                Segment(
                    id=segment_id,
                    transcript_id=transcript_id,
                    transcript_title=title,
                    source_file=path.name,
                    start_ms=int(row.get("start_ms", 0)),
                    end_ms=int(row.get("end_ms", row.get("start_ms", 0))),
                    text=text,
                )
            )
    return segments


def parse_source(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".tsv":
        return parse_tsv(path)
    if suffix in {".srt", ".vtt"}:
        return parse_subtitles(path)
    if suffix == ".json":
        return parse_json(path)
    return parse_txt(path)


def parse_tsv(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            text = row.get("text") or row.get("Text") or ""
            rows.append(
                {
                    "start_ms": parse_number(row.get("start") or row.get("start_ms") or 0),
                    "end_ms": parse_number(row.get("end") or row.get("end_ms") or 0),
                    "text": text,
                }
            )
    return rows


def parse_subtitles(path: Path) -> list[dict[str, Any]]:
    content = path.read_text(encoding="utf-8", errors="replace").replace("\ufeff", "")
    blocks = re.split(r"\n\s*\n", content.strip())
    rows = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        time_line = next((line for line in lines if "-->" in line), "")
        if not time_line:
            continue
        start_raw, end_raw = [part.strip() for part in time_line.split("-->", 1)]
        text_lines = [line for line in lines if line != time_line and not line.isdigit() and line.upper() != "WEBVTT"]
        rows.append(
            {
                "start_ms": parse_timestamp_ms(start_raw),
                "end_ms": parse_timestamp_ms(end_raw.split()[0]),
                "text": " ".join(text_lines),
            }
        )
    return rows


def parse_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    if isinstance(data, dict) and isinstance(data.get("segments"), list):
        return [
            {
                "start_ms": int(float(row.get("start", 0)) * 1000),
                "end_ms": int(float(row.get("end", 0)) * 1000),
                "text": row.get("text", ""),
            }
            for row in data["segments"]
        ]
    if isinstance(data, dict) and data.get("text"):
        return chunk_plain_text(str(data["text"]))
    if isinstance(data, list):
        return [
            {
                "start_ms": int(float(row.get("start", 0)) * 1000),
                "end_ms": int(float(row.get("end", 0)) * 1000),
                "text": row.get("text", ""),
            }
            for row in data
            if isinstance(row, dict)
        ]
    return []


def parse_txt(path: Path) -> list[dict[str, Any]]:
    return chunk_plain_text(path.read_text(encoding="utf-8", errors="replace"))


def chunk_plain_text(text: str, size: int = 900) -> list[dict[str, Any]]:
    words = clean_text(text).split()
    rows = []
    for index in range(0, len(words), size):
        rows.append({"start_ms": index * 300, "end_ms": (index + size) * 300, "text": " ".join(words[index : index + size])})
    return rows


def build_dictionaries(registry: dict[str, Any]) -> tuple[dict[str, list[str]], set[str]]:
    dictionaries: dict[str, set[str]] = {category: set(values) for category, values in DEFAULT_TERMS.items()}
    for category, values in registry.get("categories", {}).items():
        dictionaries.setdefault(category, set()).update(values)
    for category in CATEGORY_LABELS:
        dictionaries.setdefault(category, set())

    omit_terms = {normalize_name(term) for term in registry.get("omit", [])}
    compiled = {
        category: sorted({term.strip() for term in values if term and term.strip()}, key=lambda value: (-len(value), value.lower()))
        for category, values in dictionaries.items()
    }
    return compiled, omit_terms


def extract_mentions(segments: list[Segment], dictionaries: dict[str, list[str]], omit_terms: set[str]) -> list[Mention]:
    mentions: list[Mention] = []
    seen_mentions: set[tuple[str, str, str]] = set()
    for segment in segments:
        text = segment.text
        lower = text.lower()

        for category, terms in dictionaries.items():
            if category in PATTERN_CATEGORIES:
                continue
            for term in terms:
                normalized = normalize_name(term)
                if normalized in omit_terms:
                    continue
                if term.lower() not in lower:
                    continue
                pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.I)
                for match in pattern.finditer(text):
                    add_mention(
                        mentions,
                        seen_mentions,
                        segment,
                        name=match.group(0),
                        category=category,
                        detector="gazetteer",
                        confidence=0.92,
                        reason=f"Matched curated term in {label(category)}",
                        excerpt=excerpt(text, match.start(), match.end()),
                    )

        for item in pattern_mentions(segment):
            if normalize_name(item["name"]) in omit_terms:
                continue
            add_mention(mentions, seen_mentions, segment, **item)

        for person in person_mentions(segment, omit_terms):
            add_mention(mentions, seen_mentions, segment, **person)

    return mentions


def resolve_competing_mentions(mentions: list[Mention]) -> list[Mention]:
    priority = {
        "whistleblowers": 100,
        "newsrooms": 97,
        "journalists": 96,
        "professors": 94,
        "politicians": 92,
        "experiencers": 90,
        "government_agencies": 88,
        "government_project_codenames": 86,
        "military_bases": 84,
        "contractors": 82,
        "technology": 81,
        "chemicals": 81,
        "document_names": 80,
        "people": 10,
    }
    grouped: dict[tuple[str, str], list[Mention]] = defaultdict(list)
    for mention in mentions:
        grouped[(mention.segment_id, normalize_name(mention.name))].append(mention)

    resolved: list[Mention] = []
    for group in grouped.values():
        if len(group) == 1:
            resolved.extend(group)
            continue
        best_score = max(priority.get(mention.category, 50) for mention in group)
        winners = [mention for mention in group if priority.get(mention.category, 50) == best_score]
        if any(mention.category != "people" for mention in winners):
            winners = [mention for mention in winners if mention.category != "people"]
        resolved.extend(winners)
    resolved.sort(key=lambda mention: int(mention.id.split("-")[-1]))
    for index, mention in enumerate(resolved, start=1):
        mention.id = f"m-{index:07d}"
    return resolved


def pattern_mentions(segment: Segment) -> list[dict[str, Any]]:
    text = segment.text
    items: list[dict[str, Any]] = []
    for category, regex, detector, confidence, reason in [
        ("websites", URL_RE, "regex:url", 0.98, "Matched URL/domain pattern"),
        ("ip_addresses", IP_RE, "regex:ip", 0.99, "Matched IPv4 address pattern"),
        ("gps_coordinates", GPS_RE, "regex:gps", 0.98, "Matched latitude/longitude coordinate pattern"),
        ("frequencies", FREQ_RE, "regex:frequency", 0.96, "Matched frequency with unit"),
        ("frequencies", FREQ_RANGE_RE, "regex:frequency_range", 0.96, "Matched frequency range with unit"),
        ("frequencies", FREQ_BAND_RE, "regex:frequency_band", 0.88, "Matched named frequency band"),
        ("radio_frequencies", RADIO_RE, "regex:radio_frequency", 0.92, "Matched radio-style decimal frequency"),
        ("radio_frequencies", RADIO_TERM_RE, "regex:radio_frequency_term", 0.84, "Matched radio frequency phrase"),
        ("dates_times", DATE_RE, "regex:datetime", 0.86, "Matched date/time expression"),
        ("blood_types", BLOOD_RE, "regex:blood_type", 0.92, "Matched blood type notation"),
        ("patents", PATENT_RE, "regex:patent", 0.72, "Matched patent phrase"),
    ]:
        for match in regex.finditer(text):
            items.append(
                {
                    "name": match.group(0).strip(),
                    "category": category,
                    "detector": detector,
                    "confidence": confidence,
                    "reason": reason,
                    "excerpt": excerpt(text, match.start(), match.end()),
                }
            )

    return items


def person_mentions(segment: Segment, omit_terms: set[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    text = segment.text
    for match in PERSON_RE.finditer(text):
        raw = re.sub(r"^(Dr\.|Mr\.|Ms\.|Sen\.|Rep\.)\s+", "", match.group(0).strip())
        name = re.sub(r"\s+", " ", raw)
        if len(name) < 5 or normalize_name(name) in omit_terms:
            continue
        if MALFORMED_SERVICE_FRAGMENT_RE.match(name):
            continue
        if any(part.lower() in {"the", "and", "but", "you", "this", "that"} for part in name.split()):
            continue
        context = excerpt(text, match.start(), match.end(), width=220)
        military_category = classify_military_organization(name)
        if military_category:
            items.append(
                {
                    "name": name,
                    "category": military_category,
                    "detector": "heuristic:military_organization",
                    "confidence": 0.74,
                    "reason": f"Military organization heuristic matched {label(military_category)} naming",
                    "excerpt": context,
                }
            )
            continue
        organization_category = classify_non_person_name(name)
        if organization_category:
            items.append(
                {
                    "name": name,
                    "category": organization_category,
                    "detector": "heuristic:organization_name",
                    "confidence": 0.66,
                    "reason": f"Organization-name heuristic matched {label(organization_category)} naming",
                    "excerpt": context,
                }
            )
            continue
        if name in PERSON_STOPWORDS:
            continue
        category, reason, confidence = classify_person(context)
        items.append(
            {
                "name": name,
                "category": category,
                "detector": "heuristic:person_name",
                "confidence": confidence,
                "reason": reason,
                "excerpt": context,
            }
        )
    return items


def classify_military_organization(name: str) -> str | None:
    if not MILITARY_ORG_NAME_RE.search(name):
        return None
    if MILITARY_PERSON_ROLE_RE.search(name):
        return None
    lowered = name.lower()
    if MILITARY_BASE_NAME_RE.search(name) or "air force base" in lowered:
        return "military_bases"
    if any(term in lowered for term in ["army", "navy", "air force", "marine corps", "coast guard"]):
        return "government_agencies"
    return None


def classify_non_person_name(name: str) -> str | None:
    if NEWSROOM_NAME_RE.search(name):
        return "newsrooms"
    if UNIVERSITY_NAME_RE.search(name):
        return "universities"
    if RESEARCH_ORG_NAME_RE.search(name):
        return "research_groups"
    if INSTITUTE_NAME_RE.search(name):
        return "institutes"
    if GOVERNMENT_ORG_NAME_RE.search(name):
        return "government_agencies"
    if GOVERNMENT_ROLE_GROUP_RE.search(name):
        return "government_agencies"
    if RESEARCH_ROLE_GROUP_RE.search(name):
        return "research_groups"
    if COMPANY_ORG_NAME_RE.search(name):
        return "companies"
    if GENERAL_ORG_NAME_RE.search(name):
        return "companies"
    return None


def classify_person(context: str) -> tuple[str, str, float]:
    lower = context.lower()
    for category, hints in CLASSIFY_HINTS.items():
        if any(hint in lower for hint in hints):
            return category, f"Person-name heuristic with {label(category)} context", 0.68
    return "people", "Person-name heuristic without stronger role context", 0.54


def add_mention(
    mentions: list[Mention],
    seen_mentions: set[tuple[str, str, str]],
    segment: Segment,
    name: str,
    category: str,
    detector: str,
    confidence: float,
    reason: str,
    excerpt: str,
) -> None:
    canonical = canonicalize(name, category)
    entity_id = entity_key(canonical, category)
    dedupe_key = (segment.id, entity_id, detector)
    if dedupe_key in seen_mentions:
        return
    seen_mentions.add(dedupe_key)
    mention_id = f"m-{len(mentions) + 1:07d}"
    mentions.append(
        Mention(
            id=mention_id,
            entity_id=entity_id,
            name=name.strip(),
            category=category,
            category_label=label(category),
            segment_id=segment.id,
            transcript_id=segment.transcript_id,
            transcript_title=segment.transcript_title,
            source_file=segment.source_file,
            start_ms=segment.start_ms,
            timestamp=format_timestamp(segment.start_ms),
            excerpt=excerpt,
            detector=detector,
            confidence=round(confidence, 3),
            reason=reason,
        )
    )


def review_alias_for(entity_id: str, name: str, aliases_by_id: dict[str, Any], aliases_by_name: dict[str, Any]) -> str | None:
    alias = aliases_by_id.get(entity_id) or aliases_by_name.get(normalize_name(name))
    if isinstance(alias, str) and alias.strip():
        return alias.strip()
    return None


def review_merge_for(entity_id: str, name: str, merges: dict[str, Any], name_merges: dict[str, Any]) -> dict[str, Any] | None:
    merge = name_merges.get(normalize_name(name)) or merges.get(entity_id)
    if isinstance(merge, dict) and merge.get("targetName"):
        return merge
    return None


def reviewed_category_for_name(name: str, category: str, name_reclassifications: dict[str, Any]) -> str:
    target_category = name_reclassifications.get(normalize_name(name), category)
    if target_category not in CATEGORY_LABELS:
        target_category = category
    if target_category in PERSON_LIKE_CATEGORIES:
        target_category = classify_non_person_name(name) or target_category
    return target_category


def resolve_review_merge_chain(
    entity_id: str,
    name: str,
    category: str,
    merges: dict[str, Any],
    name_merges: dict[str, Any],
    aliases_by_id: dict[str, Any],
    aliases_by_name: dict[str, Any],
    name_reclassifications: dict[str, Any],
) -> tuple[str, str, str]:
    current_id = entity_id
    current_name = name
    current_category = category
    seen: set[tuple[str, str, str]] = set()

    for _ in range(24):
        state = (current_id, normalize_name(current_name), current_category)
        if state in seen:
            break
        seen.add(state)
        merge = review_merge_for(current_id, current_name, merges, name_merges)
        if not merge:
            break

        next_name = clean_text(str(merge["targetName"]))
        next_category = merge.get("targetCategory") if merge.get("targetCategory") in CATEGORY_LABELS else current_category
        target_id = str(merge.get("targetId") or "")
        next_alias = review_alias_for(target_id, next_name, aliases_by_id, aliases_by_name)
        if next_alias:
            next_name = next_alias
        next_category = reviewed_category_for_name(next_name, next_category, name_reclassifications)
        next_id = entity_key(canonicalize(next_name, next_category), next_category)
        next_state = (next_id, normalize_name(next_name), next_category)
        if next_state == state:
            break

        current_id = next_id
        current_name = next_name
        current_category = next_category

    return current_name, current_category, current_id


def apply_review_to_mentions(mentions: list[Mention], review: dict[str, Any]) -> list[Mention]:
    false_positives = review.get("falsePositives", {})
    false_ids = set(false_positives.keys())
    false_names = {
        normalize_name(value.get("name", ""))
        for value in false_positives.values()
        if isinstance(value, dict) and value.get("name")
    }
    omission_names = {normalize_name(name) for name in review.get("omissions", {}).keys()}
    reclassifications = review.get("reclassifications", {})
    name_reclassifications = review.get("nameReclassifications", {})
    raw_aliases = review.get("aliases", {})
    aliases_by_id = {key: value for key, value in raw_aliases.items() if ":" in key}
    aliases_by_name = {normalize_name(key): value for key, value in raw_aliases.items() if ":" not in key}
    merges = review.get("merges", {})
    name_merges = {normalize_name(key): value for key, value in review.get("nameMerges", {}).items()}

    reviewed: list[Mention] = []
    for mention in mentions:
        mention_name = normalize_name(mention.name)
        if mention.entity_id in false_ids or mention_name in false_names or mention_name in omission_names:
            continue

        alias = review_alias_for(mention.entity_id, mention.name, aliases_by_id, aliases_by_name)
        if alias:
            mention.name = alias
            mention.entity_id = entity_key(canonicalize(alias, mention.category), mention.category)
            mention_name = normalize_name(mention.name)

        merged_name, merged_category, merged_id = resolve_review_merge_chain(
            mention.entity_id,
            mention.name,
            mention.category,
            merges,
            name_merges,
            aliases_by_id,
            aliases_by_name,
            name_reclassifications,
        )
        if merged_id != mention.entity_id or merged_name != mention.name or merged_category != mention.category:
            mention.name = merged_name
            mention.category = merged_category
            mention.category_label = label(merged_category)
            mention.entity_id = merged_id
            reviewed.append(mention)
            continue

        target_category = reclassifications.get(mention.entity_id) or name_reclassifications.get(mention_name)
        if target_category:
            target_category = reviewed_category_for_name(mention.name, target_category, name_reclassifications)
            mention.category = target_category
            mention.category_label = label(mention.category)
            mention.entity_id = entity_key(canonicalize(mention.name, mention.category), mention.category)
        alias = review_alias_for(mention.entity_id, mention.name, aliases_by_id, aliases_by_name)
        if alias:
            mention.name = alias
            mention.entity_id = entity_key(canonicalize(alias, mention.category), mention.category)
        reviewed.append(mention)
    return reviewed


def build_entities(mentions: list[Mention]) -> list[Entity]:
    grouped: dict[str, list[Mention]] = defaultdict(list)
    for mention in mentions:
        grouped[mention.entity_id].append(mention)

    entities: list[Entity] = []
    for entity_id, group in grouped.items():
        first = group[0]
        name = most_common([m.name for m in group])
        transcripts = sorted({m.transcript_title for m in group})
        detectors = sorted({m.detector for m in group})
        avg_conf = sum(m.confidence for m in group) / len(group)
        top_evidence = sorted(group, key=lambda m: (-m.confidence, m.transcript_title, m.start_ms))[:8]
        entities.append(
            Entity(
                id=entity_id,
                name=name,
                canonical_name=canonicalize(name, first.category),
                category=first.category,
                category_label=first.category_label,
                count=len(group),
                confidence=round(avg_conf, 3),
                transcripts=transcripts,
                significance=significance_sentence(name, first.category, len(group), transcripts, detectors),
                detectors=detectors,
                evidence_ids=[m.id for m in top_evidence],
            )
        )
    entities.sort(key=lambda e: (-e.count, e.category_label, e.name.lower()))
    return entities


def build_relationships(segments: list[Segment], mentions: list[Mention], entities: list[Entity], review: dict[str, Any]) -> list[Relationship]:
    entity_by_id = {entity.id: entity for entity in entities}
    mentions_by_segment: dict[str, list[Mention]] = defaultdict(list)
    for mention in mentions:
        mentions_by_segment[mention.segment_id].append(mention)

    segments_by_transcript: dict[str, list[Segment]] = defaultdict(list)
    for segment in segments:
        segments_by_transcript[segment.transcript_id].append(segment)
    for transcript_segments in segments_by_transcript.values():
        transcript_segments.sort(key=lambda segment: (segment.start_ms, segment.id))

    pair_weights: Counter[tuple[str, str, str]] = Counter()
    pair_evidence: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    pair_confidence: dict[tuple[str, str, str], list[float]] = defaultdict(list)

    for transcript_segments in segments_by_transcript.values():
        for index, center_segment in enumerate(transcript_segments):
            window_segments = transcript_segments[
                max(0, index - RELATIONSHIP_WINDOW_RADIUS) : min(len(transcript_segments), index + RELATIONSHIP_WINDOW_RADIUS + 1)
            ]
            window_mentions = dedupe_mentions_for_segment(
                [
                    mention
                    for segment in window_segments
                    for mention in mentions_by_segment.get(segment.id, [])
                ]
            )
            if len(window_mentions) < 2:
                continue
            window_mentions = sorted(window_mentions, key=lambda m: (-m.confidence, m.name))[:RELATIONSHIP_WINDOW_MENTION_LIMIT]
            window_text = " ".join(segment.text for segment in window_segments)
            window_start = window_segments[0].start_ms
            window_timestamp = format_timestamp(window_start)
            evidence_text = clean_text(window_text[:900])

            for i, a in enumerate(window_mentions):
                for b in window_mentions[i + 1 :]:
                    if a.entity_id == b.entity_id:
                        continue
                    source, target = sorted([a.entity_id, b.entity_id])
                    source_entity = entity_by_id.get(source)
                    target_entity = entity_by_id.get(target)
                    if not source_entity or not target_entity:
                        continue
                    if normalize_name(source_entity.name) == normalize_name(target_entity.name):
                        continue
                    rel_type, rel_confidence, rel_reason = infer_relationship_from_context(
                        source_entity,
                        target_entity,
                        window_text,
                    )
                    key = (source, target, rel_type)
                    pair_weights[key] += 2 if rel_type != "co_mentioned" else 1
                    pair_confidence[key].append(rel_confidence)
                    if len(pair_evidence[key]) < 8:
                        pair_evidence[key][center_segment.id] = {
                            "segment_id": center_segment.id,
                            "transcript": center_segment.transcript_title,
                            "timestamp": window_timestamp,
                            "excerpt": evidence_text,
                            "reason": rel_reason,
                            "relationship_type": rel_type,
                        }

    relationships = []
    for index, ((source, target, rel_type), weight) in enumerate(
        sorted(pair_weights.items(), key=lambda item: (-item[1], item[0]))
    ):
        source_entity = entity_by_id[source]
        target_entity = entity_by_id[target]
        evidence = list(pair_evidence[(source, target, rel_type)].values())[:6]
        relationships.append(
            Relationship(
                id=f"rel-{index + 1:06d}",
                source=source,
                target=target,
                source_name=source_entity.name,
                target_name=target_entity.name,
                type=rel_type,
                weight=weight,
                evidence_segment_ids=[item["segment_id"] for item in evidence],
                evidence=evidence,
                confidence=round(sum(pair_confidence[(source, target, rel_type)]) / max(1, len(pair_confidence[(source, target, rel_type)])), 3),
            )
        )
    return apply_manual_relationships(relationships[:RELATIONSHIP_OUTPUT_LIMIT], entities, review)


def apply_manual_relationships(relationships: list[Relationship], entities: list[Entity], review: dict[str, Any]) -> list[Relationship]:
    entity_by_id = {entity.id: entity for entity in entities}
    entities_by_name: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        entities_by_name[normalize_name(entity.name)].append(entity)
    alias_targets = review.get("aliases") or {}
    existing_ids = {relationship.id for relationship in relationships}
    existing_manual_pairs = {
        canonical_manual_relationship_key(relationship.source, relationship.target)
        for relationship in relationships
        if relationship.type == "manual"
    }
    manual_relationships: list[Relationship] = []
    next_index = len(relationships) + 1
    for key, item in sorted((review.get("manualRelationships") or {}).items()):
        if not isinstance(item, dict):
            continue
        source = resolve_manual_entity(item, "source", entity_by_id, entities_by_name, alias_targets)
        target = resolve_manual_entity(item, "target", entity_by_id, entities_by_name, alias_targets)
        if not source or not target or source.id == target.id:
            continue
        canonical_key = canonical_manual_relationship_key(source.id, target.id)
        if canonical_key in existing_manual_pairs:
            continue
        rel_id = f"manual-{slugify(canonical_key)}"
        if rel_id in existing_ids:
            rel_id = f"manual-{next_index:06d}"
        manual_relationships.append(
            Relationship(
                id=rel_id,
                source=min(source.id, target.id),
                target=max(source.id, target.id),
                source_name=entity_by_id[min(source.id, target.id)].name,
                target_name=entity_by_id[max(source.id, target.id)].name,
                type="manual",
                weight=max(50, int(item.get("weight") or 50)),
                evidence_segment_ids=[],
                evidence=[],
                confidence=1.0,
            )
        )
        existing_ids.add(rel_id)
        existing_manual_pairs.add(canonical_key)
        next_index += 1
    if not manual_relationships:
        return relationships[:RELATIONSHIP_OUTPUT_LIMIT]
    return manual_relationships[:RELATIONSHIP_OUTPUT_LIMIT] + relationships[: max(0, RELATIONSHIP_OUTPUT_LIMIT - len(manual_relationships))]


def resolve_manual_entity(
    item: dict[str, Any],
    side: str,
    entity_by_id: dict[str, Entity],
    entities_by_name: dict[str, list[Entity]],
    alias_targets: dict[str, str],
) -> Entity | None:
    entity_id = item.get(f"{side}Id")
    if entity_id and entity_id in entity_by_id:
        return entity_by_id[entity_id]
    names = [str(item.get(f"{side}Name") or "")]
    if entity_id and alias_targets.get(entity_id):
        names.append(str(alias_targets[entity_id]))
    normalized_name = normalize_name(names[0])
    if normalized_name and alias_targets.get(normalized_name):
        names.append(str(alias_targets[normalized_name]))
    category = item.get(f"{side}Category")
    for name_value in names:
        name = normalize_name(name_value)
        if not name:
            continue
        matches = entities_by_name.get(name, [])
        if category:
            category_matches = [entity for entity in matches if entity.category == category]
            if len(category_matches) == 1:
                return category_matches[0]
        if len(matches) == 1:
            return matches[0]
    return None


def infer_relationship_from_context(source: Entity, target: Entity, text: str) -> tuple[str, float, str]:
    lowered = text.lower()
    typed_patterns = [
        ("worked_for", 0.86, ["worked for", "works for", "director of", "chief of", "inside the", "from the agency", "former director"]),
        ("testified_about", 0.84, ["testified", "hearing", "congress", "committee", "under oath"]),
        ("reported_statement", 0.78, ["claimed", "claims", "said", "says", "alleged", "revealed", "told"]),
        ("authored_or_published", 0.82, ["wrote", "authored", "published", "book", "paper", "report", "memo"]),
        ("funded_or_contracts_with", 0.83, ["funded", "funding", "contract", "contractor", "paid by", "backed by"]),
        ("located_at", 0.8, ["located", "based at", "near", "site", "facility", "base", "location"]),
        ("investigated", 0.79, ["investigated", "looked into", "studied", "research", "analyzed"]),
        ("debunked_or_hoaxed", 0.81, ["debunked", "hoax", "fake", "fraud", "fabricated"]),
        ("operates_or_oversees", 0.84, ["operated", "ran", "runs", "managed", "oversaw", "oversees"]),
    ]
    for rel_type, confidence, patterns in typed_patterns:
        if any(pattern in lowered for pattern in patterns):
            return rel_type, confidence, "Relationship language found nearby"

    base_type = infer_relationship_type(source.category, target.category)
    if base_type != "co_mentioned":
        return base_type, 0.7, "Category-pair relationship rule"
    return "co_mentioned", 0.45, "Entities appear in the same local transcript window"


def build_relationships_old(segments: list[Segment], mentions: list[Mention], entities: list[Entity]) -> list[Relationship]:
    entity_by_id = {entity.id: entity for entity in entities}
    mentions_by_segment: dict[str, list[Mention]] = defaultdict(list)
    for mention in mentions:
        mentions_by_segment[mention.segment_id].append(mention)

    pairs: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    for segment in segments:
        segment_mentions = dedupe_mentions_for_segment(mentions_by_segment.get(segment.id, []))
        if len(segment_mentions) < 2:
            continue
        segment_mentions = sorted(segment_mentions, key=lambda m: (-m.confidence, m.name))[:18]
        for i, a in enumerate(segment_mentions):
            for b in segment_mentions[i + 1 :]:
                if a.entity_id == b.entity_id:
                    continue
                source, target = sorted([a.entity_id, b.entity_id])
                rel_type = infer_relationship_type(entity_by_id[source].category, entity_by_id[target].category)
                pairs[(source, target, rel_type)][segment.id] += 1

    relationships = []
    for index, ((source, target, rel_type), segment_counter) in enumerate(
        sorted(pairs.items(), key=lambda item: (-sum(item[1].values()), item[0]))
    ):
        source_entity = entity_by_id[source]
        target_entity = entity_by_id[target]
        relationships.append(
            Relationship(
                id=f"rel-{index + 1:06d}",
                source=source,
                target=target,
                source_name=source_entity.name,
                target_name=target_entity.name,
                type=rel_type,
                weight=sum(segment_counter.values()),
                evidence_segment_ids=[segment_id for segment_id, _ in segment_counter.most_common(6)],
            )
        )
    return relationships[:2500]


def dedupe_mentions_for_segment(mentions: list[Mention]) -> list[Mention]:
    by_entity: dict[str, Mention] = {}
    for mention in mentions:
        existing = by_entity.get(mention.entity_id)
        if not existing or mention.confidence > existing.confidence:
            by_entity[mention.entity_id] = mention
    return list(by_entity.values())


def infer_relationship_type(left_category: str, right_category: str) -> str:
    pair = {left_category, right_category}
    for categories, relation in RELATION_RULES:
        if set(categories) == pair:
            return relation
    return "co_mentioned"


def build_graph(entities: list[Entity], relationships: list[Relationship]) -> dict[str, Any]:
    nodes = [
        {
            "id": entity.id,
            "label": entity.name,
            "category": entity.category,
            "categoryLabel": entity.category_label,
            "count": entity.count,
            "confidence": entity.confidence,
        }
        for entity in entities
    ]
    edges = [
        {
            "id": relationship.id,
            "source": relationship.source,
            "target": relationship.target,
            "type": relationship.type,
            "weight": relationship.weight,
        }
        for relationship in relationships
    ]
    return {"nodes": nodes, "edges": edges}


def build_manifest(
    sources: list[Path],
    segments: list[Segment],
    mentions: list[Mention],
    entities: list[Entity],
    relationships: list[Relationship],
    review: dict[str, Any],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": PROJECT_ID,
        "reproducibility": {
            "no_openai_api": True,
            "source_extensions": SOURCE_EXTENSIONS,
            "preferred_extensions": PREFERRED_EXTENSIONS,
            "review_input_applied": bool(
                review.get("source_path")
                or review.get("reclassifications")
                or review.get("nameReclassifications")
                or review.get("falsePositives")
                or review.get("removedFalsePositives")
                or review.get("omissions")
                or review.get("aliases")
                or review.get("merges")
                or review.get("nameMerges")
                or review.get("removedMerges")
                or review.get("removedNameMerges")
                or review.get("removedManualRelationships")
                or review.get("manualRelationships")
            ),
            "transcript_source_dir": str(TRANSCRIPTS_DIR.relative_to(ROOT)),
            "relationship_window_radius": RELATIONSHIP_WINDOW_RADIUS,
            "relationship_window_mentions": RELATIONSHIP_WINDOW_MENTION_LIMIT,
            "relationship_output_limit": RELATIONSHIP_OUTPUT_LIMIT,
            "review_source": review.get("source_path") or (str(DATA_EXPORT_INPUT.relative_to(ROOT)) if DATA_EXPORT_INPUT.exists() and review.get("reclassifications") else None),
            "note": "Generated graph files are overwritten on each rebuild. Long-term reclassification decisions live in data/reclass.json.",
        },
        "counts": {
            "transcripts": len(sources),
            "segments": len(segments),
            "mentions": len(mentions),
            "entities": len(entities),
            "relationships": len(relationships),
            "categories": len({entity.category for entity in entities}),
        },
        "input_hashes": {path.name: sha256(path) for path in sources},
        "registry_hash": sha256(REGISTRY_PATH) if REGISTRY_PATH.exists() else None,
        "pipeline_hash": sha256(Path(__file__)),
        "review_counts": {
            "reclassifications": len(review.get("reclassifications", {})),
            "name_reclassifications": len(review.get("nameReclassifications", {})),
            "false_positives": len(review.get("falsePositives", {})),
            "removed_false_positives": len(review.get("removedFalsePositives", {})),
            "omissions": len(review.get("omissions", {})),
            "aliases": len(review.get("aliases", {})),
            "merges": len(review.get("merges", {})),
            "name_merges": len(review.get("nameMerges", {})),
            "removed_merges": len(review.get("removedMerges", {})),
            "removed_name_merges": len(review.get("removedNameMerges", {})),
            "removed_manual_relationships": len(review.get("removedManualRelationships", {})),
            "manual_relationships": len(review.get("manualRelationships", {})),
        },
    }


def write_report(
    segments: list[Segment],
    mentions: list[Mention],
    entities: list[Entity],
    relationships: list[Relationship],
    graph: dict[str, Any],
    manifest: dict[str, Any],
    review: dict[str, Any],
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for stale_name in ("review-template.json", "review-decisions.json"):
        stale_path = DATA_DIR / stale_name
        if stale_path.exists():
            stale_path.unlink()

    write_json(DATA_DIR / "segments.json", [asdict(segment) for segment in segments])
    write_json(DATA_DIR / "mentions.json", [asdict(mention) for mention in mentions])
    write_json(DATA_DIR / "entities.json", [asdict(entity) for entity in entities])
    write_json(DATA_DIR / "relationships.json", [asdict(relationship) for relationship in relationships])
    write_json(DATA_DIR / "graph.json", graph)
    write_json(DATA_DIR / "manifest.json", manifest)
    write_json(DATA_DIR / "reclass.json", export_review(review))
    write_json(
        DATA_DIR / "reclass-template.json",
        {
            "reclassifications": {},
            "falsePositives": {},
            "removedFalsePositives": {},
            "omissions": {},
            "aliases": {},
            "merges": {},
            "nameMerges": {},
            "removedMerges": {},
            "removedNameMerges": {},
            "removedManualRelationships": {},
            "manualRelationships": {},
            "notes": "Download reclassified data from the app, replace data/reclass.json with it, then rerun python3 build_graph.py.",
        },
    )

    app_core_payload = {
        "manifest": manifest,
        "entities": [asdict(entity) for entity in entities],
        "mentions": [],
        "relationships": [],
        "segments": [],
        "graph": graph,
        "reclassDecisions": export_review(review),
        "reviewDecisions": export_review(review),
        "categoryLabels": CATEGORY_LABELS,
        "topCategoryLabels": TOP_CATEGORY_LABELS,
        "categoryToTop": CATEGORY_TO_TOP,
    }
    app_mentions_json = json.dumps([asdict(mention) for mention in mentions], ensure_ascii=False)
    app_relationships_json = json.dumps([asdict(relationship) for relationship in relationships], ensure_ascii=False)
    app_core_json = json.dumps(app_core_payload, ensure_ascii=False)
    app_payload_version = hashlib.sha256(
        (app_core_json + app_mentions_json + app_relationships_json).encode("utf-8")
    ).hexdigest()[:16]
    (ROOT / "app-data.js").write_text(
        "window.TRANSCRIPT_INTELLIGENCE_DATA = " + app_core_json + ";\n",
        encoding="utf-8",
    )
    (ROOT / "app-data-mentions.js").write_text(
        "window.TRANSCRIPT_INTELLIGENCE_DATA.mentions = " + app_mentions_json + ";\n",
        encoding="utf-8",
    )
    (ROOT / "app-data-relationships.js").write_text(
        "window.TRANSCRIPT_INTELLIGENCE_DATA.relationships = " + app_relationships_json + ";\n",
        encoding="utf-8",
    )
    (ROOT / "index.html").write_text(render_html(app_payload_version), encoding="utf-8")


def render_html(app_data_version: str = "") -> str:
    app_data_scripts = "\n".join(
        f'    <script src="{name}{f"?v={app_data_version}" if app_data_version else ""}"></script>'
        for name in ("app-data.js", "app-data-mentions.js", "app-data-relationships.js")
    )
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UFO Files Relationship Graph</title>
  <style>
    :root {
      --bg: #f5f6f8;
      --panel: #fff;
      --ink: #171a1f;
      --muted: #657080;
      --line: #d9dee7;
      --accent: #0f766e;
      --warn: #9a3412;
      --chip: #eef6f4;
      --shadow: 0 1px 2px rgba(15, 23, 42, .08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background: var(--bg);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      position: sticky;
      top: 0;
      z-index: 5;
      border-bottom: 1px solid var(--line);
      background: rgba(245, 246, 248, .96);
      backdrop-filter: blur(10px);
    }
    .bar {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      max-width: 1600px;
      margin: 0 auto;
      padding: 12px 16px;
      align-items: center;
    }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
    h2 { margin: 0; font-size: 15px; letter-spacing: 0; }
    h3 { margin: 0 0 6px; font-size: 14px; letter-spacing: 0; }
    .meta { color: var(--muted); font-size: 12px; }
    .toolbar, .row-actions {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    input, select, button, textarea {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }
    input, select, button { height: 34px; padding: 0 10px; }
    input { min-width: 280px; }
    button { cursor: pointer; font-weight: 650; }
    button.primary { border-color: var(--accent); background: var(--accent); color: #fff; }
    main {
      display: grid;
      grid-template-columns: 290px minmax(0, 1fr) 420px;
      gap: 14px;
      max-width: 1600px;
      margin: 0 auto;
      padding: 14px;
    }
    aside, section, .panel, .stat {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }
    aside {
      position: sticky;
      top: 75px;
      height: calc(100vh - 90px);
      overflow: auto;
    }
    .panel { margin-bottom: 12px; overflow: hidden; }
    .panel-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
    }
    .panel-body { padding: 12px; }
    .stats {
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 8px;
      margin-bottom: 12px;
    }
    .stat { padding: 10px 12px; }
    .stat b { display: block; font-size: 18px; }
    .stat span { color: var(--muted); font-size: 12px; }
    .category-button {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      width: 100%;
      min-height: 36px;
      height: auto;
      border: 0;
      border-bottom: 1px solid #edf0f5;
      border-radius: 0;
      background: transparent;
      text-align: left;
      gap: 8px;
    }
    .category-button.active { background: var(--chip); color: var(--accent); }
    .count { color: var(--muted); font-variant-numeric: tabular-nums; }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }
    th, td {
      padding: 9px 10px;
      border-bottom: 1px solid #edf0f5;
      vertical-align: top;
      text-align: left;
    }
    th {
      position: sticky;
      top: 0;
      background: #fbfcfd;
      z-index: 1;
      color: #3f4652;
      font-size: 12px;
    }
    td { overflow-wrap: anywhere; }
    tr.selected { background: #f0fdfa; }
    .entity-name { font-weight: 750; }
    .tag {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 7px;
      border-radius: 999px;
      background: #f1f4f8;
      color: #4b5563;
      font-size: 12px;
      white-space: nowrap;
    }
    .entity-table-wrap {
      max-height: 320px;
      overflow: auto;
    }
    #relationship-map {
      display: block;
      width: 100%;
      height: 600px;
      background: #fbfcfd;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .graph-node, .graph-edge {
      cursor: pointer;
    }
    .map-controls {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }
    .map-controls button.active {
      border-color: var(--accent);
      color: var(--accent);
      background: var(--chip);
    }
    .details {
      display: grid;
      gap: 10px;
    }
    .evidence, .relationship {
      border-top: 1px solid #edf0f5;
      padding-top: 8px;
    }
    .brief-list {
      display: grid;
      gap: 8px;
    }
    .brief-item {
      width: 100%;
      height: auto;
      min-height: 0;
      padding: 10px;
      text-align: left;
      white-space: normal;
      border: 1px solid #edf0f5;
      background: #fff;
    }
    .brief-item strong {
      display: block;
      margin-bottom: 3px;
      color: #111827;
    }
    .brief-section {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid #edf0f5;
    }
    .brief-section:first-child {
      margin-top: 0;
      padding-top: 0;
      border-top: 0;
    }
    .evidence a { color: var(--accent); font-weight: 700; text-decoration: none; }
    .review-controls {
      display: grid;
      gap: 8px;
      margin-top: 0;
      padding-top: 0;
      border-top: 1px solid #edf0f5;
    }
    textarea {
      width: 100%;
      min-height: 70px;
      padding: 8px 10px;
      resize: vertical;
    }
    .empty {
      padding: 18px;
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: #fff;
    }
    @media (max-width: 1100px) {
      .bar, main, .stats { grid-template-columns: 1fr; }
      aside { position: static; height: auto; max-height: 320px; }
      input { min-width: 0; width: 100%; }
      .toolbar { justify-content: start; }
    }
  </style>
</head>
<body>
  <header>
    <div class="bar">
      <div>
        <h1>UFO Files Relationship Graph</h1>
        <div class="meta">Evidence-backed extraction, review labels, and reproducible graph exports. No OpenAI API.</div>
      </div>
      <div class="toolbar">
        <input id="search" type="search" placeholder="Search entity, evidence, source">
        <select id="sort">
          <option value="count">Sort by mentions</option>
          <option value="confidence">Sort by confidence</option>
          <option value="name">Sort by name</option>
        </select>
        <button id="download-review">Download Review</button>
        <button class="primary" id="download-data">Download Data</button>
      </div>
    </div>
  </header>
  <main>
    <aside id="categories"></aside>
    <section>
      <div class="stats">
        <div class="stat"><b id="stat-transcripts"></b><span>transcripts</span></div>
        <div class="stat"><b id="stat-segments"></b><span>segments</span></div>
        <div class="stat"><b id="stat-entities"></b><span>entities</span></div>
        <div class="stat"><b id="stat-mentions"></b><span>mentions</span></div>
        <div class="stat"><b id="stat-relationships"></b><span>relationships</span></div>
      </div>
      <div class="panel">
        <div class="panel-head">
          <div>
            <h2>Relationship Map</h2>
            <div class="meta" id="map-status">Category-level graph</div>
          </div>
          <div class="map-controls">
            <button id="map-categories" class="active">Categories</button>
            <button id="map-selection">Selection</button>
            <button id="map-fit">Fit</button>
          </div>
        </div>
        <div class="panel-body">
          <svg id="relationship-map" role="img" aria-label="Visual relationship map"></svg>
        </div>
      </div>
      <div class="panel">
        <div class="panel-head">
          <h2>Entity Review Table</h2>
          <div class="meta" id="table-status"></div>
        </div>
        <div class="entity-table-wrap">
          <table>
            <thead>
              <tr>
                <th style="width: 31%">Entity</th>
                <th style="width: 22%">Category</th>
                <th style="width: 12%">Mentions</th>
                <th style="width: 12%">Confidence</th>
                <th>Why it matters</th>
              </tr>
            </thead>
            <tbody id="entity-rows"></tbody>
          </table>
        </div>
      </div>
    </section>
    <section class="details">
      <div class="panel">
        <div class="panel-head">
          <h2>Selected Entity</h2>
          <button id="clear-selection">Clear</button>
        </div>
        <div class="panel-body" id="entity-details">
          <div class="empty">Select an entity to inspect evidence and direct relationships.</div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-head">
          <h2>Relationship Brief</h2>
          <div class="meta">Ranked leads</div>
        </div>
        <div class="panel-body" id="relationship-brief">
        </div>
      </div>
    </section>
  </main>
  <script src="app-data.js"></script>
  <script>
    const DATA = window.TRANSCRIPT_INTELLIGENCE_DATA;
    const REVIEW_KEY = "relationship-graph-reclass";
    const PREVIOUS_REVIEW_KEY = "uap-relationship-graph-reclass";
    const LEGACY_REVIEW_KEY = "transcript-intelligence-v2-review";
    let activeCategory = "all";
    let selectedEntityId = null;
    let mapMode = "categories";

    const entitiesById = new Map(DATA.entities.map((entity) => [entity.id, entity]));
    const mentionsById = new Map(DATA.mentions.map((mention) => [mention.id, mention]));
    const segmentsById = new Map(DATA.segments.map((segment) => [segment.id, segment]));
    const relationshipsByEntity = new Map();
    for (const relationship of DATA.relationships) {
      if (!relationshipsByEntity.has(relationship.source)) relationshipsByEntity.set(relationship.source, []);
      if (!relationshipsByEntity.has(relationship.target)) relationshipsByEntity.set(relationship.target, []);
      relationshipsByEntity.get(relationship.source).push(relationship);
      relationshipsByEntity.get(relationship.target).push(relationship);
    }

    document.getElementById("stat-transcripts").textContent = DATA.manifest.counts.transcripts.toLocaleString();
    document.getElementById("stat-segments").textContent = DATA.manifest.counts.segments.toLocaleString();
    document.getElementById("stat-entities").textContent = DATA.manifest.counts.entities.toLocaleString();
    document.getElementById("stat-mentions").textContent = DATA.manifest.counts.mentions.toLocaleString();
    document.getElementById("stat-relationships").textContent = DATA.manifest.counts.relationships.toLocaleString();

    function readReview() {
      try {
        const storedReview = localStorage.getItem(REVIEW_KEY) || localStorage.getItem(PREVIOUS_REVIEW_KEY) || localStorage.getItem(LEGACY_REVIEW_KEY);
        const review = JSON.parse(storedReview || '{"reclassifications":{},"falsePositives":{},"omissions":{},"aliases":{},"merges":{},"nameMerges":{},"notes":{}}');
        review.merges = review.merges || {};
        review.nameMerges = review.nameMerges || {};
        return review;
      } catch {
        return { reclassifications: {}, falsePositives: {}, omissions: {}, aliases: {}, merges: {}, nameMerges: {}, notes: {} };
      }
    }

    function saveReview(review) {
      localStorage.setItem(REVIEW_KEY, JSON.stringify(normalizeReview(review)));
      updateReviewButton();
    }

    function hasReviewDecisions(review) {
      return Boolean(
        Object.keys(review.reclassifications || {}).length ||
        Object.keys(review.nameReclassifications || {}).length ||
        Object.keys(review.falsePositives || {}).length ||
        Object.keys(review.merges || {}).length ||
        Object.keys(review.nameMerges || {}).length
      );
    }

    function updateReviewButton() {
      const button = document.getElementById("download-review");
      if (button) button.hidden = !hasReviewDecisions(readReview());
    }

    function visibleEntities() {
      const review = readReview();
      const falseIds = new Set(Object.keys(review.falsePositives || {}));
      const omitted = new Set(Object.keys(review.omissions || {}).map((name) => name.toLowerCase()));
      const query = document.getElementById("search").value.trim().toLowerCase();
      let rows = DATA.entities.filter((entity) => {
        if (falseIds.has(entity.id) || omitted.has(entity.name.toLowerCase())) return false;
        if (activeCategory !== "all" && entity.category !== activeCategory) return false;
        if (!query) return true;
        const evidence = entity.evidence_ids.map((id) => mentionsById.get(id)?.excerpt || "").join(" ");
        return [entity.name, entity.categoryLabel, entity.significance, evidence, entity.transcripts.join(" ")].join(" ").toLowerCase().includes(query);
      });
      const sort = document.getElementById("sort").value;
      rows.sort((a, b) => {
        if (sort === "name") return a.name.localeCompare(b.name);
        if (sort === "confidence") return b.confidence - a.confidence || b.count - a.count;
        return b.count - a.count || b.confidence - a.confidence || a.name.localeCompare(b.name);
      });
      return rows;
    }

    function renderCategories() {
      const counts = new Map();
      for (const entity of DATA.entities) counts.set(entity.category, (counts.get(entity.category) || 0) + 1);
      const categories = [["all", "All categories", DATA.entities.length]].concat(
        Object.entries(DATA.categoryLabels)
          .filter(([id]) => counts.has(id))
          .sort((a, b) => (counts.get(b[0]) || 0) - (counts.get(a[0]) || 0))
          .map(([id, label]) => [id, label, counts.get(id)])
      );
      document.getElementById("categories").innerHTML = categories.map(([id, label, count]) =>
        '<button class="category-button ' + (activeCategory === id ? 'active' : '') + '" data-category="' + escapeHtml(id) + '">' +
        '<span>' + escapeHtml(label) + '</span><span class="count">' + count.toLocaleString() + '</span></button>'
      ).join("");
      document.querySelectorAll("[data-category]").forEach((button) => {
        button.addEventListener("click", () => {
          activeCategory = button.dataset.category;
          render();
        });
      });
    }

    function renderRows() {
      const rows = visibleEntities();
      document.getElementById("table-status").textContent = rows.length.toLocaleString() + " matching entities";
      document.getElementById("entity-rows").innerHTML = rows.slice(0, 600).map((entity) =>
        '<tr class="' + (selectedEntityId === entity.id ? 'selected' : '') + '" data-entity-id="' + escapeHtml(entity.id) + '">' +
          '<td><div class="entity-name">' + escapeHtml(entity.name) + '</div><div class="meta">' + escapeHtml(entity.transcripts.slice(0, 2).join(" · ")) + '</div></td>' +
          '<td><span class="tag">' + escapeHtml(entity.categoryLabel) + '</span></td>' +
          '<td>' + entity.count.toLocaleString() + '</td>' +
          '<td>' + Math.round(entity.confidence * 100) + '%</td>' +
          '<td>' + escapeHtml(entity.significance) + '</td>' +
        '</tr>'
      ).join("");
      document.querySelectorAll("[data-entity-id]").forEach((row) => {
        row.addEventListener("click", () => {
          selectedEntityId = row.dataset.entityId;
          mapMode = "selection";
          render();
        });
      });
    }

    function renderDetails() {
      const panel = document.getElementById("entity-details");
      if (!selectedEntityId || !entitiesById.has(selectedEntityId)) {
        panel.innerHTML = '<div class="empty">Select an entity to inspect evidence and direct relationships.</div>';
        return;
      }
      const entity = entitiesById.get(selectedEntityId);
      const related = (relationshipsByEntity.get(entity.id) || []).slice().sort((a, b) => b.weight - a.weight);
      const evidence = entity.evidence_ids.map((id) => mentionsById.get(id)).filter(Boolean);
      panel.innerHTML =
        '<h3>' + escapeHtml(entity.name) + '</h3>' +
        '<p><span class="tag">' + escapeHtml(entity.categoryLabel) + '</span> ' + entity.count.toLocaleString() + ' mentions · ' + Math.round(entity.confidence * 100) + '% confidence</p>' +
        '<p>' + escapeHtml(entity.significance) + '</p>' +
        '<div class="review-controls">' +
          '<label>Correct category <select id="review-category">' + Object.entries(DATA.categoryLabels).map(([id, label]) => '<option value="' + escapeHtml(id) + '"' + (id === entity.category ? ' selected' : '') + '>' + escapeHtml(label) + '</option>').join("") + '</select></label>' +
          '<textarea id="review-note" placeholder="Review note"></textarea>' +
          '<div class="row-actions"><button id="save-review">Save Review</button><button id="false-positive">False Positive</button><button id="omit-name">Omit Name</button></div>' +
        '</div>' +
        '<h3>Relationships</h3>' +
        related.slice(0, 30).map((relationship) => {
          const otherId = relationship.source === entity.id ? relationship.target : relationship.source;
          const other = entitiesById.get(otherId);
          return '<div class="relationship"><button data-related="' + escapeHtml(otherId) + '">' + escapeHtml(other ? other.name : otherId) + '</button><div class="meta">' + escapeHtml(relationship.type) + ' · weight ' + relationship.weight + '</div></div>';
        }).join("") +
        '<h3>Evidence</h3>' +
        evidence.map((mention) => {
          const segment = segmentsById.get(mention.segment_id);
          return '<div class="evidence"><div class="meta">' + escapeHtml(mention.transcript_title) + ' · ' + escapeHtml(mention.timestamp) + ' · ' + escapeHtml(mention.detector) + '</div>' +
            '<div>' + escapeHtml(mention.excerpt) + '</div>' +
            '<a href="#' + escapeHtml(mention.segment_id) + '">Segment ' + escapeHtml(segment ? segment.id : mention.segment_id) + '</a></div>';
        }).join("");
      document.getElementById("save-review").addEventListener("click", () => saveEntityReview(entity));
      document.getElementById("false-positive").addEventListener("click", () => markFalsePositive(entity));
      document.getElementById("omit-name").addEventListener("click", () => omitEntityName(entity));
      document.querySelectorAll("[data-related]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedEntityId = button.dataset.related;
          mapMode = "selection";
          render();
        });
      });
    }

    function saveEntityReview(entity) {
      const review = readReview();
      review.reclassifications[entity.id] = document.getElementById("review-category").value;
      review.notes[entity.id] = document.getElementById("review-note").value.trim();
      saveReview(review);
      render();
    }

    function markFalsePositive(entity) {
      const review = readReview();
      review.falsePositives[entity.id] = { name: entity.name, category: entity.category, categoryLabel: entity.categoryLabel };
      saveReview(review);
      selectedEntityId = null;
      render();
    }

    function omitEntityName(entity) {
      const review = readReview();
      review.omissions[entity.name] = { category: entity.category, reason: "Marked as recurring omission in v2 app" };
      saveReview(review);
      selectedEntityId = null;
      render();
    }

    function renderRelationshipMap() {
      document.getElementById("map-categories").classList.toggle("active", mapMode === "categories");
      document.getElementById("map-selection").classList.toggle("active", mapMode === "selection");
      if (mapMode === "selection" && selectedEntityId && entitiesById.has(selectedEntityId)) {
        renderEntityNeighborhoodMap(entitiesById.get(selectedEntityId));
      } else if (activeCategory !== "all" && DATA.categoryLabels[activeCategory]) {
        renderCategoryDrillMap(activeCategory);
      } else {
        renderCategoryRelationshipMap();
      }
    }

    function renderCategoryRelationshipMap() {
      const svg = document.getElementById("relationship-map");
      const width = 980;
      const height = 620;
      const cx = width / 2;
      const cy = height / 2;
      const categoryStats = new Map();
      for (const entity of DATA.entities) {
        const stat = categoryStats.get(entity.category) || { id: entity.category, label: entity.categoryLabel, entities: 0, mentions: 0 };
        stat.entities += 1;
        stat.mentions += entity.count;
        categoryStats.set(entity.category, stat);
      }
      const categories = Array.from(categoryStats.values()).sort((a, b) => b.mentions - a.mentions).slice(0, 34);
      const categorySet = new Set(categories.map((category) => category.id));
      const edgeWeights = new Map();
      for (const relationship of DATA.relationships) {
        const source = entitiesById.get(relationship.source);
        const target = entitiesById.get(relationship.target);
        if (!source || !target || source.category === target.category) continue;
        if (!categorySet.has(source.category) || !categorySet.has(target.category)) continue;
        const key = [source.category, target.category].sort().join("::");
        edgeWeights.set(key, (edgeWeights.get(key) || 0) + relationship.weight);
      }
      const maxMentions = Math.max(1, ...categories.map((category) => category.mentions));
      const maxEdge = Math.max(1, ...edgeWeights.values());
      const nodes = categories.map((category, index) => {
        const angle = (Math.PI * 2 * index) / Math.max(1, categories.length) - Math.PI / 2;
        const radius = index < 10 ? 180 : index < 22 ? 245 : 292;
        return {
          ...category,
          x: cx + Math.cos(angle) * radius,
          y: cy + Math.sin(angle) * radius,
          r: Math.max(18, Math.min(48, 16 + Math.sqrt(category.mentions / maxMentions) * 34)),
        };
      });
      const nodeByCategory = new Map(nodes.map((node) => [node.id, node]));
      const edgeShapes = Array.from(edgeWeights.entries()).sort((a, b) => b[1] - a[1]).slice(0, 80).map(([key, weight]) => {
        const [aId, bId] = key.split("::");
        const a = nodeByCategory.get(aId);
        const b = nodeByCategory.get(bId);
        if (!a || !b) return "";
        return '<line class="graph-edge" data-category-a="' + escapeHtml(aId) + '" data-category-b="' + escapeHtml(bId) + '" x1="' + a.x + '" y1="' + a.y + '" x2="' + b.x + '" y2="' + b.y + '" stroke="#94a3b8" stroke-width="' + (0.8 + (weight / maxEdge) * 7).toFixed(1) + '" opacity=".36"><title>' + escapeHtml(a.label + " ↔ " + b.label + " · weight " + weight) + '</title></line>';
      }).join("");
      const nodeShapes = nodes.map((node) => {
        return '<g class="graph-node" data-map-category="' + escapeHtml(node.id) + '">' +
          '<circle cx="' + node.x + '" cy="' + node.y + '" r="' + node.r + '" fill="#0f766e" opacity=".9"></circle>' +
          '<text x="' + node.x + '" y="' + (node.y + node.r + 17) + '" text-anchor="middle" font-size="12" font-weight="750" fill="#111827">' + escapeHtml(truncate(node.label, 24)) + '</text>' +
          '<text x="' + node.x + '" y="' + (node.y + node.r + 32) + '" text-anchor="middle" font-size="10" fill="#657080">' + node.entities + ' entities · ' + node.mentions + ' mentions</text>' +
        '</g>';
      }).join("");
      svg.setAttribute("viewBox", "0 0 " + width + " " + height);
      svg.innerHTML = edgeShapes + nodeShapes;
      document.getElementById("map-status").textContent = "Category map: click a category to drill into entities";
      svg.querySelectorAll("[data-map-category]").forEach((node) => {
        node.addEventListener("click", () => {
          activeCategory = node.dataset.mapCategory;
          selectedEntityId = null;
          mapMode = "categories";
          render();
        });
      });
      svg.querySelectorAll("[data-category-a]").forEach((edge) => {
        edge.addEventListener("click", () => {
          activeCategory = edge.dataset.categoryA;
          selectedEntityId = null;
          mapMode = "categories";
          render();
        });
      });
    }

    function renderCategoryDrillMap(categoryId) {
      const svg = document.getElementById("relationship-map");
      const categoryLabel = DATA.categoryLabels[categoryId] || categoryId;
      const width = 980;
      const height = 620;
      const cx = width / 2;
      const cy = height / 2;
      const categoryEntities = DATA.entities.filter((entity) => entity.category === categoryId).sort((a, b) => b.count - a.count).slice(0, 58);
      const entitySet = new Set(categoryEntities.map((entity) => entity.id));
      const visibleRelationships = DATA.relationships.filter((relationship) => entitySet.has(relationship.source) || entitySet.has(relationship.target)).slice(0, 180);
      const outsideIds = [];
      for (const relationship of visibleRelationships) {
        const other = entitySet.has(relationship.source) ? relationship.target : relationship.source;
        if (!entitySet.has(other) && !outsideIds.includes(other)) outsideIds.push(other);
        if (outsideIds.length >= 18) break;
      }
      const entities = categoryEntities.concat(outsideIds.map((id) => entitiesById.get(id)).filter(Boolean));
      const maxCount = Math.max(1, ...entities.map((entity) => entity.count));
      const nodes = entities.map((entity, index) => {
        const inCategory = entity.category === categoryId;
        const angle = (Math.PI * 2 * index) / Math.max(1, entities.length) - Math.PI / 2;
        const radius = inCategory ? (index < 16 ? 148 : 238) : 298;
        return {
          entity,
          x: cx + Math.cos(angle) * radius,
          y: cy + Math.sin(angle) * radius,
          r: Math.max(inCategory ? 10 : 8, Math.min(inCategory ? 28 : 18, 8 + Math.sqrt(entity.count / maxCount) * 24)),
          inCategory,
        };
      });
      const nodeById = new Map(nodes.map((node) => [node.entity.id, node]));
      const maxEdge = Math.max(1, ...visibleRelationships.map((relationship) => relationship.weight));
      const edgeShapes = visibleRelationships.map((relationship) => {
        const source = nodeById.get(relationship.source);
        const target = nodeById.get(relationship.target);
        if (!source || !target) return "";
        const cross = source.inCategory !== target.inCategory;
        return '<line x1="' + source.x + '" y1="' + source.y + '" x2="' + target.x + '" y2="' + target.y + '" stroke="' + (cross ? '#0f766e' : '#94a3b8') + '" stroke-width="' + (0.8 + (relationship.weight / maxEdge) * 5.5).toFixed(1) + '" opacity="' + (cross ? '.5' : '.28') + '"></line>';
      }).join("");
      const nodeShapes = nodes.map((node) => {
        return '<g class="graph-node" data-map-entity="' + escapeHtml(node.entity.id) + '">' +
          '<circle cx="' + node.x + '" cy="' + node.y + '" r="' + node.r + '" fill="' + (node.inCategory ? '#0f766e' : '#ffffff') + '" stroke="#0f766e" stroke-width="2" opacity=".94"></circle>' +
          '<text x="' + node.x + '" y="' + (node.y + node.r + 15) + '" text-anchor="middle" font-size="11" font-weight="700" fill="#111827">' + escapeHtml(truncate(node.entity.name, 22)) + '</text>' +
        '</g>';
      }).join("");
      svg.setAttribute("viewBox", "0 0 " + width + " " + height);
      svg.innerHTML = '<circle cx="' + cx + '" cy="' + cy + '" r="72" fill="#eef6f4" stroke="#0f766e" opacity=".75"></circle>' +
        '<text x="' + cx + '" y="' + cy + '" text-anchor="middle" font-size="18" font-weight="800" fill="#0f766e">' + escapeHtml(truncate(categoryLabel, 28)) + '</text>' +
        '<text x="' + cx + '" y="' + (cy + 22) + '" text-anchor="middle" font-size="11" fill="#657080">' + categoryEntities.length + ' top entities</text>' +
        edgeShapes + nodeShapes;
      document.getElementById("map-status").textContent = categoryLabel + ": click an entity to inspect its neighborhood";
      svg.querySelectorAll("[data-map-entity]").forEach((node) => {
        node.addEventListener("click", () => {
          selectedEntityId = node.dataset.mapEntity;
          mapMode = "selection";
          render();
        });
      });
    }

    function renderEntityNeighborhoodMap(entity) {
      const svg = document.getElementById("relationship-map");
      const relationships = (relationshipsByEntity.get(entity.id) || []).slice().sort((a, b) => b.weight - a.weight).slice(0, 36);
      const width = 980;
      const height = 620;
      const cx = width / 2;
      const cy = height / 2;
      const maxWeight = Math.max(1, ...relationships.map((relationship) => relationship.weight));
      const nodes = relationships.map((relationship, index) => {
        const otherId = relationship.source === entity.id ? relationship.target : relationship.source;
        const other = entitiesById.get(otherId);
        const angle = (Math.PI * 2 * index) / Math.max(1, relationships.length) - Math.PI / 2;
        const radius = index < 14 ? 175 : 268;
        return { relationship, otherId, other, x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius };
      });
      const edgeShapes = nodes.map((node) => '<line x1="' + cx + '" y1="' + cy + '" x2="' + node.x + '" y2="' + node.y + '" stroke="#94a3b8" stroke-width="' + (1 + (node.relationship.weight / maxWeight) * 7).toFixed(1) + '" opacity=".58"></line>').join("");
      const nodeShapes = nodes.map((node) => {
        const label = node.other ? node.other.name : node.otherId;
        const category = node.other ? node.other.categoryLabel : "Entity";
        return '<g class="graph-node" data-map-entity="' + escapeHtml(node.otherId) + '">' +
          '<circle cx="' + node.x + '" cy="' + node.y + '" r="18" fill="#ffffff" stroke="#0f766e" stroke-width="2"></circle>' +
          '<text x="' + node.x + '" y="' + (node.y + 34) + '" text-anchor="middle" font-size="11" font-weight="700" fill="#111827">' + escapeHtml(truncate(label, 22)) + '</text>' +
          '<text x="' + node.x + '" y="' + (node.y + 49) + '" text-anchor="middle" font-size="9" fill="#657080">' + escapeHtml(truncate(category, 26)) + '</text>' +
        '</g>';
      }).join("");
      svg.setAttribute("viewBox", "0 0 " + width + " " + height);
      svg.innerHTML = edgeShapes +
        '<circle cx="' + cx + '" cy="' + cy + '" r="38" fill="#0f766e"></circle>' +
        '<text x="' + cx + '" y="' + (cy + 58) + '" text-anchor="middle" font-size="15" font-weight="800" fill="#111827">' + escapeHtml(truncate(entity.name, 36)) + '</text>' +
        '<text x="' + cx + '" y="' + (cy + 76) + '" text-anchor="middle" font-size="11" fill="#657080">' + escapeHtml(entity.categoryLabel) + ' · ' + relationships.length + ' direct links</text>' +
        nodeShapes;
      document.getElementById("map-status").textContent = entity.name + ": direct relationship neighborhood";
      svg.querySelectorAll("[data-map-entity]").forEach((node) => {
        node.addEventListener("click", () => {
          selectedEntityId = node.dataset.mapEntity;
          mapMode = "selection";
          render();
        });
      });
    }

    function renderRelationshipBrief() {
      const panel = document.getElementById("relationship-brief");
      const typed = DATA.relationships
        .filter((relationship) => relationship.type !== "co_mentioned")
        .slice()
        .sort((a, b) => b.weight - a.weight)
        .slice(0, 10);
      const strongest = DATA.relationships
        .slice()
        .sort((a, b) => b.weight - a.weight)
        .slice(0, 10);
      const hubScores = new Map();
      for (const relationship of DATA.relationships) {
        hubScores.set(relationship.source, (hubScores.get(relationship.source) || 0) + relationship.weight);
        hubScores.set(relationship.target, (hubScores.get(relationship.target) || 0) + relationship.weight);
      }
      const hubs = Array.from(hubScores.entries())
        .map(([id, score]) => ({ entity: entitiesById.get(id), score }))
        .filter((item) => item.entity)
        .sort((a, b) => b.score - a.score)
        .slice(0, 10);

      panel.innerHTML =
        '<div class="brief-section"><h3>Start here: strongest pairs</h3><div class="brief-list">' +
        strongest.map(relationshipBriefButton).join("") +
        '</div></div>' +
        '<div class="brief-section"><h3>Typed relationship leads</h3><div class="brief-list">' +
        (typed.length ? typed.map(relationshipBriefButton).join("") : '<div class="empty">No typed relationships ranked above co-mentions yet.</div>') +
        '</div></div>' +
        '<div class="brief-section"><h3>Most connected entities</h3><div class="brief-list">' +
        hubs.map((item) => '<button class="brief-item" data-brief-entity="' + escapeHtml(item.entity.id) + '"><strong>' + escapeHtml(item.entity.name) + '</strong><span class="meta">' + escapeHtml(item.entity.categoryLabel) + ' · relationship weight ' + item.score.toLocaleString() + ' · ' + item.entity.count.toLocaleString() + ' mentions</span></button>').join("") +
        '</div></div>';

      panel.querySelectorAll("[data-brief-entity]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedEntityId = button.dataset.briefEntity;
          mapMode = "selection";
          render();
        });
      });
      panel.querySelectorAll("[data-brief-relationship]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedEntityId = button.dataset.source;
          mapMode = "selection";
          render();
        });
      });
    }

    function relationshipBriefButton(relationship) {
      const source = entitiesById.get(relationship.source);
      const target = entitiesById.get(relationship.target);
      if (!source || !target) return "";
      return '<button class="brief-item" data-brief-relationship="' + escapeHtml(relationship.id) + '" data-source="' + escapeHtml(source.id) + '">' +
        '<strong>' + escapeHtml(source.name) + ' ↔ ' + escapeHtml(target.name) + '</strong>' +
        '<span class="meta">' + escapeHtml(relationship.type) + ' · weight ' + relationship.weight.toLocaleString() + ' · ' + escapeHtml(source.categoryLabel) + ' / ' + escapeHtml(target.categoryLabel) + '</span></button>';
    }

    function download(filename, payload) {
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    }

    function render() {
      renderCategories();
      renderRows();
      renderDetails();
      renderRelationshipMap();
      renderRelationshipBrief();
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
    }

    function truncate(value, length) {
      const text = String(value);
      return text.length > length ? text.slice(0, length - 1) + "…" : text;
    }

    document.getElementById("search").addEventListener("input", render);
    document.getElementById("sort").addEventListener("change", render);
    document.getElementById("clear-selection").addEventListener("click", () => {
      selectedEntityId = null;
      mapMode = "categories";
      render();
    });
    document.getElementById("map-categories").addEventListener("click", () => {
      activeCategory = "all";
      selectedEntityId = null;
      mapMode = "categories";
      render();
    });
    document.getElementById("map-selection").addEventListener("click", () => {
      mapMode = "selection";
      render();
    });
    document.getElementById("map-fit").addEventListener("click", () => {
      renderRelationshipMap();
    });
    document.getElementById("download-review").addEventListener("click", () => {
      const review = readReview();
      review.generatedAt = new Date().toISOString();
      review.note = "Replace data/reclass.json with this file before rebuilding.";
      download("reclass.json", review);
    });
    document.getElementById("download-data").addEventListener("click", () => {
      download("relationship-graph-data.json", DATA);
    });
    render();
  </script>
</body>
</html>
"""


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_number(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def parse_timestamp_ms(value: str) -> int:
    value = value.replace(",", ".")
    parts = value.split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)
        if len(parts) == 2:
            minutes, seconds = parts
            return int((int(minutes) * 60 + float(seconds)) * 1000)
    except ValueError:
        return 0
    return 0


def format_timestamp(ms: int) -> str:
    seconds = max(0, int(ms / 1000))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def excerpt(text: str, start: int, end: int, width: int = 170) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    prefix = "…" if left else ""
    suffix = "…" if right < len(text) else ""
    return prefix + clean_text(text[left:right]) + suffix


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def canonicalize(name: str, category: str) -> str:
    cleaned = clean_text(name)
    if category in {"websites", "ip_addresses", "gps_coordinates", "radio_frequencies", "frequencies"}:
        return cleaned.lower()
    return re.sub(r"^(Dr\.|Mr\.|Ms\.|Sen\.|Rep\.)\s+", "", cleaned).strip()


def entity_key(name: str, category: str) -> str:
    return f"{category}:{slugify(name)}"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def titleize(stem: str) -> str:
    return " ".join(word.capitalize() for word in stem.replace("_", "-").split("-") if word)


def label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").title())


def most_common(values: list[str]) -> str:
    return Counter(values).most_common(1)[0][0]


def significance_sentence(name: str, category: str, count: int, transcripts: list[str], detectors: list[str]) -> str:
    transcript_phrase = f"{len(transcripts)} transcript" + ("" if len(transcripts) == 1 else "s")
    detector_phrase = ", ".join(detectors[:3])
    return f"{name} appears as {label(category).lower()} with {count} mention(s) across {transcript_phrase}; detected by {detector_phrase}."


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_html(app_data_version: str = "") -> str:
    app_data_scripts = "\n".join(
        f'    <script src="{name}{f"?v={app_data_version}" if app_data_version else ""}"></script>'
        for name in ("app-data.js", "app-data-mentions.js", "app-data-relationships.js")
    )
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UFO Files Relationship Graph</title>
  <style>
    :root {
      --bg: #f6f5ef;
      --panel: rgba(246, 245, 239, .96);
      --ink: #111;
      --muted: #555;
      --line: #111;
      --accent: #111;
      --chip: #ecebe4;
      --graph-bg: #f6f5ef;
      --font: "SF Mono", "IBM Plex Mono", "Roboto Mono", ui-monospace, monospace;
      --shadow: none;
    }
    * { box-sizing: border-box; }
    html, body {
      width: 100%;
      height: 100%;
      margin: 0;
      overflow: hidden;
      color: var(--ink);
      background: var(--bg);
      font: 14px/1.45 var(--font);
    }
    #graph {
      position: fixed;
      inset: 0;
      width: 100vw;
      height: 100vh;
      display: block;
      background: var(--graph-bg);
      cursor: grab;
      touch-action: none;
    }
    #graph.dragging { cursor: grabbing; }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .graph-label-layer {
      position: fixed;
      inset: 0;
      z-index: 3;
      overflow: hidden;
      pointer-events: none;
      touch-action: none;
    }
    .html-graph-label {
      position: absolute;
      max-width: 190px;
      text-align: center;
      transform: translate(-50%, 0);
      pointer-events: auto;
      cursor: pointer;
      user-select: none;
      touch-action: none;
      text-shadow: 0 1px 0 #fff, 0 -1px 0 #fff, 1px 0 0 #fff, -1px 0 0 #fff, 0 2px 8px rgba(255,255,255,.9);
      transition: color .16s ease, text-shadow .16s ease;
    }
    .html-graph-label {
      text-shadow: 0 1px 0 var(--graph-bg), 0 -1px 0 var(--graph-bg), 1px 0 0 var(--graph-bg), -1px 0 0 var(--graph-bg);
      text-transform: uppercase;
      letter-spacing: 0;
    }
    .html-graph-label.hover {
      color: #0f172a;
      z-index: 2;
      text-shadow: 0 1px 0 #fff, 0 -1px 0 #fff, 1px 0 0 #fff, -1px 0 0 #fff, 0 5px 16px rgba(15,23,42,.22);
    }
    .html-graph-label:focus-visible {
      outline: 2px solid var(--ink);
      outline-offset: 4px;
      background: rgba(246, 245, 239, .92);
    }
    .label-primary {
      display: block;
      color: var(--ink);
      font-size: 1rem;
      font-weight: 400;
      line-height: 1.15;
    }
    .label-secondary {
      display: block;
      margin-top: 6px;
      color: var(--muted);
      font-size: .875rem;
      line-height: 1.2;
    }
    .topbar {
      position: fixed;
      top: 12px;
      left: 12px;
      right: 12px;
      z-index: 5;
      display: grid;
      grid-template-columns: minmax(240px, 1fr) auto;
      gap: 10px;
      align-items: start;
      pointer-events: none;
    }
    .brand, .controls, .node-card, .legend, .corner-label, .hover-card {
      pointer-events: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }
    .brand {
      padding: 10px 12px;
      max-width: 640px;
    }
    .brand,
    .controls,
    .node-card,
    .corner-label,
    .hover-card {
      border-radius: 0;
      backdrop-filter: none;
    }
    h1 {
      margin: 0;
      font-size: 15px;
      font-weight: 400;
      text-transform: uppercase;
      letter-spacing: 0;
    }
    .meta {
      color: var(--muted);
      font-size: 12px;
    }
    .controls {
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: end;
      flex-wrap: wrap;
      padding: 8px;
    }
    .review-status {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.2;
    }
    input, select, button {
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      padding: 0 10px;
      font: inherit;
    }
    input:focus-visible,
    select:focus-visible,
    button:focus-visible,
    .node-card:focus-visible {
      outline: 2px solid var(--ink);
      outline-offset: 2px;
    }
    input { width: 280px; }
    button {
      cursor: pointer;
      font-weight: 400;
    }
    button.active {
      border-color: var(--accent);
      color: var(--accent);
      background: var(--chip);
    }
    .node-card {
      position: fixed;
      left: 12px;
      top: 12px;
      bottom: 12px;
      z-index: 6;
      width: min(440px, calc(100vw - 24px));
      padding: 0;
      display: none;
    }
    .node-card.open { display: block; }
    .node-card-body {
      height: 100%;
      max-height: none;
      overflow-y: auto;
      overflow-x: hidden;
      padding: 12px;
    }
    .card-close {
      position: absolute;
      top: 8px;
      right: -36px;
      width: 28px;
      height: 28px;
      padding: 0;
      line-height: 1;
      background: var(--panel);
    }
    .hover-card {
      position: fixed;
      left: 0;
      top: 0;
      z-index: 7;
      width: min(340px, calc(100vw - 24px));
      padding: 10px 12px;
      display: none;
      pointer-events: none;
      transform: translate(16px, 16px);
    }
    .hover-card.open { display: block; }
    .hover-card h2 {
      margin: 0 0 4px;
      font-size: 15px;
      line-height: 1.15;
      letter-spacing: 0;
    }
    .hover-card p {
      margin: 6px 0 0;
      color: #334155;
      font-size: 13px;
    }
    .hover-card .meta {
      font-size: 12px;
    }
    .corner-label {
      position: fixed;
      top: 72px;
      right: 12px;
      z-index: 4;
      max-width: min(460px, calc(100vw - 24px));
      padding: 12px 14px;
      display: none;
      text-align: right;
      pointer-events: none;
    }
    .corner-label.open { display: block; }
    .corner-label strong {
      display: block;
      color: var(--accent);
      font-size: 30px;
      font-weight: 400;
      line-height: 1.05;
      letter-spacing: 0;
    }
    .corner-label span {
      display: block;
      margin-top: 5px;
      color: #334155;
      font-size: 14px;
      font-weight: 400;
    }
    .node-card h2 {
      margin: 0 0 4px;
      font-size: 17px;
      letter-spacing: 0;
    }
    .node-card p { margin: 7px 0; }
    .card-actions {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      min-width: 0;
      margin-top: 0;
      padding-top: 0;
      border-top: 1px solid #edf0f5;
    }
    .node-card .card-actions input,
    .node-card .card-actions select {
      min-width: 0;
      max-width: 100%;
      flex: 1 1 180px;
    }
    .node-card .card-actions button {
      flex: 0 0 auto;
    }
    .card-field {
      display: grid;
      gap: 4px;
      width: 100%;
      min-width: 0;
    }
    .card-field span {
      color: var(--muted);
      font-size: 12px;
    }
    .card-field select,
    .card-field input {
      width: 100%;
    }
    .false-positive-actions {
      margin-top: 0;
      border-top: 0;
    }
    .node-card h3.false-positive-heading {
      margin-top: 14px;
    }
    .merge-results {
      display: grid;
      gap: 4px;
      width: 100%;
      max-height: 150px;
      overflow-y: auto;
      overflow-x: hidden;
      padding: 4px 0;
    }
    .merge-results button {
      width: 100%;
      height: auto;
      min-height: 32px;
      text-align: left;
      white-space: normal;
    }
    .merge-results button[aria-pressed="true"] {
      background: var(--chip);
      border-color: var(--ink);
    }
    .relationship-list {
      display: grid;
      gap: 6px;
      margin-top: 10px;
    }
    .relationship-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 30px;
      gap: 6px;
      align-items: stretch;
      min-width: 0;
    }
    .relationship-row .relationship-target {
      min-width: 0;
    }
    .relationship-row .remove-connection {
      width: 30px;
      min-width: 30px;
      padding: 0;
      color: var(--ink);
      text-align: center;
    }
    .relationship-list button {
      width: 100%;
      height: auto;
      min-height: 34px;
      text-align: left;
      white-space: normal;
    }
    .entity-directory {
      display: grid;
      gap: 5px;
      max-height: min(58vh, 620px);
      overflow-y: auto;
      overflow-x: hidden;
      padding-right: 2px;
    }
    .entity-directory button {
      width: 100%;
      height: auto;
      min-height: 34px;
      text-align: left;
      white-space: normal;
    }
    .evidence {
      border-top: 1px solid #edf0f5;
      padding-top: 8px;
      margin-top: 8px;
    }
    .node-card h3 {
      margin: 12px 0 6px;
      font-size: 13px;
      letter-spacing: 0;
    }
    .node-card h3.action-heading,
    .node-card h3.merge-heading {
      margin-bottom: 2px;
      font-size: 15px;
    }
    .relationship-list button {
      width: 100%;
      height: auto;
      min-height: 30px;
      text-align: left;
      white-space: normal;
    }
    .tag {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 7px;
      border-radius: 999px;
      border: 1px solid var(--ink);
      background: transparent;
      color: var(--ink);
      font-size: 12px;
      white-space: nowrap;
    }
    .graph-node, .graph-edge { cursor: pointer; }
    .graph-node, .graph-node * {
      pointer-events: all;
    }
    .graph-node {
      transform-box: fill-box;
      transform-origin: center;
      transition: transform .16s ease, filter .16s ease;
    }
    .graph-node circle {
      transition: stroke-width .16s ease;
      transform-box: fill-box;
      transform-origin: center;
    }
    .graph-node.hover {
      transform: scale(1.16);
      filter: drop-shadow(0 6px 14px rgba(15, 23, 42, .26));
    }
    .graph-node.hover {
      transform-box: fill-box;
      transform-origin: center;
    }
    .graph-node.connection-highlight circle {
      stroke: var(--ink) !important;
      stroke-width: 3.4;
    }
    .graph-node.connection-dim,
    .html-graph-label.connection-dim {
      opacity: .14;
    }
    .graph-edge {
      transition: opacity .16s ease, stroke-width .16s ease;
    }
    .graph-edge.connection-highlight {
      opacity: .95;
      stroke: var(--ink) !important;
      stroke-width: 4px;
    }
    .graph-edge.connection-dim {
      opacity: .035;
    }
    .html-graph-label.connection-highlight {
      z-index: 8;
      color: var(--ink);
      border-color: var(--ink);
      background: rgba(246, 245, 239, .94);
      box-shadow: 0 2px 8px rgba(17, 17, 17, .12);
      opacity: 1;
    }
    .graph-label {
      paint-order: stroke;
      stroke: #fff;
      stroke-width: 4px;
      stroke-linejoin: round;
    }
    .category-label {
      paint-order: stroke;
      stroke: #fff;
      stroke-width: 5px;
      stroke-linejoin: round;
    }
    .graph-primary-label {
      font-size: 1rem;
    }
    .graph-secondary-label {
      font-size: .875rem;
    }
    @media (max-width: 820px) {
      .topbar {
        top: 8px;
        left: 8px;
        right: 8px;
        grid-template-columns: 1fr;
        gap: 6px;
      }
      .brand { padding: 8px 10px; }
      h1 { font-size: 13px; }
      .controls {
        justify-content: start;
        gap: 6px;
        padding: 6px;
      }
      input { width: 100%; }
      input, select, button {
        height: 30px;
        padding: 0 8px;
        font-size: 12px;
      }
      .legend { display: none; }
      .corner-label {
        top: auto;
        right: 12px;
        bottom: 12px;
        max-width: calc(100vw - 24px);
      }
      .corner-label strong { font-size: 22px; }
      .node-card {
        top: 8px;
        left: 8px;
        right: 8px;
        bottom: 8px;
        width: auto;
      }
      .card-close {
        top: 8px;
        right: 8px;
      }
    }
  </style>
</head>
<body>
  <p id="graph-help" class="sr-only">Interactive relationship graph. Use Tab to move through visible graph labels, Enter or Space to open a category or entity, Escape to move back up the graph, and the search field to jump to a specific label.</p>
  <main aria-labelledby="app-title">
  <svg id="graph" role="img" aria-label="Transcript relationship graph" aria-describedby="graph-help status"></svg>
  <div id="graph-labels" class="graph-label-layer" aria-label="Keyboard accessible graph labels"></div>
  <div class="topbar">
    <div class="brand">
      <h1 id="app-title">UFO Files Relationship Graph</h1>
      <div class="meta" id="status" role="status" aria-live="polite">Loading graph...</div>
    </div>
    <form class="controls" id="search-form" role="search" aria-label="Graph search and downloads">
      <label class="sr-only" for="search">Search entity or category</label>
      <input id="search" type="search" placeholder="Search entity or category" autocomplete="off">
      <span id="review-status" class="review-status" role="status" aria-live="polite"></span>
      <button id="review-false-positives" type="button" hidden>Review false positives</button>
      <button id="download-review" type="button" hidden>Download reclassified data</button>
      <button id="download-data" type="button">Download data</button>
    </form>
  </div>
  <section id="node-card" class="node-card" tabindex="-1" aria-live="polite" aria-label="Selected graph item details"></section>
  <div id="hover-card" class="hover-card" aria-hidden="true"></div>
  <div id="corner-label" class="corner-label" role="status" aria-live="polite"></div>
  </main>
__APP_DATA_SCRIPTS__
  <script>
    const RAW = window.TRANSCRIPT_INTELLIGENCE_DATA;
    const REVIEW_KEY = "relationship-graph-reclass";
    const PREVIOUS_REVIEW_KEY = "uap-relationship-graph-reclass";
    const LEGACY_REVIEW_KEY = "transcript-intelligence-v2-review";
    const BUILT_REVIEW = normalizeReview(RAW.reclassDecisions || RAW.reclass_decisions || RAW.reviewDecisions || RAW.review_decisions || {});
    const THEME = {
      primary: "#111111",
      primarySoft: "#f6f5ef",
      entityFill: "#111111",
      entityAlt: "#f6f5ef",
      edge: "#111111",
      context: "#999999",
      activeHalo: "#ffffff",
      bgStroke: "#f6f5ef",
      edgeOpacity: { low: ".08", mid: ".16", high: ".34", relationship: ".36" },
    };
    const svg = document.getElementById("graph");
    const graphLabelsEl = document.getElementById("graph-labels");
    const statusEl = document.getElementById("status");
    const cardEl = document.getElementById("node-card");
    const hoverCardEl = document.getElementById("hover-card");
    const cornerLabelEl = document.getElementById("corner-label");
    const searchEl = document.getElementById("search");
    const reviewStatusEl = document.getElementById("review-status");
    const reviewFalsePositivesButton = document.getElementById("review-false-positives");
    let mode = "categories";
    let activeCategory = null;
    let selectedEntityId = null;
    let viewBox = { x: 120, y: 80, w: 1960, h: 1340 };
    let dragStart = null;
    let labelItems = [];
    let hoverZoomTarget = null;
    let hoverZoomDelta = 0;
    let touchState = null;
    const HOVER_ZOOM_ACTIVATE_DELTA = 900;
    const ENTITY_ZOOM_OUT_STEP_UP_WIDTH = 5600;
    const CATEGORY_ZOOM_OUT_STEP_UP_WIDTH = 7400;
    const MIN_ZOOM_WIDTH = 240;
    const MIN_ZOOM_HEIGHT = 165;
    const MAX_ZOOM_WIDTH = 10800;
    const MAX_ZOOM_HEIGHT = 10800;
    const NEIGHBORHOOD_RELATIONSHIP_LIMIT = 48;
    const CARD_RELATIONSHIP_LIMIT = 28;
    const SECOND_DEGREE_CONTEXT_LIMIT = 12;
    const SECOND_DEGREE_PER_NEIGHBOR_LIMIT = 2;
    const SECOND_DEGREE_EDGE_LIMIT = 24;
    const SECOND_DEGREE_LABEL_LIMIT = 0;

    initializeReviewStorage();
    let DATA = applyReviewDecisions(normalizeData(RAW));
    const entitiesById = new Map();
    const mentionsById = new Map(DATA.mentions.map((mention) => [mention.id, mention]));
    const relationshipsById = new Map();
    const relationshipsByEntity = new Map();
    rebuildIndexes();

    function currentTheme() {
      return THEME;
    }

    function normalizeData(raw) {
      const entities = raw.entities.map((entity) => ({
        ...entity,
        categoryLabel: entity.categoryLabel || entity.category_label || raw.categoryLabels[entity.category] || entity.category,
        topCategory: raw.categoryToTop[entity.category] || "needs_review",
        topCategoryLabel: raw.topCategoryLabels[raw.categoryToTop[entity.category] || "needs_review"] || "Needs Review",
        evidenceIds: entity.evidenceIds || entity.evidence_ids || [],
      }));
      const mentions = raw.mentions.map((mention) => ({
        ...mention,
        categoryLabel: mention.categoryLabel || mention.category_label || raw.categoryLabels[mention.category] || mention.category,
      }));
      const relationships = raw.relationships.map((relationship) => ({
        ...relationship,
        sourceName: relationship.sourceName || relationship.source_name,
        targetName: relationship.targetName || relationship.target_name,
        evidenceSegmentIds: relationship.evidenceSegmentIds || relationship.evidence_segment_ids || [],
        evidence: relationship.evidence || [],
      }));
      return { ...raw, entities, mentions, relationships };
    }

    function applyReviewDecisions(data) {
      const review = readReview();
      const falseIds = new Set(Object.keys(review.falsePositives || {}));
      data.entities = data.entities.filter((entity) => !falseIds.has(entity.id));
      for (const entity of data.entities) {
        const targetCategory = review.reclassifications && review.reclassifications[entity.id];
        if (targetCategory && data.categoryLabels[targetCategory]) {
          applyEntityCategory(entity, targetCategory, data);
        }
        const aliases = review.aliases || {};
        const alias = aliases[entity.id] || aliases[normalizeText(entity.name)];
        if (alias && alias.trim()) {
          applyEntityRename(entity, alias.trim(), data);
        }
      }
      const mergeRules = Object.values(review.merges || {}).concat(Object.values(review.nameMerges || {}));
      for (const merge of mergeRules) {
        if (!merge || !merge.targetName) continue;
        const source = data.entities.find((entity) => entity.id === merge.sourceId || normalizeText(entity.name) === normalizeText(merge.sourceName || ""));
        const target = data.entities.find((entity) => entity.id === merge.targetId) ||
          data.entities.find((entity) => normalizeText(entity.name) === normalizeText(merge.targetName) && entity.category === merge.targetCategory);
        if (source && target && source.id !== target.id) mergeEntityInto(source, target, data);
      }
      removeManualRelationships(data, review.removedManualRelationships || {});
      applyManualRelationships(data, review.manualRelationships || {});
      const visibleEntityIds = new Set(data.entities.map((entity) => entity.id));
      data.relationships = data.relationships.filter((relationship) => visibleEntityIds.has(relationship.source) && visibleEntityIds.has(relationship.target));
      return data;
    }

    function manualRelationshipKey(sourceId, targetId) {
      return [sourceId, targetId].sort().join("--");
    }

    function manualRelationshipDomId(key) {
      const slug = String(key || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
      return "manual-" + (slug || "item");
    }

    function entityByManualReference(item, side, data = DATA) {
      const id = item && item[side + "Id"];
      const entityById = id ? data.entities.find((entity) => entity.id === id) : null;
      if (entityById) return entityById;
      const category = item && item[side + "Category"];
      const review = readReview();
      const aliases = { ...(BUILT_REVIEW.aliases || {}), ...(review.aliases || {}) };
      const names = [item && item[side + "Name"]];
      if (id && aliases[id]) names.push(aliases[id]);
      const normalizedName = normalizeText(item && item[side + "Name"]);
      if (normalizedName && aliases[normalizedName]) names.push(aliases[normalizedName]);
      for (const nameValue of names) {
        const name = normalizeText(nameValue);
        if (!name) continue;
        const matches = data.entities.filter((entity) => normalizeText(entity.name) === name);
        if (category) {
          const categoryMatches = matches.filter((entity) => entity.category === category);
          if (categoryMatches.length === 1) return categoryMatches[0];
        }
        if (matches.length === 1) return matches[0];
      }
      return null;
    }

    function removeManualRelationships(data, removedManualRelationships) {
      const removed = new Set(Object.entries(removedManualRelationships || {}).map(([key, item]) => {
        if (item && typeof item === "object" && item.sourceId && item.targetId) {
          return manualRelationshipKey(item.sourceId, item.targetId);
        }
        return key;
      }));
      if (!removed.size) return;
      data.relationships = data.relationships.filter((relationship) => {
        if (relationship.type !== "manual") return true;
        return !removed.has(manualRelationshipKey(relationship.source, relationship.target)) && !removed.has(relationship.id.replace(/^manual-/, ""));
      });
    }

    function applyManualRelationships(data, manualRelationships) {
      const existingManualPairs = new Set(data.relationships
        .filter((relationship) => relationship.type === "manual")
        .map((relationship) => manualRelationshipKey(relationship.source, relationship.target)));
      for (const [id, item] of Object.entries(manualRelationships || {})) {
        if (!item || typeof item !== "object") continue;
        const source = entityByManualReference(item, "source", data);
        const target = entityByManualReference(item, "target", data);
        if (!source || !target || source.id === target.id) continue;
        const key = manualRelationshipKey(source.id, target.id);
        if (existingManualPairs.has(key)) continue;
        data.relationships.unshift({
          id: manualRelationshipDomId(key),
          source: source.id < target.id ? source.id : target.id,
          target: source.id < target.id ? target.id : source.id,
          sourceName: source.id < target.id ? source.name : target.name,
          targetName: source.id < target.id ? target.name : source.name,
          type: "manual",
          weight: 50,
          confidence: 1,
          evidenceSegmentIds: [],
          evidence: [],
        });
        existingManualPairs.add(key);
      }
    }

    function mergeEntityInto(source, target, data = DATA) {
      target.count = (target.count || 0) + (source.count || 0);
      target.evidenceIds = Array.from(new Set([...(target.evidenceIds || []), ...(source.evidenceIds || [])]));
      target.transcripts = Array.from(new Set([...(target.transcripts || []), ...(source.transcripts || [])])).sort();
      data.entities = data.entities.filter((entity) => entity.id !== source.id);
      const mergedRelationships = new Map();
      for (const relationship of data.relationships) {
        const next = { ...relationship };
        if (next.source === source.id) {
          next.source = target.id;
          next.sourceName = target.name;
        }
        if (next.target === source.id) {
          next.target = target.id;
          next.targetName = target.name;
        }
        if (next.source === next.target) continue;
        const key = [next.source, next.target].sort().join("::") + "::" + next.type;
        const existing = mergedRelationships.get(key);
        if (existing) {
          existing.weight += next.weight || 0;
          existing.evidenceSegmentIds = Array.from(new Set([...(existing.evidenceSegmentIds || []), ...(next.evidenceSegmentIds || [])]));
          existing.evidence = [...(existing.evidence || []), ...(next.evidence || [])].slice(0, 8);
        } else {
          mergedRelationships.set(key, next);
        }
      }
      data.relationships = Array.from(mergedRelationships.values());
    }

    function applyEntityCategory(entity, category, data = DATA) {
      entity.category = category;
      entity.categoryLabel = data.categoryLabels[category] || category;
      entity.topCategory = data.categoryToTop[category] || "needs_review";
      entity.topCategoryLabel = data.topCategoryLabels[entity.topCategory] || "Needs Review";
    }

    function applyEntityRename(entity, name, data = DATA) {
      const nextName = String(name || "").trim();
      if (!nextName) return;
      const previousName = entity.name;
      entity.name = nextName;
      entity.canonicalName = nextName;
      entity.significance = entity.significance ? entity.significance.replace(previousName, nextName) : entity.significance;
      for (const relationship of data.relationships) {
        if (relationship.source === entity.id) relationship.sourceName = nextName;
        if (relationship.target === entity.id) relationship.targetName = nextName;
      }
    }

    function rebuildIndexes() {
      entitiesById.clear();
      relationshipsById.clear();
      relationshipsByEntity.clear();
      for (const entity of DATA.entities) {
        entitiesById.set(entity.id, entity);
      }
      DATA.relationships = DATA.relationships.filter((relationship) => entitiesById.has(relationship.source) && entitiesById.has(relationship.target));
      for (const relationship of DATA.relationships) {
        relationshipsById.set(relationship.id, relationship);
        if (!relationshipsByEntity.has(relationship.source)) relationshipsByEntity.set(relationship.source, []);
        if (!relationshipsByEntity.has(relationship.target)) relationshipsByEntity.set(relationship.target, []);
        relationshipsByEntity.get(relationship.source).push(relationship);
        relationshipsByEntity.get(relationship.target).push(relationship);
      }
    }

    function setViewBox(x, y, w, h) {
      viewBox = { x, y, w, h };
      svg.setAttribute("viewBox", [x, y, w, h].join(" "));
      renderLabelLayer();
    }

    function graphHeaderInsetPx() {
      const topbar = document.querySelector(".topbar");
      if (!topbar) return 0;
      const rect = topbar.getBoundingClientRect();
      return Math.max(0, Math.ceil(rect.bottom + 18));
    }

    function graphSidebarInsetPx() {
      if (!cardEl.classList.contains("open") || isCompactViewport()) return 0;
      const rect = cardEl.getBoundingClientRect();
      return Math.max(0, Math.ceil(rect.right + 24));
    }

    function fitBoundsToViewport(minX, minY, maxX, maxY, options = {}) {
      const rect = svg.getBoundingClientRect();
      const rectWidth = Math.max(1, rect.width || svg.clientWidth || 1);
      const rectHeight = Math.max(1, rect.height || svg.clientHeight || 1);
      const topInset = options.reserveHeader === false ? 0 : graphHeaderInsetPx();
      const bottomInset = options.bottomInsetPx ?? 24;
      const leftInset = options.leftInsetPx ?? 0;
      const rightInset = options.rightInsetPx ?? 0;
      const padding = options.padding ?? 0;
      const availableW = Math.max(240, rectWidth - leftInset - rightInset);
      const availableH = Math.max(180, rectHeight - topInset - bottomInset);
      const paddedMinX = minX - padding;
      const paddedMinY = minY - padding;
      const paddedMaxX = maxX + padding;
      const paddedMaxY = maxY + padding;
      const contentW = Math.max(1, paddedMaxX - paddedMinX);
      const contentH = Math.max(1, paddedMaxY - paddedMinY);
      const ratio = rectWidth / rectHeight;
      let scale = Math.min(availableW / contentW, availableH / contentH);
      if (!Number.isFinite(scale) || scale <= 0) scale = 1;
      scale *= options.zoomFactor ?? 1;
      let width = clamp(rectWidth / scale, MIN_ZOOM_WIDTH, MAX_ZOOM_WIDTH);
      let height = width / ratio;
      if (height < MIN_ZOOM_HEIGHT) {
        height = MIN_ZOOM_HEIGHT;
        width = height * ratio;
      }
      if (height > MAX_ZOOM_HEIGHT) {
        height = MAX_ZOOM_HEIGHT;
        width = height * ratio;
      }
      const actualScale = rectWidth / width;
      const contentCx = (paddedMinX + paddedMaxX) / 2;
      const contentCy = (paddedMinY + paddedMaxY) / 2;
      const availableCenterX = leftInset + availableW / 2;
      const availableCenterY = topInset + availableH / 2;
      setViewBox(
        contentCx - availableCenterX / actualScale,
        contentCy - availableCenterY / actualScale,
        width,
        height
      );
    }

    function fitNodesToViewport(nodes, options = {}) {
      const items = nodes.filter(Boolean);
      if (!items.length) return;
      fitBoundsToViewport(
        Math.min(...items.map((node) => node.x - (node.r || 0))),
        Math.min(...items.map((node) => node.y - (node.r || 0))),
        Math.max(...items.map((node) => node.x + (node.r || 0))),
        Math.max(...items.map((node) => node.y + (node.r || 0))),
        options
      );
    }

    function isCompactViewport() {
      const rect = svg.getBoundingClientRect();
      return Math.min(rect.width || window.innerWidth, window.innerWidth) <= 820;
    }

    function fit() {
      setViewBox(0, -250, 2200, 2000);
    }

    function fitParentGraph() {
      setViewBox(-2100, -2500, 6400, 6600);
    }

    function fitEgoGraph(nodes, center) {
      const items = [center].concat(nodes);
      const maxRadius = Math.max(...items.map((node) => node.r));
      const longestLabel = Math.max(...items.map((node) => (node.raw?.name || node.label || "").length));
      const labelWidthPad = longestLabel * maxRadius * .42;
      const labelHeightPad = maxRadius * 4.8;
      const xPad = Math.max(maxRadius * 5.2, labelWidthPad);
      const topPad = Math.max(maxRadius * 2.8, labelHeightPad * .55);
      const bottomPad = Math.max(maxRadius * 4.2, labelHeightPad);
      const minX = Math.min(...items.map((node) => node.x - node.r)) - xPad;
      const maxX = Math.max(...items.map((node) => node.x + node.r)) + xPad;
      const minY = Math.min(...items.map((node) => node.y - node.r)) - topPad;
      const maxY = Math.max(...items.map((node) => node.y + node.r)) + bottomPad;
      fitBoundsToViewport(minX, minY, maxX, maxY, {
        reserveHeader: true,
        bottomInsetPx: 32,
        leftInsetPx: graphSidebarInsetPx(),
        zoomFactor: isCompactViewport() ? 1.08 : 1.18,
      });
    }

    function fitCategoryDrillViewport(activeCategoryNode, nodes) {
      if (!isCompactViewport()) {
        fitNodesToViewport([activeCategoryNode].concat(nodes), { padding: 260, reserveHeader: true, bottomInsetPx: 32 });
        return;
      }
      const focusRadius = 760;
      fitBoundsToViewport(
        activeCategoryNode.x - focusRadius,
        activeCategoryNode.y - focusRadius,
        activeCategoryNode.x + focusRadius,
        activeCategoryNode.y + focusRadius,
        {
          padding: 80,
          reserveHeader: true,
          bottomInsetPx: 48,
          leftInsetPx: 12,
          rightInsetPx: 12,
        }
      );
    }

    function setCornerLabel(title, detail) {
      if (!title) {
        cornerLabelEl.classList.remove("open");
        cornerLabelEl.innerHTML = "";
        return;
      }
      cornerLabelEl.innerHTML = '<strong>' + esc(title) + '</strong><span>' + esc(detail || "") + '</span>';
      cornerLabelEl.classList.add("open");
    }

    function setGraphLabels(items) {
      labelItems = items;
      renderLabelLayer();
    }

    function nodeLabel(id, kind, node, primary, secondary = "", radius = node.r) {
      return {
        id,
        kind,
        x: node.x,
        y: node.y + radius,
        primary,
        secondary,
      };
    }

    function graphViewportTransform() {
      const rect = svg.getBoundingClientRect();
      const svgRatio = rect.width / rect.height;
      const viewRatio = viewBox.w / viewBox.h;
      const scale = svgRatio > viewRatio ? rect.height / viewBox.h : rect.width / viewBox.w;
      const renderedW = viewBox.w * scale;
      const renderedH = viewBox.h * scale;
      return {
        rect,
        scale,
        offsetX: rect.left + (rect.width - renderedW) / 2,
        offsetY: rect.top + (rect.height - renderedH) / 2,
      };
    }

    function graphToScreen(x, y) {
      const transform = graphViewportTransform();
      return {
        x: transform.offsetX + (x - viewBox.x) * transform.scale,
        y: transform.offsetY + (y - viewBox.y) * transform.scale,
      };
    }

    function screenToGraph(x, y) {
      const transform = graphViewportTransform();
      return {
        x: viewBox.x + (x - transform.offsetX) / transform.scale,
        y: viewBox.y + (y - transform.offsetY) / transform.scale,
      };
    }

    function renderLabelLayer() {
      if (!graphLabelsEl || !labelItems.length) {
        if (graphLabelsEl) graphLabelsEl.innerHTML = "";
        return;
      }
      graphLabelsEl.innerHTML = labelItems.map((item) => {
        const point = graphToScreen(item.x, item.y);
        if (item.kind === "annotation") {
          return '<div class="html-graph-label" aria-hidden="true" style="left:' + point.x.toFixed(1) + 'px;top:' + (point.y + 6).toFixed(1) + 'px">' +
            '<span class="label-primary">' + esc(item.primary) + '</span>' +
            (item.secondary ? '<span class="label-secondary">' + esc(item.secondary) + '</span>' : '') +
          '</div>';
        }
        const attr = item.kind === "category"
          ? ' data-label-category="' + esc(item.id) + '"'
          : item.kind === "category-list"
            ? ' data-label-category-list="' + esc(item.id) + '"'
            : ' data-label-entity="' + esc(item.id) + '"';
        const state = ((item.kind === "category" || item.kind === "category-list") && activeCategory === item.id) || (item.kind === "entity" && selectedEntityId === item.id)
          ? ' aria-current="true"'
          : "";
        const secondary = item.secondary ? ". " + item.secondary : "";
        const action = item.kind === "category"
          ? "Open category"
          : item.kind === "category-list"
            ? "Open full entity list"
            : "Open entity";
        return '<div class="html-graph-label" role="button" tabindex="0" aria-label="' + esc(action + ": " + item.primary + secondary) + '"' + state + ' style="left:' + point.x.toFixed(1) + 'px;top:' + (point.y + 6).toFixed(1) + 'px"' + attr + '>' +
          '<span class="label-primary">' + esc(item.primary) + '</span>' +
          (item.secondary ? '<span class="label-secondary">' + esc(item.secondary) + '</span>' : '') +
        '</div>';
      }).join("");
    }

    function render() {
      if (mode === "neighborhood" && selectedEntityId && entitiesById.has(selectedEntityId)) {
        renderNeighborhood(entitiesById.get(selectedEntityId));
      } else if (mode === "category-list" && activeCategory) {
        renderCategoryGrid(activeCategory);
      } else if (activeCategory) {
        renderCategory(activeCategory);
      } else {
        renderCategories();
      }
    }

    function renderCategories() {
      const theme = currentTheme();
      const layout = buildCategoryLayout();
      const nodes = layout.nodes;
      const nodeById = layout.nodeById;
      const maxEdge = layout.maxEdge;
      const edges = layout.edges;
      svg.innerHTML = drawEdges(edges, nodeById, maxEdge, "category") + nodes.map((node) => {
        return '<g class="graph-node" data-category="' + esc(node.id) + '">' +
          '<circle cx="' + node.x + '" cy="' + node.y + '" r="' + node.r + '" fill="' + theme.primary + '" opacity=".9"></circle>' +
        '</g>';
      }).join("");
      setGraphLabels(nodes.map((node) => nodeLabel(
        node.id,
        "category",
        node,
        truncate(node.label, 24),
        node.count + " entities · " + node.mentions + " mentions"
      )));
      statusEl.textContent = nodes.length + " groups · " + DATA.manifest.counts.entities.toLocaleString() + " entities · select a group";
      cardEl.classList.remove("open");
      setCornerLabel(null);
      wireCategoryNodes();
      fitParentGraph();
    }

    function buildCategoryLayout() {
      const categoryStats = new Map();
      for (const entity of DATA.entities) {
        const stat = categoryStats.get(entity.topCategory) || { id: entity.topCategory, label: entity.topCategoryLabel, count: 0, mentions: 0 };
        stat.count += 1;
        stat.mentions += entity.count || 0;
        categoryStats.set(entity.topCategory, stat);
      }
      const categories = Object.keys(DATA.topCategoryLabels)
        .map((id) => categoryStats.get(id) || { id, label: DATA.topCategoryLabels[id], count: 0, mentions: 0 })
        .filter((category) => category.count > 0);
      const categorySet = new Set(categories.map((category) => category.id));
      const edgeWeights = new Map();
      for (const relationship of DATA.relationships) {
        const source = entitiesById.get(relationship.source);
        const target = entitiesById.get(relationship.target);
        if (!source || !target || source.topCategory === target.topCategory) continue;
        if (!categorySet.has(source.topCategory) || !categorySet.has(target.topCategory)) continue;
        const key = [source.topCategory, target.topCategory].sort().join("::");
        edgeWeights.set(key, (edgeWeights.get(key) || 0) + relationship.weight);
      }
      const nodes = parentCategoryNodes(categories.sort((a, b) => b.count - a.count), 1100, 750);
      const nodeById = new Map(nodes.map((node) => [node.id, node]));
      const maxEdge = Math.max(1, ...edgeWeights.values());
      const edges = Array.from(edgeWeights.entries()).sort((a, b) => b[1] - a[1]).slice(0, 95).map(([key, weight]) => {
        const [source, target] = key.split("::");
        return { source, target, weight };
      });
      return { nodes, nodeById, maxEdge, edges, edgeWeights };
    }

    function renderCategory(categoryId) {
      const theme = currentTheme();
      const label = DATA.topCategoryLabels[categoryId] || categoryId;
      const categoryLayout = buildCategoryLayout();
      const activeCategoryNode = categoryLayout.nodeById.get(categoryId) || { x: 1100, y: 750, r: 24 };
      const allPrimary = DATA.entities.filter((entity) => entity.topCategory === categoryId).sort((a, b) => entityGraphScore(b) - entityGraphScore(a));
      const primary = allPrimary.slice(0, 50);
      const primarySet = new Set(primary.map((entity) => entity.id));
      const rels = DATA.relationships.filter((relationship) => primarySet.has(relationship.source) && primarySet.has(relationship.target)).slice(0, 150);
      const nodes = radialNodes(primary, activeCategoryNode.x, activeCategoryNode.y, 460, 900, (entity) => entity.count || 1);
      const nodeById = new Map(nodes.map((node) => [node.id, node]));
      const maxEdge = Math.max(1, ...rels.map((relationship) => relationship.weight));
      const sharedNeighborById = new Map();
      const sharedEdgeWeights = new Map();
      for (const node of nodes) {
        for (const relationship of relationshipsByEntity.get(node.id) || []) {
          const outsideId = relationship.source === node.id ? relationship.target : relationship.source;
          const outside = entitiesById.get(outsideId);
          if (!outside || outside.topCategory === categoryId || primarySet.has(outsideId)) continue;
          if (!sharedNeighborById.has(outsideId)) {
            sharedNeighborById.set(outsideId, { entity: outside, sources: new Set(), weight: 0 });
          }
          const shared = sharedNeighborById.get(outsideId);
          shared.sources.add(node.id);
          shared.weight += relationship.weight;
          const edgeKey = node.id + "::" + outsideId;
          sharedEdgeWeights.set(edgeKey, (sharedEdgeWeights.get(edgeKey) || 0) + relationship.weight);
        }
      }
      const sharedNeighbors = Array.from(sharedNeighborById.entries())
        .map(([id, item]) => ({ id, ...item, sourceCount: item.sources.size }))
        .filter((item) => item.sourceCount >= 2)
        .sort((a, b) => b.sourceCount - a.sourceCount || b.weight - a.weight || entityGraphScore(b.entity) - entityGraphScore(a.entity))
        .slice(0, 22);
      const sharedNeighborIds = new Set(sharedNeighbors.map((item) => item.id));
      const maxSharedWeight = Math.max(1, ...sharedNeighbors.map((item) => item.weight));
      const sharedNodes = sharedNeighbors.map((item, index) => {
        const sourceNodes = Array.from(item.sources).map((id) => nodeById.get(id)).filter(Boolean);
        const avgX = sourceNodes.reduce((total, node) => total + node.x, 0) / Math.max(1, sourceNodes.length);
        const avgY = sourceNodes.reduce((total, node) => total + node.y, 0) / Math.max(1, sourceNodes.length);
        const dx = avgX - activeCategoryNode.x;
        const dy = avgY - activeCategoryNode.y;
        const length = Math.max(1, Math.hypot(dx, dy));
        const angle = Math.atan2(dy, dx) + ((index % 5) - 2) * .08;
        const radius = 1260 + (index % 3) * 120;
        return {
          id: item.id,
          x: activeCategoryNode.x + Math.cos(angle) * radius,
          y: activeCategoryNode.y + Math.sin(angle) * radius,
          r: 9 + Math.sqrt(item.weight / maxSharedWeight) * 13,
          weight: item.weight,
          sourceCount: item.sourceCount,
          raw: item.entity,
        };
      });
      const sharedNodeById = new Map(sharedNodes.map((node) => [node.id, node]));
      const sharedNodesSvg = sharedNodes.map((node) => {
        return '<g class="graph-node" data-entity="' + esc(node.id) + '">' +
          '<circle cx="' + node.x + '" cy="' + node.y + '" r="' + node.r + '" fill="' + theme.entityAlt + '" stroke="' + theme.primary + '" stroke-width="1" opacity=".76"></circle>' +
        '</g>';
      }).join("");
      const contextEdges = Array.from(sharedEdgeWeights.entries())
        .map(([key, weight]) => {
          const [childId, outsideId] = key.split("::");
          return { childId, outsideId, weight };
        })
        .filter((edge) => nodeById.has(edge.childId) && sharedNeighborIds.has(edge.outsideId) && sharedNodeById.has(edge.outsideId))
        .sort((a, b) => b.weight - a.weight)
        .slice(0, 80);
      const maxContextEdge = Math.max(1, ...contextEdges.map((edge) => edge.weight));
      const contextEdgesSvg = contextEdges.map((edge) => {
        const child = nodeById.get(edge.childId);
        const outside = sharedNodeById.get(edge.outsideId);
        if (!child || !outside) return "";
        const width = (0.7 + (edge.weight / maxContextEdge) * 3.4).toFixed(1);
        return '<line x1="' + child.x + '" y1="' + child.y + '" x2="' + outside.x + '" y2="' + outside.y + '" stroke="' + theme.primary + '" stroke-width="' + width + '" opacity=".34"></line>';
      }).join("");
      svg.innerHTML =
        contextEdgesSvg +
        '<g class="graph-node" data-category-list="' + esc(categoryId) + '">' +
          '<circle cx="' + activeCategoryNode.x + '" cy="' + activeCategoryNode.y + '" r="' + activeCategoryNode.r + '" fill="' + theme.activeHalo + '" stroke="' + theme.primary + '" stroke-width="1"></circle>' +
        '</g>' +
        drawRelationshipEdges(rels, nodeById, maxEdge, "drill") +
        nodes.map((node) => {
          const entity = node.raw;
          const inCategory = entity.topCategory === categoryId;
          return '<g class="graph-node" data-entity="' + esc(entity.id) + '">' +
            '<circle cx="' + node.x + '" cy="' + node.y + '" r="' + node.r + '" fill="' + (inCategory ? theme.entityFill : theme.entityAlt) + '" stroke="' + (inCategory ? theme.bgStroke : theme.primary) + '" stroke-width="1"></circle>' +
          '</g>';
        }).join("") +
        sharedNodesSvg;
      const sharedLabelNodes = sharedNodes
        .slice()
        .sort((a, b) => b.sourceCount - a.sourceCount || b.weight - a.weight)
        .slice(0, 8);
      setGraphLabels([nodeLabel(
        categoryId,
        "category-list",
        activeCategoryNode,
        "View all " + truncate(label, 18),
        allPrimary.length.toLocaleString() + " entities",
        activeCategoryNode.r
      )].concat(nodes.map((node) => nodeLabel(
        node.raw.id,
        "entity",
        node,
        truncate(node.raw.name, 24)
      ))).concat(sharedLabelNodes.map((node) => nodeLabel(
        node.id,
        "entity",
        node,
        truncate(node.raw.name, 22),
        node.sourceCount + " connected nodes",
        node.r
      ))));
      statusEl.textContent = label + " · select an entity for its direct relationship graph";
      setCornerLabel(null);
      wireEntityNodes();
      wireCategoryNodes();
      wireCategoryListNodes();
      fitCategoryDrillViewport(activeCategoryNode, nodes);
    }

    function renderCategoryGrid(categoryId) {
      const theme = currentTheme();
      const label = DATA.topCategoryLabels[categoryId] || categoryId;
      const entities = DATA.entities
        .filter((entity) => entity.topCategory === categoryId)
        .sort((a, b) => entityGraphScore(b) - entityGraphScore(a) || a.name.localeCompare(b.name));
      const scores = entities.map((entity) => Math.max(1, entityGraphScore(entity)));
      const minScore = Math.min(...scores);
      const maxScore = Math.max(1, ...scores);
      const logMin = Math.log(minScore);
      const logRange = Math.max(.001, Math.log(maxScore) - logMin);
      const maxRadius = 18;
      const minRadius = 3.5;
      const cell = maxRadius * 3.4;
      const headerHeight = cell * .9;
      const blockGap = cell * 1.4;
      const grouped = new Map();
      for (const entity of entities) {
        const group = grouped.get(entity.category) || {
          id: entity.category,
          label: entity.categoryLabel,
          entities: [],
          score: 0,
        };
        group.entities.push(entity);
        group.score += entityGraphScore(entity);
        grouped.set(entity.category, group);
      }
      const groups = Array.from(grouped.values())
        .sort((a, b) => b.entities.length - a.entities.length || b.score - a.score || a.label.localeCompare(b.label));
      const targetAtlasWidth = Math.max(cell * 18, Math.sqrt(Math.max(1, entities.length)) * cell * 1.45);
      let cursorX = 0;
      let cursorY = 0;
      let rowHeight = 0;
      const blocks = groups.map((group) => {
        const columns = Math.max(1, Math.ceil(Math.sqrt(group.entities.length * 1.25)));
        const rows = Math.max(1, Math.ceil(group.entities.length / columns));
        const width = columns * cell;
        const height = rows * cell + headerHeight;
        if (cursorX > 0 && cursorX + width > targetAtlasWidth) {
          cursorX = 0;
          cursorY += rowHeight + blockGap;
          rowHeight = 0;
        }
        const block = { ...group, x: cursorX, y: cursorY, width, height, columns, rows };
        cursorX += width + blockGap;
        rowHeight = Math.max(rowHeight, height);
        return block;
      });
      const atlasWidth = Math.max(...blocks.map((block) => block.x + block.width), cell);
      const atlasHeight = Math.max(...blocks.map((block) => block.y + block.height), cell);
      const offsetX = 1100 - atlasWidth / 2;
      const offsetY = 750 - atlasHeight / 2;
      const blockSvg = blocks.map((block) => {
        return '<rect x="' + (offsetX + block.x - cell * .28) + '" y="' + (offsetY + block.y - cell * .18) + '" width="' + (block.width + cell * .56) + '" height="' + (block.height + cell * .42) + '" fill="none" stroke="' + theme.context + '" stroke-width="1" opacity=".24"></rect>';
      }).join("");
      const groupLabels = blocks.map((block) => ({
        id: "group:" + block.id,
        kind: "annotation",
        x: offsetX + block.x,
        y: offsetY + block.y - cell * .34,
        primary: block.label,
        secondary: block.entities.length.toLocaleString() + " entities",
      }));
      const nodes = [];
      for (const block of blocks) {
        for (const [index, entity] of block.entities.entries()) {
          const column = index % block.columns;
          const row = Math.floor(index / block.columns);
          const value = Math.max(1, entityGraphScore(entity));
          const normalized = (Math.log(value) - logMin) / logRange;
          nodes.push({
            id: entity.id,
            x: offsetX + block.x + column * cell + cell / 2,
            y: offsetY + block.y + headerHeight + row * cell + cell / 2,
            r: minRadius + Math.pow(normalized, 1.05) * (maxRadius - minRadius),
            raw: entity,
            score: value,
            group: block,
          });
        }
      }
      svg.innerHTML = blockSvg + nodes.map((node) => {
        const opacity = node.r < 6 ? ".72" : ".9";
        const stroke = node.r < 6 ? theme.context : theme.primary;
        return '<g class="graph-node" data-entity="' + esc(node.id) + '">' +
          '<circle cx="' + node.x + '" cy="' + node.y + '" r="' + node.r + '" fill="' + theme.entityAlt + '" stroke="' + stroke + '" stroke-width="1" opacity="' + opacity + '"></circle>' +
          '<title>' + esc(node.raw.name + " · " + node.raw.categoryLabel + " · " + (node.raw.count || 0).toLocaleString() + " mentions") + '</title>' +
        '</g>';
      }).join("");
      const labeledByGroup = new Map();
      const labelNodes = nodes.filter((node) => {
        const count = labeledByGroup.get(node.group.id) || 0;
        if (count >= 10) return false;
        if (node.r < 8 && count >= 3) return false;
        labeledByGroup.set(node.group.id, count + 1);
        return true;
      }).slice(0, 180);
      setGraphLabels(groupLabels.concat(labelNodes.map((node) => nodeLabel(
        node.raw.id,
        "entity",
        node,
        truncate(node.raw.name, 22),
        (node.raw.count || 0).toLocaleString() + " mentions",
        node.r
      ))));
      statusEl.textContent = label + " atlas · " + entities.length.toLocaleString() + " entities grouped by category";
      setCornerLabel(label, entities.length.toLocaleString() + " entities · grouped atlas");
      cardEl.classList.remove("open");
      wireEntityNodes();
      const padding = cell * 2.2;
      const minX = offsetX - padding;
      const minY = offsetY - padding;
      const maxX = offsetX + atlasWidth + padding;
      const maxY = offsetY + atlasHeight + padding;
      fitBoundsToViewport(minX, minY, maxX, maxY, { reserveHeader: true, bottomInsetPx: 32 });
    }

    function entityGraphScore(entity) {
      const relationships = relationshipsByEntity.get(entity.id) || [];
      const evidence = (entity.evidenceIds || []).map((id) => mentionsById.get(id)).filter(Boolean);
      const transcriptCount = new Set(evidence.map((mention) => mention.transcript_title || mention.transcript_id || "")).size;
      const relationshipWeight = relationships.reduce((total, relationship) => total + (relationship.weight || 1), 0);
      return (entity.count || 0) * 4 + transcriptCount * 18 + relationships.length * 10 + relationshipWeight * 1.5;
    }

    function renderNeighborhood(entity) {
      const theme = currentTheme();
      const rels = (relationshipsByEntity.get(entity.id) || [])
        .slice()
        .sort((a, b) => relationshipGraphScore(b) - relationshipGraphScore(a))
        .slice(0, NEIGHBORHOOD_RELATIONSHIP_LIMIT);
      const relatedById = new Map();
      for (const relationship of rels) {
        const otherId = relationship.source === entity.id ? relationship.target : relationship.source;
        const relatedEntity = entitiesById.get(otherId);
        if (relatedEntity && !relatedById.has(relatedEntity.id)) {
          relatedById.set(relatedEntity.id, { entity: relatedEntity, relationship });
        }
      }
      const visibleNeighborIds = new Set(relatedById.keys());
      const neighborRelByPair = new Map();
      for (const neighborId of visibleNeighborIds) {
        for (const relationship of relationshipsByEntity.get(neighborId) || []) {
          if (!visibleNeighborIds.has(relationship.source) || !visibleNeighborIds.has(relationship.target)) continue;
          const a = relationship.source < relationship.target ? relationship.source : relationship.target;
          const b = relationship.source < relationship.target ? relationship.target : relationship.source;
          const key = a + "::" + b;
          const score = relationshipGraphScore(relationship);
          if (!neighborRelByPair.has(key)) {
            neighborRelByPair.set(key, {
              id: "neighbor:" + key,
              source: a,
              target: b,
              source_name: entitiesById.get(a)?.name || relationship.source_name,
              target_name: entitiesById.get(b)?.name || relationship.target_name,
              type: relationship.type,
              weight: relationship.weight || 1,
              confidence: relationship.confidence || 0,
              layoutScore: score,
            });
          } else {
            const existing = neighborRelByPair.get(key);
            existing.weight += relationship.weight || 1;
            existing.layoutScore += score;
            existing.confidence = Math.max(existing.confidence || 0, relationship.confidence || 0);
            if (existing.type !== relationship.type) existing.type = "related";
          }
        }
      }
      const neighborRels = Array.from(neighborRelByPair.values())
        .sort((a, b) => b.layoutScore - a.layoutScore)
        .slice(0, 18);
      const maxNeighborCount = Math.max(1, ...Array.from(relatedById.values()).map((item) => item.entity.count || 1));
      const neighborScoreByPair = new Map();
      for (const relationship of neighborRels) {
        neighborScoreByPair.set(relationship.source + "::" + relationship.target, relationship.layoutScore || relationship.weight || 1);
        neighborScoreByPair.set(relationship.target + "::" + relationship.source, relationship.layoutScore || relationship.weight || 1);
      }
      function pairScore(a, b) {
        return neighborScoreByPair.get(a + "::" + b) || 0;
      }
      function directScore(id) {
        const item = relatedById.get(id);
        return item ? relationshipGraphScore(item.relationship) : 0;
      }
      const adjacency = new Map(Array.from(visibleNeighborIds).map((id) => [id, []]));
      for (const relationship of neighborRels) {
        if (adjacency.has(relationship.source)) adjacency.get(relationship.source).push(relationship.target);
        if (adjacency.has(relationship.target)) adjacency.get(relationship.target).push(relationship.source);
      }
      const unseen = new Set(visibleNeighborIds);
      const components = [];
      while (unseen.size) {
        const seed = Array.from(unseen).sort((a, b) => directScore(b) - directScore(a))[0];
        const stack = [seed];
        const component = [];
        unseen.delete(seed);
        while (stack.length) {
          const id = stack.pop();
          component.push(id);
          for (const next of adjacency.get(id) || []) {
            if (!unseen.has(next)) continue;
            unseen.delete(next);
            stack.push(next);
          }
        }
        components.push(component);
      }
      const orderedIds = [];
      for (const component of components.sort((a, b) => Math.max(...b.map(directScore)) - Math.max(...a.map(directScore)))) {
        const remaining = new Set(component);
        let current = component.slice().sort((a, b) => directScore(b) - directScore(a))[0];
        while (current) {
          orderedIds.push(current);
          remaining.delete(current);
          const previous = current;
          current = Array.from(remaining)
            .sort((a, b) => pairScore(previous, b) - pairScore(previous, a) || directScore(b) - directScore(a))[0];
        }
      }
      const allDirectNeighborIds = new Set();
      for (const relationship of relationshipsByEntity.get(entity.id) || []) {
        const otherId = relationship.source === entity.id ? relationship.target : relationship.source;
        allDirectNeighborIds.add(otherId);
      }
      const secondDegreeById = new Map();
      const secondDegreeEdgeByPair = new Map();
      for (const neighborId of orderedIds) {
        const candidates = (relationshipsByEntity.get(neighborId) || [])
          .map((relationship) => {
            const otherId = relationship.source === neighborId ? relationship.target : relationship.source;
            return { relationship, otherId, score: relationshipGraphScore(relationship) };
          })
          .filter((item) => {
            const other = entitiesById.get(item.otherId);
            return other && item.otherId !== entity.id && !visibleNeighborIds.has(item.otherId) && !allDirectNeighborIds.has(item.otherId);
          })
          .sort((a, b) => b.score - a.score || entityGraphScore(entitiesById.get(b.otherId)) - entityGraphScore(entitiesById.get(a.otherId)))
          .slice(0, SECOND_DEGREE_PER_NEIGHBOR_LIMIT);
        for (const item of candidates) {
          const other = entitiesById.get(item.otherId);
          if (!secondDegreeById.has(item.otherId)) {
            secondDegreeById.set(item.otherId, { id: item.otherId, entity: other, sources: new Set(), weight: 0, score: 0 });
          }
          const context = secondDegreeById.get(item.otherId);
          context.sources.add(neighborId);
          context.weight += item.relationship.weight || 1;
          context.score += item.score + Math.min(90, entityGraphScore(other) * .025);
          const key = neighborId + "::" + item.otherId;
          if (!secondDegreeEdgeByPair.has(key)) {
            secondDegreeEdgeByPair.set(key, {
              id: "context:" + key,
              source: neighborId,
              target: item.otherId,
              type: item.relationship.type,
              weight: item.relationship.weight || 1,
              score: item.score,
            });
          } else {
            const existing = secondDegreeEdgeByPair.get(key);
            existing.weight += item.relationship.weight || 1;
            existing.score += item.score;
            if (existing.type !== item.relationship.type) existing.type = "related";
          }
        }
      }
      const secondDegree = Array.from(secondDegreeById.values())
        .map((item) => ({ ...item, sourceCount: item.sources.size }))
        .sort((a, b) => b.sourceCount - a.sourceCount || b.score - a.score || entityGraphScore(b.entity) - entityGraphScore(a.entity))
        .slice(0, SECOND_DEGREE_CONTEXT_LIMIT);
      const secondDegreeIds = new Set(secondDegree.map((item) => item.id));
      const nodes = orderedIds.map((id, index) => {
        const item = relatedById.get(id);
        const count = orderedIds.length;
        const angle = (Math.PI * 2 * index) / Math.max(1, count) - Math.PI / 2;
        const ring = count <= 18 ? 0 : index % 2;
        const radius = count <= 10 ? 690 : count <= 18 ? 740 : ring ? 840 : 610;
        const scale = Math.sqrt(Math.max(1, item.entity.count || 1) / maxNeighborCount);
        return {
          id: item.entity.id,
          label: item.entity.name,
          x: 1100 + Math.cos(angle) * radius,
          y: 750 + Math.sin(angle) * radius,
          r: 9 + scale * 22,
          raw: item.entity,
          relationship: item.relationship,
        };
      });
      const nodeById = new Map(nodes.map((node) => [node.id, node]));
      const center = { id: entity.id, x: 1100, y: 750, r: 46, raw: entity };
      nodeById.set(entity.id, center);
      const secondDegreeGroups = new Map();
      for (const item of secondDegree) {
        const anchorId = Array.from(item.sources)
          .sort((a, b) => {
            const bEdge = secondDegreeEdgeByPair.get(b + "::" + item.id);
            const aEdge = secondDegreeEdgeByPair.get(a + "::" + item.id);
            return (bEdge?.score || 0) - (aEdge?.score || 0) || directScore(b) - directScore(a);
          })[0];
        item.anchorId = anchorId;
        if (!secondDegreeGroups.has(anchorId)) secondDegreeGroups.set(anchorId, []);
        secondDegreeGroups.get(anchorId).push(item);
      }
      const maxSecondDegreeScore = Math.max(1, ...secondDegree.map((item) => item.score || item.weight || 1));
      const secondDegreeNodes = secondDegree.map((item, index) => {
        const anchorNode = nodeById.get(item.anchorId);
        const sourceNodes = Array.from(item.sources).map((id) => nodeById.get(id)).filter(Boolean);
        const group = secondDegreeGroups.get(item.anchorId) || [item];
        const groupIndex = Math.max(0, group.findIndex((candidate) => candidate.id === item.id));
        const fan = Math.min(.88, Math.max(.24, (group.length - 1) * .24));
        const fanOffset = group.length <= 1 ? 0 : (groupIndex / (group.length - 1) - .5) * fan;
        const avgX = sourceNodes.reduce((total, node) => total + node.x, 0) / Math.max(1, sourceNodes.length);
        const avgY = sourceNodes.reduce((total, node) => total + node.y, 0) / Math.max(1, sourceNodes.length);
        const baseAngle = anchorNode
          ? Math.atan2(anchorNode.y - center.y, anchorNode.x - center.x)
          : sourceNodes.length
            ? Math.atan2(avgY - center.y, avgX - center.x)
            : (Math.PI * 2 * index) / Math.max(1, secondDegree.length) - Math.PI / 2;
        const angle = baseAngle + fanOffset;
        const radius = 1040 + (groupIndex % 3) * 82 + Math.floor(groupIndex / 3) * 40 + Math.min(56, item.sourceCount * 12);
        const scoreScale = Math.sqrt(Math.max(1, item.score || item.weight || 1) / maxSecondDegreeScore);
        return {
          id: item.id,
          label: item.entity.name,
          x: center.x + Math.cos(angle) * radius,
          y: center.y + Math.sin(angle) * radius,
          r: 3.5 + scoreScale * 5 + Math.min(2, item.sourceCount),
          raw: item.entity,
          anchorId: item.anchorId,
          anchorName: anchorNode?.raw?.name || "",
          sourceCount: item.sourceCount,
          score: item.score,
        };
      });
      for (const node of secondDegreeNodes) nodeById.set(node.id, node);
      const maxEdge = Math.max(1, ...rels.map((relationship) => relationship.weight));
      const maxNeighborEdge = Math.max(1, ...neighborRels.map((relationship) => relationship.weight || 1));
      const secondDegreeEdges = Array.from(secondDegreeEdgeByPair.values())
        .filter((relationship) => nodeById.has(relationship.source) && secondDegreeIds.has(relationship.target))
        .sort((a, b) => b.score - a.score || b.weight - a.weight)
        .slice(0, SECOND_DEGREE_EDGE_LIMIT);
      const maxSecondDegreeEdge = Math.max(1, ...secondDegreeEdges.map((relationship) => relationship.weight || 1));
      const secondDegreeEdgesSvg = secondDegreeEdges.map((relationship) => {
        const source = nodeById.get(relationship.source);
        const target = nodeById.get(relationship.target);
        if (!source || !target) return "";
        const width = (0.25 + ((relationship.weight || 1) / maxSecondDegreeEdge) * .9).toFixed(1);
        return '<line class="graph-edge" data-edge="' + esc(relationship.id) + '" x1="' + source.x + '" y1="' + source.y + '" x2="' + target.x + '" y2="' + target.y + '" stroke="' + theme.context + '" stroke-width="' + width + '" opacity=".12"><title>' + esc(connectionCategoryText(relationship)) + '</title></line>';
      }).join("");
      const neighborEdgesSvg = neighborRels.map((relationship) => {
        const source = nodeById.get(relationship.source);
        const target = nodeById.get(relationship.target);
        if (!source || !target) return "";
        const width = (0.45 + ((relationship.weight || 1) / maxNeighborEdge) * 2.1).toFixed(1);
        return '<line class="graph-edge" data-edge="' + esc(relationship.id) + '" x1="' + source.x + '" y1="' + source.y + '" x2="' + target.x + '" y2="' + target.y + '" stroke="' + theme.context + '" stroke-width="' + width + '" opacity=".26"><title>' + esc(connectionCategoryText(relationship)) + '</title></line>';
      }).join("");
      const secondDegreeNodesSvg = secondDegreeNodes.map((node) => {
        return '<g class="graph-node context-node" data-entity="' + esc(node.raw.id) + '">' +
          '<circle cx="' + node.x + '" cy="' + node.y + '" r="' + node.r + '" fill="' + theme.entityAlt + '" stroke="' + theme.context + '" stroke-width="1" opacity=".38"></circle>' +
          '<title>' + esc(node.raw.name + " · connected through " + node.sourceCount + " direct " + pluralize("neighbor", node.sourceCount)) + '</title>' +
        '</g>';
      }).join("");
      svg.innerHTML = secondDegreeEdgesSvg +
        neighborEdgesSvg +
        drawRelationshipEdges(rels, nodeById, maxEdge, "drill") +
        secondDegreeNodesSvg +
        '<g class="graph-node" data-entity="' + esc(entity.id) + '">' +
          '<circle cx="1100" cy="750" r="46" fill="' + theme.primary + '" stroke="' + theme.bgStroke + '" stroke-width="1"></circle>' +
        '</g>' +
        nodes.map((node) => {
          const relatedEntity = node.raw;
          return '<g class="graph-node" data-entity="' + esc(relatedEntity.id) + '">' +
            '<circle cx="' + node.x + '" cy="' + node.y + '" r="' + node.r + '" fill="' + theme.entityAlt + '" stroke="' + theme.primary + '" stroke-width="1"></circle>' +
          '</g>';
        }).join("");
      const secondDegreeLabelNodes = secondDegreeNodes
        .slice()
        .sort((a, b) => b.sourceCount - a.sourceCount || b.score - a.score || entityGraphScore(b.raw) - entityGraphScore(a.raw))
        .slice(0, SECOND_DEGREE_LABEL_LIMIT);
      setGraphLabels([nodeLabel(
        entity.id,
        "entity",
        center,
        truncate(entity.name, 34),
        entity.topCategoryLabel
      )].concat(nodes.map((node) => nodeLabel(
        node.raw.id,
        "entity",
        node,
        truncate(node.raw.name, 24),
        truncate(node.raw.topCategoryLabel || node.raw.categoryLabel, 28)
      ))).concat(secondDegreeLabelNodes.map((node) => nodeLabel(
        node.raw.id,
        "entity",
        node,
        truncate(node.raw.name, 22),
        node.sourceCount > 1
          ? node.sourceCount + " real connections"
          : "from " + truncate(node.anchorName || "direct node", 18),
        node.r
      ))));
      statusEl.textContent = entity.name + " · " + entity.topCategoryLabel;
      setCornerLabel(null);
      renderCard(entity, rels);
      wireEntityNodes();
      fitEgoGraph(nodes, center);
    }

    function relationshipGraphScore(relationship) {
      if (relationship.type === "manual") return 1000000 + (relationship.weight || 1);
      const typeBoost = relationship.type === "co_mentioned" ? 0 : 18;
      const source = entitiesById.get(relationship.source);
      const target = entitiesById.get(relationship.target);
      const crossCategoryBoost = source && target && source.topCategory !== target.topCategory ? 10 : 0;
      return (relationship.weight || 1) * 24 + typeBoost + crossCategoryBoost + Math.round((relationship.confidence || 0) * 10);
    }

    function pluralize(word, count) {
      return count === 1 ? word : word + "s";
    }

    function connectionCategoryText(relationship) {
      const source = entitiesById.get(relationship.source);
      const target = entitiesById.get(relationship.target);
      const sourceLabel = source?.topCategoryLabel || source?.categoryLabel || "Entity";
      const targetLabel = target?.topCategoryLabel || target?.categoryLabel || "Entity";
      return sourceLabel === targetLabel ? sourceLabel : sourceLabel + " ↔ " + targetLabel;
    }

    function radialNodes(items, cx, cy, innerRadius, outerRadius, sizeValue) {
      const values = items.map((item) => Math.max(1, sizeValue(item)));
      const minValue = Math.min(...values);
      const maxValue = Math.max(1, ...values);
      return items.map((item, index) => {
        const angle = (Math.PI * 2 * index) / Math.max(1, items.length) - Math.PI / 2;
        const progress = items.length <= 1 ? 1 : index / (items.length - 1);
        const radius = innerRadius + Math.pow(progress, .62) * (outerRadius - innerRadius);
        const value = Math.max(1, sizeValue(item));
        const logMin = Math.log(minValue);
        const logRange = Math.log(maxValue) - logMin;
        const normalized = logRange < 0.001 ? 0.5 : (Math.log(value) - logMin) / logRange;
        const scale = Math.pow(normalized, 1.08);
        return {
          id: item.id,
          label: item.label || item.name,
          count: item.count || item.entities || 0,
          mentions: item.mentions || value,
          x: cx + Math.cos(angle) * radius,
          y: cy + Math.sin(angle) * radius,
          r: 8 + scale * 28,
          raw: item,
        };
      });
    }

    function parentCategoryNodes(categories, cx, cy) {
      const maxCount = Math.max(1, ...categories.map((category) => category.count || 1));
      const radiusFor = (category) => Math.max(16, Math.min(190, Math.sqrt((category.count || 1) / maxCount) * 190));
      const outerRadius = 1850;
      return categories.map((category, index) => {
        const angle = (Math.PI * 2 * index) / Math.max(1, categories.length) - Math.PI / 2;
        return {
          id: category.id,
          label: category.label,
          count: category.count || 0,
          mentions: category.mentions || 0,
          x: cx + Math.cos(angle) * outerRadius,
          y: cy + Math.sin(angle) * outerRadius,
          r: radiusFor(category),
          raw: category,
        };
      });
    }

    function drawEdges(edges, nodeById, maxEdge) {
      const theme = currentTheme();
      return edges.map((edge) => {
        const source = nodeById.get(edge.source);
        const target = nodeById.get(edge.target);
        if (!source || !target) return "";
        return '<line class="graph-edge" x1="' + source.x + '" y1="' + source.y + '" x2="' + target.x + '" y2="' + target.y + '" stroke="' + theme.edge + '" stroke-width="' + (0.8 + (edge.weight / maxEdge) * 7).toFixed(1) + '" opacity="' + theme.edgeOpacity.high + '"></line>';
      }).join("");
    }

    function drawRelationshipEdges(relationships, nodeById, maxEdge, density = "normal") {
      const theme = currentTheme();
      const baseWidth = density === "drill" ? 0.45 : 0.8;
      const weightWidth = density === "drill" ? 2.6 : 7;
      const opacity = density === "drill" ? ".24" : theme.edgeOpacity.relationship;
      return relationships.map((relationship) => {
        const source = nodeById.get(relationship.source);
        const target = nodeById.get(relationship.target);
        if (!source || !target) return "";
        return '<line class="graph-edge" data-edge="' + esc(relationship.id) + '" x1="' + source.x + '" y1="' + source.y + '" x2="' + target.x + '" y2="' + target.y + '" stroke="' + theme.edge + '" stroke-width="' + (baseWidth + (relationship.weight / maxEdge) * weightWidth).toFixed(1) + '" opacity="' + opacity + '"><title>' + esc(connectionCategoryText(relationship)) + '</title></line>';
      }).join("");
    }

    function mergeCandidates(entity, query = "") {
      const normalizedQuery = query.trim().toLowerCase();
      const sourceName = normalizeText(entity.name);
      return DATA.entities
        .filter((candidate) => {
          if (candidate.id === entity.id) return false;
          if (!normalizedQuery) return true;
          return [candidate.name, candidate.categoryLabel, candidate.topCategoryLabel].join(" ").toLowerCase().includes(normalizedQuery);
        })
        .sort((a, b) => {
          const aSameName = normalizeText(a.name) === sourceName ? 1 : 0;
          const bSameName = normalizeText(b.name) === sourceName ? 1 : 0;
          if (aSameName !== bSameName) return bSameName - aSameName;
          const aSameTop = a.topCategory === entity.topCategory ? 1 : 0;
          const bSameTop = b.topCategory === entity.topCategory ? 1 : 0;
          if (aSameTop !== bSameTop) return bSameTop - aSameTop;
          return (b.count || 0) - (a.count || 0);
        })
        .slice(0, 80);
    }

    function mergeResultButtons(entity, query = "") {
      const candidates = mergeCandidates(entity, query);
      if (!candidates.length) return '<div class="meta">No matches.</div>';
      return candidates.slice(0, 8).map((candidate) => {
        return '<button type="button" data-merge-target="' + esc(candidate.id) + '" aria-pressed="false">' +
          esc(candidate.name) +
          '<div class="meta">' + esc(candidate.categoryLabel) + ' · ' + (candidate.count || 0).toLocaleString() + ' mentions</div>' +
        '</button>';
      }).join("");
    }

    function mergeRemovalDecisions(entity) {
      const review = readReview();
      const removed = { ...(review.removedMerges || {}), ...(review.removedNameMerges || {}) };
      const decisions = mergeReviews(BUILT_REVIEW, review);
      const rows = [];
      const seen = new Set();
      for (const [key, merge] of Object.entries(decisions.merges || {})) {
        if (!merge || typeof merge !== "object") continue;
        if (removed[key]) continue;
        const targetMatches = merge.targetId === entity.id || normalizeText(merge.targetName || "") === normalizeText(entity.name);
        if (!targetMatches || seen.has(key)) continue;
        rows.push({ key, nameKey: normalizeText(merge.sourceName || key), merge });
        seen.add(key);
      }
      return rows.sort((a, b) => String(a.merge.sourceName || a.key).localeCompare(String(b.merge.sourceName || b.key)));
    }

    function mergeRemovalControls(entity) {
      const rows = mergeRemovalDecisions(entity);
      if (!rows.length) return "";
      return '<h3 class="merge-heading">Merged into this node</h3>' +
        '<div class="card-actions">' + rows.slice(0, 12).map((row) => {
          return '<button type="button" data-remove-merge="' + esc(row.key) + '" data-remove-name-merge="' + esc(row.nameKey) + '">' +
            'Remove merge: ' + esc(row.merge.sourceName || row.key) +
            '<div class="meta">' + esc(row.merge.sourceCategory || "Entity") + '</div>' +
          '</button>';
        }).join("") + '</div>';
    }

    function manualConnectionResultButtons(entity, query = "") {
      const candidates = mergeCandidates(entity, query);
      if (!candidates.length) return '<div class="meta">No matches.</div>';
      return candidates.slice(0, 8).map((candidate) => {
        return '<button type="button" data-manual-target="' + esc(candidate.id) + '" aria-pressed="false">' +
          esc(candidate.name) +
          '<div class="meta">' + esc(candidate.topCategoryLabel || candidate.categoryLabel) + '</div>' +
        '</button>';
      }).join("");
    }

    function falsePositiveRows() {
      const review = mergeReviews(BUILT_REVIEW, readReview());
      return Object.entries(review.falsePositives || {})
        .map(([id, item]) => ({
          id,
          name: item && item.name ? item.name : reviewEntryName(id, item)[0] || id,
          categoryLabel: item && item.categoryLabel ? item.categoryLabel : DATA.categoryLabels[item?.category] || item?.category || "Entity",
          built: Object.prototype.hasOwnProperty.call(BUILT_REVIEW.falsePositives || {}, id),
        }))
        .sort((a, b) => a.name.localeCompare(b.name));
    }

    function renderFalsePositiveReviewCard() {
      const rows = falsePositiveRows();
      cardEl.classList.add("open");
      cardEl.setAttribute("aria-labelledby", "card-title");
      cardEl.innerHTML = '<button class="card-close" id="close-card" aria-label="Close info window">x</button>' +
        '<div class="node-card-body"><h2 id="card-title">False positives</h2>' +
        '<p><span class="tag">Review</span> ' + rows.length.toLocaleString() + ' marked false positive</p>' +
        (rows.length ? '<div class="entity-directory">' + rows.map((row) => {
          return '<button type="button" data-restore-false-positive="' + esc(row.id) + '">' +
            esc(row.name) +
            '<div class="meta">' + esc(row.categoryLabel) + (row.built ? ' · restores on rebuild' : '') + '</div>' +
          '</button>';
        }).join("") + '</div>' : '<div class="meta">No false positives in the current review data.</div>') +
        '</div>';
      cardEl.querySelectorAll("[data-restore-false-positive]").forEach((button) => {
        button.addEventListener("click", () => restoreFalsePositive(button.dataset.restoreFalsePositive));
      });
      wireCardClose();
      focusDetailsCard();
    }

    function resetDataFromReview() {
      DATA = applyReviewDecisions(normalizeData(RAW));
      rebuildIndexes();
    }

    function restoreFalsePositive(entityId) {
      const review = readReview();
      const merged = mergeReviews(BUILT_REVIEW, review);
      const item = (merged.falsePositives || {})[entityId];
      if (!item) return;
      review.falsePositives = review.falsePositives || {};
      review.removedFalsePositives = review.removedFalsePositives || {};
      delete review.falsePositives[entityId];
      if (Object.prototype.hasOwnProperty.call(BUILT_REVIEW.falsePositives || {}, entityId)) {
        review.removedFalsePositives[entityId] = item;
      }
      saveReview(review);
      resetDataFromReview();
      render();
      renderFalsePositiveReviewCard();
    }

    function renderCard(entity, relationships) {
      const evidence = (entity.evidenceIds || []).map((id) => mentionsById.get(id)).filter(Boolean).slice(0, 6);
      cardEl.classList.add("open");
      cardEl.setAttribute("aria-labelledby", "card-title");
      cardEl.innerHTML = '<button class="card-close" id="close-card" aria-label="Close info window">x</button>' +
        '<div class="node-card-body"><h2 id="card-title">' + esc(entity.name) + '</h2>' +
        '<p><span class="tag">' + esc(entity.topCategoryLabel) + '</span> <span class="tag">' + esc(entity.categoryLabel) + '</span> ' + (entity.count || 0).toLocaleString() + ' mentions · ' + Math.round((entity.confidence || 0) * 100) + '% confidence</p>' +
        '<p>' + esc(entity.significance || "") + '</p>' +
        '<h3>Transcript snippets</h3>' +
        (evidence.length ? evidence.map((mention) => {
          return '<div class="evidence"><div class="meta">' + esc(mention.transcript_title) + ' · ' + esc(mention.timestamp) + ' · ' + esc(mention.detector) + '</div><div>' + esc(mention.excerpt) + '</div></div>';
        }).join("") : '<div class="meta">No snippets available for this entity.</div>') +
        '<h3>Connections</h3>' +
        '<div class="relationship-list">' + relationships.slice(0, CARD_RELATIONSHIP_LIMIT).map((relationship) => {
          const otherId = relationship.source === entity.id ? relationship.target : relationship.source;
          const other = entitiesById.get(otherId);
          const otherName = other ? other.name : otherId;
          const manualKey = relationship.type === "manual" ? manualRelationshipKey(relationship.source, relationship.target) : "";
          return '<div class="relationship-row">' +
            '<button class="relationship-target" data-card-entity="' + esc(otherId) + '">' + esc(otherName) + '<div class="meta">' + esc(other ? other.topCategoryLabel : "Entity") + '</div></button>' +
            (manualKey ? '<button class="remove-connection" type="button" data-remove-manual-connection="' + esc(manualKey) + '" aria-label="Remove manual connection to ' + esc(otherName) + '">x</button>' : '') +
          '</div>';
        }).join("") + '</div>' +
        '<h3 class="action-heading">Reclassify</h3>' +
        '<div class="card-actions"><label class="card-field"><span>Category</span><select id="review-category">' + Object.entries(DATA.categoryLabels).map(([id, label]) => '<option value="' + esc(id) + '"' + (id === entity.category ? ' selected' : '') + '>' + esc(label) + '</option>').join("") + '</select></label></div>' +
        '<h3 class="action-heading">Rename node</h3>' +
        '<div class="card-actions"><label class="card-field"><span>Display name</span><input id="rename-node-input" type="text" autocomplete="off" value="' + esc(entity.name) + '"></label><button id="rename-node">Rename</button></div>' +
        '<h3 class="action-heading false-positive-heading">False positive</h3>' +
        '<div class="card-actions false-positive-actions"><button id="false-positive">Mark false positive</button></div>' +
        '<h3 class="merge-heading">Merge duplicate</h3>' +
        '<div class="card-actions"><label class="card-field"><span>Find entity to merge into</span><input id="merge-target-search" type="search" autocomplete="off" aria-controls="merge-results" placeholder="Search by name or category"></label><div id="merge-results" class="merge-results" aria-label="Merge target results">' + mergeResultButtons(entity) + '</div><button id="merge-entity" disabled>Merge</button></div>' +
        mergeRemovalControls(entity) +
        '<h3 class="merge-heading">Add connection</h3>' +
        '<div class="card-actions"><label class="card-field"><span>Find entity to connect</span><input id="manual-connection-search" type="search" autocomplete="off" aria-controls="manual-connection-results" placeholder="Search by name or category"></label><div id="manual-connection-results" class="merge-results" aria-label="Manual connection results">' + manualConnectionResultButtons(entity) + '</div><button id="add-manual-connection" disabled>Add connection</button></div></div>';
      cardEl.querySelectorAll("[data-card-entity]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedEntityId = button.dataset.cardEntity;
          mode = "neighborhood";
          render();
          focusDetailsCard();
        });
      });
      cardEl.querySelectorAll("[data-remove-manual-connection]").forEach((button) => {
        button.addEventListener("click", (event) => {
          event.stopPropagation();
          const key = button.dataset.removeManualConnection;
          const relationship = DATA.relationships.find((candidate) => candidate.type === "manual" && manualRelationshipKey(candidate.source, candidate.target) === key);
          const source = relationship ? entitiesById.get(relationship.source) : null;
          const target = relationship ? entitiesById.get(relationship.target) : null;
          const review = readReview();
          review.manualRelationships = review.manualRelationships || {};
          review.removedManualRelationships = review.removedManualRelationships || {};
          const manual = review.manualRelationships[key] || {
            sourceId: relationship?.source || key.split("--")[0],
            sourceName: source?.name || "",
            sourceCategory: source?.category || "",
            targetId: relationship?.target || key.split("--")[1],
            targetName: target?.name || "",
            targetCategory: target?.category || "",
          };
          review.removedManualRelationships[key] = manual;
          delete review.manualRelationships[key];
          saveReview(review);
          DATA.relationships = DATA.relationships.filter((candidate) => candidate.type !== "manual" || manualRelationshipKey(candidate.source, candidate.target) !== key);
          rebuildIndexes();
          render();
          focusDetailsCard();
        });
      });
      wireCardClose();
      document.getElementById("review-category").addEventListener("change", (event) => {
        const review = readReview();
        const targetCategory = event.target.value;
        review.reclassifications[entity.id] = targetCategory;
        review.nameReclassifications = review.nameReclassifications || {};
        review.nameReclassifications[entity.name.toLowerCase()] = targetCategory;
        if (review.falsePositives) delete review.falsePositives[entity.id];
        saveReview(review);
        applyEntityCategory(entity, targetCategory);
        activeCategory = entity.topCategory;
        rebuildIndexes();
        render();
      });
      document.getElementById("rename-node").addEventListener("click", () => {
        const input = document.getElementById("rename-node-input");
        const nextName = input.value.trim();
        if (!nextName || nextName === entity.name) return;
        const previousName = entity.name;
        const review = readReview();
        review.aliases = review.aliases || {};
        review.aliases[entity.id] = nextName;
        review.aliases[normalizeText(previousName)] = nextName;
        if (review.falsePositives) delete review.falsePositives[entity.id];
        saveReview(review);
        applyEntityRename(entity, nextName);
        rebuildIndexes();
        render();
        focusDetailsCard();
      });
      document.getElementById("false-positive").addEventListener("click", () => {
        const confirmed = window.confirm('Mark "' + entity.name + '" as a false positive? This removes it from the graph and downloaded review data.');
        if (!confirmed) return;
        const review = readReview();
        review.falsePositives[entity.id] = { name: entity.name, category: entity.category, categoryLabel: entity.categoryLabel };
        if (review.reclassifications) delete review.reclassifications[entity.id];
        saveReview(review);
        DATA.entities = DATA.entities.filter((candidate) => candidate.id !== entity.id);
        DATA.relationships = DATA.relationships.filter((relationship) => relationship.source !== entity.id && relationship.target !== entity.id);
        selectedEntityId = null;
        mode = "categories";
        activeCategory = null;
        cardEl.classList.remove("open");
        rebuildIndexes();
        render();
      });
      const mergeSearch = document.getElementById("merge-target-search");
      const mergeResults = document.getElementById("merge-results");
      const mergeButton = document.getElementById("merge-entity");
      let selectedMergeTargetId = "";

      function selectMergeTarget(targetId) {
        const target = entitiesById.get(targetId);
        selectedMergeTargetId = target ? target.id : "";
        mergeButton.disabled = !selectedMergeTargetId;
        mergeResults.querySelectorAll("[data-merge-target]").forEach((button) => {
          const selected = button.dataset.mergeTarget === selectedMergeTargetId;
          button.setAttribute("aria-pressed", selected ? "true" : "false");
        });
        if (target) mergeSearch.value = target.name;
      }

      function wireMergeResults() {
        mergeResults.querySelectorAll("[data-merge-target]").forEach((button) => {
          button.addEventListener("click", () => selectMergeTarget(button.dataset.mergeTarget));
        });
      }

      mergeSearch.addEventListener("input", () => {
        selectedMergeTargetId = "";
        mergeButton.disabled = true;
        mergeResults.innerHTML = mergeResultButtons(entity, mergeSearch.value);
        wireMergeResults();
      });
      mergeSearch.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        const first = mergeResults.querySelector("[data-merge-target]");
        if (!first) return;
        event.preventDefault();
        selectMergeTarget(first.dataset.mergeTarget);
      });
      wireMergeResults();
      document.getElementById("merge-entity").addEventListener("click", () => {
        const target = entitiesById.get(selectedMergeTargetId);
        if (!target || target.id === entity.id) return;
        const review = readReview();
        review.merges = review.merges || {};
        review.nameMerges = review.nameMerges || {};
        const merge = {
          sourceId: entity.id,
          sourceName: entity.name,
          sourceCategory: entity.category,
          targetId: target.id,
          targetName: target.name,
          targetCategory: target.category,
        };
        review.merges[entity.id] = merge;
        review.nameMerges[normalizeText(entity.name)] = merge;
        if (review.reclassifications) delete review.reclassifications[entity.id];
        if (review.falsePositives) delete review.falsePositives[entity.id];
        saveReview(review);
        mergeEntityInto(entity, target);
        selectedEntityId = target.id;
        activeCategory = null;
        mode = "neighborhood";
        rebuildIndexes();
        render();
        focusDetailsCard();
      });

      cardEl.querySelectorAll("[data-remove-merge]").forEach((button) => {
        button.addEventListener("click", () => {
          const review = readReview();
          review.removedMerges = review.removedMerges || {};
          review.removedNameMerges = review.removedNameMerges || {};
          const key = button.dataset.removeMerge;
          const nameKey = button.dataset.removeNameMerge;
          const decisions = mergeReviews(BUILT_REVIEW, review);
          const merge = (decisions.merges || {})[key] || (decisions.nameMerges || {})[nameKey] || { sourceName: nameKey, targetName: entity.name };
          review.removedMerges[key] = merge;
          if (nameKey) review.removedNameMerges[nameKey] = merge;
          if (review.merges) delete review.merges[key];
          if (review.nameMerges && nameKey) delete review.nameMerges[nameKey];
          saveReview(review);
          render();
          focusDetailsCard();
        });
      });

      const manualSearch = document.getElementById("manual-connection-search");
      const manualResults = document.getElementById("manual-connection-results");
      const manualButton = document.getElementById("add-manual-connection");
      let selectedManualTargetId = "";

      function selectManualTarget(targetId) {
        const target = entitiesById.get(targetId);
        selectedManualTargetId = target ? target.id : "";
        manualButton.disabled = !selectedManualTargetId;
        manualResults.querySelectorAll("[data-manual-target]").forEach((button) => {
          const selected = button.dataset.manualTarget === selectedManualTargetId;
          button.setAttribute("aria-pressed", selected ? "true" : "false");
        });
        if (target) manualSearch.value = target.name;
      }

      function wireManualResults() {
        manualResults.querySelectorAll("[data-manual-target]").forEach((button) => {
          button.addEventListener("click", () => selectManualTarget(button.dataset.manualTarget));
        });
      }

      manualSearch.addEventListener("input", () => {
        selectedManualTargetId = "";
        manualButton.disabled = true;
        manualResults.innerHTML = manualConnectionResultButtons(entity, manualSearch.value);
        wireManualResults();
      });
      manualSearch.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        const first = manualResults.querySelector("[data-manual-target]");
        if (!first) return;
        event.preventDefault();
        selectManualTarget(first.dataset.manualTarget);
      });
      wireManualResults();
      manualButton.addEventListener("click", () => {
        const target = entitiesById.get(selectedManualTargetId);
        if (!target || target.id === entity.id) return;
        const review = readReview();
        review.manualRelationships = review.manualRelationships || {};
        const ids = [entity.id, target.id].sort();
        const key = manualRelationshipKey(ids[0], ids[1]);
        if (review.removedManualRelationships) delete review.removedManualRelationships[key];
        review.manualRelationships[key] = {
          sourceId: ids[0],
          sourceName: (entitiesById.get(ids[0]) || entity).name,
          sourceCategory: (entitiesById.get(ids[0]) || entity).category,
          targetId: ids[1],
          targetName: (entitiesById.get(ids[1]) || target).name,
          targetCategory: (entitiesById.get(ids[1]) || target).category,
        };
        saveReview(review);
        applyManualRelationships(DATA, { [key]: review.manualRelationships[key] });
        rebuildIndexes();
        render();
        focusDetailsCard();
      });
    }

    function renderCategoryListCard(categoryId) {
      const label = DATA.topCategoryLabels[categoryId] || categoryId;
      const entities = DATA.entities
        .filter((entity) => entity.topCategory === categoryId)
        .sort((a, b) => entityGraphScore(b) - entityGraphScore(a) || a.name.localeCompare(b.name));
      const mentions = entities.reduce((total, entity) => total + (entity.count || 0), 0);
      cardEl.classList.add("open");
      cardEl.setAttribute("aria-labelledby", "card-title");
      cardEl.innerHTML = '<button class="card-close" id="close-card" aria-label="Close info window">x</button>' +
        '<div class="node-card-body"><h2 id="card-title">' + esc(label) + '</h2>' +
        '<p><span class="tag">' + esc(label) + '</span> ' + entities.length.toLocaleString() + ' entities · ' + mentions.toLocaleString() + ' mentions</p>' +
        '<h3>All entities</h3>' +
        '<div class="entity-directory">' + entities.map((entity) => {
          return '<button data-card-entity="' + esc(entity.id) + '">' +
            esc(entity.name) +
            '<div class="meta">' + esc(entity.categoryLabel) + ' · ' + (entity.count || 0).toLocaleString() + ' mentions</div>' +
          '</button>';
        }).join("") + '</div></div>';
      cardEl.querySelectorAll("[data-card-entity]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedEntityId = button.dataset.cardEntity;
          mode = "neighborhood";
          render();
          focusDetailsCard();
        });
      });
      wireCardClose();
    }

    function renderEdgeCard(relationship) {
      const source = entitiesById.get(relationship.source);
      const target = entitiesById.get(relationship.target);
      const evidence = relationship.evidence || [];
      cardEl.classList.add("open");
      cardEl.setAttribute("aria-labelledby", "card-title");
      cardEl.innerHTML = '<button class="card-close" id="close-card" aria-label="Close info window">x</button>' +
        '<div class="node-card-body"><h2 id="card-title">' + esc(source ? source.name : relationship.sourceName) + ' ↔ ' + esc(target ? target.name : relationship.targetName) + '</h2>' +
        '<p><span class="tag">' + esc(connectionCategoryText(relationship)) + '</span></p>' +
        '<h3>Evidence</h3>' +
        (evidence.length ? evidence.map((item) => {
          return '<div class="evidence"><div class="meta">' + esc(item.transcript) + ' · ' + esc(item.timestamp) + '</div><div>' + esc(item.excerpt) + '</div></div>';
        }).join("") : '<div class="meta">No relationship snippets available.</div>') +
        '<div class="card-actions"><button data-card-entity="' + esc(relationship.source) + '">' + esc(source ? source.name : "Source") + '</button><button data-card-entity="' + esc(relationship.target) + '">' + esc(target ? target.name : "Target") + '</button></div></div>';
      cardEl.querySelectorAll("[data-card-entity]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedEntityId = button.dataset.cardEntity;
          mode = "neighborhood";
          render();
          focusDetailsCard();
        });
      });
      wireCardClose();
    }

    function focusDetailsCard() {
      if (cardEl.classList.contains("open")) cardEl.focus({ preventScroll: true });
    }

    function focusSelectedGraphLabel() {
      const selectors = selectedEntityId
        ? ['[data-label-entity="' + cssEscape(selectedEntityId) + '"]']
        : activeCategory
          ? ['[data-label-category="' + cssEscape(activeCategory) + '"]', '[data-label-category-list="' + cssEscape(activeCategory) + '"]']
          : [".html-graph-label"];
      const label = selectors.map((selector) => graphLabelsEl.querySelector(selector)).find(Boolean);
      if (label) label.focus({ preventScroll: true });
    }

    function wireCardClose() {
      const closeButton = document.getElementById("close-card");
      if (!closeButton) return;
      closeButton.addEventListener("click", () => {
        cardEl.classList.remove("open");
        cardEl.removeAttribute("aria-labelledby");
        focusSelectedGraphLabel();
      });
    }

    function wireCategoryNodes() {
      svg.querySelectorAll("[data-category]").forEach((node) => {
        node.addEventListener("click", () => activateGraphNode(node));
      });
    }

    function wireCategoryListNodes() {
      svg.querySelectorAll("[data-category-list]").forEach((node) => {
        node.addEventListener("click", () => activateGraphNode(node, { focusGraph: true }));
      });
    }

    function wireEntityNodes() {
      svg.querySelectorAll("[data-entity]").forEach((node) => {
        node.addEventListener("click", () => activateGraphNode(node));
      });
      svg.querySelectorAll("[data-edge]").forEach((edge) => {
        edge.addEventListener("click", (event) => {
          event.stopPropagation();
          const relationship = relationshipsById.get(edge.dataset.edge);
          if (relationship) renderEdgeCard(relationship);
        });
      });
    }

    function activateGraphNode(node, options = {}) {
      if (!node) return false;
      if (node.dataset.category) {
        activeCategory = node.dataset.category;
        selectedEntityId = null;
        mode = "categories";
      } else if (node.dataset.categoryList) {
        activeCategory = node.dataset.categoryList;
        selectedEntityId = null;
        mode = "category-list";
        hideHoverPreview();
        render();
        if (options.focusGraph) focusSelectedGraphLabel();
        return true;
      } else if (node.dataset.entity) {
        selectedEntityId = node.dataset.entity;
        mode = "neighborhood";
      } else {
        return false;
      }
      hideHoverPreview();
      render();
      if (options.focusCard && node.dataset.entity) {
        focusDetailsCard();
      } else if (options.focusGraph) {
        focusSelectedGraphLabel();
      }
      return true;
    }

    function promoteNode(node) {
      if (node && node.parentNode === svg) {
        svg.appendChild(node);
      }
    }

    function clearConnectionHighlights() {
      svg.querySelectorAll(".connection-highlight, .connection-dim").forEach((element) => {
        element.classList.remove("connection-highlight", "connection-dim");
      });
      graphLabelsEl.querySelectorAll(".connection-highlight, .connection-dim").forEach((element) => {
        element.classList.remove("connection-highlight", "connection-dim");
      });
    }

    function highlightEntityConnections(entityId) {
      clearConnectionHighlights();
      const relationships = relationshipsByEntity.get(entityId) || [];
      if (!entityId || !relationships.length) return;
      const connectedIds = new Set([entityId]);
      const connectedRelationshipIds = new Set();
      relationships.forEach((relationship) => {
        connectedRelationshipIds.add(relationship.id);
        connectedIds.add(relationship.source === entityId ? relationship.target : relationship.source);
      });

      svg.querySelectorAll("[data-entity]").forEach((node) => {
        const isConnected = connectedIds.has(node.dataset.entity);
        node.classList.toggle("connection-highlight", isConnected);
        node.classList.toggle("connection-dim", !isConnected);
      });
      graphLabelsEl.querySelectorAll("[data-label-entity]").forEach((label) => {
        const isConnected = connectedIds.has(label.dataset.labelEntity);
        label.classList.toggle("connection-highlight", isConnected);
        label.classList.toggle("connection-dim", !isConnected);
      });
      svg.querySelectorAll("[data-edge]").forEach((edge) => {
        const isConnected = connectedRelationshipIds.has(edge.dataset.edge);
        edge.classList.toggle("connection-highlight", isConnected);
        edge.classList.toggle("connection-dim", !isConnected);
      });
    }

    function setHoveredNode(node) {
      clearConnectionHighlights();
      svg.querySelectorAll(".graph-node.hover").forEach((current) => {
        if (current !== node) current.classList.remove("hover");
      });
      graphLabelsEl.querySelectorAll(".html-graph-label.hover").forEach((current) => {
        current.classList.remove("hover");
      });
      if (!node) return;
      promoteNode(node);
      node.classList.add("hover");
      if (node.dataset.entity) highlightEntityConnections(node.dataset.entity);
      const labelKind = node.dataset.entity ? "labelEntity" : node.dataset.categoryList ? "labelCategoryList" : "labelCategory";
      const id = node.dataset.entity || node.dataset.categoryList || node.dataset.category;
      Array.from(graphLabelsEl.querySelectorAll(".html-graph-label")).forEach((label) => {
        if (label.dataset[labelKind] === id) label.classList.add("hover");
      });
    }

    function graphNodeFromTarget(target) {
      let node = target;
      while (node && node !== svg) {
        if (node.classList && node.classList.contains("graph-node")) return node;
        node = node.parentNode;
      }
      return null;
    }

    function graphLabelFromTarget(target) {
      let label = target;
      while (label && label !== graphLabelsEl) {
        if (label.classList && label.classList.contains("html-graph-label")) return label;
        label = label.parentNode;
      }
      return null;
    }

    function svgNodeFromLabel(label) {
      if (!label) return null;
      const isEntity = Boolean(label.dataset.labelEntity);
      const isCategoryList = Boolean(label.dataset.labelCategoryList);
      const id = label.dataset.labelEntity || label.dataset.labelCategoryList || label.dataset.labelCategory;
      const nodes = svg.querySelectorAll(isEntity ? "[data-entity]" : isCategoryList ? "[data-category-list]" : "[data-category]");
      return Array.from(nodes).find((node) => {
        if (isEntity) return node.dataset.entity === id;
        if (isCategoryList) return node.dataset.categoryList === id;
        return node.dataset.category === id;
      }) || null;
    }

    function interactionNodeFromTarget(target) {
      return graphNodeFromTarget(target) ||
        svgNodeFromLabel(graphLabelFromTarget(target)) ||
        svg.querySelector(".graph-node.hover");
    }

    function graphNodeKey(node) {
      if (!node) return "";
      return node.dataset.entity
        ? "entity:" + node.dataset.entity
        : node.dataset.categoryList
          ? "category-list:" + node.dataset.categoryList
          : "category:" + node.dataset.category;
    }

    function resetHoverZoomActivation() {
      hoverZoomTarget = null;
      hoverZoomDelta = 0;
    }

    function categoryPreview(categoryId) {
      const label = DATA.topCategoryLabels[categoryId] || categoryId;
      const entities = DATA.entities.filter((entity) => entity.topCategory === categoryId);
      const mentions = entities.reduce((total, entity) => total + (entity.count || 0), 0);
      const topEntities = entities
        .slice()
        .sort((a, b) => (b.count || 0) - (a.count || 0))
        .slice(0, 4)
        .map((entity) => entity.name)
        .join(", ");
      return {
        title: label,
        meta: entities.length.toLocaleString() + " entities · " + mentions.toLocaleString() + " mentions",
        body: topEntities ? "Top entities: " + topEntities : "No entities in this group.",
      };
    }

    function entityPreview(entityId) {
      const entity = entitiesById.get(entityId);
      if (!entity) return null;
      const relCount = (relationshipsByEntity.get(entity.id) || []).length;
      const evidence = (entity.evidenceIds || []).map((id) => mentionsById.get(id)).find(Boolean);
      const body = evidence
        ? truncate(evidence.excerpt, 180)
        : truncate(entity.significance || "No transcript snippet available.", 180);
      return {
        title: entity.name,
        meta: entity.categoryLabel + " · " + (entity.count || 0).toLocaleString() + " mentions · " + relCount + " links",
        body,
      };
    }

    function showHoverPreview(node, event) {
      if (!node || dragStart) {
        hideHoverPreview();
        return;
      }
      const preview = node.dataset.entity
        ? entityPreview(node.dataset.entity)
        : categoryPreview(node.dataset.categoryList || node.dataset.category);
      if (!preview) {
        hideHoverPreview();
        return;
      }
      hoverCardEl.innerHTML = '<h2>' + esc(preview.title) + '</h2>' +
        '<div class="meta">' + esc(preview.meta) + '</div>' +
        '<p>' + esc(preview.body) + '</p>';
      hoverCardEl.classList.add("open");
      positionHoverPreview(event);
    }

    function hideHoverPreview() {
      hoverCardEl.classList.remove("open");
    }

    function positionHoverPreview(event) {
      if (!hoverCardEl.classList.contains("open")) return;
      const margin = 12;
      const offset = 16;
      const rect = hoverCardEl.getBoundingClientRect();
      let x = event.clientX + offset;
      let y = event.clientY + offset;
      if (x + rect.width + margin > window.innerWidth) x = event.clientX - rect.width - offset;
      if (y + rect.height + margin > window.innerHeight) y = event.clientY - rect.height - offset;
      hoverCardEl.style.left = Math.max(margin, x) + "px";
      hoverCardEl.style.top = Math.max(margin, y) + "px";
    }

    function searchGraph() {
      const query = searchEl.value.trim().toLowerCase();
      if (!query) return;
      const category = Object.entries(DATA.topCategoryLabels).find(([id, label]) => label.toLowerCase().includes(query) || id.toLowerCase().includes(query));
      const entity = DATA.entities.find((item) => item.name.toLowerCase().includes(query));
      if (entity) {
        selectedEntityId = entity.id;
        activeCategory = null;
        mode = "neighborhood";
      } else if (category) {
        activeCategory = category[0];
        selectedEntityId = null;
        mode = "categories";
      } else {
        statusEl.textContent = "No graph result for " + query;
        return;
      }
      render();
      focusSelectedGraphLabel();
    }

    function stepBackGraph() {
      if (cardEl.classList.contains("open")) {
        cardEl.classList.remove("open");
        cardEl.removeAttribute("aria-labelledby");
        focusSelectedGraphLabel();
        return true;
      }
      if (mode === "neighborhood") {
        selectedEntityId = null;
        mode = "categories";
        render();
        focusSelectedGraphLabel();
        return true;
      }
      if (mode === "category-list") {
        selectedEntityId = null;
        mode = "categories";
        render();
        focusSelectedGraphLabel();
        return true;
      }
      if (activeCategory) {
        activeCategory = null;
        selectedEntityId = null;
        mode = "categories";
        renderCategories();
        focusSelectedGraphLabel();
        return true;
      }
      return false;
    }

    function defaultReview() {
      return {
        reclassifications: {},
        nameReclassifications: {},
        falsePositives: {},
        removedFalsePositives: {},
        omissions: {},
        aliases: {},
        merges: {},
        nameMerges: {},
        removedMerges: {},
        removedNameMerges: {},
        removedManualRelationships: {},
        manualRelationships: {},
        notes: {},
      };
    }

    function normalizeReview(review) {
      const normalized = defaultReview();
      if (!review || typeof review !== "object") return normalized;
      for (const key of ["reclassifications", "nameReclassifications", "falsePositives", "removedFalsePositives", "omissions", "aliases", "merges", "nameMerges", "removedMerges", "removedNameMerges", "removedManualRelationships", "manualRelationships", "notes"]) {
        normalized[key] = review[key] && typeof review[key] === "object" && !Array.isArray(review[key]) ? review[key] : {};
      }
      normalized.manualRelationships = normalizeManualRelationshipDecisions(normalized.manualRelationships);
      normalized.removedManualRelationships = normalizeManualRelationshipDecisions(normalized.removedManualRelationships, true);
      if (review.generatedAt) normalized.generatedAt = review.generatedAt;
      if (review.note) normalized.note = review.note;
      return normalized;
    }

    function normalizeManualRelationshipDecisions(decisions, allowFallbackKey = false) {
      const normalized = {};
      for (const [key, item] of Object.entries(decisions || {})) {
        if (item && typeof item === "object" && item.sourceId && item.targetId && item.sourceId !== item.targetId) {
          normalized[manualRelationshipKey(item.sourceId, item.targetId)] = item;
        } else if (allowFallbackKey && key) {
          normalized[key] = item;
        }
      }
      return normalized;
    }

    function mergeReviews(base, overlay) {
      const merged = normalizeReview(base);
      const next = normalizeReview(overlay);
      for (const key of ["reclassifications", "nameReclassifications", "falsePositives", "removedFalsePositives", "omissions", "aliases", "merges", "nameMerges", "removedMerges", "removedNameMerges", "removedManualRelationships", "manualRelationships", "notes"]) {
        merged[key] = { ...(merged[key] || {}), ...(next[key] || {}) };
      }
      for (const key of Object.keys(merged.removedFalsePositives || {})) delete merged.falsePositives[key];
      for (const key of Object.keys(merged.removedMerges || {})) delete merged.merges[key];
      for (const key of Object.keys(merged.removedNameMerges || {})) delete merged.nameMerges[key];
      for (const key of Object.keys(merged.removedManualRelationships || {})) delete merged.manualRelationships[key];
      if (next.generatedAt) merged.generatedAt = next.generatedAt;
      if (next.note) merged.note = next.note;
      return merged;
    }

    function sameReviewValue(left, right) {
      return JSON.stringify(left) === JSON.stringify(right);
    }

    function reviewEntryName(id, value) {
      const names = [];
      if (id) {
        const textId = String(id);
        names.push(textId.includes(":") ? textId.split(":").slice(1).join(" ").replace(/-/g, " ") : textId);
      }
      if (value && typeof value === "object" && value.name) names.push(value.name);
      if (value && typeof value === "object" && value.sourceName) names.push(value.sourceName);
      return names.map(normalizeText).filter(Boolean);
    }

    function rawEntityById(id) {
      return (RAW.entities || []).find((entity) => entity.id === id);
    }

    function rawEntityByName(name) {
      const normalized = normalizeText(name);
      if (!normalized) return null;
      return (RAW.entities || []).find((entity) => normalizeText(entity.name) === normalized) || null;
    }

    function reviewCategoryIsBaked(id, category) {
      if (Object.prototype.hasOwnProperty.call(BUILT_REVIEW.reclassifications || {}, id) && BUILT_REVIEW.reclassifications[id] === category) {
        return true;
      }
      for (const name of reviewEntryName(id, category)) {
        if ((BUILT_REVIEW.nameReclassifications || {})[name] === category) return true;
        const entity = rawEntityById(id) || rawEntityByName(name);
        if (entity && entity.category === category) return true;
      }
      return false;
    }

    function reviewAliasIsBaked(id, alias) {
      if (Object.prototype.hasOwnProperty.call(BUILT_REVIEW.aliases || {}, id) && sameReviewValue(alias, BUILT_REVIEW.aliases[id])) {
        return true;
      }
      const aliasName = normalizeText(alias);
      if (!aliasName) return false;
      return Boolean(rawEntityById(id) && normalizeText(rawEntityById(id).name) === aliasName) || Boolean(rawEntityByName(aliasName));
    }

    function reviewFalsePositiveIsBaked(id, value) {
      if (Object.prototype.hasOwnProperty.call(BUILT_REVIEW.falsePositives || {}, id) && sameReviewValue(value, BUILT_REVIEW.falsePositives[id])) {
        return true;
      }
      const entity = rawEntityById(id);
      return !entity && reviewEntryName(id, value).every((name) => !rawEntityByName(name));
    }

    function reviewMergeIsBaked(id, value) {
      const built = (BUILT_REVIEW.merges || {})[id] || (BUILT_REVIEW.nameMerges || {})[id];
      if (built && sameReviewValue(value, built)) return true;
      if (!value || typeof value !== "object") return false;
      const source = rawEntityById(value.sourceId) || rawEntityByName(value.sourceName);
      const target = rawEntityById(value.targetId) || rawEntityByName(value.targetName);
      return !source && Boolean(target);
    }

    function removeBuiltReviewEntries(review) {
      const cleaned = normalizeReview(review);
      let changed = false;
      for (const key of ["reclassifications", "nameReclassifications", "falsePositives", "removedFalsePositives", "omissions", "aliases", "merges", "nameMerges", "removedManualRelationships", "manualRelationships"]) {
        for (const [id, value] of Object.entries(cleaned[key] || {})) {
          const exactBuilt = Object.prototype.hasOwnProperty.call(BUILT_REVIEW[key] || {}, id) && sameReviewValue(value, BUILT_REVIEW[key][id]);
          const bakedCategory = key === "reclassifications" || key === "nameReclassifications" ? reviewCategoryIsBaked(id, value) : false;
          const bakedFalsePositive = key === "falsePositives" ? reviewFalsePositiveIsBaked(id, value) : false;
          const bakedAlias = key === "aliases" ? reviewAliasIsBaked(id, value) : false;
          const bakedMerge = key === "merges" || key === "nameMerges" ? reviewMergeIsBaked(id, value) : false;
          if (exactBuilt || bakedCategory || bakedFalsePositive || bakedAlias || bakedMerge) {
            delete cleaned[key][id];
            changed = true;
          }
        }
      }
      return { cleaned, changed };
    }

    function initializeReviewStorage() {
      const previousRaw = localStorage.getItem(PREVIOUS_REVIEW_KEY);
      if (!localStorage.getItem(REVIEW_KEY) && previousRaw) {
        localStorage.setItem(REVIEW_KEY, previousRaw);
      }
      if (previousRaw) localStorage.removeItem(PREVIOUS_REVIEW_KEY);
      const legacyRaw = localStorage.getItem(LEGACY_REVIEW_KEY);
      if (!localStorage.getItem(REVIEW_KEY) && legacyRaw) {
        localStorage.setItem(REVIEW_KEY, legacyRaw);
      }
      if (legacyRaw) localStorage.removeItem(LEGACY_REVIEW_KEY);
      const storedRaw = localStorage.getItem(REVIEW_KEY);
      if (!storedRaw) return;
      try {
        const { cleaned, changed } = removeBuiltReviewEntries(JSON.parse(storedRaw));
        if (changed) {
          if (hasReviewDecisions(cleaned)) {
            localStorage.setItem(REVIEW_KEY, JSON.stringify(cleaned));
          } else {
            localStorage.removeItem(REVIEW_KEY);
          }
        }
      } catch {
        localStorage.removeItem(REVIEW_KEY);
      }
    }

    function readReview() {
      try {
        return normalizeReview(JSON.parse(localStorage.getItem(REVIEW_KEY) || "{}"));
      } catch {
        return defaultReview();
      }
    }

    function saveReview(review) {
      localStorage.setItem(REVIEW_KEY, JSON.stringify(review));
      updateReviewButton();
    }

    function hasReviewDecisions(review) {
      return reviewDecisionCount(review) > 0;
    }

    function reviewDecisionCount(review) {
      return (
        Object.keys(review.reclassifications || {}).length +
        Object.keys(review.nameReclassifications || {}).length +
        Object.keys(review.falsePositives || {}).length +
        Object.keys(review.removedFalsePositives || {}).length +
        Object.keys(review.omissions || {}).length +
        Object.keys(review.aliases || {}).length +
        Object.keys(review.merges || {}).length +
        Object.keys(review.nameMerges || {}).length +
        Object.keys(review.removedMerges || {}).length +
        Object.keys(review.removedNameMerges || {}).length +
        Object.keys(review.removedManualRelationships || {}).length +
        Object.keys(review.manualRelationships || {}).length
      );
    }

    function updateReviewButton() {
      const button = document.getElementById("download-review");
      const review = readReview();
      const count = reviewDecisionCount(review);
      if (button) button.hidden = count === 0;
      if (reviewFalsePositivesButton) reviewFalsePositivesButton.hidden = falsePositiveRows().length === 0;
      if (reviewStatusEl) reviewStatusEl.textContent = count ? count.toLocaleString() + " new reclass changes" : "";
    }

    function download(filename, payload) {
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    }

    function esc(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
    }

    function cssEscape(value) {
      if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(String(value ?? ""));
      return String(value ?? "").replace(/["\\\\]/g, "\\\\$&");
    }

    function truncate(value, length) {
      const text = String(value ?? "");
      return text.length > length ? text.slice(0, length - 1) + "..." : text;
    }

    function normalizeText(value) {
      return String(value ?? "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    }

    function clamp(value, min, max) {
      return Math.max(min, Math.min(max, value));
    }

    function touchPoint(touch) {
      return { x: touch.clientX, y: touch.clientY };
    }

    function midpoint(a, b) {
      return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    }

    function distance(a, b) {
      return Math.hypot(a.x - b.x, a.y - b.y);
    }

    function setZoomFromScreenPoint(screenPoint, startViewBox, nextW, nextH) {
      const pointer = screenToGraph(screenPoint.x, screenPoint.y);
      const pointerRatioX = (pointer.x - startViewBox.x) / startViewBox.w;
      const pointerRatioY = (pointer.y - startViewBox.y) / startViewBox.h;
      setViewBox(pointer.x - pointerRatioX * nextW, pointer.y - pointerRatioY * nextH, nextW, nextH);
    }

    function startTouch(event) {
      if (!event.touches.length) return;
      event.preventDefault();
      resetHoverZoomActivation();
      hideHoverPreview();
      if (event.touches.length >= 2) {
        const first = touchPoint(event.touches[0]);
        const second = touchPoint(event.touches[1]);
        touchState = {
          mode: "pinch",
          startDistance: Math.max(1, distance(first, second)),
          startMidpoint: midpoint(first, second),
          startViewBox: { ...viewBox },
        };
        svg.classList.add("dragging");
        return;
      }
      const point = touchPoint(event.touches[0]);
      touchState = {
        mode: "pan",
        startPoint: point,
        startViewBox: { ...viewBox },
        moved: false,
        tapNode: interactionNodeFromTarget(event.target),
      };
      svg.classList.add("dragging");
    }

    function moveTouch(event) {
      if (!touchState || !event.touches.length) return;
      event.preventDefault();
      if (event.touches.length >= 2) {
        const first = touchPoint(event.touches[0]);
        const second = touchPoint(event.touches[1]);
        if (touchState.mode !== "pinch") {
          touchState = {
            mode: "pinch",
            startDistance: Math.max(1, distance(first, second)),
            startMidpoint: midpoint(first, second),
            startViewBox: { ...viewBox },
          };
        }
        const scale = Math.max(0.1, distance(first, second) / touchState.startDistance);
        const nextW = clamp(touchState.startViewBox.w / scale, MIN_ZOOM_WIDTH, MAX_ZOOM_WIDTH);
        const nextH = clamp(touchState.startViewBox.h / scale, MIN_ZOOM_HEIGHT, MAX_ZOOM_HEIGHT);
        setZoomFromScreenPoint(midpoint(first, second), touchState.startViewBox, nextW, nextH);
        return;
      }
      if (touchState.mode !== "pan") return;
      const point = touchPoint(event.touches[0]);
      const dx = point.x - touchState.startPoint.x;
      const dy = point.y - touchState.startPoint.y;
      if (Math.hypot(dx, dy) > 8) touchState.moved = true;
      const transform = graphViewportTransform();
      setViewBox(
        touchState.startViewBox.x - dx / transform.scale,
        touchState.startViewBox.y - dy / transform.scale,
        touchState.startViewBox.w,
        touchState.startViewBox.h
      );
    }

    function endTouch(event) {
      if (!touchState) return;
      event.preventDefault();
      if (touchState.mode === "pan" && !touchState.moved && touchState.tapNode) {
        activateGraphNode(touchState.tapNode);
      }
      touchState = null;
      svg.classList.remove("dragging");
    }

    graphLabelsEl.addEventListener("pointermove", (event) => {
      const label = graphLabelFromTarget(event.target);
      const node = svgNodeFromLabel(label);
      setHoveredNode(node);
      showHoverPreview(node, event);
    });
    graphLabelsEl.addEventListener("pointerleave", () => {
      setHoveredNode(null);
      hideHoverPreview();
    });
    graphLabelsEl.addEventListener("click", (event) => {
      const label = graphLabelFromTarget(event.target);
      if (!label) return;
      activateGraphNode(svgNodeFromLabel(label));
    });
    graphLabelsEl.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const label = graphLabelFromTarget(event.target);
      if (!label) return;
      event.preventDefault();
      activateGraphNode(svgNodeFromLabel(label), { focusCard: true, focusGraph: true });
    });
    graphLabelsEl.addEventListener("focusin", (event) => {
      const label = graphLabelFromTarget(event.target);
      const node = svgNodeFromLabel(label);
      if (!node || !label) return;
      setHoveredNode(node);
      const rect = label.getBoundingClientRect();
      showHoverPreview(node, { clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 });
    });
    graphLabelsEl.addEventListener("focusout", (event) => {
      if (graphLabelsEl.contains(event.relatedTarget)) return;
      setHoveredNode(null);
      hideHoverPreview();
    });
    window.addEventListener("resize", renderLabelLayer);

    function handleGraphWheel(event) {
      event.preventDefault();
      const interactionNode = event.deltaY < 0 ? interactionNodeFromTarget(event.target) : null;
      const interactionNodeKey = graphNodeKey(interactionNode);
      if (event.deltaY >= 0 || !interactionNodeKey) {
        resetHoverZoomActivation();
      } else if (hoverZoomTarget !== interactionNodeKey) {
        hoverZoomTarget = interactionNodeKey;
        hoverZoomDelta = 0;
      }
      const pointer = screenToGraph(event.clientX, event.clientY);
      const pointerX = pointer.x;
      const pointerY = pointer.y;
      const intensity = event.deltaMode === 1 ? 0.08 : 0.0015;
      const factor = clamp(Math.exp(event.deltaY * intensity), 0.82, 1.22);
      const nextW = clamp(viewBox.w * factor, MIN_ZOOM_WIDTH, MAX_ZOOM_WIDTH);
      const nextH = clamp(viewBox.h * factor, MIN_ZOOM_HEIGHT, MAX_ZOOM_HEIGHT);
      const pointerRatioX = (pointerX - viewBox.x) / viewBox.w;
      const pointerRatioY = (pointerY - viewBox.y) / viewBox.h;
      setViewBox(pointerX - pointerRatioX * nextW, pointerY - pointerRatioY * nextH, nextW, nextH);
      if (event.deltaY < 0 && interactionNodeKey) {
        hoverZoomDelta += Math.abs(event.deltaY) * (event.deltaMode === 1 ? 16 : 1);
        if (hoverZoomDelta >= HOVER_ZOOM_ACTIVATE_DELTA && activateGraphNode(interactionNode)) {
          resetHoverZoomActivation();
          return;
        }
      }
      if (event.deltaY > 0 && mode === "neighborhood" && nextW >= ENTITY_ZOOM_OUT_STEP_UP_WIDTH) {
        selectedEntityId = null;
        mode = "categories";
        hideHoverPreview();
        if (activeCategory) {
          renderCategory(activeCategory);
        } else {
          renderCategories();
        }
        return;
      }
      if (event.deltaY > 0 && mode === "category-list" && nextW >= ENTITY_ZOOM_OUT_STEP_UP_WIDTH) {
        selectedEntityId = null;
        mode = "categories";
        hideHoverPreview();
        renderCategory(activeCategory);
        return;
      }
      if (event.deltaY > 0 && activeCategory && mode === "categories" && nextW >= CATEGORY_ZOOM_OUT_STEP_UP_WIDTH) {
        activeCategory = null;
        selectedEntityId = null;
        hideHoverPreview();
        renderCategories();
      }
    }

    svg.addEventListener("wheel", handleGraphWheel, { passive: false });
    graphLabelsEl.addEventListener("wheel", handleGraphWheel, { passive: false });
    svg.addEventListener("touchstart", startTouch, { passive: false });
    svg.addEventListener("touchmove", moveTouch, { passive: false });
    svg.addEventListener("touchend", endTouch, { passive: false });
    svg.addEventListener("touchcancel", endTouch, { passive: false });
    graphLabelsEl.addEventListener("touchstart", startTouch, { passive: false });
    graphLabelsEl.addEventListener("touchmove", moveTouch, { passive: false });
    graphLabelsEl.addEventListener("touchend", endTouch, { passive: false });
    graphLabelsEl.addEventListener("touchcancel", endTouch, { passive: false });
    svg.addEventListener("pointermove", (event) => {
      const node = graphNodeFromTarget(event.target);
      setHoveredNode(node);
      showHoverPreview(node, event);
    });
    svg.addEventListener("pointerleave", () => {
      setHoveredNode(null);
      hideHoverPreview();
    });
    svg.addEventListener("pointerdown", (event) => {
      if (graphNodeFromTarget(event.target) || event.target.closest(".graph-edge")) return;
      hideHoverPreview();
      dragStart = { x: event.clientX, y: event.clientY, viewBox: { ...viewBox } };
      svg.classList.add("dragging");
      svg.setPointerCapture(event.pointerId);
    });
    svg.addEventListener("pointermove", (event) => {
      if (!dragStart) return;
      const scaleX = viewBox.w / svg.clientWidth;
      const scaleY = viewBox.h / svg.clientHeight;
      setViewBox(dragStart.viewBox.x - (event.clientX - dragStart.x) * scaleX, dragStart.viewBox.y - (event.clientY - dragStart.y) * scaleY, viewBox.w, viewBox.h);
    });
    svg.addEventListener("pointerup", (event) => {
      if (dragStart && svg.hasPointerCapture(event.pointerId)) {
        svg.releasePointerCapture(event.pointerId);
      }
      dragStart = null;
      svg.classList.remove("dragging");
    });
    document.getElementById("search-form").addEventListener("submit", (event) => {
      event.preventDefault();
      searchGraph();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (stepBackGraph()) event.preventDefault();
    });
    document.getElementById("download-review").addEventListener("click", () => {
      const review = mergeReviews(BUILT_REVIEW, readReview());
      review.generatedAt = new Date().toISOString();
      review.note = "Replace data/reclass.json with this file before rebuilding.";
      download("reclass.json", review);
    });
    reviewFalsePositivesButton.addEventListener("click", () => renderFalsePositiveReviewCard());
    document.getElementById("download-data").addEventListener("click", () => download("relationship-graph-data.json", DATA));
    updateReviewButton();
    render();
  </script>
</body>
</html>
""".replace("__APP_DATA_SCRIPTS__", app_data_scripts)


if __name__ == "__main__":
    main()
