from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from webdriver_manager.firefox import GeckoDriverManager
import os
import platform

def get_driver():
    firefox_options = Options()

    # Mode headless uniquement sur Lambda
    if os.getenv('AWS_LAMBDA_FUNCTION_NAME'):
        firefox_options.add_argument('--headless')
        firefox_options.add_argument('--no-sandbox')
        firefox_options.add_argument('--disable-dev-shm-usage')

    # Définition du chemin de Firefox sur macOS
    if platform.system() == 'Darwin':  # macOS
        firefox_paths = [
            "/Applications/Firefox.app/Contents/MacOS/firefox",
            "/usr/local/bin/firefox",
            "/opt/homebrew/bin/firefox"
        ]

        for path in firefox_paths:
            if os.path.exists(path):
                firefox_options.binary_location = path
                break
        else:
            raise Exception("Firefox n'est pas installé. Installez-le ici : https://www.mozilla.org/fr/firefox/new/")


    os.environ['GH_TOKEN'] = "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"

    # Installation automatique de GeckoDriver
    service = Service(GeckoDriverManager().install())

    return webdriver.Firefox(
        service=service,
        options=firefox_options
    )
