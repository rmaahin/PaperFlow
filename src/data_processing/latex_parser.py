import os
import glob
import re
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple

ARXIV_RAW_PATH = "data/raw/arxiv"
PROCESSED_DATA_PATH = "data/processed/arxiv"

class LatexParser:
    def __init__(self, paper_dir, arxiv_id):
        self.paper_dir = paper_dir
        self.latex_dir = Path(paper_dir) / "latex_files"
        self.main_tex_file = None
        self.arxiv_id = arxiv_id
        self.processed_files = set()  # Track processed files to avoid circular includes

    def find_main_tex_file(self) -> Tuple[Optional[Path], Optional[str]]:
        """Find and return the main .tex file and its content."""
        tex_files = glob.glob(str(Path(ARXIV_RAW_PATH) / self.arxiv_id / "**/*.tex"), recursive=True)
        
        # First pass: look for \documentclass
        for tex_file in tex_files:
            try:
                with open(tex_file, 'r', encoding='utf-8', errors='ignore') as file:
                    content = file.read()
                    if "\\documentclass" in content:
                        return Path(tex_file), content
            except Exception as e:
                print(f"Error reading {tex_file}: {e}")
                continue
        
        # Second pass: common names
        common_main_tex_filenames = ['main.tex', 'paper.tex', 'manuscript.tex']
        for name in common_main_tex_filenames:
            potential_path = Path(ARXIV_RAW_PATH) / self.arxiv_id / "latex_files" / name
            if potential_path.exists():
                try:
                    with open(potential_path, 'r', encoding='utf-8', errors='ignore') as file:
                        content = file.read()
                    return potential_path, content
                except Exception as e:
                    print(f"Error reading {potential_path}: {e}")
                    continue
        
        print(f"Warning: No main .tex file found for {self.arxiv_id}")
        return None, None
    
    def resolve_inputs(self, latex_content: str, base_path: Path) -> str:
        """Resolve \\input{} and \\include{} commands to merge content from included files."""
        
        def extract_braced_content(text: str, start_pos: int) -> Optional[str]:
            """Extract content from balanced braces starting at position."""
            if start_pos >= len(text) or text[start_pos] != '{':
                return None
            
            brace_count = 0
            i = start_pos
            while i < len(text):
                if text[i] == '{':
                    brace_count += 1
                elif text[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        return text[start_pos + 1:i]
                i += 1
            return None
        
        def replace_input(match):
            command = match.group(0)
            
            # Extract filename from \input{filename} or \include{filename}
            # Find the opening brace
            brace_start = command.find('{')
            if brace_start == -1:
                return command
            
            filename = extract_braced_content(command, brace_start)
            if not filename:
                return command
            
            # Add .tex extension if missing
            if not filename.endswith('.tex'):
                filename = filename + '.tex'
            
            # Try multiple path resolution strategies
            possible_paths = [
                base_path / filename,                           # Same directory
                base_path / Path(filename).name,                # Just filename
                self.latex_dir / filename,                      # Project root
                self.latex_dir / Path(filename).name,           # Project root, just filename
            ]
            
            # Also try subdirectories if filename has path components
            if '/' in filename:
                possible_paths.append(base_path.parent / filename)
            
            for file_path in possible_paths:
                if file_path.exists() and str(file_path.resolve()) not in self.processed_files:
                    try:
                        self.processed_files.add(str(file_path.resolve()))
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            included_content = f.read()
                            # Recursively resolve inputs in included file
                            return self.resolve_inputs(included_content, file_path.parent)
                    except Exception as e:
                        print(f"Warning: Could not include {file_path}: {e}")
                        return command
            
            # File not found - keep original command
            print(f"Warning: Could not resolve include: {filename}")
            return command
        
        # Replace \input{} and \include{} commands
        # Use non-greedy matching and handle nested braces
        latex_content = re.sub(r'\\input\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', replace_input, latex_content)
        latex_content = re.sub(r'\\include\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', replace_input, latex_content)
        
        return latex_content

    def extract_sections(self, latex_content: str) -> List[Dict[str, str]]:
        """Extract all sections, subsections, subsubsections from LaTeX content."""
        sections = []
        
        # Pattern to match section commands
        # Matches: \section{title}, \section[short]{title}, \section*{title}
        pattern = r'\\((?:sub)*section|paragraph|subparagraph)(\*)?(?:\[[^\]]*\])?\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}'
        
        # Find all section matches with their positions
        matches = list(re.finditer(pattern, latex_content))
        
        for i, match in enumerate(matches):
            section_type = match.group(1)
            is_starred = match.group(2) is not None
            title = match.group(3)
            
            # Find content between this section and the next
            start_pos = match.end()
            
            # End position is either the next section or end of document
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                end_pos = len(latex_content)
            
            # Extract content
            content = latex_content[start_pos:end_pos]
            
            # Clean up content (normalize whitespace but preserve structure)
            content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)  # Remove excessive blank lines
            content = content.strip()
            
            sections.append({
                'type': section_type,
                'title': title.strip(),
                'is_starred': is_starred,
                'content': content[:5000]  # Limit content length to prevent memory issues
            })
        
        return sections

    def extract_figures(self, latex_content: str) -> List[Dict[str, str]]:
        """Extract all figure environments from LaTeX content."""
        figures = []
        
        # Pattern to match \begin{figure}...\end{figure}
        pattern = r'\\begin\{figure\*?\}(?:\[[^\]]*\])?(.*?)\\end\{figure\*?\}'
        
        matches = re.finditer(pattern, latex_content, re.DOTALL)
        
        for idx, match in enumerate(matches, 1):
            figure_content = match.group(1)
            
            # Extract caption with nested braces handling
            caption = ""
            caption_match = re.search(r'\\caption\s*(?:\[[^\]]*\])?\s*\{', figure_content)
            if caption_match:
                start_pos = caption_match.end() - 1
                brace_count = 0
                i = start_pos
                while i < len(figure_content):
                    if figure_content[i] == '{':
                        brace_count += 1
                    elif figure_content[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            caption = figure_content[start_pos + 1:i]
                            break
                    i += 1
            
            # Extract label
            label_match = re.search(r'\\label\{([^}]+)\}', figure_content)
            label = label_match.group(1) if label_match else f"figure_{idx}"
            
            # Extract includegraphics
            graphics_match = re.search(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', figure_content)
            image_path = graphics_match.group(1) if graphics_match else ""
            
            figures.append({
                'label': label,
                'caption': caption.strip(),
                'image_path': image_path,
                'full_content': figure_content[:1000]  # Limit size
            })
        
        return figures

    def extract_tables(self, latex_content: str) -> List[Dict[str, str]]:
        """Extract all table environments from LaTeX content."""
        tables = []
        
        # Pattern to match \begin{table}...\end{table}
        pattern = r'\\begin\{table\*?\}(?:\[[^\]]*\])?(.*?)\\end\{table\*?\}'
        
        matches = re.finditer(pattern, latex_content, re.DOTALL)
        
        for idx, match in enumerate(matches, 1):
            table_content = match.group(1)
            
            # Extract caption with nested braces
            caption = ""
            caption_match = re.search(r'\\caption\s*(?:\[[^\]]*\])?\s*\{', table_content)
            if caption_match:
                start_pos = caption_match.end() - 1
                brace_count = 0
                i = start_pos
                while i < len(table_content):
                    if table_content[i] == '{':
                        brace_count += 1
                    elif table_content[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            caption = table_content[start_pos + 1:i]
                            break
                    i += 1
            
            # Extract label
            label_match = re.search(r'\\label\{([^}]+)\}', table_content)
            label = label_match.group(1) if label_match else f"table_{idx}"
            
            # Extract tabular environment
            tabular_match = re.search(
                r'\\begin\{tabular\}(?:\[[^\]]*\])?\{([^}]+)\}(.*?)\\end\{tabular\}',
                table_content,
                re.DOTALL
            )
            
            if tabular_match:
                column_spec = tabular_match.group(1)
                tabular_content = tabular_match.group(2)
            else:
                column_spec = ""
                tabular_content = ""
            
            tables.append({
                'label': label,
                'caption': caption.strip(),
                'column_spec': column_spec,
                'tabular_content': tabular_content[:1000],  # Limit size
                'full_content': table_content[:1000]
            })
        
        return tables

    def extract_equations(self, latex_content: str) -> List[Dict[str, str]]:
        """Extract all equation environments from LaTeX content."""
        equations = []
        
        # Patterns for display equation environments
        equation_patterns = [
            (r'\\begin\{equation\*?\}(.*?)\\end\{equation\*?\}', 'equation'),
            (r'\\begin\{align\*?\}(.*?)\\end\{align\*?\}', 'align'),
            (r'\\begin\{eqnarray\*?\}(.*?)\\end\{eqnarray\*?\}', 'eqnarray'),
            (r'\\begin\{multline\*?\}(.*?)\\end\{multline\*?\}', 'multline'),
            (r'\\begin\{gather\*?\}(.*?)\\end\{gather\*?\}', 'gather'),
            (r'\\begin\{displaymath\}(.*?)\\end\{displaymath\}', 'displaymath'),
            (r'\\\[(.*?)\\\]', 'display'),  # \[ ... \]
        ]
        
        for pattern, eq_type in equation_patterns:
            matches = re.finditer(pattern, latex_content, re.DOTALL)
            
            for match in matches:
                eq_content = match.group(1)
                
                # Extract label if present
                label_match = re.search(r'\\label\{([^}]+)\}', eq_content)
                label = label_match.group(1) if label_match else None
                
                # Clean up equation content
                eq_content_clean = eq_content.strip()
                
                equations.append({
                    'type': eq_type,
                    'label': label,
                    'content': eq_content_clean,
                    'is_display': True
                })
        
        # Extract inline equations - be more conservative to avoid false positives
        # Only match $ ... $ where content doesn't span multiple lines and is reasonable length
        inline_pattern = r'\$([^\$\n]{1,200})\$'
        matches = re.finditer(inline_pattern, latex_content)
        
        for match in matches:
            eq_content = match.group(1).strip()
            # Skip if it looks like a regular dollar amount
            if re.match(r'^\d+(\.\d+)?$', eq_content):
                continue
            
            equations.append({
                'type': 'inline',
                'label': None,
                'content': eq_content,
                'is_display': False
            })
        
        return equations

    def parse(self, save_to_file: bool = False, output_format: str = 'json') -> Optional[Dict]:
        """
        Parse LaTeX file and extract sections, figures, tables, and equations.
        
        Args:
            save_to_file: If True, automatically save parsed data to file
            output_format: Format to save in ('json' or 'jsonl') if save_to_file is True
        
        Returns:
            Dictionary containing parsed sections, figures, tables, and equations
        """
        try:
            main_file, main_latex_content = self.find_main_tex_file()

            if not main_file or not main_latex_content:
                print(f"No .tex file available to parse for {self.arxiv_id}")
                return None

            # Reset processed files for this parse
            self.processed_files = set()
            self.processed_files.add(str(Path(main_file).resolve()))
            
            # Resolve input/include commands
            base_path = Path(main_file).parent
            print(f"Resolving includes for {self.arxiv_id}...")
            resolved_content = self.resolve_inputs(main_latex_content, base_path)
            
            # Extract all components
            print(f"Extracting sections...")
            sections = self.extract_sections(resolved_content)
            
            print(f"Extracting figures...")
            figures = self.extract_figures(resolved_content)
            
            print(f"Extracting tables...")
            tables = self.extract_tables(resolved_content)
            
            print(f"Extracting equations...")
            equations = self.extract_equations(resolved_content)
            
            parsed_data = {
                "arxiv_id": self.arxiv_id,
                "main_tex_file": str(main_file),
                "included_files": [str(f) for f in self.processed_files],
                "sections": sections,
                "figures": figures,
                "tables": tables,
                "equations": equations,
                "stats": {
                    "num_sections": len(sections),
                    "num_figures": len(figures),
                    "num_tables": len(tables),
                    "num_equations": len(equations)
                }
            }
            
            # Save to file if requested
            if save_to_file:
                self.save_parsed_data(parsed_data, output_format)
            
            return parsed_data
            
        except Exception as e:
            print(f"Error parsing {self.arxiv_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_methodology_sections(self, parsed_data: Dict) -> List[Dict[str, str]]:
        """Extract sections likely containing methodology/implementation details."""
        methodology_keywords = [
            'method', 'approach', 'algorithm', 'implementation', 
            'architecture', 'model', 'framework', 'technique',
            'procedure', 'design', 'system'
        ]
        
        methodology_sections = []
        for section in parsed_data.get('sections', []):
            title_lower = section['title'].lower()
            if any(keyword in title_lower for keyword in methodology_keywords):
                methodology_sections.append(section)
        
        return methodology_sections
    
    def get_section_by_title(self, title: str, parsed_data: Dict) -> Optional[Dict[str, str]]:
        """Get a specific section by its title (case-insensitive)."""
        title_lower = title.lower()
        for section in parsed_data.get('sections', []):
            if title_lower in section['title'].lower():
                return section
        return None
    
    def get_figure_by_label(self, label: str, parsed_data: Dict) -> Optional[Dict[str, str]]:
        """Get a specific figure by its label."""
        for figure in parsed_data.get('figures', []):
            if figure['label'] == label:
                return figure
        return None
    
    def get_table_by_label(self, label: str, parsed_data: Dict) -> Optional[Dict[str, str]]:
        """Get a specific table by its label."""
        for table in parsed_data.get('tables', []):
            if table['label'] == label:
                return table
        return None
    
    def get_equation_by_label(self, label: str, parsed_data: Dict) -> Optional[Dict[str, str]]:
        """Get a specific equation by its label."""
        for equation in parsed_data.get('equations', []):
            if equation.get('label') == label:
                return equation
        return None
    
    def save_parsed_data(self, parsed_data: Dict, output_format: str = 'json') -> Optional[str]:
        """
        Save parsed data to a file.
        
        Args:
            parsed_data: The parsed data dictionary from parse() method
            output_format: Format to save in ('json' or 'jsonl')
        
        Returns:
            Path to the saved file, or None if saving failed
        """
        if not parsed_data:
            print("No parsed data to save.")
            return None
        
        # Create processed data directory if it doesn't exist
        processed_dir = Path(PROCESSED_DATA_PATH) / self.arxiv_id
        processed_dir.mkdir(parents=True, exist_ok=True)
        
        if output_format == 'json':
            output_file = processed_dir / f"{self.arxiv_id}_parsed.json"
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(parsed_data, f, indent=2, ensure_ascii=False)
                print(f"Parsed data saved to: {output_file}")
                return str(output_file)
            except Exception as e:
                print(f"Error saving parsed data: {e}")
                return None
                
        elif output_format == 'jsonl':
            # Save each component as a separate JSONL file
            output_files = {}
            for component_type in ['sections', 'figures', 'tables', 'equations']:
                output_file = processed_dir / f"{self.arxiv_id}_{component_type}.jsonl"
                try:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        for item in parsed_data.get(component_type, []):
                            f.write(json.dumps(item, ensure_ascii=False) + '\n')
                    output_files[component_type] = str(output_file)
                except Exception as e:
                    print(f"Error saving {component_type}: {e}")
            
            # Save metadata separately
            metadata_file = processed_dir / f"{self.arxiv_id}_metadata.json"
            try:
                metadata = {
                    'arxiv_id': parsed_data['arxiv_id'],
                    'main_tex_file': parsed_data['main_tex_file'],
                    'included_files': parsed_data['included_files'],
                    'stats': parsed_data['stats']
                }
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                output_files['metadata'] = str(metadata_file)
                print(f"All components saved to {processed_dir}")
            except Exception as e:
                print(f"Error saving metadata: {e}")
            
            return output_files
        else:
            print(f"Unsupported output format: {output_format}")
            return None
    
    def load_parsed_data(self, input_file: Optional[str] = None) -> Optional[Dict]:
        """
        Load previously parsed data from a JSON file.
        
        Args:
            input_file: Path to the JSON file. If None, looks for default file.
        
        Returns:
            Parsed data dictionary, or None if loading failed
        """
        if input_file is None:
            input_file = Path(PROCESSED_DATA_PATH) / self.arxiv_id / f"{self.arxiv_id}_parsed.json"
        else:
            input_file = Path(input_file)
        
        if not input_file.exists():
            print(f"Parsed data file not found: {input_file}")
            return None
        
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                parsed_data = json.load(f)
            print(f"Parsed data loaded from: {input_file}")
            return parsed_data
        except Exception as e:
            print(f"Error loading parsed data: {e}")
            return None


if __name__ == "__main__":
    arxiv_id = "1706.03762"
    paper_dir = Path(ARXIV_RAW_PATH) / arxiv_id
    
    lp = LatexParser(paper_dir, arxiv_id)
    
    # Parse and save to file
    parsed_data = lp.parse(save_to_file=True, output_format='json')
    
    if parsed_data:
        print(f"\n{'='*60}")
        print(f"Parsing Summary for {arxiv_id}")
        print(f"{'='*60}")
        print(f"Sections: {parsed_data['stats']['num_sections']}")
        print(f"Figures: {parsed_data['stats']['num_figures']}")
        print(f"Tables: {parsed_data['stats']['num_tables']}")
        print(f"Equations: {parsed_data['stats']['num_equations']}")
        print(f"Included files: {len(parsed_data['included_files'])}")
        
        # Show methodology sections
        methodology = lp.get_methodology_sections(parsed_data)
        if methodology:
            print(f"\n{'='*60}")
            print(f"Methodology Sections Found: {len(methodology)}")
            print(f"{'='*60}")
            for section in methodology:
                print(f"- [{section['type']}] {section['title']}")
                print(f"  Content preview: {section['content'][:150]}...\n")