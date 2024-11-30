import os
import re
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Tuple
import json
from datetime import datetime

import unicodedata


class PartyNormalizer:
    @staticmethod
    def normalize_party_name(name: str) -> str:
        """
        Normalize party name by:
        1. Converting to uppercase
        2. Removing diacritics
        3. Removing special characters
        4. Normalizing spaces
        """
        # Convert to uppercase
        name = name.upper()

        # Remove diacritics
        name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')

        # Remove special characters and normalize spaces
        name = re.sub(r'[^\w\s]', '', name)
        name = ' '.join(name.split())

        return name


class ElectoralAnalyzer:
    def __init__(self, input_folder: str, metadata_file: str, output_folder: str = 'graphs'):
        """
        Initialize the analyzer with paths to input XML files and metadata JSON.

        Args:
            input_folder: Directory containing XML files
            metadata_file: Path to the enriched metadata JSON file
            output_folder: Directory for output files
        """
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.violations_data = []
        self.metadata = self._load_metadata(metadata_file)

        # Create output directory if it doesn't exist
        os.makedirs(output_folder, exist_ok=True)

    def _load_metadata(self, metadata_file: str) -> Dict:
        """
        Load and index the metadata file by ad_archive_id for efficient lookups.

        Args:
            metadata_file: Path to the metadata JSON file

        Returns:
            Dict mapping ad_archive_id to metadata
        """
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata_list = json.load(f)

            # Create an indexed dictionary for O(1) lookups
            return {str(item['ad_archive_id']): item for item in metadata_list}
        except Exception as e:
            print(f"Error loading metadata file: {str(e)}")
            return {}

    def extract_ad_id_from_xml(self, content: str) -> str:
        """
        Extract post_id from XML content which maps to ad_archive_id in metadata.
        """
        match = re.search(r'<post_id>(.*?)</post_id>', content, re.DOTALL)
        return match.group(1).strip() if match else None

    def extract_numbers_from_range(self, range_str: str) -> Tuple[int, int]:
        """Extract lower and upper bounds from a range string"""
        numbers = re.findall(r'[\d,]+', str(range_str))
        if len(numbers) >= 2:
            lower = int(numbers[0].replace(',', ''))
            upper = int(numbers[1].replace(',', ''))
            return lower, upper
        return 0, 0

    def calculate_reach_score(self, reach_str: str) -> float:
        """Calculate a normalized reach score"""
        lower, upper = self.extract_numbers_from_range(reach_str)
        return (lower + upper) / 2

    def extract_xml_content(self, text: str) -> Dict:
        """Extract XML-like content using regex with propaganda detection"""
        output_match = re.search(r'<output>(.*?)</output>', text, re.DOTALL)
        if not output_match:
            return None

        output_content = output_match.group(1)
        conclusion_match = re.search(r'<conclusion>(.*?)</conclusion>', output_content, re.DOTALL)
        if not conclusion_match:
            return None

        conclusion_content = conclusion_match.group(1)

        # Extract fields
        fields = {
            'post_id': re.search(r'<post_id>(.*?)</post_id>', conclusion_content),
            'propaganda_decision': re.search(r'<electoral-propaganda-decision>(.*?)</electoral-propaganda-decision>',
                                             conclusion_content),
            'responsible_party': re.search(r'<responsible-party-or-group>(.*?)</responsible-party-or-group>',
                                           conclusion_content)
        }

        if not all(fields.values()):
            return None

        # Track both TRUE and FALSE cases
        propaganda_result = fields['propaganda_decision'].group(1).strip()

        # Extract candidates for TRUE cases
        candidates = []
        if propaganda_result == 'TRUE':
            candidate_pattern = r'<candidate>\s*<name>(.*?)</name>\s*<impact>(.*?)</impact>\s*</candidate>'
            for match in re.finditer(candidate_pattern, conclusion_content):
                candidates.append({
                    'name': match.group(1).strip(),
                    'impact': match.group(2).strip()
                })

        return {
            'post_id': fields['post_id'].group(1).strip(),
            'responsible_party': PartyNormalizer.normalize_party_name(fields['responsible_party'].group(1).strip()),
            'is_propaganda': propaganda_result == 'TRUE',
            'candidates': candidates
        }

    def parse_file(self, file_path: str) -> Dict:
        """Parse a single file and extract information"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            violation_data = self.extract_xml_content(content)
            if not violation_data:
                return None

            # Extract post_id from XML (which corresponds to ad_archive_id)
            post_id = self.extract_ad_id_from_xml(content)
            if not post_id:
                print(f"Warning: No post_id found in {file_path}")
                return violation_data

            # Lookup metadata using post_id as ad_archive_id
            ad_metadata = self.metadata.get(post_id, {})
            if not ad_metadata:
                print(f"Warning: No metadata found for post_id/ad_archive_id {post_id}")
                # Set default values if no metadata found
                violation_data.update({
                    'reach': '0-0',
                    'spend': {'lower_bound': 0, 'upper_bound': 0, 'average': 0},
                    'currency': 'RON',
                    'start_date': None,
                    'end_date': None
                })
            else:
                # Update with metadata from the enriched file
                violation_data.update({
                    'reach': ad_metadata.get('estimated_audience_size', '0-0'),
                    'spend': ad_metadata.get('spend', {
                        'lower_bound': 0,
                        'upper_bound': 0,
                        'average': 0
                    }),
                    'currency': ad_metadata.get('currency', 'RON'),
                    'start_date': ad_metadata.get('ad_delivery_start_time'),
                    'end_date': ad_metadata.get('ad_delivery_stop_time')
                })

            return violation_data

        except Exception as e:
            print(f"Error processing file {file_path}: {str(e)}")
            return None

    def analyze_all_files(self):
        """Process all files in input folder"""
        for filename in os.listdir(self.input_folder):
            if filename.endswith('.xml'):
                file_path = os.path.join(self.input_folder, filename)
                violation_data = self.parse_file(file_path)
                if violation_data:
                    self.violations_data.append(violation_data)

    def calculate_impact_summary(self, impact_df: pd.DataFrame) -> Dict:
        """Calculate comprehensive impact summary including totals"""
        positive_impacts = impact_df[impact_df['impact_type'] == 'POSITIVE']
        negative_impacts = impact_df[impact_df['impact_type'] == 'NEGATIVE']

        summary = {
            'positive_impact': {
                'total_spend': positive_impacts['spend'].apply(
                    lambda x: x['average'] if isinstance(x, dict) else x).sum(),
                'total_reach': positive_impacts['reach'].sum(),
                'total_posts': len(positive_impacts),
                'by_candidate': []
            },
            'negative_impact': {
                'total_spend': negative_impacts['spend'].apply(
                    lambda x: x['average'] if isinstance(x, dict) else x).sum(),
                'total_reach': negative_impacts['reach'].sum(),
                'total_posts': len(negative_impacts),
                'by_candidate': []
            }
        }

        # Process positive impacts
        pos_by_candidate = positive_impacts.groupby('candidate').agg({
            'spend': lambda x: sum(d['average'] if isinstance(d, dict) else d for d in x),
            'reach': 'sum',
            'impact_weight': 'sum',
            'party_responsible': lambda x: list(set(x))
        }).reset_index()

        summary['positive_impact']['by_candidate'] = [
            {
                'candidate': row['candidate'],
                'total_spend': row['spend'],
                'total_reach': row['reach'],
                'impact_score': row['impact_weight'],
                'promoting_parties': row['party_responsible']
            }
            for _, row in pos_by_candidate.nlargest(5, 'impact_weight').iterrows()
        ]

        # Process negative impacts
        neg_by_candidate = negative_impacts.groupby('candidate').agg({
            'spend': 'sum',
            'reach': 'sum',
            'impact_weight': 'sum',
            'party_responsible': lambda x: list(set(x))
        }).reset_index()

        summary['negative_impact']['by_candidate'] = [
            {
                'candidate': row['candidate'],
                'total_spend': row['spend'],
                'total_reach': row['reach'],
                'impact_score': abs(row['impact_weight']),
                'attacking_parties': row['party_responsible']
            }
            for _, row in neg_by_candidate.nlargest(5, 'impact_weight').iterrows()
        ]

        return summary

    def plot_violations_summary(self, violations_df: pd.DataFrame):
        """Create summary visualizations"""
        plt.figure(figsize=(20, 15))

        # Make a copy of the DataFrame to avoid the warning
        df = violations_df.copy()

        # 1. Violations by Party
        plt.subplot(2, 2, 1)
        party_counts = df['party'].value_counts()
        sns.barplot(x=party_counts.index, y=party_counts.values)
        plt.title('Violations by Party', fontsize=14, pad=20)
        plt.xlabel('Party', fontsize=12)
        plt.ylabel('Number of Violations', fontsize=12)
        plt.xticks(rotation=45)

        # 2. Total Reach by Party
        plt.subplot(2, 2, 2)
        reach_by_party = df.groupby('party')['reach'].sum()
        sns.barplot(x=reach_by_party.index, y=reach_by_party.values)
        plt.title('Total Reach by Party', fontsize=14, pad=20)
        plt.xlabel('Party', fontsize=12)
        plt.ylabel('Total Reach', fontsize=12)
        plt.xticks(rotation=45)

        # 3. Average Spend by Party
        plt.subplot(2, 2, 3)
        spend_by_party = df.groupby('party')['spend'].mean()
        sns.barplot(x=spend_by_party.index, y=spend_by_party.values)
        plt.title('Average Spend by Party (RON)', fontsize=14, pad=20)
        plt.xlabel('Party', fontsize=12)
        plt.ylabel('Average Spend', fontsize=12)
        plt.xticks(rotation=45)

        # 4. Violation Severity Score
        plt.subplot(2, 2, 4)
        # Calculate severity score on the copy
        df.loc[:, 'severity_score'] = (df['reach'] * df['spend']) / 1000000
        severity_by_party = df.groupby('party')['severity_score'].mean()
        sns.barplot(x=severity_by_party.index, y=severity_by_party.values)
        plt.title('Violation Severity Score by Party', fontsize=14, pad=20)
        plt.xlabel('Party', fontsize=12)
        plt.ylabel('Severity Score', fontsize=12)
        plt.xticks(rotation=45)

        plt.tight_layout()
        plt.savefig(os.path.join(self.output_folder, 'violations_summary.png'),
                    dpi=300, bbox_inches='tight')
        plt.close()

    def plot_false_positives_analysis(self, violations_df: pd.DataFrame, false_positives_df: pd.DataFrame):
        """Create visualizations for false positives analysis"""
        plt.figure(figsize=(20, 10))

        # 1. False Positive Rate by Party
        plt.subplot(1, 2, 1)
        fp_rates = self.calculate_fp_rates_by_party(violations_df, false_positives_df)
        sns.barplot(x=fp_rates.index, y=fp_rates.values)
        plt.title('False Positive Rate by Party', fontsize=14, pad=20)
        plt.xlabel('Party', fontsize=12)
        plt.ylabel('False Positive Rate (%)', fontsize=12)
        plt.xticks(rotation=45)

        # 2. Precision by Party
        plt.subplot(1, 2, 2)
        precision = self.calculate_precision_by_party(pd.concat([violations_df, false_positives_df]))
        precision_df = pd.DataFrame.from_dict(precision, orient='index', columns=['precision'])
        sns.barplot(x=precision_df.index, y=precision_df['precision'])
        plt.title('Precision by Party', fontsize=14, pad=20)
        plt.xlabel('Party', fontsize=12)
        plt.ylabel('Precision', fontsize=12)
        plt.xticks(rotation=45)

        plt.tight_layout()
        plt.savefig(os.path.join(self.output_folder, 'false_positives_analysis.png'),
                    dpi=300, bbox_inches='tight')
        plt.close()

    def calculate_fp_rates_by_party(self, violations_df: pd.DataFrame,
                                    false_positives_df: pd.DataFrame) -> pd.Series:
        """Calculate false positive rates for each party"""
        total_by_party = pd.concat([violations_df, false_positives_df])['party'].value_counts()
        fp_by_party = false_positives_df['party'].value_counts()

        fp_rates = (fp_by_party / total_by_party * 100).round(2)
        return fp_rates.sort_values(ascending=False)

    def calculate_precision_by_party(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate precision by party"""
        precision = {}
        for party in df['party'].unique():
            party_data = df[df['party'] == party]
            true_positives = sum(party_data['is_propaganda'])
            total = len(party_data)
            precision[party] = (true_positives / total) if total > 0 else 0

        return precision

    def generate_analysis(self):
        """Generate complete analysis"""
        if not self.violations_data:
            print("No data to analyze!")
            return

        # Create DataFrames
        data_entries = []
        impact_entries = []

        for v in self.violations_data:
            entry = {
                'party': v['responsible_party'],
                'reach': float(self.calculate_reach_score(v['reach'])),  # Ensure float
                'spend': float(v['spend']['average'] if isinstance(v['spend'], dict) else v['spend']),  # Ensure float
                'candidates_affected': int(len(v.get('candidates', []))),  # Ensure int
                'start_date': v['start_date'],
                'end_date': v['end_date'],
                'is_propaganda': bool(v['is_propaganda'])  # Ensure bool
            }
            data_entries.append(entry)

            if v['is_propaganda']:
                for c in v['candidates']:
                    impact_entries.append({
                        'candidate': c['name'],
                        'impact_type': c['impact'],
                        'party_responsible': v['responsible_party'],
                        'reach': float(entry['reach']),  # Ensure float
                        'spend': float(entry['spend']),  # Ensure float
                        'impact_weight': float((entry['reach'] * entry['spend']) / 1000000)  # Ensure float
                    })

        full_df = pd.DataFrame(data_entries)
        impact_df = pd.DataFrame(impact_entries)

        # Split into violations and false positives
        violations_df = full_df[full_df['is_propaganda']].copy()  # Make a copy
        false_positives_df = full_df[~full_df['is_propaganda']].copy()  # Make a copy

        # Generate visualizations
        self.plot_violations_summary(violations_df)
        self.plot_false_positives_analysis(violations_df, false_positives_df)

        # Calculate impact summary
        impact_summary = self.calculate_impact_summary(impact_df)

        # Generate complete statistics with explicit type conversion
        stats = {
            'analysis_timestamp': datetime.now().strftime('%Y-%m-%d_%H-%M-%S'),
            'violations_summary': {
                'total_analyzed': int(len(full_df)),
                'total_violations': int(len(violations_df)),
                'total_false_positives': int(len(false_positives_df)),
                'false_positive_rate': float(len(false_positives_df) / len(full_df) if len(full_df) > 0 else 0),
                'violations_by_party': {k: int(v) for k, v in violations_df['party'].value_counts().to_dict().items()},
                'false_positives_by_party': {k: int(v) for k, v in
                                             false_positives_df['party'].value_counts().to_dict().items()},
                'precision_by_party': {k: float(v) for k, v in self.calculate_precision_by_party(full_df).items()},
                'total_reach': float(violations_df['reach'].sum()),
                'total_spend': float(violations_df['spend'].sum()),
                'avg_severity_by_party': {k: float(v) for k, v in
                                          violations_df.groupby('party')['spend'].mean().to_dict().items()}
            },
            'impact_analysis': impact_summary
        }

        # Save statistics to JSON
        with open(os.path.join(self.output_folder, 'analysis_summary.json'), 'w',
                  encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

        return stats


def main():
    analyzer = ElectoralAnalyzer(
        input_folder='ai/analysis',
        metadata_file='final_enriched_meta_ad_data.json'
    )
    analyzer.analyze_all_files()
    stats = analyzer.generate_analysis()

    # Print comprehensive report
    print("\nAnaliza încălcărilor electorale")
    print("=" * 50)

    print(f"\nTotal analizate: {stats['violations_summary']['total_analyzed']}")
    print(f"Încălcări confirmate: {stats['violations_summary']['total_violations']}")
    print(f"False positives: {stats['violations_summary']['total_false_positives']}")
    print(f"Rata false positives: {stats['violations_summary']['false_positive_rate']:.2%}")

    print("\nAnaliză per partid:")
    print("-" * 30)
    for party in sorted(stats['violations_summary']['violations_by_party'].keys()):
        violations = stats['violations_summary']['violations_by_party'].get(party, 0)
        fp = stats['violations_summary']['false_positives_by_party'].get(party, 0)
        precision = stats['violations_summary']['precision_by_party'].get(party, 0)
        print(f"\n{party}:")
        print(f"  Încălcări confirmate: {violations}")
        print(f"  False positives: {fp}")
        print(f"  Precizie: {precision:.2%}")

    print("\nAnaliza de Impact")
    print("=" * 50)

    impact_stats = stats['impact_analysis']

    print("\nImpact Pozitiv")
    print("-" * 30)
    print(f"Total cheltuieli marketing pozitiv: {impact_stats['positive_impact']['total_spend']:,.2f} RON")
    print(f"Total impresii pozitive: {impact_stats['positive_impact']['total_reach']:,}")
    print(f"Număr total postări pozitive: {impact_stats['positive_impact']['total_posts']}")

    print("\nTop 5 Candidați - Impact Pozitiv:")
    for idx, candidate in enumerate(impact_stats['positive_impact']['by_candidate'], 1):
        print(f"\n{idx}. {candidate['candidate']}")
        print(f"   Cheltuieli totale: {candidate['total_spend']:,.2f} RON")
        print(f"   Reach total: {candidate['total_reach']:,}")
        print(f"   Score impact: {candidate['impact_score']:,.2f}")
        print(f"   Promovat de: {', '.join(candidate['promoting_parties'])}")

    print("\nImpact Negativ")
    print("-" * 30)
    print(f"Total cheltuieli atacuri: {impact_stats['negative_impact']['total_spend']:,.2f} RON")
    print(f"Total impresii negative: {impact_stats['negative_impact']['total_reach']:,}")
    print(f"Număr total postări negative: {impact_stats['negative_impact']['total_posts']}")

    print("\nTop 5 Candidați - Impact Negativ:")
    for idx, candidate in enumerate(impact_stats['negative_impact']['by_candidate'], 1):
        print(f"\n{idx}. {candidate['candidate']}")
        print(f"   Cheltuieli totale atacuri: {candidate['total_spend']:,.2f} RON")
        print(f"   Reach total atacuri: {candidate['total_reach']:,}")
        print(f"   Score impact negativ: {candidate['impact_score']:,.2f}")
        print(f"   Atacat de: {', '.join(candidate['attacking_parties'])}")

    print("\nVizualizări generate în directorul 'graphs':")
    print("1. violations_summary.png - Sumar încălcări per partid")
    print("2. false_positives_analysis.png - Analiza false positives")
    print("3. analysis_summary.json - Date complete în format JSON")


if __name__ == "__main__":
    main()
