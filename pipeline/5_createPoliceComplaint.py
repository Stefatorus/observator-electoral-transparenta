import os
import re
from collections import defaultdict
from typing import Optional, Dict, Tuple
import unicodedata

def extract_police_message(xml_content: str) -> Optional[str]:
    pattern = r'<message-for-police>(.*?)</message-for-police>'
    match = re.search(pattern, xml_content, re.DOTALL)
    return match.group(1).strip() if match else None

def parse_complaint(message: str) -> Tuple[str, str]:
    # Normalize and remove diacritics
    message = unicodedata.normalize('NFKD', message).encode('ASCII', 'ignore').decode('ASCII')
    parts = message.split(', pentru incalcarea articolului 55 t) din Legea 370/2004, prin', 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return message, ""

def convert_fb_ids_to_links(text: str) -> str:
    """Convert large numbers that look like Facebook IDs to embedded links."""
    pattern = r'(?<!\d)(\d{10,16})(?!\d)'

    def replace_number(match):
        number = match.group(1)
        url = f'https://www.facebook.com/ads/library/?id={number}'
        # Return LaTeX code to display the number as a link
        return f'\\href{{{url}}}{{{number}}}'

    return re.sub(pattern, replace_number, text)

def escape_latex(text: str) -> str:
    """Escape special LaTeX characters, preserving URLs and hyperlinks."""
    chars = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\^{}',
        '\\': r'\textbackslash{}',
    }

    # First convert Facebook IDs to links
    text = convert_fb_ids_to_links(text)

    # Then escape special characters, preserving URLs and hyperlinks
    parts = []
    url_pattern = r'(\\url\{[^}]+\}|\\href\{[^}]+\}\{[^}]+\})'
    last_end = 0

    for match in re.finditer(url_pattern, text):
        start, end = match.span()
        # Escape text before the URL/hyperlink
        before_url = ''.join(chars.get(c, c) for c in text[last_end:start])
        parts.extend([before_url, text[start:end]])
        last_end = end

    if last_end < len(text):
        parts.append(''.join(chars.get(c, c) for c in text[last_end:]))

    return ''.join(parts)

def create_latex_document(police_msg: str, complaints_by_entity: Dict[str, list], output_file: str):
    latex_content = r"""\documentclass[a4paper,12pt]{article}
\usepackage[romanian]{babel}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{geometry}
\usepackage{enumitem}
\usepackage{titlesec}
\usepackage{parskip}
\usepackage{microtype}
\usepackage[none]{hyphenat}
\usepackage{ragged2e}
\usepackage{url}
\usepackage{xurl}
\usepackage{hyperref}
\usepackage{fancyhdr}
\usepackage{listings}
\usepackage{tocloft}
\usepackage{lastpage}  % <-- Added lastpage package

% Set margins and spacing
\geometry{
    a4paper,
    margin=2.5cm,
    includehead
}

% Header and Footer
\pagestyle{fancy}
\fancyhf{}
\lhead{Plângere Contravențională}
\rhead{pagina \thepage/\pageref{LastPage}}  % <-- Updated header
\renewcommand{\headrulewidth}{0.4pt}

% Table of Contents formatting
\renewcommand{\contentsname}{Cuprins}
\setcounter{tocdepth}{2}  % Include up to subsections in TOC
\renewcommand{\cftsecfont}{\normalsize\bfseries}
\renewcommand{\cftsubsecfont}{\normalsize}
\renewcommand{\cftsecpagefont}{\normalsize}
\renewcommand{\cftsubsecpagefont}{\normalsize}
\setlength{\cftbeforesecskip}{5pt}
\setlength{\cftbeforesubsecskip}{2pt}

% Section formatting
\titleformat{\section}
  {\normalfont\Large\bfseries}{\thesection.}{0.5em}{}
\titleformat{\subsection}
  {\normalfont\large\bfseries}{\thesubsection.}{0.5em}{}

\begin{document}

\begin{center}
    \Large\textbf{PLÂNGERE CONTRAVENȚIONALĂ}
\end{center}

\vspace{1cm}

Subsemnatul Deleanu Ștefan-Lucian, domiciliat în Jud. Cluj, Cluj-Napoca, Str. Aurel Vlaicu, nr. 2, bloc 5A, Sc. I, etaj 7, ap. 28, în calitate de observator electoral acreditat de Funky Citizens, asociatie acreditata de Autoritatea Electorala Permanenta prin ACREDITAREA nr. 29743/07.10.2024, în temeiul prevederilor Legii 370/2004 privind alegerea Președintelui României, cu modificările și completările ulterioare, formulez următoarea:

\vspace{0.5cm}
\begin{center}
\textbf{\Large PLÂNGERE CONTRAVENȚIONALĂ}
\end{center}
\vspace{0.5cm}

prin care sesizez următoarele contraventii definite de art. 55 lit t), art 56, pg 1, pg 2 lit a, din Legea 370/2004 privind alegerea Președintelui României.

In analiza caracterului de propaganda electorala, s-a avut in vedere definitia prevazuta de Art 36, pct 7, din legea 334/2006, republicata, cu modificarile si completarile ulterioare.

"""

    # Removed the inclusion of police_msg as per your request
    # If needed, you can uncomment the following lines
    # if police_msg:
    #     police_msg_escaped = escape_latex(police_msg)
    #     latex_content += f"\n{police_msg_escaped}\n\n"

    # Insert Table of Contents
    latex_content += r"""
\newpage
\tableofcontents
\newpage
"""

    latex_content += r"""
\section{Împotriva numiților}
"""

    # Sort entities for consistent ordering
    sorted_entities = sorted(complaints_by_entity.items(), key=lambda x: x[0])

    for entity_count, (entity, violations) in enumerate(sorted_entities, start=1):
        entity_escaped = escape_latex(entity)

        # Add a subsection for each entity (without manual numbering)
        latex_content += f"""
\subsection{{{entity_escaped}}}
"""

        latex_content += "Următoarele fapte contravenționale sunt sesizate împotriva acestei entități:\n\n"

        # Enumerate violations with numerical labels
        latex_content += "\\begin{enumerate}[leftmargin=*, label=\\arabic*.)]\n"
        for violation in violations:
            violation_escaped = escape_latex(violation)
            latex_content += f"    \\item {violation_escaped}\n"
        latex_content += "\\end{enumerate}\n"

        latex_content += "\n\\vspace{0.5cm}\n"

    latex_content += r"""
\section{Solicitări}

Față de cele de mai sus, solicit:

\begin{enumerate}[leftmargin=*, label=\arabic*.]
    \item Constatarea contravențiilor săvârșite;
    \item Identificarea persoanelor vinovate;
    \item Aplicarea sancțiunilor prevăzute de lege.
\end{enumerate}

\section{Anexe}

Anexez prezentei plângeri următoarele dovezi:

\begin{enumerate}[leftmargin=*, label=\arabic*.]
    \item Capturi de ecran ale postărilor care fac obiectul sesizării;
    \item Dovada calității de observator electoral.
\end{enumerate}

\vspace{1cm}
\noindent Data: \today

\vspace{1.5cm}
\noindent Observator electoral,\\[0.3cm]
Deleanu Ștefan-Lucian

\vspace{1cm}
\noindent Semnătura: [SEMNAT ELECTRONIC]

\end{document}
"""

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(latex_content)

def create_police_complaint(input_dir: str, output_dir: str):
    input_dir = os.path.abspath(input_dir)
    output_dir = os.path.abspath(output_dir)

    if not os.path.exists(input_dir):
        print(f"Error: Input directory '{input_dir}' does not exist!")
        return

    police_msg = None  # We'll no longer use police_msg in the LaTeX document
    complaints_by_entity = defaultdict(list)

    xml_files = [f for f in os.listdir(input_dir) if f.endswith('.xml')]

    for filename in xml_files:
        file_path = os.path.join(input_dir, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            msg = extract_police_message(content)
            if msg:
                if police_msg is None:
                    # Extract police_msg only once
                    police_msg = msg
                entity, violation = parse_complaint(msg)
                if violation:
                    complaints_by_entity[entity].append(violation)

        except Exception as e:
            print(f"Error processing {filename}: {str(e)}")

    if complaints_by_entity:
        try:
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, 'plangere.tex')
            create_latex_document(police_msg, complaints_by_entity, output_file)
            print(f"Complaint document generated: {output_file}")
        except Exception as e:
            print(f"Error creating LaTeX document: {str(e)}")
    else:
        print("No valid violations found in any XML files.")

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)

    input_dir = os.path.join(base_dir, 'ai', 'analysis')
    output_dir = os.path.join(base_dir, 'plangeri')

    create_police_complaint(input_dir, output_dir)
