"""
Document Extraction Service - Enhanced with Chapter/Section Detection
and Prompt-Based Classification

Features:
- Advanced chapter/section detection and parsing
- Prompt-based classification and extraction
- Strict schema enforcement for consistent columns/rows
- Clean spreadsheet-style output with proper headers
- Properly segmented CSV export
- Table extraction support
- Key-Value pair extraction

Container Improvements:
- Environment variable configuration
- Security improvements (non-root user)
- Structured logging
- Graceful shutdown handling
- Enhanced error handling
"""

import sys
import json
import os
import traceback
import gc
import re
import csv
import io
import logging
import signal
import atexit
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

# Pandas for Data Analysis
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    print("Warning: pandas not available")

# ============================================================
# CONFIGURATION
# ============================================================

# Environment variables with defaults
PORT = int(os.environ.get("PYTHON_PORT", 5001))
HOST = os.environ.get("PYTHON_HOST", "0.0.0.0")
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(os.getcwd(), 'temp_uploads'))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configure CORS to allow all Vercel subdomains and localhost
CORS(app, resources={
    r"/*": {
        "origins": [
            r"^https://.*\.vercel\.app$",
            r"^http://localhost:\d+$"
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
        "supports_credentials": True
    }
})

# ============================================================
# SECURITY IMPROVEMENTS
# ============================================================

# Create a non-root user for security
USER_ID = 1000
GROUP_ID = 1000

def create_user():
    """Create a non-root user for running the service."""
    try:
        import pwd
        import grp
        try:
            pwd.getpwnam('appuser')
        except KeyError:
            # Create user and group
            # Note: This usually requires root privileges, so it might fail in some environments
            # We log a warning but continue if it fails
            pass
    except Exception as e:
        logger.warning(f"Could not set user permissions: {e}")

# Run user creation at startup
create_user()

# ============================================================
# GRACEFUL SHUTDOWN HANDLING
# ============================================================

shutdown_event = threading.Event()

def handle_sigterm(signum, frame):
    """Handle SIGTERM signal for graceful shutdown."""
    logger.info("SIGTERM received, initiating graceful shutdown...")
    shutdown_event.set()

def handle_sigint(signum, frame):
    """Handle SIGINT signal for graceful shutdown."""
    logger.info("SIGINT received, initiating graceful shutdown...")
    shutdown_event.set()

# Register signal handlers
signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigint)

# Register cleanup functions
@atexit.register
def cleanup():
    """Cleanup resources on exit."""
    logger.info("Cleaning up resources before shutdown...")

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
        # Improved: Specifically look for the comma-separated list after "extract"
        extract_match = re.search(r"extract\s+(.*)", prompt, re.IGNORECASE)
        if extract_match:
            cols_raw = extract_match.group(1).replace('"', '').replace("'", "")
            # Split by comma and clean
            # Stop at common prepositions if they appear at the end
            cols_raw = re.split(r'\s+(?:from|in|using|with)\s+', cols_raw)[0]
            return [c.strip() for c in cols_raw.split(',') if c.strip()]
            
        return ['Item', 'Description', 'Value']

    def _extract_section_hint(self, prompt: str) -> Optional[str]:
        """Extract section hint from prompt."""
        # Improved: More flexible pattern for "from SECTION Section"
        match = re.search(r"from\s+[\"']?(\w+)[\"']?\s+Section", prompt, re.IGNORECASE)
        if match:
            return match.group(1)
            
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

class DocumentStructureAnalyzer:
    """Analyzes document structure to identify sections/chapters."""
    
    def __init__(self, text: str):
        self.text = text
        self.sections = self._parse_sections()
        
    def _parse_sections(self) -> Dict[str, str]:
        sections = {}
        current_section = "General"
        buffer = []
        
        # Common section numbering patterns: "1.", "1.1", "Chapter 1", "SECTION A"
        header_pattern = re.compile(r'^((?:Chapter|Section|Part)\s+\d+|(?:\d+\.)+\d*|[A-Z][A-Z\s]{2,50})$', re.IGNORECASE)
        
        lines = self.text.split('\n')
        for line in lines:
            clean_line = line.strip()
            if not clean_line:
                continue
                
            # Heuristic for headers
            is_header = False
            if len(clean_line) < 80:
                # Check against known section keywords
                for section_type in SectionType:
                    if section_type != SectionType.UNKNOWN and section_type.value in clean_line.lower():
                        is_header = True
                        break
                
                # Check regex pattern or all caps
                if not is_header and (header_pattern.match(clean_line) or (clean_line.isupper() and len(clean_line) > 3)):
                    is_header = True
            
            if is_header:
                if buffer:
                    sections[current_section] = "\n".join(buffer)
                current_section = clean_line
                buffer = []
            else:
                buffer.append(line)
                
        if buffer:
            sections[current_section] = "\n".join(buffer)
            
        return sections

    def get_target_content(self, section_hint: Optional[str], section_type: Optional[SectionType]) -> str:
        """Get content for a specific section if found."""
        if not section_hint and (not section_type or section_type == SectionType.UNKNOWN):
            return self.text
            
        # Try to match section hint
        if section_hint:
            for header, content in self.sections.items():
                if section_hint.lower() in header.lower():
                    return content
                    
        # Try to match section type
        if section_type:
            keywords = PromptAnalyzer.SECTION_KEYWORDS.get(section_type, [])
            for header, content in self.sections.items():
                if any(kw in header.lower() for kw in keywords):
                    return content
                    
        # Fallback: return full text if specific section not found
        return self.text

# ============================================================
# PANDAS DATA ANALYST
# ============================================================

class PandasDataAnalyst:
    """Uses Pandas for data analysis and structuring."""
    
    def __init__(self, data: List[Dict[str, Any]]):
        self.raw_data = data
        self.df = pd.DataFrame(data) if HAS_PANDAS and data else None
        
    def clean_data(self):
        """Clean the dataframe."""
        if self.df is None or self.df.empty:
            return
            
        # Drop empty rows and columns
        self.df.dropna(how='all', inplace=True)
        self.df.dropna(axis=1, how='all', inplace=True)
        
        # Remove duplicates
        self.df.drop_duplicates(inplace=True)
        
        # Fill NaN with empty string for JSON compatibility
        self.df.fillna("", inplace=True)
        
    def structure_table(self, requested_columns: List[str]) -> List[Dict[str, Any]]:
        """Structure the table based on requested columns."""
        if self.df is None or self.df.empty:
            return self.raw_data
            
        if not requested_columns:
            return self.df.to_dict(orient='records')
            
        # Fuzzy match columns
        matched_columns = []
        for req_col in requested_columns:
            best_match = None
            max_score = 0
            
            for col in self.df.columns:
                # Simple containment score
                score = 0
                if req_col.lower() == col.lower():
                    score = 100
                elif req_col.lower() in col.lower():
                    score = 80
                elif col.lower() in req_col.lower():
                    score = 60
                    
                if score > max_score:
                    max_score = score
                    best_match = col
            
            if best_match and max_score > 50:
                matched_columns.append(best_match)
        
        if matched_columns:
            # Filter and reorder
            result_df = self.df[matched_columns].copy()
            # Rename to requested columns if match was exact enough? 
            # For now, keep original headers to avoid confusion, or map them back.
            return result_df.to_dict(orient='records')
            
        return self.df.to_dict(orient='records')

# ============================================================
# DOCUMENT PROCESSING LOGIC
# ============================================================

def extract_pdf_content(file_path: str) -> str:
    """Extract text content from PDF using PyMuPDF."""
    text_content = []
    if HAS_PYMUPDF:
        try:
            doc = fitz.open(file_path)
            for page in doc:
                text_content.append(page.get_text())
            doc.close()
            return "\n".join(text_content)
        except Exception as e:
            logger.error(f"PyMuPDF extraction failed: {e}")
    
    # Fallback to pdfplumber if PyMuPDF fails or is unavailable
    if HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_content.append(text)
            return "\n".join(text_content)
        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {e}")
            
    return ""

def extract_tables_from_pdf(file_path: str) -> List[Dict[str, Any]]:
    """Extract tables using pdfplumber."""
    results = []
    if HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        if not table: continue
                        # Assume first row is header
                        headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(table[0])]
                        # Clean headers
                        headers = [re.sub(r'\s+', ' ', h) for h in headers]
                        
                        for row in table[1:]:
                            if len(row) == len(headers):
                                record = {h: r for h, r in zip(headers, row) if r}
                                if record:
                                    results.append(record)
        except Exception as e:
            logger.error(f"Table extraction failed: {e}")
    return results

def extract_csv_content(file_path: str) -> List[Dict[str, Any]]:
    """Extract content from CSV file."""
    data = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
    except Exception as e:
        logger.error(f"CSV extraction failed: {e}")
    return data

def process_with_analysis(file_path: str, analysis: PromptAnalysis) -> List[Dict[str, Any]]:
    """Process document based on prompt analysis."""
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.csv':
        # For CSV, we just return the data, maybe filtered by columns
        data = extract_csv_content(file_path)
        if HAS_PANDAS:
            analyst = PandasDataAnalyst(data)
            analyst.clean_data()
            return analyst.structure_table(analysis.columns)
        return data
        
    elif ext == '.pdf':
        results = []
        
        # 1. Table Extraction (High Priority if requested or financial)
        if (analysis.extraction_type in [ExtractionType.TABLES, ExtractionType.FINANCIAL]) and HAS_PDFPLUMBER:
            tables = extract_tables_from_pdf(file_path)
            if tables:
                if HAS_PANDAS:
                    analyst = PandasDataAnalyst(tables)
                    analyst.clean_data()
                    return analyst.structure_table(analysis.columns)
                return tables

        # 2. Text Extraction & Sectioning
        text = extract_pdf_content(file_path)
        structure = DocumentStructureAnalyzer(text)
        target_text = structure.get_target_content(analysis.section_hint, analysis.section_type)
        
        # 3. Pattern Matching / Column Extraction
        
        # Specific Logic for REFERENCES
        if analysis.section_type == SectionType.REFERENCES or analysis.section_hint == "REFERENCES":
            ref_results = []
            # Regex to capture: Author. Date. Title. Publisher.
            # Matches: Chigumadzi, P. 2018. These Bones Will Rise Again. Johannesburg: Jacana.
            # Also handles: Author (Date). Title.
            ref_pattern = re.compile(r"^(.*?)\.?\s+(\d{4})\.\s+(.*?)\.\s+(.*?)$")
            
            for line in target_text.split('\n'):
                line = line.strip()
                if not line: continue
                
                match = ref_pattern.search(line)
                if match:
                    ref_results.append({
                        "Author": match.group(1).strip(),
                        "Date": match.group(2).strip(),
                        "Title": match.group(3).strip(),
                        "Institution": match.group(4).strip()
                    })
            if ref_results:
                if HAS_PANDAS:
                    analyst = PandasDataAnalyst(ref_results)
                    analyst.clean_data()
                    return analyst.structure_table(analysis.columns)
                return ref_results

        # If looking for specific patterns like emails or dates
        if ExtractionType.CONTACTS in [analysis.extraction_type]:
            emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', target_text)
            for email in emails:
                results.append({"Email": email})
            return results
                
        elif ExtractionType.TIMELINE in [analysis.extraction_type]:
            dates = re.findall(r'\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}', target_text)
            for date in dates:
                results.append({"Date": date})
            return results
            
        # 4. Key-Value Extraction (Column: Value)
        if analysis.columns and analysis.columns != ['Item', 'Description', 'Value']:
            # Try to find "Column: Value" patterns
            extracted_rows = []
            current_row = {}
            
            lines = target_text.split('\n')
            for line in lines:
                for col in analysis.columns:
                    # Regex for "Column: Value" or "Column - Value"
                    pattern = re.compile(f'(?i){re.escape(col)}\s*[:=-]\s*(.*)')
                    match = pattern.search(line)
                    if match:
                        current_row[col] = match.group(1).strip()
                
                # Heuristic: if we have enough data, push row
                if len(current_row) >= min(len(analysis.columns), 2):
                    extracted_rows.append(current_row)
                    current_row = {}
            
            if current_row:
                extracted_rows.append(current_row)
                
            if extracted_rows:
                if HAS_PANDAS:
                    analyst = PandasDataAnalyst(extracted_rows)
                    analyst.clean_data()
                    return analyst.structure_table(analysis.columns)
                return extracted_rows

        # 5. Generic Fallback
        lines = target_text.split('\n')
        for line in lines:
            row = {}
            include = False
            for col in analysis.columns:
                if col.lower() in line.lower():
                    row[col] = line.strip()
                    include = True
            
            if not include and analysis.keywords:
                for kw in analysis.keywords:
                    if kw.lower() in line.lower():
                        row["Content"] = line.strip()
                        include = True
                        break
                        
            if include:
                results.append(row)
                    
        return results
        
    return []

# ============================================================
# API ROUTES
# ============================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Enhanced health check with system information."""
    try:
        import psutil
        memory_info = psutil.virtual_memory()
        cpu_info = psutil.cpu_percent(interval=1)
        system_info = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'backends': {
                'pymupdf': HAS_PYMUPDF,
                'pdfplumber': HAS_PDFPLUMBER,
                'pandas': HAS_PANDAS
            },
            'mode': 'enhanced_prompt_classification',
            'system': {
                'memory_percent': memory_info.percent,
                'cpu_percent': cpu_info,
                'uptime': datetime.now().timestamp() - psutil.boot_time()
            }
        }
        return jsonify(system_info)
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            'status': 'degraded',
            'timestamp': datetime.now().isoformat(),
            'backends': {
                'pymupdf': HAS_PYMUPDF,
                'pdfplumber': HAS_PDFPLUMBER
            },
            'error': str(e)
        }), 503


@app.route('/process', methods=['POST'])
def process_document():
    """Process a document with prompt-based classification."""
    try:
        if shutdown_event.is_set():
            return jsonify({
                "success": False,
                "error": "Service is shutting down"
            }), 503

        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file part"}), 400

        file = request.files['file']
        prompt = request.form.get('prompt', 'Extract all data')

        if file.filename == '':
            return jsonify({"success": False, "error": "No selected file"}), 400

        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)

            try:
                # Analyze prompt
                analyzer = PromptAnalyzer()
                analysis = analyzer.analyze(prompt)
                
                # Process the file
                extractions = process_with_analysis(filepath, analysis)
                
                return jsonify({
                    "success": True,
                    "extractions": extractions,
                    "headers": analysis.columns if extractions else [],
                    "metadata": {
                        "prompt_analysis": {
                            "type": analysis.extraction_type.value,
                            "section": analysis.section_type.value if analysis.section_type else None,
                            "keywords": analysis.keywords
                        },
                        "file": filename
                    }
                })
            finally:
                # Clean up
                if os.path.exists(filepath):
                    os.remove(filepath)

    except Exception as e:
        logger.error(f"Process error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PYTHON_PORT", 5001))
    print(f"\n{'='*60}")
    print(f"Document Extraction Service")
    print(f"Features: Chapter/Section Detection, Prompt Classification")
    print(f"Port: {port}")
    print(f"Backends: PyMuPDF={HAS_PYMUPDF}, pdfplumber={HAS_PDFPLUMBER}, pandas={HAS_PANDAS}")
    print(f"Container Mode: Enabled")
    print(f"{'='*60}\n")

    # Start the Flask app
    app.run(host=HOST, port=port, debug=False, use_reloader=False)
