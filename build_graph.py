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
import os
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


ROOT = Path(__file__).resolve().parent
PROJECT_ID = "relationship-graph"
RELATIONSHIP_WINDOW_RADIUS = 4
RELATIONSHIP_WINDOW_MENTION_LIMIT = 30
RELATIONSHIP_OUTPUT_LIMIT = 8000
SOURCE_DOCUMENT_DETECTOR = "source_document"
SOURCE_OUTLET_DETECTOR = "source_outlet"
SOURCE_TITLE_DETECTOR = "source_title"
SOURCE_PROVENANCE_DETECTORS = {SOURCE_DOCUMENT_DETECTOR, SOURCE_OUTLET_DETECTOR}
SOURCE_DOCUMENT_RELATIONSHIP_CATEGORIES = {"frequencies"}
SOURCE_TITLE_RELATIONSHIP_WEIGHT = 50
SOURCE_TITLE_EXCLUDED_CATEGORIES = {
    "document_names",
    "websites",
    "ip_addresses",
    "gps_coordinates",
}
SOURCE_OUTLET_RULES = [
    ("American Alchemy", "newsrooms", re.compile(r"\bAmerican\s+Alchemy\b|AmericanAlchemy", re.I)),
]
DATA_DIR = ROOT / "data"
DEFAULT_SOURCE_DATA_DIR = ROOT.parent / "data" / "data"
LEGACY_SOURCE_DATA_DIR = ROOT.parent / "uap-data" / "data"
CONFIGURED_SOURCE_DATA_DIR = os.environ.get("UFO_FILES_DATA_DIR") or os.environ.get("UAP_DATA_DIR")
SOURCE_DATA_DIR = Path(
    CONFIGURED_SOURCE_DATA_DIR
    or (
        DEFAULT_SOURCE_DATA_DIR
        if DEFAULT_SOURCE_DATA_DIR.exists()
        else LEGACY_SOURCE_DATA_DIR
        if LEGACY_SOURCE_DATA_DIR.exists()
        else DATA_DIR
    )
)
if not SOURCE_DATA_DIR.is_absolute():
    SOURCE_DATA_DIR = ROOT / SOURCE_DATA_DIR
SOURCE_DATA_DIR = SOURCE_DATA_DIR.resolve()
TRANSCRIPTS_DIR = SOURCE_DATA_DIR / "transcripts"
REGISTRY_PATH = TRANSCRIPTS_DIR / "entity-registry.json"
README_PATH = ROOT / "README.md"
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


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return os.path.relpath(path.resolve(), ROOT)

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
        "A.D. After Disclosure",
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
        "Galactic Federation",
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
OCR_FRAGMENT_DOMAIN_PREFIXES = {
    "a",
    "age",
    "al",
    "at",
    "ca",
    "du",
    "e",
    "fa",
    "ha",
    "i",
    "in",
    "intelle",
    "ju",
    "ma",
    "o",
    "pa",
    "sec",
    "so",
    "t",
    "th",
    "ti",
}
COMMON_DOMAIN_SUFFIXES = {
    "ai",
    "biz",
    "ca",
    "com",
    "edu",
    "gov",
    "info",
    "io",
    "mil",
    "net",
    "org",
    "us",
}
IP_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
GPS_RE = re.compile(r"\b[-+]?(?:[1-8]?\d(?:\.\d+)?|90(?:\.0+)?),\s*[-+]?(?:(?:1[0-7]\d|\d?\d)(?:\.\d+)?|180(?:\.0+)?)\b")
FREQ_RE = re.compile(
    r"\b\d{1,9}(?:\.\d{1,4})?\s?(?:Hz|kHz|MHz|GHz|THz|hertz|kilohertz|megahertz|gigahertz|terahertz)\b",
    re.I,
)
FREQ_RANGE_RE = re.compile(
    r"\b\d{1,9}(?:\.\d{1,4})?\s*(?:to|-|–)\s*\d{1,9}(?:\.\d{1,4})?\s*"
    r"(?:Hz|kHz|MHz|GHz|THz|hertz|kilohertz|megahertz|gigahertz|terahertz)\b",
    re.I,
)
FREQUENCY_UNIT_ALIASES = {
    "hz": "Hz",
    "hertz": "Hz",
    "khz": "kHz",
    "kilohertz": "kHz",
    "mhz": "MHz",
    "megahertz": "MHz",
    "ghz": "GHz",
    "gigahertz": "GHz",
    "thz": "THz",
    "terahertz": "THz",
}
FREQUENCY_UNIT_MULTIPLIERS = {
    "Hz": 1.0,
    "kHz": 1_000.0,
    "MHz": 1_000_000.0,
    "GHz": 1_000_000_000.0,
    "THz": 1_000_000_000_000.0,
}
FREQUENCY_UNIT_ORDER = ("THz", "GHz", "MHz", "kHz", "Hz")
FREQUENCY_BAND_ALIASES = {
    "extra low frequency": "extremely low frequency",
}
FREQUENCY_BAND_CODES = {"elf", "slf", "ulf", "vlf", "lf", "mf", "hf", "vhf", "uhf", "shf", "ehf"}
FREQ_BAND_RE = re.compile(
    r"\b(?:(?:extremely|extra|very|ultra)\s+low\s+frequency|very\s+high\s+frequency|ultra\s+high\s+frequency|"
    r"(?:ELF|SLF|ULF|VLF|LF|MF|HF|VHF|UHF|SHF|EHF)\s+(?:frequency|frequencies|band|signal|wave|waves))\b",
    re.I,
)
RADIO_TERM_RE = re.compile(r"\b(?:radio frequenc(?:y|ies)|VHF radio|UHF radio|CB radio|guard frequency)\b", re.I)
RADIO_RE = re.compile(r"\b(?:1[3-7]\d|4[0-9]\d|8[0-9]\d)\.\d{3,4}\b")
GPS_CONTEXT_RE = re.compile(r"\b(?:gps|coordinates?|coord(?:inate)?s?|latitude|longitude|lat(?:itude)?|lon(?:gitude)?|geolocation|geo[- ]?located)\b", re.I)
IP_CONTEXT_RE = re.compile(r"\b(?:ip\s+address|ipv4)\b", re.I)
RADIO_CONTEXT_RE = re.compile(r"\b(?:radio|frequency|frequencies|mhz|vhf|uhf|channel|guard|comm(?:s|unication)?)\b", re.I)
LIGHT_PHENOMENA_OCR_NAMES = {"light phenoa", "light phenom", "light phenon", "light phenos", "light phenow"}
BIRD_TABLE_OCR_PREFIXES = {"bicds", "binds", "bird", "birds", "bords"}
FREQUENCY_CONCEPT_ALIASES = {
    "frequency affec": ("Frequency Affected", "key_terms"),
    "frequency affected": ("Frequency Affected", "key_terms"),
    "frequency ultraviolet frequency": ("Ultraviolet Frequency", "key_terms"),
    "high frequency active auroral": ("High Frequency Active Auroral Research Program", "government_project_codenames"),
    "high frequency gravitational wave": ("High Frequency Gravitational Waves", "key_terms"),
    "high frequency gravitational waves": ("High Frequency Gravitational Waves", "key_terms"),
    "radio frequency electromagnetic fields": ("Radio Frequency Electromagnetic Fields", "key_terms"),
    "radiofrequency electromagnetic fields": ("Radio Frequency Electromagnetic Fields", "key_terms"),
}
FREQUENCY_KEY_TERM_NAMES = {
    "charts showing frequency",
    "effects frequency",
    "frequency",
    "frequency distribution",
    "frequency following response",
    "guard frequency",
    "radio frequency",
    "radio frequencies",
    "twilight frequency",
}
FREQUENCY_TECHNOLOGY_WORDS = {
    "agile",
    "digitally",
    "enabled",
    "electronic",
    "electronics",
    "gap",
    "integrated",
    "semiconductor",
    "sources",
    "synthesized",
    "technology",
    "vacuum",
    "wide",
}
FREQUENCY_SIGNAL_WORDS = {
    "electric",
    "electromagnetic",
    "field",
    "fields",
    "gravitational",
    "infrared",
    "radio",
    "super",
    "ultraviolet",
    "voice",
    "wave",
    "waves",
}
SIGNAL_UNIT_WORDS = {
    "hz",
    "hertz",
    "khz",
    "kilohertz",
    "mhz",
    "megahertz",
    "ghz",
    "gigahertz",
    "thz",
    "terahertz",
}
SIGNAL_TECH_WORDS = {
    "amplifier",
    "band",
    "bands",
    "detector",
    "device",
    "electronics",
    "focal",
    "frequencies",
    "frequency",
    "imaging",
    "radar",
    "receiver",
    "signal",
    "signals",
    "transistor",
    "wave",
    "waves",
}
PENTAGON_DOCUMENT_PHRASE_WORDS = {
    "allies",
    "covert",
    "former",
    "obtain",
    "official",
    "plans",
    "releases",
    "reveals",
    "told",
    "vietnam",
}
PENTAGON_KEY_TERM_PHRASES = {
    "pentagon monitor": "Pentagon Monitor",
    "pentagon operational test": "Pentagon Operational Test",
    "pentagon records group": "Pentagon Records Group",
    "pentagon special access program": "Pentagon Special Access Program",
    "pentagon special programs": "Pentagon Special Programs",
}
PENTAGON_ORG_PHRASES = {
    "pentagon information office": "Pentagon Information Office",
    "pentagon national military": "National Military Command Center",
}
UNIVERSAL_ORIGIN_NON_SPECIES_PREFIXES = {
    "almanac",
    "camera",
    "digital",
}
MEASUREMENT_FIELD_NAMES = {
    "angular acceleration": "Angular Acceleration",
    "angular velocity": "Angular Velocity",
    "appearance bearing": "Appearance Bearing",
    "color group": "Color Group",
    "disappearance bearing": "Disappearance Bearing",
    "final elevation": "Final Elevation",
    "initial bearing": "Initial Bearing",
    "initial elevation": "Initial Elevation",
    "light brightness": "Light Brightness",
    "light color": "Light Color",
    "object color": "Object Color",
    "orientation": "Orientation",
    "shape description": "Shape Description",
    "sound": "Sound",
    "speed": "Speed",
}
DATE_RE = re.compile(
    r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},?\s+\d{2,4}|"
    r"\d{1,2}:\d{2}(?:\s?[ap]\.?m\.?)?)\b",
    re.I,
)
MONTH_OR_WEEKDAY_WORDS = {
    "jan",
    "january",
    "feb",
    "february",
    "mar",
    "march",
    "apr",
    "april",
    "may",
    "jun",
    "june",
    "jul",
    "july",
    "aug",
    "august",
    "sep",
    "sept",
    "september",
    "oct",
    "october",
    "nov",
    "november",
    "dec",
    "december",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}
DATE_CONTEXT_PREFIXES = {
    "about",
    "accepted",
    "accessed",
    "after",
    "around",
    "before",
    "between",
    "by",
    "during",
    "early",
    "effective",
    "established",
    "from",
    "in",
    "late",
    "on",
    "published",
    "received",
    "released",
    "since",
    "throughout",
}
TIME_ZONE_RE = re.compile(
    r"\b(?:Greenwich|Mountain|Pacific|Central|Eastern|Zulu)(?:\s+[A-Z]\.){0,2}\s+(?:Standard\s+)?Time\b",
    re.I,
)
BLOOD_RE = re.compile(r"(?<![A-Za-z]-)(?<![A-Za-z0-9])(?:AB|A|B|O)[+-](?![A-Za-z0-9-])")
BLOOD_CONTEXT_RE = re.compile(
    r"\b(?:blood|bloodline|bloodlines|blood\s+type|blood\s+types|type|rh|rhesus|plasma|donor|donors|negative|positive)\b",
    re.I,
)
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
    r"\b(?:Department|Agency|Administration|Bureau|Office|Ministry|Command|Committee|Commission|Council|Board|Panel|Secretary|"
    r"Forest\s+Service|Geological\s+Service|Health\s+Service|Selective\s+Service|Strategic\s+Services|Technical\s+Services)\b",
    re.I,
)
COMPANY_ORG_NAME_RE = re.compile(r"\b(?:Corporation|Company|Companies|Co\.?|Inc\.?|LLC|Ltd\.?|Limited)\b", re.I)
COMPANY_BRAND_RE = re.compile(
    r"\b(?:Avro|Battelle|Bell|Boeing|Convair|Douglas|Fairchild|General\s+Dynamics|Grumman|Hughes|Lockheed|Martin|McDonnell|Northrop|Raytheon|Vought)\b",
    re.I,
)
GENERIC_AIRCRAFT_OR_TECH_RE = re.compile(r"\b(?:Aerospace|Aircraft|Aeronautics|Systems|Technologies)\b", re.I)
GOVERNMENT_ROLE_GROUP_RE = re.compile(r"\b(?:Officers|Officials|Agents|Postal\s+Service|Secret\s+Service)\b", re.I)
RESEARCH_ROLE_GROUP_RE = re.compile(r"\b(?:Scientists|Researchers|Technicians|Engineers)\b", re.I)
DOCUMENT_NAME_RE = re.compile(r"\b(?:Act|Award|Form|Medal|Memo|Memorandum|Report|Reports)\b", re.I)
NEWSROOM_BLOCK_RE = re.compile(r"\b(?:Command\s+Post|Post\s+Office|Network\s+Command|Network\s+Systems)\b", re.I)
GENERIC_ORG_DESCRIPTOR_RE = re.compile(r"\b(?:Center|Centre|Command|Control|Division|Service|Services|Staff|Systems)\b", re.I)
SYSTEMS_TERM_RE = re.compile(r"\b(?:Systems|System)\b", re.I)
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

NON_ENTITY_LABEL_NAMES = {
    "activity description",
    "additional avionics",
    "additional details",
    "aircraft airspeed",
    "aircraft altitude",
    "aircraft callsign",
    "aircraft heading",
    "aircraft location",
    "aircraft tail number",
    "arrive on station",
    "asset type",
    "contact longitude",
    "data link",
    "defense advanced research",
    "economic assumptions",
    "event description",
    "event type",
    "full name",
    "full names",
    "friendly aircraft altitude",
    "friendly aircraft location",
    "friendly aircraft speed",
    "friendly aircraft state",
    "friendly aircraft trajectory",
    "ground station callsign",
    "image file name",
    "initial contact",
    "intel gap filled",
    "last engine shutdown time",
    "last land location",
    "last land time",
    "maneuverability observations",
    "mission canceled",
    "mission data",
    "mission type",
    "msn type",
    "num chaff",
    "num flares",
    "num gun rounds",
    "observer actions",
    "on station",
    "pod name",
    "precoord effectiveness",
    "precoord time",
    "primary sensor",
    "radar tests conrad okay",
    "request number",
    "sensors available",
    "supported operation",
    "supported unit",
    "tail number",
    "takeoff location",
    "takeoff time",
    "tasked start point",
    "tasking type",
    "time off station",
    "time on station",
    "timeline takeoff",
    "total mission time",
    "total time on station",
}

STRUCTURED_KEY_TERM_NAMES = {
    "accuracy",
    "anomalous characteristics",
    "anamolous characteristics",
    "associated caveats",
    "call sign",
    "country tasked",
    "chaff designator",
    "et al",
    "first coordinate",
    "first name unknown",
    "first seen location",
    "first seen radius",
    "flare designator",
    "free world",
    "gun name",
    "insufficient info",
    "insufficient information",
    "kinetic depth",
    "kinetic depth accuracy",
    "kinetic trajectory",
    "kinetic trajectory accuracy",
    "last accuracy",
    "last coordinate",
    "last seen radius",
    "enemy aircraft",
    "enemy aircraft airspeed",
    "enemy aircraft altitude",
    "enemy aircraft heading",
    "enemy aircraft location",
    "enemy aircraft nationality",
    "enemy aircraft type",
    "fiscal year",
    "fiscal years",
    "flying saucer type aircraft",
    "radar software load",
    "radar name",
    "radar warning receiver",
    "receiver aircraft",
    "receiver aircraft type",
    "report type",
    "short title",
    "software load",
    "special assistant",
    "submit date",
    "tasking order",
    "towed decoy name",
    "towed decoy software load",
    "trajectory",
    "unidentified aircraft",
}

FIELD_LABEL_WORDS = {
    "accuracy",
    "airspeed",
    "altitude",
    "aircraft",
    "airspace",
    "caveat",
    "caveats",
    "command",
    "commands",
    "contact",
    "coordinate",
    "coordinates",
    "data",
    "date",
    "description",
    "designator",
    "event",
    "features",
    "figure",
    "fiscal",
    "first",
    "full",
    "birth",
    "case",
    "incident",
    "incidents",
    "initial",
    "last",
    "latitude",
    "load",
    "location",
    "locations",
    "longitude",
    "mission",
    "name",
    "number",
    "observer",
    "observers",
    "order",
    "other",
    "page",
    "radius",
    "rating",
    "report",
    "section",
    "seen",
    "short",
    "software",
    "station",
    "submit",
    "system",
    "table",
    "task",
    "tasking",
    "time",
    "title",
    "trajectory",
    "type",
    "witness",
    "witnesses",
    "year",
    "years",
}

STRUCTURED_KEY_TERM_SUFFIXES = {
    "accuracy",
    "caveats",
    "characteristics",
    "changed",
    "date",
    "depth",
    "designator",
    "impact",
    "info",
    "information",
    "load",
    "mission",
    "name",
    "order",
    "page",
    "radius",
    "section",
    "time",
    "trajectory",
    "type",
    "written",
}

STRUCTURED_KEY_TERM_PREFIXES = {
    "anomalous",
    "anamolous",
    "associated",
    "bulk",
    "chaff",
    "code",
    "country",
    "current",
    "date",
    "description",
    "due",
    "first",
    "flare",
    "gun",
    "kinetic",
    "mission",
    "name",
    "number",
    "official",
    "original",
    "radar",
    "senate",
    "software",
    "submit",
    "tasking",
    "time",
    "towed",
    "white",
}

NON_ENTITY_LABEL_SUFFIXES = {
    "actions",
    "airspeed",
    "altitude",
    "assumptions",
    "available",
    "callsign",
    "canceled",
    "data",
    "description",
    "designator",
    "effectiveness",
    "filled",
    "heading",
    "location",
    "name",
    "number",
    "observations",
    "operation",
    "rounds",
    "speed",
    "state",
    "time",
    "trajectory",
    "type",
    "unit",
}

NON_ENTITY_LABEL_PREFIXES = {
    "activity",
    "additional",
    "aircraft",
    "asset",
    "contact",
    "economic",
    "event",
    "flare",
    "flight",
    "friendly",
    "ground",
    "image",
    "initial",
    "intel",
    "last",
    "mission",
    "msn",
    "num",
    "observer",
    "pod",
    "precoord",
    "primary",
    "request",
    "response",
    "sensors",
    "supported",
    "tail",
    "takeoff",
    "tasked",
    "tasking",
    "time",
    "timeline",
    "total",
}

SPEAKER_LABEL_FRAGMENT_PREFIXES = {"conrad", "cooper"}
SPEAKER_LABEL_FRAGMENT_ALLOWED_NAMES = {
    "conrad quimby",
}

TABLE_OR_REPORT_LABEL_RE = re.compile(
    r"\b(?:appendix|classification|declassification|doubtful|doubtfull|doubttull|evaluation|figure|"
    r"per\s+cent|reprogrammings|serial|table|total\s+(?:adjustments|certain|congressional|reprogrammings))\b",
    re.I,
)

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
    mentions = extract_mentions(segments, dictionaries, omit_terms)
    mentions = add_source_title_mentions(segments, mentions, dictionaries, omit_terms)
    mentions = resolve_competing_mentions(mentions)
    mentions = apply_review_to_mentions(mentions, review)
    mentions = add_source_provenance_mentions(segments, mentions)
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
        review["source_path"] = display_path(path)
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
        review["note"] = f"Derived from {display_path(export_path)} because no reclass.json was present."
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
        if rows:
            segments.append(
                Segment(
                    id=source_title_segment_id(transcript_id),
                    transcript_id=transcript_id,
                    transcript_title=title,
                    source_file=path.name,
                    start_ms=-1,
                    end_ms=0,
                    text=title,
                )
            )
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


def source_title_segment_id(transcript_id: str) -> str:
    return f"seg-{transcript_id}-title"


def is_source_title_segment(segment: Segment) -> bool:
    return segment.id == source_title_segment_id(segment.transcript_id)


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
        if is_source_title_segment(segment):
            continue
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


def add_source_title_mentions(
    segments: list[Segment],
    mentions: list[Mention],
    dictionaries: dict[str, list[str]],
    omit_terms: set[str],
) -> list[Mention]:
    title_segments = [segment for segment in segments if is_source_title_segment(segment)]
    if not title_segments:
        return mentions

    seen_mentions = {(mention.segment_id, mention.entity_id, mention.detector) for mention in mentions}
    candidates: dict[tuple[str, str], tuple[str, str, float, str]] = {}

    def add_candidate(name: str, category: str, confidence: float, reason: str) -> None:
        if category in SOURCE_TITLE_EXCLUDED_CATEGORIES:
            return
        normalized = normalize_name(name)
        if len(normalized) < 3 or normalized in omit_terms:
            return
        if category in PERSON_LIKE_CATEGORIES and len(normalized.split()) < 2:
            return
        key = (canonicalize(name, category), category)
        current = candidates.get(key)
        if current and current[2] >= confidence:
            return
        candidates[key] = (name.strip(), category, confidence, reason)

    for category, terms in dictionaries.items():
        for term in terms:
            add_candidate(term, category, 0.92, f"Source title matched curated term in {label(category)}")

    for mention in mentions:
        add_candidate(
            mention.name,
            mention.category,
            min(0.86, max(0.72, mention.confidence * 0.9)),
            f"Source title matched known corpus entity in {label(mention.category)}",
        )

    ordered_candidates = sorted(candidates.values(), key=lambda item: (-len(item[0]), item[1], item[0].lower()))
    for segment in title_segments:
        title_text = segment.text
        lower = title_text.lower()
        for name, category, confidence, reason in ordered_candidates:
            if name.lower() not in lower:
                continue
            pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])", re.I)
            for match in pattern.finditer(title_text):
                add_mention(
                    mentions,
                    seen_mentions,
                    segment,
                    name=match.group(0),
                    category=category,
                    detector=SOURCE_TITLE_DETECTOR,
                    confidence=confidence,
                    reason=reason,
                    excerpt=excerpt(title_text, match.start(), match.end()),
                )

        for item in pattern_mentions(segment):
            if normalize_name(item["name"]) in omit_terms:
                continue
            add_mention(
                mentions,
                seen_mentions,
                segment,
                name=item["name"],
                category=item["category"],
                detector=SOURCE_TITLE_DETECTOR,
                confidence=item["confidence"],
                reason=f"Source title {item['reason'][0].lower()}{item['reason'][1:]}",
                excerpt=item["excerpt"],
            )

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
        ("key_terms", FREQ_BAND_RE, "regex:frequency_band", 0.88, "Matched named frequency band term"),
        ("radio_frequencies", RADIO_RE, "regex:radio_frequency", 0.92, "Matched radio-style decimal frequency"),
        ("key_terms", RADIO_TERM_RE, "regex:radio_frequency_term", 0.84, "Matched generic radio frequency phrase"),
        ("dates_times", DATE_RE, "regex:datetime", 0.86, "Matched date/time expression"),
        ("blood_types", BLOOD_RE, "regex:blood_type", 0.92, "Matched blood type notation"),
        ("patents", PATENT_RE, "regex:patent", 0.72, "Matched patent phrase"),
    ]:
        for match in regex.finditer(text):
            name = match.group(0).strip()
            if category == "websites" and is_ocr_fragment_domain(name):
                continue
            if not is_valid_pattern_mention(category, detector, name, text, match.start(), match.end()):
                continue
            if detector in {"regex:frequency", "regex:frequency_range"}:
                name = normalize_frequency_name(name)
            elif detector == "regex:frequency_band":
                name = normalize_frequency_band_name(name)
            elif detector == "regex:radio_frequency_term":
                name = normalize_radio_frequency_name(name)
            items.append(
                {
                    "name": name,
                    "category": category,
                    "detector": detector,
                    "confidence": confidence,
                    "reason": reason,
                    "excerpt": excerpt(text, match.start(), match.end()),
                }
            )

    return items


def is_valid_pattern_mention(category: str, detector: str, name: str, text: str, start: int, end: int) -> bool:
    context = text[max(0, start - 90) : min(len(text), end + 90)]
    if category == "gps_coordinates":
        return bool(GPS_CONTEXT_RE.search(context)) and gps_coordinate_has_decimal_pair(name)
    if category == "ip_addresses":
        return bool(IP_CONTEXT_RE.search(context))
    if detector == "regex:radio_frequency":
        return bool(RADIO_CONTEXT_RE.search(context))
    if detector == "regex:frequency" and is_embedded_frequency_range_tail(text, start):
        return False
    if detector in {"regex:frequency", "regex:frequency_range"}:
        return frequency_has_nonzero_value(name)
    if detector == "regex:blood_type":
        return bool(BLOOD_CONTEXT_RE.search(context))
    return True


def is_embedded_frequency_range_tail(text: str, start: int) -> bool:
    prefix = text[max(0, start - 8) : start].lower()
    return bool(re.search(r"(?:-|–|\bto\s+)$", prefix))


def frequency_has_nonzero_value(name: str) -> bool:
    values = re.findall(r"\d+(?:\.\d+)?", name)
    return any(float(value) > 0 for value in values)


def gps_coordinate_has_decimal_pair(name: str) -> bool:
    parts = [part.strip() for part in name.split(",", 1)]
    return len(parts) == 2 and all("." in part for part in parts)


def is_ocr_fragment_domain(name: str) -> bool:
    lowered = name.strip().strip(".,;:)]}").lower()
    if lowered.startswith(("http://", "https://", "www.")):
        return False
    host = lowered.split("/", 1)[0]
    parts = host.split(".")
    if len(parts) < 2:
        return False
    prefix = parts[0]
    suffix = parts[-1]
    if prefix in OCR_FRAGMENT_DOMAIN_PREFIXES:
        return True
    if suffix not in COMMON_DOMAIN_SUFFIXES:
        return True
    return False


def person_mentions(segment: Segment, omit_terms: set[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    text = segment.text
    for match in PERSON_RE.finditer(text):
        raw = re.sub(
            r"^(?:Capt(?:ain)?|Col(?:onel)?|Dr|Gen(?:eral)?|Lt|Mr|Mrs|Ms|Observer|Pilot|Prof(?:essor)?|Rep|Sen(?:ator)?|The)\.?\s+",
            "",
            match.group(0).strip(),
            flags=re.I,
        )
        name = re.sub(r"\s+", " ", raw)
        if len(name) < 5 or normalize_name(name) in omit_terms:
            continue
        if len(normalize_name(name).split()) < 2:
            continue
        if MALFORMED_SERVICE_FRAGMENT_RE.match(name):
            continue
        if any(part.lower() in {"the", "and", "but", "you", "this", "that"} for part in name.split()):
            continue
        context = excerpt(text, match.start(), match.end(), width=220)
        if is_date_like_name(name):
            items.append(
                {
                    "name": name,
                    "category": "dates_times",
                    "detector": "heuristic:date_like_name",
                    "confidence": 0.7,
                    "reason": "Date-like phrase matched month or weekday context",
                    "excerpt": context,
                }
            )
            continue
        if is_hard_non_entity_name(name):
            continue
        if normalize_name(name) in LIGHT_PHENOMENA_OCR_NAMES:
            items.append(
                {
                    "name": "Light Phenomena",
                    "category": "key_terms",
                    "detector": "heuristic:light_phenomena_ocr",
                    "confidence": 0.86,
                    "reason": "OCR variant matched Light Phenomena key term",
                    "excerpt": context,
                }
            )
            continue
        bird_table_name = canonical_bird_table_artifact_name(name)
        if bird_table_name:
            items.append(
                {
                    "name": bird_table_name,
                    "category": "key_terms",
                    "detector": "heuristic:bird_table_ocr",
                    "confidence": 0.78,
                    "reason": "OCR-coded table artifact matched Birds key term",
                    "excerpt": context,
                }
            )
            continue
        frequency_concept = classify_frequency_concept_name(name)
        if frequency_concept:
            frequency_name, frequency_category = frequency_concept
            items.append(
                {
                    "name": frequency_name,
                    "category": frequency_category,
                    "detector": "heuristic:frequency_concept",
                    "confidence": 0.78,
                    "reason": f"Frequency concept matched {label(frequency_category)}",
                    "excerpt": context,
                }
            )
            continue
        universal_origin = classify_universal_origin_name(name)
        if universal_origin:
            origin_name, origin_category = universal_origin
            items.append(
                {
                    "name": origin_name,
                    "category": origin_category,
                    "detector": "heuristic:universal_origin",
                    "confidence": 0.8,
                    "reason": f"Universal Origin phrase matched {label(origin_category)}",
                    "excerpt": context,
                }
            )
            continue
        pentagon_phrase = classify_pentagon_phrase_name(name)
        if pentagon_phrase:
            pentagon_name, pentagon_category = pentagon_phrase
            items.append(
                {
                    "name": pentagon_name,
                    "category": pentagon_category,
                    "detector": "heuristic:pentagon_phrase",
                    "confidence": 0.78,
                    "reason": f"Pentagon phrase matched {label(pentagon_category)}",
                    "excerpt": context,
                }
            )
            continue
        signal_technology_category = classify_signal_technology_name(name)
        if signal_technology_category:
            items.append(
                {
                    "name": name,
                    "category": signal_technology_category,
                    "detector": "heuristic:signal_technology_name",
                    "confidence": 0.7,
                    "reason": f"Signal-unit technical phrase matched {label(signal_technology_category)}",
                    "excerpt": context,
                }
            )
            continue
        measurement_field_name = canonical_measurement_field_name(name)
        if measurement_field_name:
            items.append(
                {
                    "name": measurement_field_name,
                    "category": "key_terms",
                    "detector": "heuristic:measurement_field",
                    "confidence": 0.82,
                    "reason": "Project Blue Book measurement/codebook field matched key term",
                    "excerpt": context,
                }
            )
            continue
        structured_label_category = classify_structured_label_name(name)
        if structured_label_category:
            items.append(
                {
                    "name": name,
                    "category": structured_label_category,
                    "detector": "heuristic:structured_label",
                    "confidence": 0.72,
                    "reason": f"Structured field-label heuristic matched {label(structured_label_category)}",
                    "excerpt": context,
                }
            )
            continue
        if is_non_entity_label(name):
            continue
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


def is_non_entity_label(name: str) -> bool:
    normalized = normalize_name(name)
    words = normalized.split()
    if normalized in NON_ENTITY_LABEL_NAMES:
        return True
    if is_speaker_label_fragment(words):
        return True
    if is_enumerated_label_fragment(words):
        return True
    if is_field_label_only_name(words):
        return True
    if TABLE_OR_REPORT_LABEL_RE.search(name):
        return True
    if len(words) < 2 or len(words) > 4:
        return False
    if words[0] in NON_ENTITY_LABEL_PREFIXES and words[-1] in NON_ENTITY_LABEL_SUFFIXES:
        return True
    if words[0] == "num":
        return True
    return False


def is_hard_non_entity_name(name: str) -> bool:
    normalized = normalize_name(name)
    words = normalized.split()
    if not words:
        return True
    if "number per" in normalized or "per cent" in normalized or "pes gent" in normalized or "pex cent" in normalized:
        return True
    if all(len(word) == 1 for word in words):
        return True
    if len(words) == 2 and words[-1] in {"date", "location", "name", "number", "page", "section", "time"}:
        return True
    if words[0] in DATE_CONTEXT_PREFIXES and len(words[-1]) == 1:
        return True
    if is_generic_aircraft_junk_phrase(words):
        return True
    return False


def is_generic_aircraft_junk_phrase(words: list[str]) -> bool:
    if not words or words[0] != "aircraft":
        return False
    if len(words) == 1:
        return True
    if any(len(word) <= 2 for word in words[1:]):
        return True
    if any(word in {"cailsign", "carri", "commmications", "numbenta", "numbents", "numben"} for word in words[1:]):
        return True
    return False


def is_enumerated_label_fragment(words: list[str]) -> bool:
    if len(words) < 2:
        return False
    if words[0] in {"section", "see"} and "section" in words:
        return True
    if words[0] == "location":
        return True
    if len(words[0]) == 1 and any(word in FIELD_LABEL_WORDS or word in MONTH_OR_WEEKDAY_WORDS or word in {"am", "pm"} for word in words[1:]):
        return True
    if len(words) >= 3 and len(words[0]) == 1 and len(words[1]) == 1 and any(word in FIELD_LABEL_WORDS or word in MONTH_OR_WEEKDAY_WORDS or word in {"am", "pm"} for word in words[2:]):
        return True
    return False


def is_generic_aircraft_or_tech_phrase(name: str) -> bool:
    if not GENERIC_AIRCRAFT_OR_TECH_RE.search(name):
        return False
    if COMPANY_BRAND_RE.search(name):
        return False
    normalized = normalize_name(name)
    words = normalized.split()
    if not words:
        return False
    if words[0] in {"aircraft", "aerospace", "aeronautics", "systems", "technologies", "unmanned", "unidentified", "tactical"}:
        return True
    if any(word in FIELD_LABEL_WORDS for word in words):
        return True
    return False


def is_date_like_name(name: str) -> bool:
    normalized = normalize_name(name)
    words = normalized.split()
    if not words:
        return False
    has_calendar_word = any(word in MONTH_OR_WEEKDAY_WORDS for word in words)
    if not has_calendar_word:
        return False
    if words[0] in DATE_CONTEXT_PREFIXES:
        return True
    if words[0] in MONTH_OR_WEEKDAY_WORDS and any(word in MONTH_OR_WEEKDAY_WORDS or len(word) == 1 for word in words[1:]):
        return True
    if all(word in MONTH_OR_WEEKDAY_WORDS or word in DATE_CONTEXT_PREFIXES for word in words):
        return True
    return False


def is_field_label_only_name(words: list[str]) -> bool:
    if len(words) < 2 or len(words) > 5:
        return False
    trimmed_words = words[1:] if len(words[0]) == 1 else words
    if len(trimmed_words) < 2:
        return False
    return all(word in FIELD_LABEL_WORDS for word in trimmed_words)


def is_speaker_label_fragment(words: list[str]) -> bool:
    if len(words) < 2:
        return False
    normalized = " ".join(words)
    if normalized in SPEAKER_LABEL_FRAGMENT_ALLOWED_NAMES:
        return False
    if words[0] not in SPEAKER_LABEL_FRAGMENT_PREFIXES:
        return False
    return True


def classify_structured_label_name(name: str) -> str | None:
    normalized = normalize_name(name)
    words = normalized.split()
    if normalized in STRUCTURED_KEY_TERM_NAMES:
        return "key_terms"
    if is_generic_aircraft_or_tech_phrase(name):
        return "key_terms"
    if len(words) < 2 or len(words) > 5:
        return None
    if words[0] in STRUCTURED_KEY_TERM_PREFIXES and words[-1] in STRUCTURED_KEY_TERM_SUFFIXES:
        return "key_terms"
    if normalized.endswith(" software load"):
        return "key_terms"
    return None


def classify_signal_technology_name(name: str) -> str | None:
    words = set(normalize_name(name).split())
    if words.intersection(SIGNAL_UNIT_WORDS) and words.intersection(SIGNAL_TECH_WORDS):
        return "technology"
    return None


def classify_frequency_concept_name(name: str) -> tuple[str, str] | None:
    normalized = normalize_name(name)
    if not normalized:
        return None
    normalized = normalized.replace("radiofrequency", "radio frequency")
    words = normalized.split()
    if not any(word in {"frequency", "frequencies"} for word in words):
        return None
    compact_normalized = " ".join(words)
    if compact_normalized in FREQUENCY_CONCEPT_ALIASES:
        return FREQUENCY_CONCEPT_ALIASES[compact_normalized]
    if compact_normalized in FREQUENCY_KEY_TERM_NAMES:
        return (titleize_words(compact_normalized), "key_terms")
    if normalized in {"radio frequency", "radio frequencies"}:
        return ("radio frequency", "key_terms")
    band_name = normalize_frequency_band_name(normalized)
    if normalize_name(band_name) != normalized:
        return (band_name, "key_terms")
    if normalized in FREQUENCY_BAND_ALIASES:
        return (FREQUENCY_BAND_ALIASES[normalized], "key_terms")
    word_set = set(words)
    if word_set.intersection(FREQUENCY_TECHNOLOGY_WORDS) and not word_set.intersection(FREQUENCY_SIGNAL_WORDS):
        return (titleize_words(compact_normalized), "technology")
    return (titleize_words(normalized), "key_terms")


def classify_universal_origin_name(name: str) -> tuple[str, str] | None:
    normalized = normalize_name(name)
    words = normalized.split()
    if len(words) < 3 or words[-2:] != ["universal", "origin"]:
        return None
    if words[0] in UNIVERSAL_ORIGIN_NON_SPECIES_PREFIXES:
        return (titleize_words(normalized), "key_terms")
    return (titleize_words(normalized), "alien_species")


def classify_pentagon_phrase_name(name: str) -> tuple[str, str] | None:
    normalized = normalize_name(name)
    words = normalized.split()
    if "pentagon" not in words:
        return None
    if normalized == "pentagon":
        return ("Pentagon", "government_agencies")
    if "papers" in words:
        return ("Pentagon Papers", "leaks")
    if normalized in PENTAGON_ORG_PHRASES:
        return (PENTAGON_ORG_PHRASES[normalized], "government_agencies")
    if normalized in PENTAGON_KEY_TERM_PHRASES:
        return (PENTAGON_KEY_TERM_PHRASES[normalized], "key_terms")
    if any(word in PENTAGON_DOCUMENT_PHRASE_WORDS for word in words):
        return (titleize_words(normalized), "document_names")
    if words[0] == "pentagon" and any(word in {"washington", "air", "our"} for word in words):
        return ("Pentagon", "government_agencies")
    if words[0] == "pentagon":
        return (titleize_words(normalized), "key_terms")
    return None


def canonical_bird_table_artifact_name(name: str) -> str | None:
    words = normalize_name(name).split()
    if not words or words[0] not in BIRD_TABLE_OCR_PREFIXES:
        return None
    tail = words[1:]
    if not tail or (len(tail) <= 4 and all(len(word) <= 16 for word in tail)):
        return "Birds"
    return None


def titleize_words(value: str) -> str:
    return " ".join(word.upper() if word in FREQUENCY_BAND_CODES else word.capitalize() for word in normalize_name(value).split())


def canonical_measurement_field_name(name: str) -> str | None:
    normalized = normalize_name(name)
    words = normalized.split()
    if not words:
        return None
    for field, display_name in MEASUREMENT_FIELD_NAMES.items():
        field_words = field.split()
        if words[: len(field_words)] == field_words:
            tail = words[len(field_words) :]
            if not tail or all(word in FIELD_LABEL_WORDS or len(word) <= 4 for word in tail):
                return display_name
        if has_word_sequence(words, field_words) and len(words) <= len(field_words) + 2:
            return display_name
    return None


def has_word_sequence(words: list[str], sequence: list[str]) -> bool:
    if len(sequence) > len(words):
        return False
    return any(words[index : index + len(sequence)] == sequence for index in range(len(words) - len(sequence) + 1))


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
    if TIME_ZONE_RE.search(name):
        return "dates_times"
    if NEWSROOM_BLOCK_RE.search(name):
        return "key_terms"
    if DOCUMENT_NAME_RE.search(name):
        if is_document_title_fragment(name):
            return "key_terms"
        return "document_names"
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
        if is_generic_company_fragment(name):
            return "key_terms"
        return "companies"
    if GENERIC_AIRCRAFT_OR_TECH_RE.search(name) and COMPANY_BRAND_RE.search(name):
        return "contractors"
    generic_category = classify_generic_org_descriptor_name(name)
    if generic_category:
        return generic_category
    return None


def classify_generic_org_descriptor_name(name: str) -> str | None:
    if not GENERIC_ORG_DESCRIPTOR_RE.search(name):
        return None
    if NEWSROOM_NAME_RE.search(name) and not NEWSROOM_BLOCK_RE.search(name):
        return None
    normalized = normalize_name(name)
    words = normalized.split()
    if not words:
        return None
    if len(words) <= 2 and SYSTEMS_TERM_RE.search(name):
        return "key_terms"
    if any(word in {"mission", "reporting", "tracking", "control", "filter", "operations", "intelligence", "security", "air", "naval", "army", "military", "defense", "space"} for word in words):
        return "government_agencies"
    if any(word in {"research", "laboratory", "lab", "scientific", "aeronautical"} for word in words):
        return "research_groups"
    if SYSTEMS_TERM_RE.search(name):
        return "key_terms"
    return "government_agencies"


def is_document_title_fragment(name: str) -> bool:
    normalized = normalize_name(name)
    words = normalized.split()
    if len(words) < 2:
        return True
    if normalized in {
        "also report",
        "be report",
        "now report",
        "others report",
        "previous report",
        "report in",
        "report them",
    }:
        return True
    non_document_words = [word for word in words if word not in {"act", "award", "form", "medal", "memo", "memorandum", "report", "reports"}]
    if non_document_words and all(word in FIELD_LABEL_WORDS for word in non_document_words):
        return True
    return False


def is_generic_company_fragment(name: str) -> bool:
    normalized = normalize_name(name)
    words = normalized.split()
    if not words:
        return True
    if COMPANY_BRAND_RE.search(name):
        return False
    if normalized in {"aircraft co", "aircraft company", "aircraft corporation", "aircraft limited"}:
        return True
    if len(words) <= 2 and words[0] in {"aircraft", "company", "corporation", "limited"}:
        return True
    return False


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


def append_provenance_mention(
    mentions: list[Mention],
    segment: Segment,
    name: str,
    category: str,
    detector: str,
    reason: str,
    excerpt: str,
) -> None:
    canonical = canonicalize(name, category)
    mention_id = f"m-{len(mentions) + 1:07d}"
    mentions.append(
        Mention(
            id=mention_id,
            entity_id=entity_key(canonical, category),
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
            confidence=1.0,
            reason=reason,
        )
    )


def add_source_provenance_mentions(segments: list[Segment], mentions: list[Mention]) -> list[Mention]:
    first_segment_by_transcript: dict[str, Segment] = {}
    outlet_matches_by_transcript: dict[str, dict[tuple[str, str], Segment]] = defaultdict(dict)

    for segment in segments:
        first_segment_by_transcript.setdefault(segment.transcript_id, segment)
        for outlet_name, category, pattern in SOURCE_OUTLET_RULES:
            key = (outlet_name, category)
            if key not in outlet_matches_by_transcript[segment.transcript_id] and pattern.search(segment.text):
                outlet_matches_by_transcript[segment.transcript_id][key] = segment

    existing = {(mention.transcript_id, mention.entity_id, mention.detector) for mention in mentions}
    for transcript_id, first_segment in sorted(first_segment_by_transcript.items(), key=lambda item: item[1].transcript_title.lower()):
        document_name = first_segment.transcript_title
        document_category = "document_names"
        document_entity_id = entity_key(canonicalize(document_name, document_category), document_category)
        document_key = (transcript_id, document_entity_id, SOURCE_DOCUMENT_DETECTOR)
        if document_key not in existing:
            append_provenance_mention(
                mentions,
                first_segment,
                document_name,
                document_category,
                SOURCE_DOCUMENT_DETECTOR,
                "Source document entity for provenance",
                f"Source document: {document_name}",
            )
            existing.add(document_key)

        for (outlet_name, outlet_category), evidence_segment in sorted(outlet_matches_by_transcript.get(transcript_id, {}).items()):
            outlet_entity_id = entity_key(canonicalize(outlet_name, outlet_category), outlet_category)
            outlet_key = (transcript_id, outlet_entity_id, SOURCE_OUTLET_DETECTOR)
            if outlet_key in existing:
                continue
            append_provenance_mention(
                mentions,
                evidence_segment,
                outlet_name,
                outlet_category,
                SOURCE_OUTLET_DETECTOR,
                "Source outlet identified from transcript text",
                clean_text(evidence_segment.text[:500]) or f"Source outlet: {outlet_name}",
            )
            existing.add(outlet_key)

    return mentions


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
    last_reviewed_target = (current_name, current_category, current_id)
    candidates: list[tuple[str, str, str]] = [last_reviewed_target]

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
        next_category = reviewed_category_for_name(next_name, next_category, name_reclassifications)
        target_id = str(merge.get("targetId") or "")
        next_alias = review_alias_for(target_id, next_name, aliases_by_id, aliases_by_name)
        if next_alias:
            next_name = next_alias
            next_category = reviewed_category_for_name(next_name, next_category, name_reclassifications)
        next_id = entity_key(canonicalize(next_name, next_category), next_category)
        next_state = (next_id, normalize_name(next_name), next_category)
        if next_state == state:
            break
        next_candidate = (next_name, next_category, next_id)
        last_reviewed_target = next_candidate
        candidates.append(next_candidate)
        if next_state in seen:
            reviewed_candidates = [
                candidate
                for candidate in candidates
                if name_reclassifications.get(normalize_name(candidate[0])) == candidate[1]
            ]
            if reviewed_candidates:
                return reviewed_candidates[-1]
            if len(candidates) > 1:
                return candidates[1]
            break

        current_id = next_id
        current_name = next_name
        current_category = next_category

    return last_reviewed_target


def apply_review_identity(
    entity_id: str,
    name: str,
    category: str,
    reclassifications: dict[str, Any],
    name_reclassifications: dict[str, Any],
    aliases_by_id: dict[str, Any],
    aliases_by_name: dict[str, Any],
    merges: dict[str, Any],
    name_merges: dict[str, Any],
) -> tuple[str, str, str]:
    current_id = entity_id
    current_name = name
    current_category = category

    alias = review_alias_for(current_id, current_name, aliases_by_id, aliases_by_name)
    if alias:
        current_name = alias
        current_id = entity_key(canonicalize(current_name, current_category), current_category)

    merged_name, merged_category, merged_id = resolve_review_merge_chain(
        current_id,
        current_name,
        current_category,
        merges,
        name_merges,
        aliases_by_id,
        aliases_by_name,
        name_reclassifications,
    )
    current_name = merged_name
    current_category = merged_category
    current_id = merged_id

    target_category = reclassifications.get(current_id) or name_reclassifications.get(normalize_name(current_name))
    if target_category:
        current_category = reviewed_category_for_name(current_name, target_category, name_reclassifications)
        current_id = entity_key(canonicalize(current_name, current_category), current_category)

    alias = review_alias_for(current_id, current_name, aliases_by_id, aliases_by_name)
    if alias:
        current_name = alias
        target_category = name_reclassifications.get(normalize_name(current_name))
        if target_category:
            current_category = reviewed_category_for_name(current_name, target_category, name_reclassifications)
        current_id = entity_key(canonicalize(current_name, current_category), current_category)

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
    name_reclassifications = {normalize_name(key): value for key, value in review.get("nameReclassifications", {}).items()}
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

        reviewed_name, reviewed_category, reviewed_id = apply_review_identity(
            mention.entity_id,
            mention.name,
            mention.category,
            reclassifications,
            name_reclassifications,
            aliases_by_id,
            aliases_by_name,
            merges,
            name_merges,
        )
        mention.name = reviewed_name
        mention.category = reviewed_category
        mention.category_label = label(reviewed_category)
        mention.entity_id = reviewed_id
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


def build_source_document_relationships(mentions: list[Mention], entities: list[Entity]) -> list[Relationship]:
    entity_by_id = {entity.id: entity for entity in entities}
    document_by_transcript: dict[str, Mention] = {}
    for mention in mentions:
        if mention.detector == SOURCE_DOCUMENT_DETECTOR and mention.entity_id in entity_by_id:
            document_by_transcript[mention.transcript_id] = mention

    target_mentions_by_pair: dict[tuple[str, str, str], list[Mention]] = defaultdict(list)
    for mention in mentions:
        document = document_by_transcript.get(mention.transcript_id)
        if not document or mention.entity_id == document.entity_id:
            continue
        if mention.detector == SOURCE_OUTLET_DETECTOR:
            target_mentions_by_pair[(document.entity_id, mention.entity_id, "source_outlet")].append(mention)
            continue
        if mention.detector == SOURCE_TITLE_DETECTOR:
            target_mentions_by_pair[(document.entity_id, mention.entity_id, "source_mentions")].append(mention)
            continue
        if mention.detector in SOURCE_PROVENANCE_DETECTORS:
            continue
        if mention.category in SOURCE_DOCUMENT_RELATIONSHIP_CATEGORIES:
            target_mentions_by_pair[(document.entity_id, mention.entity_id, "source_mentions")].append(mention)

    relationships: list[Relationship] = []
    for index, ((source_id, target_id, rel_type), evidence_mentions) in enumerate(
        sorted(
            target_mentions_by_pair.items(),
            key=lambda item: (
                item[0][2],
                entity_by_id.get(item[0][0]).name.lower() if entity_by_id.get(item[0][0]) else "",
                entity_by_id.get(item[0][1]).name.lower() if entity_by_id.get(item[0][1]) else "",
            ),
        )
    ):
        source_entity = entity_by_id.get(source_id)
        target_entity = entity_by_id.get(target_id)
        if not source_entity or not target_entity:
            continue
        evidence_mentions = sorted(evidence_mentions, key=lambda mention: (-mention.confidence, mention.start_ms, mention.id))
        evidence = [
            {
                "segment_id": mention.segment_id,
                "transcript": mention.transcript_title,
                "timestamp": mention.timestamp,
                "excerpt": mention.excerpt,
                "reason": "Source document mentions this entity" if rel_type == "source_mentions" else mention.reason,
                "relationship_type": rel_type,
            }
            for mention in evidence_mentions[:6]
        ]
        relationships.append(
            Relationship(
                id=f"rel-source-{index + 1:06d}",
                source=source_entity.id,
                target=target_entity.id,
                source_name=source_entity.name,
                target_name=target_entity.name,
                type=rel_type,
                weight=len(evidence_mentions),
                evidence_segment_ids=[item["segment_id"] for item in evidence],
                evidence=evidence,
                confidence=round(sum(mention.confidence for mention in evidence_mentions) / max(1, len(evidence_mentions)), 3),
            )
        )
    return relationships


def build_source_title_relationships(mentions: list[Mention], entities: list[Entity]) -> list[Relationship]:
    entity_by_id = {entity.id: entity for entity in entities}
    mentions_by_segment: dict[str, list[Mention]] = defaultdict(list)
    for mention in mentions:
        if mention.detector == SOURCE_TITLE_DETECTOR and mention.entity_id in entity_by_id:
            mentions_by_segment[mention.segment_id].append(mention)

    relationships: list[Relationship] = []
    seen_pairs: set[tuple[str, str]] = set()
    for segment_id, segment_mentions in sorted(mentions_by_segment.items()):
        segment_mentions = dedupe_mentions_for_segment(segment_mentions)
        segment_mentions.sort(key=lambda mention: (-mention.confidence, mention.name))
        for i, a in enumerate(segment_mentions):
            for b in segment_mentions[i + 1 :]:
                if a.entity_id == b.entity_id:
                    continue
                source, target = sorted([a.entity_id, b.entity_id])
                if (source, target) in seen_pairs:
                    continue
                source_entity = entity_by_id.get(source)
                target_entity = entity_by_id.get(target)
                if not source_entity or not target_entity:
                    continue
                if normalize_name(source_entity.name) == normalize_name(target_entity.name):
                    continue
                seen_pairs.add((source, target))
                evidence = {
                    "segment_id": segment_id,
                    "transcript": a.transcript_title,
                    "timestamp": a.timestamp,
                    "excerpt": a.excerpt,
                    "reason": "Source title names both entities",
                    "relationship_type": "co_mentioned",
                }
                relationships.append(
                    Relationship(
                        id=f"rel-title-{len(relationships) + 1:06d}",
                        source=source_entity.id,
                        target=target_entity.id,
                        source_name=source_entity.name,
                        target_name=target_entity.name,
                        type="co_mentioned",
                        weight=SOURCE_TITLE_RELATIONSHIP_WEIGHT,
                        evidence_segment_ids=[segment_id],
                        evidence=[evidence],
                        confidence=round((a.confidence + b.confidence) / 2, 3),
                    )
                )
    return relationships


def build_relationships(segments: list[Segment], mentions: list[Mention], entities: list[Entity], review: dict[str, Any]) -> list[Relationship]:
    entity_by_id = {entity.id: entity for entity in entities}
    mentions_by_segment: dict[str, list[Mention]] = defaultdict(list)
    for mention in mentions:
        if mention.detector in SOURCE_PROVENANCE_DETECTORS:
            continue
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
            context_relationship = infer_context_relationship_from_text(window_text)
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
                        context_relationship,
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
    source_relationships = build_source_document_relationships(mentions, entities)[:RELATIONSHIP_OUTPUT_LIMIT]
    title_relationships = build_source_title_relationships(mentions, entities)[:RELATIONSHIP_OUTPUT_LIMIT]
    remaining = max(0, RELATIONSHIP_OUTPUT_LIMIT - len(source_relationships) - len(title_relationships))
    return apply_manual_relationships(source_relationships + title_relationships + relationships[:remaining], entities, review)


def apply_manual_relationships(relationships: list[Relationship], entities: list[Entity], review: dict[str, Any]) -> list[Relationship]:
    entity_by_id = {entity.id: entity for entity in entities}
    entities_by_name: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        entities_by_name[normalize_name(entity.name)].append(entity)
    raw_aliases = review.get("aliases") or {}
    aliases_by_id = {key: value for key, value in raw_aliases.items() if ":" in key}
    aliases_by_name = {normalize_name(key): value for key, value in raw_aliases.items() if ":" not in key}
    reclassifications = review.get("reclassifications", {})
    name_reclassifications = {normalize_name(key): value for key, value in review.get("nameReclassifications", {}).items()}
    merges = review.get("merges", {})
    name_merges = {normalize_name(key): value for key, value in review.get("nameMerges", {}).items()}
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
        source = resolve_manual_entity(
            item,
            "source",
            entity_by_id,
            entities_by_name,
            reclassifications,
            name_reclassifications,
            aliases_by_id,
            aliases_by_name,
            merges,
            name_merges,
        )
        target = resolve_manual_entity(
            item,
            "target",
            entity_by_id,
            entities_by_name,
            reclassifications,
            name_reclassifications,
            aliases_by_id,
            aliases_by_name,
            merges,
            name_merges,
        )
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
    reclassifications: dict[str, Any],
    name_reclassifications: dict[str, Any],
    aliases_by_id: dict[str, Any],
    aliases_by_name: dict[str, Any],
    merges: dict[str, Any],
    name_merges: dict[str, Any],
) -> Entity | None:
    entity_id = item.get(f"{side}Id")
    if entity_id and entity_id in entity_by_id:
        return entity_by_id[entity_id]
    raw_name = str(item.get(f"{side}Name") or "")
    category = item.get(f"{side}Category")

    candidates: list[tuple[str, str | None, str | None]] = []
    if entity_id or raw_name:
        candidates.append((raw_name, category, str(entity_id or "")))
        reviewed_name, reviewed_category, reviewed_id = apply_review_identity(
            str(entity_id or entity_key(canonicalize(raw_name, str(category or "people")), str(category or "people"))),
            raw_name,
            str(category or "people"),
            reclassifications,
            name_reclassifications,
            aliases_by_id,
            aliases_by_name,
            merges,
            name_merges,
        )
        candidates.append((reviewed_name, reviewed_category, reviewed_id))

    for name_value, candidate_category, candidate_id in candidates:
        if candidate_id and candidate_id in entity_by_id:
            return entity_by_id[candidate_id]
        name = normalize_name(name_value)
        if not name:
            continue
        matches = entities_by_name.get(name, [])
        if candidate_category:
            category_matches = [entity for entity in matches if entity.category == candidate_category]
            if len(category_matches) == 1:
                return category_matches[0]
        if len(matches) == 1:
            return matches[0]
    return None


def infer_context_relationship_from_text(text: str) -> tuple[str, float, str] | None:
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
    return None


def infer_relationship_from_context(
    source: Entity,
    target: Entity,
    context_relationship: tuple[str, float, str] | None,
) -> tuple[str, float, str]:
    if context_relationship:
        return context_relationship
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
            "source_data_dir": display_path(SOURCE_DATA_DIR),
            "transcript_source_dir": display_path(TRANSCRIPTS_DIR),
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


def update_readme_counts(manifest: dict[str, Any]) -> None:
    if not README_PATH.exists():
        return
    counts = manifest.get("counts", {})

    def count_value(key: str) -> int:
        value = counts.get(key, 0)
        return int(value) if isinstance(value, (int, float)) else 0

    def badge(label: str, key: str) -> str:
        return (
            f"![{label}]"
            f"(https://img.shields.io/badge/{quote(label.lower(), safe='')}-"
            f"{quote(f'{count_value(key):,}', safe='')}-2b2b2b)"
        )

    badge_block = "\n".join(
        [
            "<!-- dataset-badges:start -->",
            badge("Transcript Sources", "transcripts"),
            badge("Segments", "segments"),
            badge("Entities", "entities"),
            badge("Mentions", "mentions"),
            badge("Relationships", "relationships"),
            "<!-- dataset-badges:end -->",
        ]
    )
    export_block = "\n".join(
        [
            f"- {count_value('transcripts'):,} transcript sources",
            f"- {count_value('segments'):,} transcript segments",
            f"- {count_value('mentions'):,} entity mentions",
            f"- {count_value('entities'):,} entities",
            f"- {count_value('relationships'):,} relationships",
            f"- {count_value('categories'):,} categories",
        ]
    )

    readme = README_PATH.read_text(encoding="utf-8")
    if "<!-- dataset-badges:start -->" in readme and "<!-- dataset-badges:end -->" in readme:
        readme = re.sub(
            r"<!-- dataset-badges:start -->.*?<!-- dataset-badges:end -->",
            badge_block,
            readme,
            count=1,
            flags=re.S,
        )
    else:
        readme = re.sub(
            r"(\[!\[Rebuild Report\]\([^\n]+\)\n)(?:!\[[^\n]+\]\(https://img\.shields\.io/badge/[^\n]+\)\n)*",
            r"\1" + badge_block + "\n",
            readme,
            count=1,
        )
    readme = re.sub(
        r"(The current export includes:\n\n).*?(\n\n## Interface)",
        r"\1" + export_block + r"\2",
        readme,
        count=1,
        flags=re.S,
    )
    README_PATH.write_text(readme, encoding="utf-8")


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

    mention_payload = [asdict_slim_mention(mention) for mention in mentions]
    write_json(DATA_DIR / "segments.json", [asdict(segment) for segment in segments])
    write_json(DATA_DIR / "mentions.json", mention_payload)
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
    app_mentions_json = json.dumps(mention_payload, ensure_ascii=False)
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
    update_readme_counts(manifest)


def asdict_slim_mention(mention: Mention) -> dict[str, Any]:
    return {
        "id": mention.id,
        "segment_id": mention.segment_id,
        "transcript_id": mention.transcript_id,
        "transcript_title": mention.transcript_title,
        "timestamp": mention.timestamp,
        "detector": mention.detector,
        "confidence": mention.confidence,
        "excerpt": mention.excerpt,
    }


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


def normalize_frequency_name(value: str) -> str:
    cleaned = clean_text(value).replace("–", "-")
    match = re.match(
        r"^\s*(\d{1,9}(?:\.\d{1,4})?)\s*(?:(?:to|-)\s*(\d{1,9}(?:\.\d{1,4})?)\s*)?([a-z]+)\s*$",
        cleaned,
        re.I,
    )
    if not match:
        return cleaned
    start, end, unit = match.groups()
    canonical_unit = FREQUENCY_UNIT_ALIASES.get(unit.lower())
    if not canonical_unit:
        return cleaned
    start_hz = float(start) * FREQUENCY_UNIT_MULTIPLIERS[canonical_unit]
    end_hz = float(end) * FREQUENCY_UNIT_MULTIPLIERS[canonical_unit] if end else None
    target_unit = choose_frequency_unit(max(start_hz, end_hz or start_hz))
    if end:
        return f"{format_frequency_value(start_hz, target_unit)}-{format_frequency_value(end_hz or start_hz, target_unit)} {target_unit}"
    return f"{format_frequency_value(start_hz, target_unit)} {target_unit}"


def choose_frequency_unit(max_hz: float) -> str:
    for unit in FREQUENCY_UNIT_ORDER:
        if max_hz >= FREQUENCY_UNIT_MULTIPLIERS[unit]:
            return unit
    return "Hz"


def format_frequency_value(value_hz: float, unit: str) -> str:
    value = value_hz / FREQUENCY_UNIT_MULTIPLIERS[unit]
    formatted = f"{value:.6f}".rstrip("0").rstrip(".")
    return formatted or "0"


def normalize_frequency_band_name(value: str) -> str:
    cleaned = clean_text(value)
    normalized = normalize_name(cleaned)
    if normalized in FREQUENCY_BAND_ALIASES:
        return FREQUENCY_BAND_ALIASES[normalized]
    parts = normalized.split()
    if len(parts) == 2 and parts[0] in FREQUENCY_BAND_CODES and parts[1] in {"band", "frequency", "frequencies", "signal", "wave", "waves"}:
        return f"{parts[0].upper()} frequency"
    return cleaned


def normalize_radio_frequency_name(value: str) -> str:
    cleaned = clean_text(value)
    normalized = normalize_name(cleaned)
    if normalized in {"radio frequency", "radio frequencies"}:
        return "radio frequency"
    return cleaned


def canonicalize(name: str, category: str) -> str:
    cleaned = clean_text(name)
    if category == "frequencies":
        return normalize_frequency_band_name(normalize_frequency_name(cleaned)).lower()
    if category == "radio_frequencies":
        return normalize_radio_frequency_name(cleaned).lower()
    if category in {"websites", "ip_addresses", "gps_coordinates"}:
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
    version = f"?v={app_data_version}" if app_data_version else ""
    app_data_scripts = "\n".join(
        f"    <script src=\"{name}{version}\"></script>"
        for name in ("app-data.js", "app-data-mentions.js", "app-data-relationships.js")
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UFO Files Relationship Graph</title>
  <link rel="stylesheet" href="styles.css{version}">
</head>
<body>
  <p id="graph-help" class="sr-only">Interactive relationship graph. Use Tab to move through visible graph labels, Enter or Space to open a category or entity, Escape to move back up the graph, and the search field to jump to a specific label.</p>
  <main aria-labelledby="app-title">
  <svg id="graph" role="img" aria-label="Transcript relationship graph" aria-describedby="graph-help status"></svg>
  <div id="graph-labels" class="graph-label-layer" aria-label="Keyboard accessible graph labels"></div>
  <div class="topbar">
    <div class="brand">
      <a class="owner-label" href="https://github.com/ufo-files">UFO Files</a>
      <h1 id="app-title" aria-label="UFO Files Relationship Graph">
        <span class="app-switcher">
          <span class="app-switcher-text">Relationship Graph</span>
          <select id="app-switcher" aria-label="Application">
            <option value="https://ufo-files.github.io/relationship-graph/" selected>Relationship Graph</option>
            <option value="https://ufo-files.github.io/dog-whistle/">Dog Whistle</option>
          </select>
        </span>
      </h1>
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
{app_data_scripts}
  <script src="app.js{version}"></script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
