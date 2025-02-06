import json
import boto3
import os
import io
import matplotlib.pyplot as plt
from wordcloud import WordCloud
import numpy as np
from decimal import Decimal
from urllib.parse import unquote

# Configuration AWS
AWS_REGION = "eu-west-1"
DYNAMODB_TABLE = "reviews-dev"
S3_BUCKET = "bucketrestaurants28ee0-dev"

# Clients AWS
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
s3 = boto3.client('s3', region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE)

def convert_decimal(obj):
    """Convertit les valeurs Decimal en float pour JSON."""
    if isinstance(obj, list):
        return [convert_decimal(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj

def generate_wordcloud(keywords):
    """Génère un nuage de mots et retourne une image en mémoire."""
    word_freq = {word: float(score) for word, score in keywords.items()}

    wordcloud = WordCloud(width=800, height=400, background_color='white').generate_from_frequencies(word_freq)

    img_data = io.BytesIO()
    plt.figure(figsize=(10, 5))
    plt.imshow(wordcloud, interpolation="bilinear")
    plt.axis("off")
    plt.savefig(img_data, format="png")
    plt.close()

    img_data.seek(0)
    return img_data

def generate_histogram(sentiments):
    """Génère un histogramme des sentiments et retourne une image en mémoire."""
    sentiment_counts = {s: sentiments.count(s) for s in set(sentiments)}

    plt.figure(figsize=(8, 4))
    plt.bar(sentiment_counts.keys(), sentiment_counts.values(), color=['red', 'gray', 'green'])
    plt.xlabel("Type d'avis")
    plt.ylabel("Nombre d'avis")
    plt.title("Répartition des sentiments")

    img_data = io.BytesIO()
    plt.savefig(img_data, format="png")
    plt.close()

    img_data.seek(0)
    return img_data

def upload_to_s3(file_data, file_name):
    """Upload une image sur S3 et retourne une URL pré-signée."""
    s3.put_object(Bucket=S3_BUCKET, Key=file_name, Body=file_data, ContentType="image/png")
    url = s3.generate_presigned_url('get_object', Params={'Bucket': S3_BUCKET, 'Key': file_name}, ExpiresIn=3600)
    return url

def handler(event, context):
    """Lambda principale : récupère les avis et génère les graphiques."""
    try:
        # Vérification des paramètres
        if "pathParameters" not in event or "restaurantId" not in event["pathParameters"]:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "restaurantId is required in the URL"})
            }

        restaurant_id = unquote(event["pathParameters"]["restaurantId"])
        print(f"🔍 Recherche des avis pour le restaurant : {restaurant_id}")

        # Récupération des avis du restaurant
        response = table.scan(
            FilterExpression="restaurant_id = :r",
            ExpressionAttributeValues={":r": restaurant_id}
        )
        reviews = response.get('Items', [])

        if not reviews:
            return {"statusCode": 404, "body": json.dumps({"error": "Restaurant non trouvé"})}

        # Extraction des mots-clés et des sentiments
        all_keywords = {}
        all_sentiments = []
        for review in reviews:
            sentiment_keywords = review.get("sentiment_keywords", {})

            print(f"🔍 sentiment_keywords: {sentiment_keywords}")  # Debug dans CloudWatch

            if not isinstance(sentiment_keywords, dict):  # 🔴 Vérifie que c'est bien un dict
                sentiment_keywords = {}

            for word, weight in sentiment_keywords.items():
                all_keywords[word] = all_keywords.get(word, 0) + float(weight)  # 🔄 Pas besoin de ["N"]

            print(f"📊 all_keywords après extraction: {all_keywords}")

            all_sentiments.append(review.get("sentiment", {}))

        # Générer et uploader le nuage de mots
        wordcloud_img = generate_wordcloud(all_keywords)
        wordcloud_url = upload_to_s3(wordcloud_img, f"{restaurant_id}_wordcloud.png")

        # Générer et uploader l'histogramme des sentiments
        histogram_img = generate_histogram(all_sentiments)
        histogram_url = upload_to_s3(histogram_img, f"{restaurant_id}_histogram.png")

        # Retourner les URLs des images avec les données du restaurant
        return {
            "statusCode": 200,
            "body": json.dumps({
                "restaurant_id": restaurant_id,
                "wordcloud_url": wordcloud_url,
                "histogram_url": histogram_url,
                "reviews": convert_decimal(reviews),
            }, indent=2, ensure_ascii=False)
        }

    except Exception as e:
        print(f"❌ Erreur: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
