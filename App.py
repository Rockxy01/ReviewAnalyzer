import requests
from bs4 import BeautifulSoup
import pandas as pd
from fake_useragent import UserAgent
import time
import random
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from textblob import TextBlob
from collections import defaultdict
import urllib.parse
from flask import Flask, request, jsonify

class AmazonReviewAnalyzer:
    def __init__(self):
        self.ua = UserAgent()
        self.setup_selenium()

    def setup_selenium(self):
        """Initialize Selenium WebDriver with appropriate options"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument(f'user-agent={self.ua.random}')

        self.driver = webdriver.Chrome(options=chrome_options)

    def clean_url(self, url):
        """Clean the Amazon URL to get base URL and ASIN"""
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        if not asin_match:
            asin_match = re.search(r'/product/([A-Z0-9]{10})', url)

        if not asin_match:
            raise ValueError("Could not find valid ASIN in URL")

        asin = asin_match.group(1)
        return domain, asin

    def get_review_url(self, domain, asin):
        """Generate review page URL based on domain and ASIN"""
        return f'https://{domain}/product-reviews/{asin}/'

    def analyze_sentiment(self, text):
        """Analyze sentiment of text using TextBlob"""
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity

        if polarity > 0.1:
            return 'Positive'
        elif polarity < -0.1:
            return 'Negative'
        else:
            return 'Neutral'

    def fetch_reviews_selenium(self, url, num_pages=500):
        """Fetch reviews using Selenium with international domain support"""
        reviews = []
        try:
            domain, asin = self.clean_url(url)
            review_url = self.get_review_url(domain, asin)

            for page in range(1, num_pages + 1):
                try:
                    page_url = f"{review_url}?pageNumber={page}"
                    self.driver.get(page_url)

                    # Wait for reviews to load
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "review"))
                    )

                    review_elements = self.driver.find_elements(By.CSS_SELECTOR, 'div[data-hook="review"]')

                    for review in review_elements:
                        try:
                            review_text = review.find_element(By.CSS_SELECTOR, 'span[data-hook="review-body"]').text.strip()
                            rating_element = review.find_element(By.CSS_SELECTOR, 'i[data-hook="review-star-rating"], i[data-hook="cmps-review-star-rating"]')
                            rating_text = rating_element.get_attribute('textContent')  
                            rating = float(rating_text.split(' ')[0])  

                            review_data = {
                                'text': review_text,
                                'rating': rating,
                                'sentiment': self.analyze_sentiment(review_text)
                            }
                            reviews.append(review_data)
                        except Exception as e:
                            print(f"Error parsing review: {e}")
                            continue

                    print(f"Fetched page {page} - Found {len(review_elements)} reviews")

                except Exception as e:
                    print(f"Error fetching page {page}: {e}")
                    break

        except Exception as e:
            print(f"Error: {e}")

        return reviews

    def generate_summary(self, reviews, url):
        """Generate a detailed narrative summary based on in-depth review analysis"""
        if not reviews:
            return "No reviews found for analysis."

        try:
            domain, asin = self.clean_url(url)
            self.driver.get(url)
            product_title = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "productTitle"))
            ).text.strip()
        except:
            product_title = "Product"

        df = pd.DataFrame(reviews)

        total_reviews = len(df)
        avg_rating = df['rating'].mean()

        detailed_reviews = [r for r in reviews if len(r['text']) > 200]
        positive_reviews = [r for r in detailed_reviews if r['sentiment'] == 'Positive']
        negative_reviews = [r for r in detailed_reviews if r['sentiment'] == 'Negative']
        neutral_reviews = [r for r in detailed_reviews if r['sentiment'] == 'Neutral']

        positive_percent = (len([r for r in reviews if r['sentiment'] == 'Positive']) / total_reviews) * 100
        negative_percent = (len([r for r in reviews if r['sentiment'] == 'Negative']) / total_reviews) * 100

        def extract_themes(review_list):
            themes = defaultdict(list)
            common_aspects = {
                'quality': ['quality', 'build', 'material', 'durability', 'construction'],
                'value': ['price', 'value', 'worth', 'cost', 'expensive', 'cheap'],
                'performance': ['performance', 'speed', 'fast', 'slow', 'efficient'],
                'features': ['feature', 'functionality', 'options', 'capabilities'],
                'design': ['design', 'look', 'aesthetic', 'style', 'appearance'],
                'usability': ['easy', 'simple', 'intuitive', 'user-friendly', 'difficult'],
                'reliability': ['reliable', 'consistent', 'stable', 'issues', 'problems'],
                'support': ['support', 'customer service', 'warranty', 'help']
            }

            for review in review_list:
                text = review['text'].lower()
                for aspect, keywords in common_aspects.items():
                    if any(keyword in text for keyword in keywords):
                        sentences = text.split('.')
                        relevant_sentences = [s.strip() for s in sentences if any(keyword in s for keyword in keywords) and s.strip()]
                        if relevant_sentences:
                            themes[aspect].append(relevant_sentences[0])  
            return themes

        positive_themes = extract_themes(positive_reviews)
        negative_themes = extract_themes(negative_reviews)

        sentiment_desc = "mixed reviews"
        if positive_percent >= 80:
            sentiment_desc = "overwhelmingly positive reviews"
        elif positive_percent >= 70:
            sentiment_desc = "largely positive reviews"
        elif positive_percent >= 60:
            sentiment_desc = "generally positive reviews"
        elif negative_percent >= 60:
            sentiment_desc = "generally negative reviews"

        summary = f"Based on a detailed analysis of {total_reviews} customer reviews, the {product_title} has received {sentiment_desc} with an average rating of {avg_rating:.1f} out of 5 stars. "

        if positive_themes:
            summary += "The standout features praised by customers include "
            positive_points = []
            for aspect, comments in positive_themes.items():
                if comments:
                    example = max(comments, key=len)  
                    positive_points.append(f"the {aspect} ({example})")

            if positive_points:
                summary += ", ".join(positive_points[:-1])
                if len(positive_points) > 1:
                    summary += f", and {positive_points[-1]}"
                else:
                    summary += positive_points[0]
                summary += ". "

        if neutral_reviews:
            balanced_opinion = max(neutral_reviews, key=lambda x: len(x['text']))
            summary += f"A balanced perspective from users notes that {balanced_opinion['text'][:150]}... "

        if negative_themes:
            summary += "However, some users have expressed concerns about "
            negative_points = []
            for aspect, comments in negative_themes.items():
                if comments:
                    example = max(comments, key=len)  
                    negative_points.append(f"the {aspect} ({example})")

            if negative_points:
                summary += ", ".join(negative_points[:-1])
                if len(negative_points) > 1:
                    summary += f", and {negative_points[-1]}"
                else:
                    summary += negative_points[0]
                summary += ". "

        if avg_rating >= 4.0 and positive_percent >= 70:
            summary += "Given the substantial positive feedback and high average rating, this product comes highly recommended by the majority of users, particularly for those valuing "
            summary += " and ".join(list(positive_themes.keys())[:2]) + "."
        elif avg_rating >= 3.5 and positive_percent >= 60:
            summary += "While most users are satisfied with their purchase, potential buyers should weigh the praised aspects against the reported limitations to ensure it meets their specific needs."
        else:
            summary += "Given the mixed feedback, potential buyers may want to explore other options or consider specific use cases before deciding."

        return summary

    def scrape_amazon_reviews(self, url):
        """Scrape reviews and generate summary"""
        reviews = self.fetch_reviews_selenium(url)
        summary = self.generate_summary(reviews, url)
        return summary

# Create Flask app
app = Flask(__name__)
analyzer = AmazonReviewAnalyzer()

@app.route('/analyze', methods=['POST'])
def analyze():
    """Endpoint to analyze reviews"""
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'URL is required.'}), 400

    try:
        summary = analyzer.scrape_amazon_reviews(url)
        return jsonify({'summary': summary}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
