import os
import re
import json
from collections import defaultdict
from typing import Optional, Dict, Tuple
import unicodedata


def extract_complaint_info(json_content: Dict) -> Optional[Tuple[str, str]]:
    """Extract entity and violation from the JSON response"""
    try:
        # Navigate through the JSON structure
        output = json_content.get('candidates', [])[0].get('content', {}).get('parts', [])[0].get('text', '')

        # Extract information using regex
        message_pattern = r"<message-for-police>(.*?)<\/message-for-police>"
        entity_pattern = r"<responsible-party-or-group>(.*?)<\/responsible-party-or-group>"

        # Both must be multiline (dot matches newline)
        message_match = re.search(message_pattern, output, re.DOTALL)
        entity_match = re.search(entity_pattern, output, re.DOTALL)

        if message_match and entity_match:

            message = message_match.group(1).strip()
            entity = entity_match.group(1).strip()

            return entity, message

        return None
    except Exception as e:
        print(f"Error extracting complaint info: {str(e)}")
        return None


def parse_complaint(message: str) -> Tuple[str, str]:
    """Parse the complaint message to extract violation details"""
    if not message:
        return "", ""

    # Normalize and remove diacritics
    message = unicodedata.normalize('NFKD', message).encode('ASCII', 'ignore').decode('ASCII')
    parts = message.split(', pentru incalcarea articolului 98 t) din LEGEA nr. 208 din 20 iulie 2015, prin', 1)
    if len(parts) == 2:

        # For the second part, replace "23.11.2024" with "30.11.2024"
        parts[1] = parts[1].replace("23.11.2024", "30.11.2024")

        return parts[0].strip(), parts[1].strip()
    return message, ""


def convert_fb_ids_to_links(text: str) -> str:
    """Convert large numbers that look like Facebook IDs to embedded links."""
    pattern = r'(?<!\d)(\d{14,16})(?!\d)'

    def replace_number(match):
        number = match.group(1)
        url = f'https://www.facebook.com/ads/library/?id={number}'
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

    text = convert_fb_ids_to_links(text)

    parts = []
    url_pattern = r'(\\url\{[^}]+\}|\\href\{[^}]+\}\{[^}]+\})'
    last_end = 0

    for match in re.finditer(url_pattern, text):
        start, end = match.span()
        before_url = ''.join(chars.get(c, c) for c in text[last_end:start])
        parts.extend([before_url, text[start:end]])
        last_end = end

    if last_end < len(text):
        parts.append(''.join(chars.get(c, c) for c in text[last_end:]))

    return ''.join(parts)


def create_latex_document(complaints_by_entity: Dict[str, list], output_file: str):
    """Create the LaTeX document with the complaints"""
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
\usepackage{lastpage}

\geometry{
    a4paper,
    margin=2.5cm,
    includehead
}

\pagestyle{fancy}
\fancyhf{}
\lhead{Plângere Contravențională}
\rhead{pagina \thepage/\pageref{LastPage}}
\renewcommand{\headrulewidth}{0.4pt}

\renewcommand{\contentsname}{Cuprins}
\setcounter{tocdepth}{2}
\renewcommand{\cftsecfont}{\normalsize\bfseries}
\renewcommand{\cftsubsecfont}{\normalsize}
\renewcommand{\cftsecpagefont}{\normalsize}
\renewcommand{\cftsubsecpagefont}{\normalsize}
\setlength{\cftbeforesecskip}{5pt}
\setlength{\cftbeforesubsecskip}{2pt}

\titleformat{\section}
  {\normalfont\Large\bfseries}{\thesection.}{0.5em}{}
\titleformat{\subsection}
  {\normalfont\large\bfseries}{\thesubsection.}{0.5em}{}

\begin{document}

\begin{flushleft}
    \normalsize
    Către: IPJ Cluj\\
    cabinet@cj.politiaromana.ro\\
\end{flushleft}

\begin{flushleft}
    \normalsize
    Către: Inspectoratul General al Jandarmeriei Romane\\
    jandarmerie@mai.gov.ro\\
\end{flushleft}

\begin{flushleft}
    \normalsize
    Către: BIROUL ELECTORAL CENTRAL\\
    secretariat@bec.ro\\
\end{flushleft}

\begin{flushleft}
    \normalsize
    Către: Biroul electoral județean nr. 13 CLUJ\\
    bej.cluj@bec.ro\\
\end{flushleft}

\vspace{1cm}

Subsemnatul Deleanu Ștefan-Lucian, identificat prin act de identitate electronic nr. CJ10026, domiciliat în Jud. Cluj, Cluj-Napoca, Str. Aurel Vlaicu, nr. 2, bloc 5A, Sc. I, etaj 7, ap. 28, în virtutea calității de observator electoral acreditat de Funky Citizens, asociație legal acreditată de Autoritatea Electorală Permanentă prin ACREDITAREA nr. 30688/13.10.2024, în conformitate cu și în temeiul dispozițiilor imperative ale Legii 208/2015 privind alegerea Senatului și a Camerei Deputaților, cu modificările și completările ulterioare, formulez și înaintez prezenta:

\vspace{0.5cm}
\begin{center}
\textbf{\Large PLÂNGERE CONTRAVENȚIONALĂ}
\end{center}
\vspace{0.5cm}

prin intermediul căreia sesizez și aduc la cunoștință săvârșirea contravențiilor prevăzute și definite de art. 98 lit. t), art. 99 alin (1), alin. (2) lit. a) din cuprinsul Legii 208/2015 privind alegerea Senatului și a Camerei Deputaților.

În procesul de evaluare a caracterului de propagandă electorală al aspectelor semnalate, am avut în considerare definiția statuată de art. 36 pct. 7 din Legea 334/2006, republicată, cu modificările și completările ulterioare.

Dat fiind natura generală și amploarea conduitei contravenționale, ce ia forma a peste 100 de fapte contravenționale distincte, cu un caracter efemer, se impune cu necesitate constatarea cu celeritate a acestora, motiv pentru care am procedat la sesizarea, în mod concomitent, a tuturor organelor abilitate în acest sens, respectiv: ofițerii, agenții și subofițerii din cadrul Poliției Române, Poliției de Frontieră Române și Jandarmeriei Române, precum și polițiștii locali.

Mai mult, fiind vorba de aspecte ce influenteaza scrutinul parlamentar, am procedat la notificarea Biroului Electoral Central și a Biroului Electoral Județean nr. 13 CLUJ, în vederea luării măsurilor legale ce se impun.

Intrucat caracterul analizei este unul cu un caracter subiectiv, este notabil ca anumite aspecte sesizate pot fi interpretate diferit de către organele abilitate, motiv pentru care se impune o analiză detaliată a postărilor cu potențial caracter electoral propagandistic, în conformitate cu prevederile legale în vigoare.

Spre exemplu, multe partide au incercat substituirea campaniei intr-o campanie pentru "alegeri locale", insa scopul fiind vadit pentru atragerea unui numar cat mai mare de locuri la alegerile parlamentare. Alte partide folosesc PBN-uri (private blog networks) pentru a crea ideea ca postarile sunt neutre, jurnalistice, insa in realitate sunt postari cu caracter electoral.

Desi Facebook obliga furnizarea de informatii reale despre titularul reclamei si cel care plateste pentru ea, aceste informatii sunt deseori false, iar Facebook nu verifica aceste informatii. Este notabil faptul ca declararea in fals a acestor informatii este de natura sa se incadreze la Art. 325 Cod Penal - Falsul informatic, astfel incat daca organul de constatare a contraventiilor are si competenta in constatarea faptelor penale, ii rugam sa se sesizeze si cu privire la aceste aspecte.

\noindent\rule{\textwidth}{1pt}

Organul competent cu constatarea contravențiilor poate accesa link-urile în formă originală pentru o analiză detaliată a postărilor cu potențial caracter electoral propagandistic, prin \textbf{dublu click pe ID-urile postărilor respective}.

\textbf{Metodologia aplicată în cadrul studiului ce a fundamentat prezenta plângere, cu scopul asigurării unui caracter echidistant și obiectiv în analiza naturii postărilor, poate fi consultată accesând următorul link:}

\href{https://github.com/Stefatorus/observator-electoral-transparenta}{https://github.com/Stefatorus/observator-electoral-transparenta}

Analizele au fost efectuate in perioada 30.11.2024, incepand cu ora 18:00, pana in data de 30.11.2024, la ora 19:30, folosind analiza automata cu AI, si a vizat EXCLUSIV platforma "META" (Facebook, Instagram, WhatsApp).

\tableofcontents
\newpage

\section{Împotriva numiților}
"""

    sorted_entities = sorted(complaints_by_entity.items(), key=lambda x: x[0])

    for entity_count, (entity, violations) in enumerate(sorted_entities, start=1):
        entity_escaped = escape_latex(entity)
        latex_content += f"""
\subsection{{{entity_escaped}}}
"""
        latex_content += "Următoarele fapte contravenționale sunt sesizate împotriva acestei entități:\n\n"
        latex_content += "\\begin{enumerate}[leftmargin=*, label=\\arabic*.)]\n"
        for violation in violations:
            violation_escaped = escape_latex(violation)
            latex_content += f"    \\item {violation_escaped}\n"
        latex_content += "\\end{enumerate}\n"
        latex_content += "\n\\vspace{0.5cm}\n"

    # Add the rest of the LaTeX document (Solicitări, Anexe, etc.)
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
    """Main function to create police complaint from JSON files"""
    input_dir = os.path.abspath(input_dir)
    output_dir = os.path.abspath(output_dir)

    if not os.path.exists(input_dir):
        print(f"Error: Input directory '{input_dir}' does not exist!")
        return

    complaints_by_entity = defaultdict(list)

    # Process all JSON files in the input directory
    json_files = [f for f in os.listdir(input_dir) if f.endswith('.json')]

    print(f"Found {len(json_files)} JSON files in the input directory.")

    for filename in json_files:
        file_path = os.path.join(input_dir, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = json.load(f)

            complaint_info = extract_complaint_info(content)
            if complaint_info:

                entity, message = complaint_info

                if entity and message:
                    _, violation = parse_complaint(message)
                    if violation:
                        complaints_by_entity[entity].append(violation)

        except Exception as e:
            print(f"Error processing {filename}: {str(e)}")

    if complaints_by_entity:
        try:
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, 'plangere.tex')
            create_latex_document(complaints_by_entity, output_file)
            print(f"Complaint document generated: {output_file}")
        except Exception as e:
            print(f"Error creating LaTeX document: {str(e)}")
    else:
        print("No valid violations found in any JSON files.")


if __name__ == "__main__":
    input_dir = os.path.join('ai', 'analysis')
    output_dir = os.path.join('plangeri')

    create_police_complaint(input_dir, output_dir)
