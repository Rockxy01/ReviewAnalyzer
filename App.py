from flask import Flask, request, jsonify, render_template
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from textblob import TextBlob
import time
import pandas as pd
import requests
from PIL import Image
from io import BytesIO
from collections import Counter
import random
from urllib.parse import urlparse

app = Flask(__name__)

# Function to set up the WebDriver using DevTools
def setup_driver():
    options = Options()
    options.add_argument("--headless")  # run in headless mode (no UI)
    options.add_argument(f"user-agent={get_random_user_agent()}")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

# Function to get a random user agent
def get_random_user_agent():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    ]
    return random.choice(user_agents)

# Function to extract product rating, reviews, and image from multiple review pages
def extract_amazon_reviews(url):
    driver = setup_driver()
    driver.get(url)
    timeout = 10  # seconds

    # Extract product rating
    try:
        rating = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'span.a-icon-alt'))
        ).text.strip()
    except Exception as e:
        rating = f"Error finding rating: {e}"
    
    # Extract total reviews
    try:
        total_reviews_element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, "//span[contains(text(), 'global ratings') or contains(text(), 'customer reviews')]"))
        )
        total_reviews = total_reviews_element.text.strip()
    except Exception as e:
        total_reviews = f"Error finding reviews: {e}"

    # Extract product image
    image_url = None
    try:
        image_element = driver.find_element(By.ID, 'landingImage')
        image_url = image_element.get_attribute('src')
    except Exception as e:
        image_url = f"Error fetching image: {e}"

    reviews = []

    # Simulate scrolling to load more reviews
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

        # Parse page with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        review_elements = soup.find_all('div', {'data-hook': 'review'})

        for review in review_elements:
            review_text = review.find('span', {'data-hook': 'review-body'})
            review_rating = review.find('span', {'class': 'a-icon-alt'})
            if review_text and review_rating:
                reviews.append({
                    'text': review_text.text.strip(),
                    'rating': review_rating.text.strip()
                })

    driver.quit()
    return reviews, image_url

# Function to summarize reviews in a more natural paragraph
def summarize_reviews(reviews, url):
    if not reviews:
        return "No reviews found for analysis."

    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    path_parts = parsed_url.path.split('/')

    # Find ASIN in path parts (assuming it's the last part)
    asin = path_parts[-1] if path_parts else ""

    product_title = ""

    try:
        driver = setup_driver()
        driver.get(url)
        time.sleep(10)
        product_title = driver.find_element(By.ID, "productTitle").text.strip()
        driver.quit()
    except Exception as e:
        product_title = "Product"

    total_reviews = len(reviews)
    avg_rating = sum([float(review['rating'].split(' out of ')[0]) for review in reviews]) / total_reviews

    # Get detailed reviews (longer than 200 characters)
    detailed_reviews = [r for r in reviews if len(r['text']) > 200]
    positive_reviews = [r for r in detailed_reviews if TextBlob(r['text']).sentiment.polarity > 0]
    negative_reviews = [r for r in detailed_reviews if TextBlob(r['text']).sentiment.polarity < 0]
    neutral_reviews = [r for r in detailed_reviews if TextBlob(r['text']).sentiment.polarity == 0]

    # Calculate percentages
    positive_percent = (len([r for r in reviews if TextBlob(r['text']).sentiment.polarity > 0]) / total_reviews) * 100
    negative_percent = (len([r for r in reviews if TextBlob(r['text']).sentiment.polarity < 0]) / total_reviews) * 100

    # Analyze common themes in detailed reviews
    def extract_themes(review_list):
        themes = {}
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
                    # Find complete sentences containing the keyword
                    sentences = text.split('.')
                    relevant_sentences = [s.strip() for s in sentences if any(keyword in s for keyword in keywords) and s.strip()]
                    if relevant_sentences:
                        if aspect not in themes:
                            themes[aspect] = []
                        themes[aspect].append(relevant_sentences[0])  # Store the first relevant complete sentence
        return themes

    positive_themes = extract_themes(positive_reviews)
    negative_themes = extract_themes(negative_reviews)

    # Generate the comprehensive summary
    sentiment_desc = "mixed reviews"
    if positive_percent >= 80:
        sentiment_desc = "overwhelmingly positive reviews"
    elif positive_percent >= 70:
        sentiment_desc = "largely positive reviews"
    elif positive_percent >= 60:
        sentiment_desc = "generally positive reviews"
    elif negative_percent >= 60:
        sentiment_desc = "generally negative reviews"

    # Create the main summary paragraph
    summary = f"Based on a detailed analysis of many customer reviews, the {product_title} has received {sentiment_desc} with an average rating of {avg_rating:.1f} out of 5 stars. "

    # Add positive aspects with specific examples
    if positive_themes:
        summary += "The standout features praised by customers include "
        positive_points = []
        for aspect, comments in positive_themes.items():
            if comments:
                example = max(comments, key=len)  # Get the most detailed comment
                positive_points.append(f"the {aspect} ({example})")

        if positive_points:
            summary += ", ".join(positive_points[:-1])
            if len(positive_points) > 1:
                summary += f", and {positive_points[-1]}"
            else:
                summary += positive_points[0]
            summary += ". "

    # Add balanced perspective from neutral reviews
    if neutral_reviews:
        balanced_opinion = max(neutral_reviews, key=lambda x: len(x['text']))
        summary += f"A balanced perspective from users notes that {balanced_opinion['text'][:150]}... "

    if negative_themes:
        summary += "However, some users have expressed concerns about "
        negative_points = []
        for aspect, comments in negative_themes.items():
            if comments:
                example = max(comments, key=len)  # Get the most detailed comment
                negative_points.append(f"the {aspect} ({example})")

        if negative_points:
            summary += ", ".join(negative_points[:-1])
            if len(negative_points) > 1:
                summary += f", and {negative_points[-1]}"
            else:
                summary += negative_points[0]
            summary += ". "

    # Add final recommendation
    if avg_rating >= 4.0 and positive_percent >= 70:
        summary += "Given the substantial positive feedback and high average rating, this product comes highly recommended by the majority of users, particularly for those valuing "
        summary += " and ".join(list(positive_themes.keys())[:2]) + "."
    elif avg_rating >= 3.5 and positive_percent >= 60:
        summary += "While most users are satisfied with their purchase, potential buyers should weigh the praised aspects against the reported limitations to ensure it meets their specific needs."
    else:
        summary += "Given the mixed feedback, potential buyers should carefully consider these varied experiences and whether the reported issues might affect their intended use of the product."

    return summary

def analyze_sentiment(reviews):
    sentiment_scores = []
    for review in reviews:
        analysis = TextBlob(review['text'])
        sentiment_scores.append(analysis.sentiment.polarity)
    
    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
    return avg_sentiment

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_reviews():
    product_url = request.form.get('product_url')
    
    try:
        # Extract reviews
        reviews, image_url = extract_amazon_reviews(product_url)
        
        if not reviews:
            return jsonify({
                'error': 'No reviews found',
                'success': False
            })
        
        # Analyze sentiment
        sentiment = analyze_sentiment(reviews)
        
        # Summarize reviews
        summary = summarize_reviews(reviews, product_url)
        
        # Create review summary DataFrame
        review_summary = pd.DataFrame({
            'Review': [review['text'] for review in reviews],
            'Rating': [review['rating'] for review in reviews],
            'Sentiment': [TextBlob(review['text']).sentiment.polarity for review in reviews]
        }).to_dict(orient='records')
        
        
        return jsonify({
            'success': True,
            'reviews': review_summary,
            'sentiment': sentiment,
            'summary': summary,
            'image_url': image_url
        })
    
    except Exception as e:
        return jsonify({
            'error': str(e),
            'success': False
        })

if __name__ == '__main__':
    app.run(debug=True)
