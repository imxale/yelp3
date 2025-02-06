import json
import boto3

# Configuration AWS
AWS_REGION = "eu-west-1"
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
TABLE_NAME = "restaurants-dev"
table = dynamodb.Table(TABLE_NAME)

def handler(event, context):
    try:
        # Scan de la table pour récupérer tous les restaurants
        response = table.scan(ProjectionExpression="id")
        restaurant_ids = [item["id"] for item in response.get("Items", [])]

        return {
            "statusCode": 200,
            "body": json.dumps(restaurant_ids, ensure_ascii=False)
        }

    except Exception as e:
        print(f"❌ Erreur: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
