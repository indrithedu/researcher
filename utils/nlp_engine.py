import nltk
from typing import List, Dict
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from rake_nltk import Rake
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lex_rank import LexRankSummarizer
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NLPEngine:
    """
    A deterministic NLP engine for JewelScope Research.
    Provides sentiment analysis, keyword extraction, and summarization without external APIs.
    """
    def __init__(self):
        self._ensure_nltk_resources()
        self.analyzer = SentimentIntensityAnalyzer()
        # Rake instance will be created per call to avoid state issues if needed, 
        # but one instance is generally fine for simple extraction.
        self.summarizer = LexRankSummarizer()

    def _ensure_nltk_resources(self):
        """Ensures necessary NLTK resources are downloaded."""
        resources = [
            'stopwords', 'punkt', 'punkt_tab', 
            'maxent_ne_chunker', 'maxent_ne_chunker_tab', 'words', 
            'averaged_perceptron_tagger', 'averaged_perceptron_tagger_eng'
        ]
        for resource in resources:
            try:
                # Check for corpora or tokenizers
                if resource == 'stopwords':
                    nltk.data.find('corpora/stopwords')
                elif resource == 'punkt':
                    nltk.data.find('tokenizers/punkt')
                elif resource == 'punkt_tab':
                    nltk.data.find('tokenizers/punkt_tab')
                elif resource == 'maxent_ne_chunker':
                    nltk.data.find('chunkers/maxent_ne_chunker')
                elif resource == 'maxent_ne_chunker_tab':
                    nltk.data.find('chunkers/maxent_ne_chunker_tab')
                elif resource == 'words':
                    nltk.data.find('corpora/words')
                elif resource == 'averaged_perceptron_tagger':
                    nltk.data.find('taggers/averaged_perceptron_tagger')
                elif resource == 'averaged_perceptron_tagger_eng':
                    nltk.data.find('taggers/averaged_perceptron_tagger_eng')
                else:
                    nltk.data.find(resource)
            except LookupError:
                logger.info(f"Downloading NLTK resource: {resource}")
                nltk.download(resource, quiet=True)

    def analyze_sentiment(self, text):
        """
        Analyzes sentiment of the text using VADER.
        Returns a dict with 'score' (-1 to 1) and 'label' (Positive, Neutral, Negative).
        """
        if not text or not isinstance(text, str):
            return {"score": 0.0, "label": "Neutral"}
        
        scores = self.analyzer.polarity_scores(text)
        compound_score = scores['compound']
        
        if compound_score >= 0.05:
            label = "Positive"
        elif compound_score <= -0.05:
            label = "Negative"
        else:
            label = "Neutral"
            
        return {"score": compound_score, "label": label}

    def extract_keywords(self, text, top_n=5):
        """
        Extracts the top N key phrases using RAKE.
        """
        if not text or not isinstance(text, str):
            return []
        
        r = Rake()
        r.extract_keywords_from_text(text)
        return r.get_ranked_phrases()[:top_n]

    def extract_entities(self, text):
        """
        Extracts named entities (Organizations, People, Places that might be brands) from text.
        Returns a list of unique names.
        """
        if not text or not isinstance(text, str):
            return []

        try:
            tokens = nltk.word_tokenize(text)
            pos_tags = nltk.pos_tag(tokens)
            chunks = nltk.ne_chunk(pos_tags)
            
            entities = []
            
            # Common non-brand words that NLTK sometimes mislabels as GPE or PERSON
            blacklist = {
                'q1', 'q2', 'q3', 'q4', 'fy', 'fiscal', 'year', 'quarter',
                'january', 'february', 'march', 'april', 'may', 'june', 
                'july', 'august', 'september', 'october', 'november', 'december',
                'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'
            }
            stop_words = set(nltk.corpus.stopwords.words('english'))
            
            i = 0
            chunk_list = list(chunks)
            while i < len(chunk_list):
                chunk = chunk_list[i]
                if hasattr(chunk, 'label') and chunk.label() in ['ORGANIZATION', 'PERSON', 'GPE']:
                    entity_name = " ".join([c[0] for c in chunk])
                    
                    # Look ahead for common brand suffixes or continuations (e.g., "Tiffany & Co.")
                    j = i + 1
                    while j < len(chunk_list):
                        next_item = chunk_list[j]
                        if not hasattr(next_item, 'label'):
                            word, pos = next_item
                            if word in ['&', 'and', 'Co.', 'Corp.', 'Inc.', 'Ltd.', 'S.A.', 'GmbH']:
                                entity_name += f" {word}"
                                j += 1
                            elif pos in ['NNP', 'NN'] and word[0].isupper(): # Continuation of proper name
                                entity_name += f" {word}"
                                j += 1
                            else:
                                break
                        else:
                            # If next chunk is also an entity, could be part of same brand
                            break
                    
                    # Basic filtering
                    lower_name = entity_name.lower()
                    if lower_name in blacklist or lower_name in stop_words:
                        i = j
                        continue
                    
                    # If it's a single word and in blacklist, skip
                    if " " not in entity_name and lower_name in blacklist:
                        i = j
                        continue
                        
                    if len(entity_name) >= 2:
                        entities.append(entity_name)
                    
                    i = j
                else:
                    i += 1
            
            return sorted(list(set(entities)))
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return []

    def summarize(self, text, sentences_count=1):
        """
        Provides an extractive summary using LexRank.
        Reduces text to its most important sentence(s).
        """
        if not text or not isinstance(text, str):
            return ""
        
        if len(text.split()) < 20: # Too short to summarize
            return text

        try:
            parser = PlaintextParser.from_string(text, Tokenizer("english"))
            summary = self.summarizer(parser.document, sentences_count)
            return " ".join([str(sentence) for sentence in summary])
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return text[:200] + "..." if len(text) > 200 else text

    def cluster_articles(self, articles: List[Dict]) -> Dict[int, List[Dict]]:
        """
        Clusters articles using K-Means based on their titles.
        Returns a mapping of cluster_id to list of articles.
        """
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.cluster import KMeans
        import numpy as np

        if not articles:
            return {}

        # If only a few articles, put them in cluster 0
        if len(articles) <= 2:
            return {0: articles}

        titles = [a.get("title", "") for a in articles]
        
        # Heuristic for number of clusters: 1/3 of total, capped at 10
        n_clusters = max(1, len(articles) // 3)
        n_clusters = min(n_clusters, 10) 

        try:
            vectorizer = TfidfVectorizer(stop_words='english')
            X = vectorizer.fit_transform(titles)
            
            # Use KMeans to cluster
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init='auto')
            kmeans.fit(X)
            
            clusters = {}
            for i, cluster_id in enumerate(kmeans.labels_):
                cluster_id = int(cluster_id)
                if cluster_id not in clusters:
                    clusters[cluster_id] = []
                clusters[cluster_id].append(articles[i])
                
            return clusters
        except Exception as e:
            logger.error(f"Clustering failed: {e}")
            return {0: articles}

if __name__ == "__main__":
    # Quick manual test
    engine = NLPEngine()
    sample_text = (
        "JewelScope Research is a revolutionary tool for jewelry professionals. "
        "It provides deep insights into market trends and helps identify high-value opportunities. "
        "The platform is extremely easy to use and has been receiving glowing reviews from the community. "
        "However, some users have noted that the initial setup can be a bit slow."
    )
    
    print("--- Sentiment ---")
    print(engine.analyze_sentiment(sample_text))
    
    print("\n--- Keywords ---")
    print(engine.extract_keywords(sample_text))
    
    print("\n--- Summary ---")
    print(engine.summarize(sample_text))
