import json
import time
import boto3
from decimal import Decimal
from datetime import datetime
from botocore.exceptions import ClientError
from urllib.parse import unquote
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
from selenium_config import get_driver

dynamodb = boto3.resource('dynamodb', region_name='eu-west-1')

def handler(event, context):
    try:
        restaurant_table = dynamodb.Table('restaurants-dev')
        review_table = dynamodb.Table('reviews-dev')

        operation = event.get('operation', 'restaurants_and_reviews')
        location = event.get('location', 'Paris')
        max_restaurants = event.get('max_restaurants', 10)
        max_reviews = event.get('max_reviews_per_restaurant', 10)

        if operation == 'restaurants_and_reviews':
            search_url = f'https://www.yelp.fr/search?find_desc=Restaurants&find_loc={location}'
            restaurants = scrape_search_results(search_url, max_pages=1)
            total_reviews = 0

            for resto in restaurants[:max_restaurants]:
                restaurant_id = unquote(resto['url'].split('/')[-1].split('?')[0])

                # Sauvegarder le restaurant
                restaurant_item = {
                    'id': restaurant_id,
                    'name': resto['name'],
                    'url': resto['url'],
                    'rating': Decimal(str(resto['rating'])),
                    'reviews_count': resto['reviews_count'],
                    'location': resto['location'],
                    'last_updated': resto['last_updated']
                }

                restaurant_table.put_item(Item=restaurant_item)
                print(f"Restaurant ajouté : {resto['name']}")

                # Scraper et sauvegarder les avis pour ce restaurant
                reviews = scrape_reviews(resto['url'], max_reviews=max_reviews)

                for review in reviews:
                    # Nettoyer et normaliser l'ID de l'avis
                    clean_user_name = review['user_name'].replace(' ', '_')
                    clean_date = review['date'].replace(' ', '_')
                    review_id = f"{restaurant_id}_{clean_user_name}_{clean_date}"

                    review_item = {
                        'id': review_id,
                        'restaurant_id': restaurant_id,
                        'user_name': review['user_name'],
                        'user_location': review['user_location'],
                        'date': review['date'],
                        'text': review['text'],
                        'rating': Decimal(str(review['rating'])),
                        'reactions': review['reactions'],
                        'review_type': review['review_type'],
                        'page_number': review['page_number'],
                        'scraped_at': review['scraped_at']
                    }

                    review_table.put_item(Item=review_item)

                total_reviews += len(reviews)
                print(f"Ajout de {len(reviews)} avis pour {resto['name']}")

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Scraping des restaurants et avis réussi',
                    'restaurants_count': len(restaurants),
                    'total_reviews': total_reviews
                }, ensure_ascii=False)
            }

        else:
            raise Exception("Opération non valide")

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            }, ensure_ascii=False)
        }

def scrape_search_results(url, max_pages=1):
    driver = get_driver()
    restaurants = []

    try:
        current_page = 1

        while current_page <= max_pages and len(restaurants) < 10:
            print(f"Scraping page {current_page}...")
            driver.get(url)

            # Attendre que les résultats soient chargés
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='serp-ia-card']"))
            )

            # Extraire les restaurants
            restaurant_cards = driver.find_elements(By.CSS_SELECTOR, "[data-testid='serp-ia-card']")

            for card in restaurant_cards[:10]:
                try:
                    name = card.find_element(By.CSS_SELECTOR, "h3 a").text
                    url = card.find_element(By.CSS_SELECTOR, "h3 a").get_attribute("href")
                    rating = float(card.find_element(By.CSS_SELECTOR, "[aria-label*='étoiles']").get_attribute("aria-label").split()[0])
                    reviews_count = card.find_element(By.CSS_SELECTOR, "[data-font-weight='semibold'] + span").text
                    location = card.find_element(By.CSS_SELECTOR, "[class*='css-4p5f5z']").text

                    restaurant_data = {
                        'name': name,
                        'url': url,
                        'rating': rating,
                        'reviews_count': reviews_count,
                        'location': location,
                        'last_updated': datetime.now().isoformat()
                    }

                    restaurants.append(restaurant_data)

                except Exception as e:
                    print(f"Erreur lors de l'extraction d'un restaurant: {str(e)}")
                    continue

            current_page += 1
            url = f"{url}&start={(current_page-1) * 10}"

        return restaurants[:10]

    finally:
        driver.quit()

def scrape_reviews(restaurant_url, max_reviews=10):
    driver = get_driver()
    reviews = []

    try:
        # Définir les URLs pour les avis positifs et négatifs
        sort_urls = {
            'positif': f"{restaurant_url}&sort_by=rating_desc",
            'negatif': f"{restaurant_url}&sort_by=rating_asc"
        }


        for review_type, url in sort_urls.items():
            try:
                # Ouvrir l'URL avec le tri approprié
                driver.get(url)

                # Accepter les cookies si présents
                try:
                    cookie_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button#onetrust-accept-btn-handler"))
                    )
                    cookie_button.click()
                except:
                    print("Pas de bannière de cookies ou déjà acceptés")

                # Attendre le chargement des avis
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "li.y-css-1sqelp2"))
                )

                # Récupérer les avis (5 par type)
                review_elements = driver.find_elements(By.CSS_SELECTOR, "li.y-css-1sqelp2")[:5]  # 5 au lieu de max_reviews//2
                print(f"Trouvé {len(review_elements)} avis {review_type}s")

                for review in review_elements:
                    try:
                        # Nom et localisation de l'utilisateur
                        user_info = review.find_element(By.CSS_SELECTOR, ".user-passport-info")
                        user_name = user_info.find_element(By.CSS_SELECTOR, "a").text

                        try:
                            user_location = user_info.find_element(By.CSS_SELECTOR, "[data-testid='UserPassportInfoTextContainer'] span").text
                        except:
                            user_location = None

                        # ID utilisateur depuis le lien du profil
                        try:
                            user_link = user_info.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
                            user_id = user_link.split("userid=")[1] if "userid=" in user_link else None
                        except:
                            user_id = None

                        # Note
                        rating_div = review.find_element(By.CSS_SELECTOR, ".y-css-dnttlc")
                        rating = int(rating_div.get_attribute("aria-label").split()[0])

                        # Date
                        date = review.find_element(By.CSS_SELECTOR, ".y-css-1d8mpv1").text

                        # Texte de l'avis
                        text = review.find_element(By.CSS_SELECTOR, ".comment__09f24__D0cxf").text

                        # Réactions
                        reactions = {}
                        reaction_buttons = review.find_elements(By.CSS_SELECTOR, ".y-css-4u1w9w")
                        for button in reaction_buttons:
                            label = button.get_attribute("aria-label")
                            if label:
                                parts = label.split("(")[1].split(")")[0].split()
                                count = int(parts[0])
                                reaction_type = label.split("(")[0].strip()
                                reaction_type = reaction_type.lower().replace(" ", "_")
                                reactions[reaction_type] = count

                        # Déterminer le type d'avis selon la note
                        if rating <= 2:
                            review_type = 'negatif'
                        elif rating == 3:
                            review_type = 'neutre'
                        else:  # 4 ou 5
                            review_type = 'positif'

                        # S'assurer que le JSON est bien formaté
                        reactions_json = json.dumps(reactions, ensure_ascii=False)


                        reviews.append({
                            'user_id': user_id,
                            'user_name': user_name,
                            'user_location': user_location,
                            'rating': rating,
                            'date': date,
                            'text': text,
                            'reactions': reactions_json,
                            'review_type': review_type,
                            'page_number': 1,
                            'scraped_at': datetime.now().isoformat()
                        })

                    except Exception as e:
                        print(f"Erreur lors de l'extraction d'un avis {review_type}: {str(e)}")
                        continue

            except Exception as e:
                print(f"Erreur lors du tri des avis {review_type}: {str(e)}")
                continue

        print(f"Total d'avis récupérés pour ce restaurant : {len(reviews)}")
        return reviews

    finally:
        driver.quit()


if __name__ == "__main__":
    test_event = {
        "operation": "restaurants_and_reviews",
        "location": "Paris",
        "max_restaurants": 10,
        "max_reviews_per_restaurant": 10
    }

    result = handler(test_event, None)

    print("Résultat final :", result)
