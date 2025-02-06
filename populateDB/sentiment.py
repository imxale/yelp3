import json
import boto3
import os
import re
from decimal import Decimal
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Configuration AWS
AWS_REGION = "eu-west-1"
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
TABLE_NAME = "reviews-dev"
table = dynamodb.Table(TABLE_NAME)

# Initialisation de l'analyseur de sentiment
analyzer = SentimentIntensityAnalyzer()

def clean_text(text):
    """Nettoie le texte en supprimant la ponctuation et en mettant en minuscule."""
    text = re.sub(r'[^\w\s]', '', text)  # Supprimer la ponctuation
    return text.lower().split()  # Découper en mots

def analyze_sentiment_vader(text):
    """Analyse le sentiment et extrait les mots les plus impactants."""
    words = clean_text(text)
    word_scores = {word: analyzer.polarity_scores(word)['compound'] for word in words}

    # Trier par impact (positif/négatif)
    sorted_words = sorted(word_scores.items(), key=lambda x: abs(x[1]), reverse=True)

    # Prendre les 3-4 mots les plus marquants
    top_words = sorted_words[:4]

    # Déterminer le sentiment général
    compound_score = analyzer.polarity_scores(text)['compound']
    sentiment = "neutre"
    if compound_score >= 0.05:
        sentiment = "positif"
    elif compound_score <= -0.05:
        sentiment = "négatif"

    # Convertir en Decimal pour DynamoDB
    sentiment_keywords = {word: Decimal(str(score)) for word, score in top_words}

    return sentiment, sentiment_keywords

def convert_decimal(obj):
    """Convertit Decimal en float pour JSON (affichage uniquement)."""
    if isinstance(obj, list):
        return [convert_decimal(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj

def handler(event, context):
    """Récupère les avis, analyse le sentiment et met à jour DynamoDB."""
    try:
        print(f"Connexion à DynamoDB - Région: {AWS_REGION}, Table: {TABLE_NAME}")

        # Récupérer les avis
        response = table.scan()
        reviews = response.get('Items', [])

        # Analyser et mettre à jour DynamoDB
        for review in reviews:
            review_text = review.get("text", "")
            if not review_text:  # Si l'avis est vide, on l'ignore
                continue
            sentiment, sentiment_keywords = analyze_sentiment_vader(review_text)

            # Mise à jour de la table avec les résultats
            table.update_item(
                Key={"id": review["id"]},
                UpdateExpression="SET sentiment = :s, sentiment_keywords = :kw",
                ExpressionAttributeValues={
                    ":s": sentiment,
                    ":kw": sentiment_keywords
                }
            )

            # Ajouter au retour JSON
            review["sentiment"] = sentiment
            review["sentiment_keywords"] = sentiment_keywords

        return {
            "statusCode": 200,
            "body": json.dumps(convert_decimal(reviews), indent=2, ensure_ascii=False)
        }

    except Exception as e:
        print(f"❌ Erreur: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

if __name__ == "__main__":
    print(handler({}, {}))
