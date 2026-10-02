import json
import os
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK", "")


CHECK_INTERVAL = 60  # secondes

CATEGORIES = {
    "Précommandes Pokémon": "https://www.tzp.fr/18-precommande",
    "Pokémon en Français": "https://www.tzp.fr/19-coffrets-etb-display-francais",
    "One Piece": "https://www.tzp.fr/17-one-piece",
}

STATE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "tzp_state.json"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


# ============================================================
# DISCORD
# ============================================================

def send_discord(title, description, color=0x00FF00):
    if not WEBHOOK_URL or "COLLE_TON_WEBHOOK" in WEBHOOK_URL:
        print("Webhook Discord non configuré.")
        return

    payload = {
        "username": "TZP Monitor",
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,
                "footer": {
                    "text": "TZP Monitor • Vérification toutes les 60 secondes"
                },
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        ]
    }

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            timeout=15
        )

        if response.status_code == 429:
            try:
                retry_after = response.json().get("retry_after", 1)
            except Exception:
                retry_after = 1

            print(
                f"[DISCORD] Rate limit. "
                f"Attente de {retry_after} seconde(s)..."
            )

            time.sleep(float(retry_after))

            response = requests.post(
                WEBHOOK_URL,
                json=payload,
                timeout=15
            )

        # Pause entre les notifications
        time.sleep(1)

        if response.status_code not in (200, 204):
            print(
                f"Erreur Discord : {response.status_code} "
                f"{response.text}"
            )

    except Exception as e:
        print(f"Erreur envoi Discord : {e}")



# ============================================================
# ETAT
# ============================================================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# PARSING TZP
# ============================================================
def clean_text(text):
    return " ".join(text.split())


def get_product_id(link):
    return link.split("?")[0].rstrip("/")


def parse_products(html, category):

    soup = BeautifulSoup(html, "html.parser")

    products = {}

    # Chemin correspondant à chaque catégorie surveillée.
    category_paths = {
        "Précommandes Pokémon": "/precommande/",
        "Pokémon en Français": "/coffrets-etb-display-francais/",
        "One Piece": "/one-piece/",
    }

    expected_path = category_paths.get(category)

    # Recherche directe des fiches produits.
    for link in soup.find_all("a", href=True):

        href = link.get("href", "")

        # On garde uniquement les URLs des produits
        # de la catégorie actuellement surveillée.
        if expected_path not in href:
            continue

        if ".html" not in href:
            continue

        # Nom du produit
        name = clean_text(
            link.get_text(" ", strip=True)
        )

        if not name:
            # Certains liens sont uniquement des images.
            # On cherche alors le titre dans le bloc parent.
            parent = link.parent

            if parent:
                name_element = parent.select_one(
                    ".product-title, "
                    "h2, "
                    "h3"
                )

                if name_element:
                    name = clean_text(
                        name_element.get_text(" ", strip=True)
                    )

        if not name:
            continue

        # URL complète
        if href.startswith("/"):
            href = "https://www.tzp.fr" + href
        elif href.startswith("//"):
            href = "https:" + href

        # On remonte jusqu'à trouver un bloc contenant un prix.
        block = link

        price = "Prix indisponible"
        block_text = ""

        for _ in range(6):

            if not block.parent:
                break

            block = block.parent

            block_text = clean_text(
                block.get_text(" ", strip=True)
            ).lower()

            price_element = block.select_one(
                "[itemprop='price'], "
                ".price, "
                ".product-price"
            )

            if price_element:
                price = clean_text(
                    price_element.get_text(" ", strip=True)
                )
                break

        # Détection du stock
        out_of_stock = (
            "rupture de stock" in block_text
            or "épuisé" in block_text
            or "indisponible" in block_text
        )

        available = not out_of_stock

        product_id = get_product_id(href)

        # Évite les doublons
        if product_id in products:
            continue

        products[product_id] = {
            "name": name,
            "url": href,
            "price": price,
            "available": available,
            "category": category,
        }

    print(
        f"[PARSE] {category}: "
        f"{len(products)} produits trouvés"
    )

    return products


# ============================================================
# REQUETE TZP
# ============================================================

def fetch_category(category, url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        print(
            f"[HTTP] {category}: "
            f"status={response.status_code}, "
            f"taille={len(response.text)} caractères"
        )

        products = parse_products(
            response.text,
            category
        )

        print(
            f"[PARSE] {category}: "
            f"{len(products)} produits trouvés"
        )

        return products

    except Exception as e:
        print(f"[ERREUR] {category}: {e}")
        return None


# ============================================================
# COMPARAISON
# ============================================================

def monitor_category(category, url, old_products):
    new_products = fetch_category(category, url)

    if new_products is None:
        return old_products

    # Première exécution :
    # on initialise simplement la base sans spammer Discord.
    if old_products is None:
        print(
            f"[INIT] {category}: "
            f"{len(new_products)} produits"
        )
        return new_products

    # Nouveaux produits
    for product_id, product in new_products.items():

        if product_id not in old_products:

            send_discord(
                "🆕 Nouveau produit détecté",
                (
                    f"**{product['name']}**\n\n"
                    f"📂 {category}\n"
                    f"💰 {product['price']}\n"
                    f"🟢 Disponible\n\n"
                    f"🔗 {product['url']}"
                ),
                0x3498DB
            )

            print(
                f"[NOUVEAU] {product['name']}"
            )

            continue

        old = old_products[product_id]

        # Rupture -> disponible
        if (
            not old["available"]
            and product["available"]
        ):
            send_discord(
                "🚨 RETOUR EN STOCK",
                (
                    f"**{product['name']}**\n\n"
                    f"📂 {category}\n"
                    f"💰 {product['price']}\n"
                    f"🟢 **DISPONIBLE**\n\n"
                    f"🔗 {product['url']}"
                ),
                0x2ECC71
            )

            print(
                f"[STOCK] {product['name']}"
            )

        # Disponible -> rupture
        elif (
            old["available"]
            and not product["available"]
        ):
            send_discord(
                "🔴 Produit en rupture",
                (
                    f"**{product['name']}**\n\n"
                    f"📂 {category}\n"
                    f"💰 {product['price']}\n"
                    f"🔴 **RUPTURE DE STOCK**\n\n"
                    f"🔗 {product['url']}"
                ),
                0xE74C3C
            )

            print(
                f"[RUPTURE] {product['name']}"
            )

        # Changement de prix
        elif (
            old["price"] != product["price"]
            and product["price"] != "Prix indisponible"
        ):
            send_discord(
                "💰 Changement de prix",
                (
                    f"**{product['name']}**\n\n"
                    f"📂 {category}\n"
                    f"Ancien prix : **{old['price']}**\n"
                    f"Nouveau prix : **{product['price']}**\n\n"
                    f"🔗 {product['url']}"
                ),
                0xF1C40F
            )

            print(
                f"[PRIX] {product['name']}: "
                f"{old['price']} -> {product['price']}"
            )

    return new_products


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():

    print("=" * 60)
    print("TZP MONITOR")
    print("=" * 60)
    print("Vérification GitHub Actions")
    print("Catégories :")

    for category in CATEGORIES:
        print(f" - {category}")

    print("=" * 60)

    state = load_state()

    for category, url in CATEGORIES.items():

        old_products = state.get(category)

        new_products = monitor_category(
            category,
            url,
            old_products
        )

        if new_products is not None:
            state[category] = new_products

    save_state(state)

    print("\nVérification terminée.")
    

)


if __name__ == "__main__":


    )

    main()


