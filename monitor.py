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
    # L'URL complète permet d'avoir une clé stable
    return link.split("?")[0].rstrip("/")



def parse_products(html, category):
    soup = BeautifulSoup(html, "html.parser")

    print(f"[DEBUG] Liens trouvés : {len(soup.find_all('a'))}")

    for link in soup.find_all("a", href=True)[:30]:
        print(
            f"[DEBUG] {link.get_text(' ', strip=True)[:80]} -> "
            f"{link.get('href')}"
        )

    products = {}

    product_blocks = soup.select(
        "article.product-miniature, "
        ".js-product-miniature, "
        ".product-miniature, "
        ".product"
    )

    for block in product_blocks:

        link_element = block.select_one(
            "a.product-thumbnail, "
            "h2.product-title a, "
            ".product-title a, "
            "a[href*='.html']"
        )

        if not link_element:
            continue

        href = link_element.get("href")

        if not href:
            continue

        name = clean_text(
            link_element.get_text(" ", strip=True)
        )

        if not name or len(name) < 3:
            continue

        if href.startswith("/"):
            href = "https://www.tzp.fr" + href
        elif href.startswith("//"):
            href = "https:" + href

        price_element = block.select_one(
            ".price, "
            ".product-price, "
            "[itemprop='price'], "
            "[data-price]"
        )

        price = (
            clean_text(price_element.get_text(" ", strip=True))
            if price_element
            else "Prix indisponible"
        )

        block_text = clean_text(
            block.get_text(" ", strip=True)
        ).lower()

        out_of_stock = (
            "rupture de stock" in block_text
            or "épuisé" in block_text
            or "indisponible" in block_text
        )

        product_id = get_product_id(href)

        if product_id in products:
            continue

        products[product_id] = {
            "name": name,
            "url": href,
            "price": price,
            "available": not out_of_stock,
            "category": category,
        }

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
    
send_discord(
    "🧪 TEST DU MONITOR",
    "Le monitor TZP fonctionne correctement et peut envoyer des notifications Discord.",
    0x3498DB
)


if __name__ == "__main__":

    send_discord(
        "🧪 TEST DU MONITOR",
        "Le monitor TZP fonctionne correctement et peut envoyer des notifications Discord.",
        0x3498DB
    )

    main()


