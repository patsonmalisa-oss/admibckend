"""
Document Extraction Service - Enhanced with Chapter/Section Detection
and Prompt-Based Classification

Features:
- Advanced chapter/section detection and parsing
- Prompt-based classification and extraction
- Strict schema enforcement for consistent columns/rows
- Clean spreadsheet-style output with proper headers
- Properly segmented CSV export
"""

import sys
import json
import os
import traceback
import gc
import re
import csv
import io
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import concurrent.futures
import threading
from functools import partial

from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from pydantic import BaseModel, Field, create_model

# PDF Processing
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("Warning: PyMuPDF not available")

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    print("Warning: pdfplumber not available")

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'temp_uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ============================================================
# ENUMS AND CONSTANTS
# ============================================================

class SectionType(Enum):
    """Types of document sections."""
    CHAPTER = "chapter"
    SECTION = "section"
    SUBSECTION = "subsection"
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    METHODOLOGY = "methodology"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    REFERENCES = "references"
    BIBLIOGRAPHY = "bibliography"
    APPENDIX = "appendix"
    ACKNOWLEDGEMENTS = "acknowledgements"
    TABLE_OF_CONTENTS = "toc"
    UNKNOWN = "unknown"


class ExtractionType(Enum):
    """Types of extraction based on prompt analysis."""
    REFERENCES = "references"
    TABLES = "tables"
    METADATA = "metadata"
    FINANCIAL = "financial"
    CONTACTS = "contacts"
    TIMELINE = "timeline"
    GENERIC = "generic"


# ============================================================
# PROMPT ANALYZER - Classifies extraction intent
# ============================================================

@dataclass
class PromptAnalysis:
    """Result of prompt analysis."""
    columns: List[str]
    section_hint: Optional[str]
    extraction_type: ExtractionType
    section_type: Optional[SectionType]
    keywords: List[str]
    constraints: Dict[str, Any]


class PromptAnalyzer:
    """
    Analyzes extraction prompts to determine:
    - What columns to extract
    - Which section to target
    - What type of extraction to perform
    """
    
    # Keywords that indicate extraction type
    EXTRACTION_KEYWORDS = {
        ExtractionType.REFERENCES: [
            'author', 'title', 'publisher', 'journal', 'doi', 'isbn',
            'reference', 'bibliography', 'citation', 'source'
        ],
        ExtractionType.TABLES: [
            'table', 'row', 'column', 'data', 'figure', 'chart'
        ],
        ExtractionType.METADATA: [
            'metadata', 'property', 'attribute', 'info', 'details'
        ],
        ExtractionType.FINANCIAL: [
            'amount', 'price', 'cost', 'value', 'total', 'fee', 'revenue',
            'expense', 'budget', 'salary', 'income', 'payment'
        ],
        ExtractionType.CONTACTS: [
            'email', 'phone', 'address', 'contact', 'name', 'organization'
        ],
        ExtractionType.TIMELINE: [
            'date', 'year', 'month', 'timeline', 'schedule', 'deadline',
            'period', 'duration', 'start', 'end'
        ]
    }
    
    # Section keywords mapping
    SECTION_KEYWORDS = {
        SectionType.REFERENCES: ['references', 'bibliography', 'citations', 'works cited'],
        SectionType.ABSTRACT: ['abstract', 'summary', 'executive summary'],
        SectionType.INTRODUCTION: ['introduction', 'background', 'overview'],
        SectionType.METHODOLOGY: ['methodology', 'methods', 'approach', 'research design'],
        SectionType.RESULTS: ['results', 'findings', 'outcomes'],
        SectionType.DISCUSSION: ['discussion', 'analysis', 'interpretation'],
        SectionType.CONCLUSION: ['conclusion', 'conclusions', 'final remarks'],
        SectionType.APPENDIX: ['appendix', 'appendices', 'supplementary'],
        SectionType.ACKNOWLEDGEMENTS: ['acknowledgements', 'acknowledgments', 'credits'],
        SectionType.TABLE_OF_CONTENTS: ['contents', 'table of contents', 'toc']
    }
    
    def analyze(self, prompt: str) -> PromptAnalysis:
        """Analyze the extraction prompt."""
        prompt_lower = prompt.lower()
        
        # Extract columns from prompt
        columns = self._extract_columns(prompt)
        
        # Extract section hint
        section_hint = self._extract_section_hint(prompt)
        
        # Determine extraction type
        extraction_type = self._determine_extraction_type(prompt, columns)
        
        # Determine section type
        section_type = self._determine_section_type(section_hint, prompt)
        
        # Extract keywords
        keywords = self._extract_keywords(prompt)
        
        # Extract constraints
        constraints = self._extract_constraints(prompt)
        
        return PromptAnalysis(
            columns=columns,
            section_hint=section_hint,
            extraction_type=extraction_type,
            section_type=section_type,
            keywords=keywords,
            constraints=constraints
        )
    
    def _extract_columns(self, prompt: str) -> List[str]:
        """Extract column names from prompt."""
        columns = []
        
        # Try quoted strings first
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", prompt)
        if quoted:
            # Filter out section references
            section_words = ['references', 'chapter', 'section', 'appendix', 'from']
            columns = [q.strip() for q in quoted if q.lower() not in section_words]
        
        # If no quoted strings, try comma-separated
        if not columns:
            # Remove common filler words
            clean_prompt = re.sub(r'\b(extract|get|find|all|from|the|and|or)\b', '', prompt, flags=re.IGNORECASE)
            parts = [p.strip() for p in clean_prompt.split(',') if p.strip()]
            columns = [p for p in parts if len(p) < 50 and not p.lower().startswith('from')]
        
        # Default columns if none found
        if not columns:
            columns = ['Item', 'Description', 'Value']
        
        return columns
    
    def _extract_section_hint(self, prompt: str) -> Optional[str]:
        """Extract section hint from prompt."""
        # Pattern: "from 'SectionName'" or "from SectionName"
        patterns = [
            r"from\s+['\"]([^'\"]+)['\"]",
            r"from\s+([A-Za-z][A-Za-z\s]{2,30})(?:\s*$|\s*[,\.])",
            r"in\s+['\"]([^'\"]+)['\"]",
            r"within\s+['\"]([^'\"]+)['\"]"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, prompt, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _determine_extraction_type(self, prompt: str, columns: List[str]) -> ExtractionType:
        """Determine the type of extraction based on prompt and columns."""
        prompt_lower = prompt.lower()
        columns_lower = [c.lower() for c in columns]
        
        # Score each extraction type
        scores = {ext_type: 0 for ext_type in ExtractionType}
        
        for ext_type, keywords in self.EXTRACTION_KEYWORDS.items():
            # Check prompt keywords
            for keyword in keywords:
                if keyword in prompt_lower:
                    scores[ext_type] += 2
            
            # Check column names
            for col in columns_lower:
                for keyword in keywords:
                    if keyword in col:
                        scores[ext_type] += 1
        
        # Return highest scoring type
        max_score = max(scores.values())
        if max_score > 0:
            for ext_type, score in scores.items():
                if score == max_score:
                    return ext_type
        
        return ExtractionType.GENERIC
    
    def _determine_section_type(self, section_hint: Optional[str], prompt: str) -> Optional[SectionType]:
        """Determine the section type from hint and prompt."""
        if section_hint:
            hint_lower = section_hint.lower()
            for section_type, keywords in self.SECTION_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in hint_lower:
                        return section_type
        
        # Check prompt for section keywords
        prompt_lower = prompt.lower()
        for section_type, keywords in self.SECTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in prompt_lower:
                    return section_type
        
        return None
    
    def _extract_keywords(self, prompt: str) -> List[str]:
        """Extract significant keywords from prompt."""
        # Remove common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                      'of', 'with', 'by', 'from', 'extract', 'get', 'find', 'all', 'please'}
        
        words = re.findall(r'\b[a-z]{3,}\b', prompt.lower())
        return list(set(w for w in words if w not in stop_words))
    
    def _extract_constraints(self, prompt: str) -> Dict[str, Any]:
        """Extract constraints from prompt."""
        constraints = {}
        
        # Year range
        year_match = re.search(r'(\d{4})\s*[-–]\s*(\d{4})', prompt)
        if year_match:
            constraints['year_range'] = (int(year_match.group(1)), int(year_match.group(2)))
        
        # Limit
        limit_match = re.search(r'(?:limit|top|first)\s*(\d+)', prompt, re.IGNORECASE)
        if limit_match:
            constraints['limit'] = int(limit_match.group(1))
        
        # Sort order
        if re.search(r'\b(ascending|asc|oldest|earliest)\b', prompt, re.IGNORECASE):
            constraints['sort'] = 'asc'
        elif re.search(r'\b(descending|desc|newest|latest|recent)\b', prompt, re.IGNORECASE):
            constraints['sort'] = 'desc'
        
        return constraints


# ============================================================
# DOCUMENT STRUCTURE ANALYZER
# ============================================================

@dataclass
class DocumentSection:
    """Represents a section/chapter in a document."""
    title: str
    section_type: SectionType
    level: int  # 1=chapter, 2=section, 3=subsection
    start_page: int
    start_char: int
    end_char: int
    content: str = ""
    number: str = ""  # Chapter/section number (e.g., "1", "2.1", "IV")
    subsections: List['DocumentSection'] = field(default_factory=list)


class DocumentStructureAnalyzer:
    """
    Advanced document structure analyzer.
    Detects chapters, sections, and other structural elements.
    """
    
    # Comprehensive section patterns
    SECTION_PATTERNS = [
        # Chapter patterns
        (r'^\s*(CHAPTER|Chapter)\s+(\d+|[IVXLCDM]+)\s*[:\-]?\s*(.*?)\s*$', 
         SectionType.CHAPTER, 1),
        (r'^\s*(\d+)\.\s+([A-Z][A-Za-z\s]{5,50})\s*$', 
         SectionType.CHAPTER, 1),
        
        # Section patterns
        (r'^\s*(SECTION|Section)\s+(\d+(?:\.\d+)?)\s*[:\-]?\s*(.*?)\s*$', 
         SectionType.SECTION, 2),
        (r'^\s*(\d+\.\d+)\s+([A-Z][A-Za-z\s]{5,50})\s*$', 
         SectionType.SECTION, 2),
        
        # Subsection patterns
        (r'^\s*(\d+\.\d+\.\d+)\s+([A-Z][A-Za-z\s]{5,50})\s*$', 
         SectionType.SUBSECTION, 3),
        
        # Named sections
        (r'^\s*(ABSTRACT|Abstract)\s*$', SectionType.ABSTRACT, 1),
        (r'^\s*(INTRODUCTION|Introduction)\s*$', SectionType.INTRODUCTION, 1),
        (r'^\s*(METHODOLOGY|Methodology|METHODS|Methods)\s*$', SectionType.METHODOLOGY, 1),
        (r'^\s*(RESULTS|Results|FINDINGS|Findings)\s*$', SectionType.RESULTS, 1),
        (r'^\s*(DISCUSSION|Discussion)\s*$', SectionType.DISCUSSION, 1),
        (r'^\s*(CONCLUSION|Conclusion|CONCLUSIONS|Conclusions)\s*$', SectionType.CONCLUSION, 1),
        (r'^\s*(REFERENCES|References|BIBLIOGRAPHY|Bibliography|WORKS CITED)\s*$', 
         SectionType.REFERENCES, 1),
        (r'^\s*(APPENDIX|Appendix)\s*([A-Z]|\d+)?\s*[:\-]?\s*(.*?)\s*$', 
         SectionType.APPENDIX, 1),
        (r'^\s*(ACKNOWLEDGEMENTS|Acknowledgements|ACKNOWLEDGMENTS|Acknowledgments)\s*$', 
         SectionType.ACKNOWLEDGEMENTS, 1),
        (r'^\s*(TABLE OF CONTENTS|CONTENTS|Contents)\s*$', 
         SectionType.TABLE_OF_CONTENTS, 1),
        
        # Markdown-style headers
        (r'^\s*(#{1})\s+(.+?)\s*$', None, 1),  # Will be classified by content
        (r'^\s*(#{2})\s+(.+?)\s*$', None, 2),
        (r'^\s*(#{3})\s+(.+?)\s*$', None, 3),
    ]
    
    def __init__(self, text: str):
        self.text = text
        self.lines = text.split('\n')
        self.sections: List[DocumentSection] = []
    
    def analyze(self) -> List[DocumentSection]:
        """Analyze document and extract section structure."""
        self.sections = []
        
        for i, line in enumerate(self.lines):
            line = line.strip()
            if not line:
                continue
            
            for pattern, section_type, level in self.SECTION_PATTERNS:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    section = self._create_section(match, pattern, section_type, level, i)
                    if section:
                        self.sections.append(section)
                    break
        
        # Fill in content for each section
        self._fill_section_content()
        
        # Build hierarchy
        self._build_hierarchy()
        
        return self.sections
    
    def _create_section(self, match, pattern: str, section_type: Optional[SectionType], 
                        level: int, line_index: int) -> Optional[DocumentSection]:
        """Create a section from a regex match."""
        groups = match.groups()
        
        # Determine section type from pattern content
        if section_type is None:
            # Markdown header - classify by content
            title = groups[-1] if groups else ""
            section_type = self._classify_by_title(title)
        
        # Extract title and number
        title = ""
        number = ""
        
        if 'CHAPTER' in pattern.upper() or 'Chapter' in pattern:
            number = groups[1] if len(groups) > 1 else ""
            title = groups[2] if len(groups) > 2 else ""
            title = f"Chapter {number}: {title}" if title else f"Chapter {number}"
        elif 'SECTION' in pattern.upper() or 'Section' in pattern:
            number = groups[1] if len(groups) > 1 else ""
            title = groups[2] if len(groups) > 2 else ""
            title = f"Section {number}: {title}" if title else f"Section {number}"
        elif 'APPENDIX' in pattern.upper() or 'Appendix' in pattern:
            number = groups[1] if len(groups) > 1 else ""
            title = groups[2] if len(groups) > 2 else ""
            title = f"Appendix {number}: {title}" if title else f"Appendix {number}"
        elif section_type in [SectionType.ABSTRACT, SectionType.INTRODUCTION, 
                              SectionType.METHODOLOGY, SectionType.RESULTS,
                              SectionType.DISCUSSION, SectionType.CONCLUSION,
                              SectionType.REFERENCES, SectionType.ACKNOWLEDGEMENTS]:
            title = section_type.value.title()
        elif '#' in pattern:
            title = groups[-1] if groups else ""
        else:
            # Numbered section
            number = groups[0] if groups else ""
            title = groups[1] if len(groups) > 1 else ""
            title = f"{number}. {title}" if number and title else title or number
        
        # Calculate character position
        char_pos = sum(len(self.lines[j]) + 1 for j in range(line_index))
        
        return DocumentSection(
            title=title.strip(),
            section_type=section_type,
            level=level,
            start_page=1,
            start_char=char_pos,
            end_char=len(self.text),
            number=number
        )
    
    def _classify_by_title(self, title: str) -> SectionType:
        """Classify section type by title content."""
        title_lower = title.lower()
        
        classification_map = {
            'abstract': SectionType.ABSTRACT,
            'introduction': SectionType.INTRODUCTION,
            'methodology': SectionType.METHODOLOGY,
            'methods': SectionType.METHODOLOGY,
            'results': SectionType.RESULTS,
            'findings': SectionType.RESULTS,
            'discussion': SectionType.DISCUSSION,
            'conclusion': SectionType.CONCLUSION,
            'references': SectionType.REFERENCES,
            'bibliography': SectionType.REFERENCES,
            'appendix': SectionType.APPENDIX,
            'acknowledgements': SectionType.ACKNOWLEDGEMENTS,
        }
        
        for keyword, section_type in classification_map.items():
            if keyword in title_lower:
                return section_type
        
        return SectionType.UNKNOWN
    
    def _fill_section_content(self):
        """Fill in content for each section."""
        for i, section in enumerate(self.sections):
            start = section.start_char
            end = self.sections[i + 1].start_char if i + 1 < len(self.sections) else len(self.text)
            section.content = self.text[start:end].strip()
            section.end_char = end
    
    def _build_hierarchy(self):
        """Build parent-child relationships between sections."""
        # Group sections by level
        for i, section in enumerate(self.sections):
            # Find parent section (lower level number = higher in hierarchy)
            for j in range(i - 1, -1, -1):
                if self.sections[j].level < section.level:
                    self.sections[j].subsections.append(section)
                    break
    
    def find_section(self, query: str) -> Optional[DocumentSection]:
        """Find a section by title query."""
        query_lower = query.lower().strip()
        
        # Direct match
        for section in self.sections:
            if query_lower in section.title.lower():
                return section
        
        # Section type match
        for section in self.sections:
            if section.section_type.value in query_lower:
                return section
        
        # Fuzzy match
        for section in self.sections:
            # Check if any word from query is in title
            query_words = set(query_lower.split())
            title_words = set(section.title.lower().split())
            if query_words & title_words:
                return section
        
        return None
    
    def get_sections_by_type(self, section_type: SectionType) -> List[DocumentSection]:
        """Get all sections of a specific type."""
        return [s for s in self.sections if s.section_type == section_type]


# ============================================================
# STRICT SCHEMA DEFINITIONS
# ============================================================

@dataclass
class ColumnSchema:
    """Defines a column with strict typing and validation."""
    name: str
    normalized_name: str
    description: str = ""
    data_type: str = "string"
    required: bool = False
    patterns: List[str] = field(default_factory=list)
    
    def validate_value(self, value: Any) -> str:
        """Validate and normalize a value for this column."""
        if value is None:
            return ""
        
        str_value = str(value).strip()
        
        if self.data_type == "number":
            nums = re.findall(r'[\d,]+\.?\d*', str_value)
            return nums[0].replace(',', '') if nums else ""
        elif self.data_type == "date":
            return self._normalize_date(str_value)
        elif self.data_type == "year":
            year_match = re.search(r'\b(19|20)\d{2}\b', str_value)
            return year_match.group(0) if year_match else ""
        elif self.data_type == "email":
            email_match = re.search(r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b', str_value)
            return email_match.group(1) if email_match else ""
        
        return str_value
    
    def _normalize_date(self, value: str) -> str:
        """Normalize date to ISO format."""
        patterns = [
            (r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', lambda m: f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"),
            (r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})', lambda m: f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"),
        ]
        
        for pattern, formatter in patterns:
            match = re.search(pattern, value, re.IGNORECASE)
            if match:
                try:
                    return formatter(match)
                except:
                    pass
        
        year_match = re.search(r'\b(19|20)\d{2}\b', value)
        return year_match.group(0) if year_match else value


class ExtractionSchema:
    """Strict schema for extraction output."""
    
    def __init__(self, column_names: List[str]):
        self.columns: List[ColumnSchema] = []
        self._build_schema(column_names)
    
    def _build_schema(self, column_names: List[str]):
        """Build column schemas from names."""
        for name in column_names:
            normalized = self._normalize_name(name)
            col_type = self._infer_type(name)
            patterns = self._get_patterns(name, col_type)
            
            self.columns.append(ColumnSchema(
                name=name,
                normalized_name=normalized,
                data_type=col_type,
                patterns=patterns
            ))
    
    def _normalize_name(self, name: str) -> str:
        """Normalize column name to snake_case."""
        clean = name.strip().lower().replace(" ", "_").replace("-", "_")
        return re.sub(r'[^a-z0-9_]', '', clean)
    
    def _infer_type(self, name: str) -> str:
        """Infer data type from column name."""
        name_lower = name.lower().replace('_', '').replace(' ', '')
        
        if any(k in name_lower for k in ['date', 'published', 'created']):
            return 'date'
        if 'year' in name_lower:
            return 'year'
        if any(k in name_lower for k in ['amount', 'price', 'cost', 'value', 'total', 'fee']):
            return 'number'
        if 'email' in name_lower:
            return 'email'
        
        return 'string'
    
    def _get_patterns(self, name: str, col_type: str) -> List[str]:
        """Get regex patterns for column."""
        patterns = {
            'date': [
                r'\b(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b',
                r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b',
            ],
            'year': [r'\b((?:19|20)\d{2})\b'],
            'number': [r'\$?\s*([\d,]+\.?\d*)'],
            'email': [r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b'],
        }
        return patterns.get(col_type, [])
    
    def get_headers(self) -> List[str]:
        return [col.normalized_name for col in self.columns]
    
    def get_display_headers(self) -> List[str]:
        return [col.name for col in self.columns]
    
    def create_record(self, data: Dict[str, Any] = None) -> Dict[str, str]:
        if data is None:
            data = {}
        record = {}
        for col in self.columns:
            raw_value = data.get(col.normalized_name, data.get(col.name, ""))
            record[col.normalized_name] = col.validate_value(raw_value)
        return record
    
    def validate_record(self, record: Dict[str, str]) -> Dict[str, str]:
        validated = {}
        for col in self.columns:
            value = record.get(col.normalized_name, record.get(col.name, ""))
            validated[col.normalized_name] = col.validate_value(value)
        return validated


# ============================================================
# EXTRACTION ENGINE
# ============================================================

class ExtractionEngine:
    """Main extraction engine with prompt-based classification."""
    
    def __init__(self, schema: ExtractionSchema, analysis: PromptAnalysis):
        self.schema = schema
        self.analysis = analysis
    
    def extract(self, text: str, tables: List[List]) -> List[Dict[str, str]]:
        """Extract data based on prompt analysis."""
        results = []
        seen = set()
        
        # Analyze document structure
        doc_analyzer = DocumentStructureAnalyzer(text)
        sections = doc_analyzer.analyze()
        
        # Determine target content
        target_text = self._get_target_text(text, doc_analyzer)
        
        print(f"Extraction type: {self.analysis.extraction_type.value}")
        print(f"Target section: {self.analysis.section_hint or 'Full document'}")
        
        # Extract based on type
        if self.analysis.extraction_type == ExtractionType.REFERENCES:
            results = self._extract_references(target_text)
        elif self.analysis.extraction_type == ExtractionType.TABLES:
            results = self._extract_tables(target_text, tables)
        elif self.analysis.extraction_type == ExtractionType.FINANCIAL:
            results = self._extract_financial(target_text)
        else:
            # Generic extraction - try all strategies
            results = self._extract_generic(target_text, tables)
        
        # Apply constraints
        results = self._apply_constraints(results)
        
        # Deduplicate
        final_results = []
        for record in results:
            validated = self.schema.validate_record(record)
            key = tuple(sorted(validated.items()))
            if key not in seen and self._has_data(validated):
                seen.add(key)
                final_results.append(validated)
        
        return final_results
    
    def _get_target_text(self, text: str, doc_analyzer: DocumentStructureAnalyzer) -> str:
        """Get the target text based on section hint."""
        if not self.analysis.section_hint:
            return text
        
        # Try to find the section
        section = doc_analyzer.find_section(self.analysis.section_hint)
        if section:
            print(f"Found section: {section.title}")
            return section.content
        
        # Try by section type
        if self.analysis.section_type:
            sections = doc_analyzer.get_sections_by_type(self.analysis.section_type)
            if sections:
                print(f"Found {len(sections)} sections of type {self.analysis.section_type.value}")
                return '\n\n'.join(s.content for s in sections)
        
        return text
    
    def _extract_references(self, text: str) -> List[Dict[str, str]]:
        """Extract academic references/bibliography with flexible pattern matching."""
        results = []
        lines = text.split('\n')
        
        # More flexible reference patterns
        patterns = [
            # APA: Author, A. A. (Year). Title. Publisher.
            r'^([A-Z][a-z]+(?:,\s*[A-Z]\.(?:\s*[A-Z]\.)*)+)\s*\((\d{4})\)\.\s*(.+)',
            # Author (Year) format
            r'^([A-Z][a-z]+,\s*[A-Z]\.(?:\s*[A-Z]\.)*)\s*\((\d{4})\)\s*(.+)',
            # Author (Year) - with dash
            r'^([A-Z][a-z]+(?:,\s*[A-Z]\.(?:\s*[A-Z]\.)*)*)\s*[\(\[]?(\d{4})[\)\]]?\s*[\.\-–]\s*(.+)',
            # Numbered reference: [1] Author, Title, Year
            r'^\s*\[?\d+\]?\s*([A-Z][^.]+)\.\s*([^.]+)\.\s*([^,]+),?\s*(\d{4})',
            # MLA: Author. Title. Publisher, Year.
            r'^([A-Z][a-z]+,\s*[A-Z][a-z]+)\.\s*([^.]+)\.\s*([^,]+),\s*(\d{4})',
            # Chicago: Author. Title. Publisher, Year.
            r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\.\s*([^.]+)\.\s*([^,]+),\s*(\d{4})',
            # Simple: Author, Title, Publisher, Year
            r'^([A-Z][^,]+),\s*([^,]+),\s*([^,]+),\s*(\d{4})',
            # Just author and year
            r'^([A-Z][a-z]+(?:,\s*[A-Z]\.(?:\s*[A-Z]\.)*)*)\s*[\(\[]?(\d{4})[\)\]]?',
        ]
        
        current_ref = ""
        ref_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_ref or ref_lines:
                    record = self._parse_reference_flexible(current_ref, ref_lines, patterns)
                    if record:
                        results.append(record)
                    current_ref = ""
                    ref_lines = []
                continue
            
            # Check if this starts a new reference
            is_new_ref = self._is_new_reference(line, patterns)
            
            if is_new_ref:
                # Process previous reference
                if current_ref or ref_lines:
                    record = self._parse_reference_flexible(current_ref, ref_lines, patterns)
                    if record:
                        results.append(record)
                current_ref = line
                ref_lines = [line]
            else:
                # Continue current reference
                current_ref += " " + line
                ref_lines.append(line)
        
        # Process last reference
        if current_ref or ref_lines:
            record = self._parse_reference_flexible(current_ref, ref_lines, patterns)
            if record:
                results.append(record)
        
        # If no references found, try line-by-line extraction
        if not results:
            results = self._extract_references_by_line(text)
        
        return results
    
    def _is_new_reference(self, line: str, patterns: List[str]) -> bool:
        """Check if line starts a new reference."""
        # Check for numbered references
        if re.match(r'^\s*\[?\d+\]?\s*[A-Z]', line):
            return True
        
        # Check for author patterns at start
        if re.match(r'^[A-Z][a-z]+,', line):
            return True
        
        # Check for year patterns
        if re.match(r'^[A-Z].*\(\d{4}\)', line):
            return True
        
        return False
    
    def _parse_reference_flexible(self, text: str, lines: List[str], patterns: List[str]) -> Optional[Dict[str, str]]:
        """Parse a reference string with flexible matching."""
        text = text.strip()
        if len(text) < 10:
            return None
        
        record = self.schema.create_record()
        
        # Extract year
        year_match = re.search(r'\b((?:19|20)\d{2})\b', text)
        year = year_match.group(1) if year_match else ""
        
        # Extract author (usually at the start, before year or title)
        author_patterns = [
            r'^([A-Z][a-z]+(?:,\s*[A-Z]\.(?:\s*[A-Z]\.)*)*)',
            r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'^([A-Z][^,\.]+)',
        ]
        
        author = ""
        for pattern in author_patterns:
            match = re.match(pattern, text)
            if match:
                author = match.group(1).strip()
                # Clean up author name
                author = re.sub(r'\s+', ' ', author)
                if len(author) > 3:
                    break
        
        # Extract title (usually the longest sentence-like part after author/year)
        title = ""
        # Remove author and year from text to find title
        remaining = text
        if author:
            remaining = remaining.replace(author, '', 1)
        if year:
            remaining = remaining.replace(f'({year})', '').replace(year, '')
        
        # Find title-like segments
        sentences = re.split(r'[.\-–]', remaining)
        for sent in sentences:
            sent = sent.strip()
            if len(sent) > 20 and not re.match(r'^\d', sent):
                title = sent
                break
        
        # Extract publisher/institution
        publisher = ""
        pub_patterns = [
            r'(?:published by|publisher:?)\s*([^,\.]+)',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:Press|Publishing|University|Institute|Ltd|Inc)))',
        ]
        for pattern in pub_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                publisher = match.group(1).strip()
                break
        
        # Map to schema columns
        for col in self.schema.columns:
            col_lower = col.name.lower().replace('_', '').replace(' ', '')
            
            if any(k in col_lower for k in ['author', 'name']):
                record[col.normalized_name] = author
            elif any(k in col_lower for k in ['date', 'year', 'published']):
                record[col.normalized_name] = year
            elif any(k in col_lower for k in ['title']):
                record[col.normalized_name] = title
            elif any(k in col_lower for k in ['publisher', 'institution', 'organization']):
                record[col.normalized_name] = publisher
            elif any(k in col_lower for k in ['detail', 'text', 'description']):
                record[col.normalized_name] = text[:200]
        
        # Only return if we have at least some data
        if author or title or year:
            return record
        
        return None
    
    def _extract_references_by_line(self, text: str) -> List[Dict[str, str]]:
        """Extract references by analyzing each line."""
        results = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 15:
                continue
            
            # Skip lines that look like headers or section titles
            if re.match(r'^(CHAPTER|Section|References|Bibliography|APPENDIX)', line, re.IGNORECASE):
                continue
            
            record = self.schema.create_record()
            
            # Extract year
            year_match = re.search(r'\b((?:19|20)\d{2})\b', line)
            year = year_match.group(1) if year_match else ""
            
            # Extract author (first capitalized words)
            author_match = re.match(r'^([A-Z][a-z]+(?:,\s*[A-Z]\.(?:\s*[A-Z]\.)*)*)', line)
            author = author_match.group(1) if author_match else ""
            
            # Extract title (text after author/year)
            title = line
            if author:
                title = title.replace(author, '', 1).strip()
            if year:
                title = re.sub(rf'\(?{year}\)?', '', title).strip()
            title = re.sub(r'^[\.\-–\s]+', '', title)
            
            # Map to schema
            for col in self.schema.columns:
                col_lower = col.name.lower().replace('_', '').replace(' ', '')
                
                if any(k in col_lower for k in ['author', 'name']):
                    record[col.normalized_name] = author
                elif any(k in col_lower for k in ['date', 'year', 'published']):
                    record[col.normalized_name] = year
                elif any(k in col_lower for k in ['title']):
                    record[col.normalized_name] = title[:150] if title else ""
                elif any(k in col_lower for k in ['detail', 'text', 'description']):
                    record[col.normalized_name] = line[:200]
            
            if author or year:
                results.append(record)
        
        return results
    
    def _parse_reference(self, text: str, patterns: List[str]) -> Optional[Dict[str, str]]:
        """Parse a reference string."""
        for pattern in patterns:
            match = re.match(pattern, text.strip())
            if match:
                groups = match.groups()
                record = self.schema.create_record()
                
                for col in self.schema.columns:
                    col_lower = col.name.lower().replace('_', '').replace(' ', '')
                    
                    if any(k in col_lower for k in ['author', 'name']):
                        record[col.normalized_name] = groups[0] if groups else ""
                    elif any(k in col_lower for k in ['date', 'year', 'published']):
                        for g in groups[1:]:
                            if g and re.match(r'^\d{4}$', g.strip()):
                                record[col.normalized_name] = g.strip()
                                break
                    elif any(k in col_lower for k in ['title']):
                        candidates = [g for g in groups[1:] if g and not re.match(r'^\d{4}$', g.strip())]
                        if candidates:
                            record[col.normalized_name] = max(candidates, key=len).strip()
                    elif any(k in col_lower for k in ['publisher', 'institution', 'organization']):
                        for g in groups[1:]:
                            if g and not re.match(r'^\d{4}$', g.strip()) and len(g.strip()) < 60:
                                record[col.normalized_name] = g.strip()
                                break
                
                return record
        
        return None
    
    def _extract_tables(self, text: str, tables: List[List]) -> List[Dict[str, str]]:
        """Extract data from tables."""
        results = []
        
        # Process detected tables
        for table in tables:
            if len(table) < 2:
                continue
            
            headers = table[0]
            data_rows = table[1:]
            
            # Map schema columns to table columns
            col_mapping = {}
            for schema_col in self.schema.columns:
                for i, header in enumerate(headers):
                    header_clean = str(header).lower().replace('_', '').replace(' ', '')
                    schema_clean = schema_col.normalized_name.replace('_', '')
                    if schema_clean in header_clean or header_clean in schema_clean:
                        col_mapping[schema_col.normalized_name] = i
                        break
            
            # Create records
            for row in data_rows:
                record = {}
                for col in self.schema.columns:
                    if col.normalized_name in col_mapping:
                        idx = col_mapping[col.normalized_name]
                        if idx < len(row):
                            record[col.normalized_name] = str(row[idx]).strip()
                        else:
                            record[col.normalized_name] = ""
                    else:
                        record[col.normalized_name] = ""
                results.append(record)
        
        # Also try to extract tables from text
        text_tables = self._extract_tables_from_text(text)
        results.extend(text_tables)
        
        return results
    
    def _extract_tables_from_text(self, text: str) -> List[Dict[str, str]]:
        """Extract table-like structures from text."""
        results = []
        lines = text.split('\n')
        potential_table = []
        
        for line in lines:
            line = line.strip()
            if not line:
                if len(potential_table) > 2:
                    results.extend(self._process_table(potential_table))
                potential_table = []
                continue
            
            # Check for delimiter-separated values
            if '\t' in line or '  ' in line or '|' in line:
                if '\t' in line:
                    cells = line.split('\t')
                elif '|' in line:
                    cells = [c.strip() for c in line.split('|') if c.strip()]
                else:
                    cells = re.split(r'\s{2,}', line)
                
                cells = [c.strip() for c in cells if c.strip()]
                if len(cells) >= 2:
                    potential_table.append(cells)
            else:
                if len(potential_table) > 2:
                    results.extend(self._process_table(potential_table))
                potential_table = []
        
        if len(potential_table) > 2:
            results.extend(self._process_table(potential_table))
        
        return results
    
    def _process_table(self, table: List[List[str]]) -> List[Dict[str, str]]:
        """Process a detected table."""
        if len(table) < 2:
            return []
        
        headers = table[0]
        data_rows = table[1:]
        
        col_mapping = {}
        for schema_col in self.schema.columns:
            for i, header in enumerate(headers):
                header_clean = str(header).lower().replace('_', '').replace(' ', '')
                schema_clean = schema_col.normalized_name.replace('_', '')
                if schema_clean in header_clean or header_clean in schema_clean:
                    col_mapping[schema_col.normalized_name] = i
                    break
        
        records = []
        for row in data_rows:
            record = {}
            for col in self.schema.columns:
                if col.normalized_name in col_mapping:
                    idx = col_mapping[col.normalized_name]
                    record[col.normalized_name] = str(row[idx]).strip() if idx < len(row) else ""
                else:
                    record[col.normalized_name] = ""
            records.append(record)
        
        return records
    
    def _extract_financial(self, text: str) -> List[Dict[str, str]]:
        """Extract financial data."""
        results = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            record = self.schema.create_record()
            has_data = False
            
            # Extract amounts
            for col in self.schema.columns:
                if col.data_type == 'number':
                    for pattern in col.patterns:
                        match = re.search(pattern, line, re.IGNORECASE)
                        if match:
                            record[col.normalized_name] = match.group(1)
                            has_data = True
                            break
            
            # Extract other fields
            for col in self.schema.columns:
                if not record.get(col.normalized_name):
                    col_lower = col.name.lower().replace('_', '').replace(' ', '')
                    
                    if any(k in col_lower for k in ['entity', 'company', 'name', 'description']):
                        # Use remaining text
                        record[col.normalized_name] = line[:100]
                        has_data = True
            
            if has_data:
                results.append(record)
        
        return results
    
    def _extract_generic(self, text: str, tables: List[List]) -> List[Dict[str, str]]:
        """Generic extraction using multiple strategies."""
        results = []
        
        # Strategy 1: Tables
        results.extend(self._extract_tables(text, tables))
        
        # Strategy 2: References (if columns suggest it)
        if any('author' in c.name.lower() or 'title' in c.name.lower() for c in self.schema.columns):
            results.extend(self._extract_references(text))
        
        # Strategy 3: Pattern-based
        results.extend(self._extract_by_patterns(text))
        
        # Strategy 4: Section content extraction (fallback)
        if not results:
            results = self._extract_section_content(text)
        
        return results
    
    def _extract_section_content(self, text: str) -> List[Dict[str, str]]:
        """
        Extract all content from section and organize into table by labels.
        This is a fallback when other extraction methods fail.
        """
        results = []
        lines = text.split('\n')
        
        # Get column names from schema
        col_names = [col.normalized_name for col in self.schema.columns]
        
        # Try to identify content blocks
        current_block = []
        block_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_block:
                    record = self._process_content_block(current_block, col_names)
                    if record and self._has_data(record):
                        results.append(record)
                    current_block = []
                continue
            
            current_block.append(line)
        
        # Process last block
        if current_block:
            record = self._process_content_block(current_block, col_names)
            if record and self._has_data(record):
                results.append(record)
        
        # If still no results, try line-by-line with smart parsing
        if not results:
            results = self._extract_line_by_line(text)
        
        return results
    
    def _process_content_block(self, lines: List[str], col_names: List[str]) -> Dict[str, str]:
        """Process a block of content lines into a record."""
        record = {col: "" for col in col_names}
        
        if not lines:
            return record
        
        # Join lines into single text
        full_text = ' '.join(lines)
        
        # Try to extract year/date
        year_match = re.search(r'\b((?:19|20)\d{2})\b', full_text)
        year = year_match.group(1) if year_match else ""
        
        # Try to extract author (look for patterns like "Last, F." or "Last, First")
        author_patterns = [
            r'([A-Z][a-z]+,\s*[A-Z]\.(?:\s*[A-Z]\.)*)',
            r'([A-Z][a-z]+,\s*[A-Z][a-z]+)',
            r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        ]
        
        author = ""
        for pattern in author_patterns:
            match = re.search(pattern, full_text)
            if match:
                author = match.group(1)
                break
        
        # Try to extract title (look for quoted text or longest sentence)
        title = ""
        quoted_match = re.search(r'["\']([^"\']+)["\']', full_text)
        if quoted_match:
            title = quoted_match.group(1)
        else:
            # Find longest segment that looks like a title
            segments = re.split(r'[.\-–,]', full_text)
            for seg in segments:
                seg = seg.strip()
                if len(seg) > 20 and not re.match(r'^\d', seg) and not re.search(r'\d{4}', seg):
                    title = seg
                    break
        
        # Try to extract publisher/institution
        publisher = ""
        pub_keywords = ['Press', 'University', 'Institute', 'Publishing', 'Ltd', 'Inc', 'Foundation']
        for keyword in pub_keywords:
            match = re.search(rf'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+{keyword})', full_text)
            if match:
                publisher = match.group(1)
                break
        
        # Map to columns
        for col in col_names:
            col_lower = col.lower().replace('_', '')
            
            if any(k in col_lower for k in ['author', 'name']):
                record[col] = author
            elif any(k in col_lower for k in ['date', 'year', 'published']):
                record[col] = year
            elif any(k in col_lower for k in ['title']):
                record[col] = title
            elif any(k in col_lower for k in ['publisher', 'institution', 'organization']):
                record[col] = publisher
            elif any(k in col_lower for k in ['detail', 'text', 'description', 'content']):
                record[col] = full_text[:300]
        
        return record
    
    def _extract_line_by_line(self, text: str) -> List[Dict[str, str]]:
        """Extract by analyzing each line individually."""
        results = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 10:
                continue
            
            # Skip obvious non-content lines
            skip_patterns = [
                r'^\s*$',  # Empty
                r'^\d+\s*$',  # Just numbers
                r'^---',  # Separators
                r'^Page \d+',  # Page numbers
            ]
            
            if any(re.match(p, line) for p in skip_patterns):
                continue
            
            record = self.schema.create_record()
            
            # Extract year
            year_match = re.search(r'\b((?:19|20)\d{2})\b', line)
            year = year_match.group(1) if year_match else ""
            
            # Extract potential author
            author_match = re.match(r'^([A-Z][a-z]+(?:,\s*[A-Z]\.(?:\s*[A-Z]\.)*)*)', line)
            author = author_match.group(1) if author_match else ""
            
            # Extract title-like content
            title = ""
            # Look for text after author or year
            remaining = line
            if author:
                remaining = remaining[len(author):].strip()
            if year:
                remaining = re.sub(rf'\(?{year}\)?', '', remaining).strip()
            
            # Clean up remaining text for title
            remaining = re.sub(r'^[\.\-–:\s]+', '', remaining)
            if len(remaining) > 10:
                title = remaining[:150]
            
            # Map to schema columns
            for col in self.schema.columns:
                col_lower = col.name.lower().replace('_', '').replace(' ', '')
                
                if any(k in col_lower for k in ['author', 'name']):
                    record[col.normalized_name] = author
                elif any(k in col_lower for k in ['date', 'year', 'published']):
                    record[col.normalized_name] = year
                elif any(k in col_lower for k in ['title']):
                    record[col.normalized_name] = title
                elif any(k in col_lower for k in ['detail', 'text', 'description', 'content']):
                    record[col.normalized_name] = line[:200]
            
            # Only add if we extracted something meaningful
            if author or year or (title and len(title) > 20):
                results.append(record)
        
        return results
    
    def _extract_by_patterns(self, text: str) -> List[Dict[str, str]]:
        """Extract using column-specific patterns."""
        results = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 10:
                continue
            
            record = self.schema.create_record()
            has_match = False
            
            for col in self.schema.columns:
                if col.patterns:
                    for pattern in col.patterns:
                        match = re.search(pattern, line, re.IGNORECASE)
                        if match:
                            record[col.normalized_name] = match.group(1) if match.groups() else match.group(0)
                            has_match = True
                            break
            
            # Fill remaining columns
            for col in self.schema.columns:
                if not record.get(col.normalized_name):
                    col_lower = col.name.lower().replace('_', '').replace(' ', '')
                    
                    if any(k in col_lower for k in ['title', 'description', 'text', 'detail']):
                        record[col.normalized_name] = line[:200]
                        has_match = True
                    elif any(k in col_lower for k in ['entity', 'company', 'organization']):
                        caps = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', line)
                        if caps:
                            record[col.normalized_name] = caps[0]
                            has_match = True
            
            if has_match:
                results.append(record)
        
        return results
    
    def _apply_constraints(self, results: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Apply constraints from prompt analysis."""
        if not results:
            return results
        
        constraints = self.analysis.constraints
        
        # Year range filter
        if 'year_range' in constraints:
            min_year, max_year = constraints['year_range']
            filtered = []
            for record in results:
                # Find year field
                for key, value in record.items():
                    if 'year' in key.lower() or 'date' in key.lower():
                        try:
                            year = int(re.search(r'\d{4}', str(value)).group(0))
                            if min_year <= year <= max_year:
                                filtered.append(record)
                        except:
                            filtered.append(record)
                        break
            results = filtered
        
        # Limit
        if 'limit' in constraints:
            results = results[:constraints['limit']]
        
        # Sort
        if 'sort' in constraints:
            # Find date/year field
            for key in results[0].keys() if results else []:
                if 'year' in key.lower() or 'date' in key.lower():
                    results.sort(key=lambda r: r.get(key, ''), reverse=(constraints['sort'] == 'desc'))
                    break
        
        return results
    
    def _has_data(self, record: Dict[str, str]) -> bool:
        """Check if record has any non-empty values."""
        return any(v for v in record.values())


# ============================================================
# CSV EXPORTER
# ============================================================

class CSVExporter:
    """Exports extraction results to properly formatted CSV."""
    
    @staticmethod
    def export(records: List[Dict[str, str]], headers: List[str], 
               display_headers: List[str] = None) -> str:
        if not records:
            return ""
        
        if display_headers is None:
            display_headers = [h.replace('_', ' ').title() for h in headers]
        
        output = io.StringIO()
        header_line = ','.join(CSVExporter._escape_csv_cell(h) for h in display_headers)
        output.write(header_line + '\n')
        
        for record in records:
            row_values = []
            for header in headers:
                value = record.get(header, "")
                row_values.append(CSVExporter._escape_csv_cell(str(value)))
            output.write(','.join(row_values) + '\n')
        
        return output.getvalue()
    
    @staticmethod
    def _escape_csv_cell(value: str) -> str:
        value = str(value).strip()
        needs_escape = any(c in value for c in [',', '"', '\n', '\r'])
        
        if needs_escape:
            value = value.replace('"', '""')
            return f'"{value}"'
        
        return value


# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_pdf_content(file_path: str) -> Tuple[str, List[List]]:
    """Extract text and tables from PDF."""
    text_parts = []
    all_tables = []
    
    if HAS_PYMUPDF:
        try:
            doc = fitz.open(file_path)
            for page_num, page in enumerate(doc):
                text = page.get_text("text")
                text_parts.append(f"--- Page {page_num + 1} ---\n{text}")
            doc.close()
            print(f"PyMuPDF extracted {sum(len(t) for t in text_parts)} chars")
        except Exception as e:
            print(f"PyMuPDF error: {e}")
    
    if HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        if table and len(table) > 1:
                            cleaned = [[str(c).strip() if c else "" for c in row] for row in table]
                            all_tables.append(cleaned)
            print(f"pdfplumber found {len(all_tables)} tables")
        except Exception as e:
            print(f"pdfplumber error: {e}")
    
    return "\n\n".join(text_parts), all_tables


def extract_csv_content(file_path: str) -> Tuple[str, List[List]]:
    """Extract content from CSV file."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        if not rows:
            return "", []
        
        headers = rows[0]
        text_parts = [", ".join(headers)]
        
        for row in rows[1:]:
            text_parts.append(" | ".join(f"{headers[i]}: {v}" if i < len(headers) else v 
                                         for i, v in enumerate(row)))
        
        return "\n".join(text_parts), [rows]
    except Exception as e:
        print(f"CSV error: {e}")
        return "", []


# ============================================================
# API ROUTES
# ============================================================

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'backends': {
            'pymupdf': HAS_PYMUPDF,
            'pdfplumber': HAS_PDFPLUMBER
        },
        'mode': 'enhanced_prompt_classification'
    })


@app.route('/process', methods=['POST'])
def process_document():
    """Process a document with prompt-based classification."""
    file_path = None
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part in request"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        
        prompt = request.form.get('prompt', 'Extract all relevant data')
        columns_param = request.form.get('columns', '')
        
        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        print(f"\n{'='*60}")
        print(f"Processing: {filename}")
        print(f"Prompt: {prompt}")
        print(f"{'='*60}")
        
        # Analyze prompt
        analyzer = PromptAnalyzer()
        analysis = analyzer.analyze(prompt)
        
        print(f"Analysis:")
        print(f"  - Columns: {analysis.columns}")
        print(f"  - Section hint: {analysis.section_hint}")
        print(f"  - Extraction type: {analysis.extraction_type.value}")
        print(f"  - Section type: {analysis.section_type}")
        
        # Extract content
        ext = os.path.splitext(filename)[1].lower()
        
        if ext == '.csv':
            text, tables = extract_csv_content(file_path)
        elif ext == '.pdf':
            text, tables = extract_pdf_content(file_path)
        else:
            return jsonify({"error": f"Unsupported file type: {ext}"}), 400
        
        if not text and not tables:
            return jsonify({"error": "Could not extract content"}), 400
        
        print(f"Extracted {len(text)} chars, {len(tables)} tables")
        
        # Create schema
        column_names = columns_param.split(',') if columns_param else analysis.columns
        schema = ExtractionSchema(column_names)
        
        # Create extraction engine
        engine = ExtractionEngine(schema, analysis)
        
        # Extract
        records = engine.extract(text, tables)
        
        # Get headers
        headers = schema.get_headers()
        display_headers = schema.get_display_headers()
        
        # Generate CSV
        csv_output = CSVExporter.export(records, headers, display_headers)
        
        # Build response
        response = {
            "success": True,
            "extractions": records,
            "headers": headers,
            "display_headers": display_headers,
            "csv": csv_output,
            "metadata": {
                "filename": filename,
                "prompt": prompt,
                "columns": column_names,
                "extraction_type": analysis.extraction_type.value,
                "section_hint": analysis.section_hint,
                "text_length": len(text),
                "tables_found": len(tables),
                "extraction_count": len(records),
                "timestamp": datetime.now().isoformat()
            }
        }
        
        print(f"Extracted {len(records)} records")
        return jsonify(response)
    
    except Exception as e:
        error_info = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        print(f"Error: {error_info}")
        return jsonify(error_info), 500
    
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        gc.collect()


@app.route('/process-multiple', methods=['POST'])
def process_multiple_documents():
    """Process multiple documents and combine results."""
    file_paths = []
    try:
        if 'files' not in request.files:
            return jsonify({"error": "No files part in request"}), 400
        
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return jsonify({"error": "No selected files"}), 400
        
        prompt = request.form.get('prompt', 'Extract all relevant data')
        columns_param = request.form.get('columns', '')
        
        # Upload restrictions from ai-agent.html
        MAX_FILES = 20
        MAX_FILE_SIZE = 15 * 1024 * 1024  # 15MB in bytes
        
        # Validate file types and collect file paths
        file_paths = []
        file_metadata = []
        
        for file in files:
            if not file.filename:
                continue
                
            # Check file count limit
            if len(file_paths) >= MAX_FILES:
                return jsonify({"error": f"Maximum {MAX_FILES} files allowed"}), 400
            
            # Check file size
            file.seek(0, 2)  # Seek to end
            file_size = file.tell()
            file.seek(0)  # Reset to beginning
            
            if file_size > MAX_FILE_SIZE:
                return jsonify({"error": f"File {file.filename} exceeds 15MB limit"}), 400
            
            filename = secure_filename(file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(file_path)
            file_paths.append(file_path)
            
            file_metadata.append({
                "filename": filename,
                "original_filename": file.filename,
                "size": file_size
            })
        
        if not file_paths:
            return jsonify({"error": "No valid files"}), 400
        
        print(f"\n{'='*60}")
        print(f"Processing {len(file_paths)} files")
        print(f"Prompt: {prompt}")
        print(f"{'='*60}")
        
        # Analyze prompt
        analyzer = PromptAnalyzer()
        analysis = analyzer.analyze(prompt)
        
        print(f"Analysis:")
        print(f"  - Columns: {analysis.columns}")
        print(f"  - Section hint: {analysis.section_hint}")
        print(f"  - Extraction type: {analysis.extraction_type.value}")
        
        # Create schema
        column_names = columns_param.split(',') if columns_param else analysis.columns
        schema = ExtractionSchema(column_names)
        
        # Create extraction engine
        engine = ExtractionEngine(schema, analysis)
        
        # Process files in parallel batches
        all_records = []
        total_text_length = 0
        total_tables = 0
        
        # Process files in batches to avoid overwhelming the server
        BATCH_SIZE = 5
        
        for i in range(0, len(file_paths), BATCH_SIZE):
            batch_paths = file_paths[i:i+BATCH_SIZE]
            batch_metadata = file_metadata[i:i+BATCH_SIZE]
            
            print(f"\nProcessing batch {i//BATCH_SIZE + 1}/{(len(file_paths)-1)//BATCH_SIZE + 1}")
            
            # Process batch in parallel
            batch_results = process_batch(batch_paths, batch_metadata, engine)
            
            # Combine results
            for result in batch_results:
                all_records.extend(result['records'])
                total_text_length += result['text_length']
                total_tables += result['tables_found']
            
            # Small delay between batches
            if i + BATCH_SIZE < len(file_paths):
                import time
                time.sleep(1)
        
        # Get headers
        headers = schema.get_headers()
        display_headers = schema.get_display_headers()
        
        # Generate CSV
        csv_output = CSVExporter.export(all_records, headers, display_headers)
        
        # Build response
        response = {
            "success": True,
            "extractions": all_records,
            "headers": headers,
            "display_headers": display_headers,
            "csv": csv_output,
            "metadata": {
                "total_files_processed": len(file_paths),
                "prompt": prompt,
                "columns": column_names,
                "extraction_type": analysis.extraction_type.value,
                "section_hint": analysis.section_hint,
                "total_text_length": total_text_length,
                "total_tables_found": total_tables,
                "total_extraction_count": len(all_records),
                "timestamp": datetime.now().isoformat(),
                "files": file_metadata,
                "upload_restrictions": {
                    "max_files": MAX_FILES,
                    "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
                    "batch_size": BATCH_SIZE
                }
            }
        }
        
        print(f"Combined extraction: {len(all_records)} total records")
        return jsonify(response)
    
    except Exception as e:
        error_info = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        print(f"Error: {error_info}")
        return jsonify(error_info), 500
    
    finally:
        # Clean up temporary files
        for file_path in file_paths:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
        gc.collect()


def process_batch(file_paths, file_metadata, engine):
    """Process a batch of files in parallel."""
    results = []
    
    def process_single_file(file_path, metadata):
        """Process a single file."""
        filename = metadata["filename"]
        try:
            # Extract content
            ext = os.path.splitext(filename)[1].lower()
            
            if ext == '.csv':
                text, tables = extract_csv_content(file_path)
            elif ext == '.pdf':
                text, tables = extract_pdf_content(file_path)
            else:
                print(f"Skipping unsupported file type: {ext}")
                return None
            
            if not text and not tables:
                print(f"No content extracted from {filename}")
                return None
            
            print(f"Extracted {len(text)} chars, {len(tables)} tables from {filename}")
            
            # Extract from this file
            records = engine.extract(text, tables)
            print(f"Extracted {len(records)} records from {filename}")
            
            # Add file identifier to records
            for record in records:
                record['source_file'] = filename
            
            return {
                'records': records,
                'text_length': len(text),
                'tables_found': len(tables),
                'filename': filename
            }
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            return None
    
    # Process files in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = []
        for file_path, metadata in zip(file_paths, file_metadata):
            future = executor.submit(process_single_file, file_path, metadata)
            futures.append(future)
        
        # Collect results
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
    
    return results


@app.route('/extract', methods=['POST'])
def extract_from_content():
    """Extract from pre-loaded content."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data"}), 400
        
        content = data.get('content', '')
        prompt = data.get('prompt', 'Extract all relevant data')
        columns = data.get('columns', [])
        
        if not content:
            return jsonify({"error": "No content"}), 400
        
        # Analyze prompt
        analyzer = PromptAnalyzer()
        analysis = analyzer.analyze(prompt)
        
        if not columns:
            columns = analysis.columns
        
        schema = ExtractionSchema(columns)
        engine = ExtractionEngine(schema, analysis)
        
        records = engine.extract(content, [])
        
        headers = schema.get_headers()
        display_headers = schema.get_display_headers()
        csv_output = CSVExporter.export(records, headers, display_headers)
        
        return jsonify({
            "success": True,
            "extractions": records,
            "headers": headers,
            "display_headers": display_headers,
            "csv": csv_output,
            "metadata": {
                "extraction_count": len(records),
                "extraction_type": analysis.extraction_type.value
            }
        })
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/export/csv', methods=['POST'])
def export_csv():
    """Export data as CSV."""
    try:
        data = request.get_json()
        extractions = data.get('extractions', [])
        headers = data.get('headers', [])
        display_headers = data.get('display_headers')
        
        if not extractions:
            return jsonify({"error": "No data"}), 400
        
        if not headers:
            headers = list(extractions[0].keys())
        
        csv_output = CSVExporter.export(extractions, headers, display_headers)
        
        return jsonify({
            "success": True,
            "csv": csv_output,
            "row_count": len(extractions)
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PYTHON_PORT", 5001))
    print(f"\n{'='*60}")
    print(f"Document Extraction Service")
    print(f"Features: Chapter/Section Detection, Prompt Classification")
    print(f"Port: {port}")
    print(f"Backends: PyMuPDF={HAS_PYMUPDF}, pdfplumber={HAS_PDFPLUMBER}")
    print(f"{'='*60}\n")
    app.run(host='0.0.0.0', port=port, debug=True)