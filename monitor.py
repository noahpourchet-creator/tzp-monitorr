import json
import os
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK", "")

CATEGORIES = {
    "Précommandes Pokémon": "https://www.tzp.fr/18-precommande",
    "Pokémon en Français": "https://www.tzp.fr/19-coffrets-etb-display-francais",
    "One Piece": "https://www.tzp.fr/17-one-piece",
}


# ============================================================
# PRODUITS PRIORITAIRES
# ============================================================
#
# Ces produits sont surveillés directement par leur fiche.
# C'est cette surveillance qui nous intéresse principalement
# pour les réassorts.
#
# ============================================================

WATCHED_PRODUCTS = {
    "etb_me06": {
        "name": (
            "Pokémon ME06 – Règne Delta – "
            "Coffret Dresseur d’Élite – ETB – Français"
        ),
        "url": (
            "https://www.tzp.fr/precommande/"
            "3527-pokemon-me06-regne-delta-coffret-dresseur-elite-"
            "etb-francais-0196214143913.html"
        ),
        "ean": "0196214143913",
        "category": "Précommandes Pokémon",
    },

    "display_me06": {
        "name": (
            "Pokémon ME06 – Règne Delta – "
            "Display 36 Boosters – Français"
        ),
        "url": (
            "https://www.tzp.fr/precommande/"
            "3528-pokemon-me06-regne-delta-display-36-boosters-"
            "francais-0196214144613.html"
        ),
        "ean": "0196214144613",
        "category": "Précommandes Pokémon",
    },
}


# ============================================================
# FICHIER D'ETAT
# ============================================================

STATE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "tzp_state.json"
)


# ============================================================
# HTTP
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


# ============================================================
# DISCORD
# ============================================================

def send_discord(title, description, color=0x00FF00):

    if not WEBHOOK_URL:
        print("[DISCORD] DISCORD_WEBHOOK n'est pas configuré.")
        return

    payload = {
        "username": "TZP Monitor",
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,
                "footer": {
                    "text": "TZP Monitor • Surveillance TZP"
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
                retry_after = response.json().get(
                    "retry_after",
                    1
                )
            except Exception:
                retry_after = 1

            print(
                f"[DISCORD] Rate limit. "
                f"Attente de {retry_after} seconde(s)..."
            )

            import time
            time.sleep(float(retry_after))

            response = requests.post(
                WEBHOOK_URL,
                json=payload,
                timeout=15
            )

        if response.status_code not in (200, 204):

            print(
                f"[DISCORD] Erreur HTTP "
                f"{response.status_code}: "
                f"{response.text}"
            )

        else:

            print("[DISCORD] Notification envoyée.")

    except Exception as e:

        print(f"[DISCORD] Erreur : {e}")


# ============================================================
# ETAT
# ============================================================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {}

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except Exception as e:

        print(
            f"[STATE] Impossible de charger "
            f"{STATE_FILE}: {e}"
        )

        return {}


def save_state(state):

    temp_file = STATE_FILE + ".tmp"

    try:

        with open(
            temp_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                state,
                file,
                ensure_ascii=False,
                indent=2
            )

        os.replace(
            temp_file,
            STATE_FILE
        )

    except Exception as e:

        print(
            f"[STATE] Erreur sauvegarde : {e}"
        )


# ============================================================
# OUTILS
# ============================================================

def clean_text(text):

    if not text:
        return ""

    return " ".join(text.split())


def get_product_id(link):

    return link.split("?")[0].rstrip("/")


# ============================================================
# PARSING DES CATEGORIES
# ============================================================

def parse_products(html, category):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    products = {}

    category_paths = {
        "Précommandes Pokémon": "/precommande/",
        "Pokémon en Français": "/coffrets-etb-display-francais/",
        "One Piece": "/one-piece/",
    }

    expected_path = category_paths.get(category)

    if not expected_path:
        return products

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link.get("href", "")

        if expected_path not in href:
            continue

        if ".html" not in href:
            continue

        name = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )

        if not name:

            parent = link.parent

            if parent:

                element = parent.select_one(
                    ".product-title, h2, h3"
                )

                if element:

                    name = clean_text(
                        element.get_text(
                            " ",
                            strip=True
                        )
                    )

        if not name:
            continue

        if href.startswith("/"):
            href = "https://www.tzp.fr" + href

        elif href.startswith("//"):
            href = "https:" + href

        block = link

        price = "Prix indisponible"
        block_text = ""

        for _ in range(8):

            if not block.parent:
                break

            block = block.parent

            block_text = clean_text(
                block.get_text(
                    " ",
                    strip=True
                )
            ).lower()

            price_element = block.select_one(
                "[itemprop='price'], "
                ".price, "
                ".product-price"
            )

            if price_element:

                price = clean_text(
                    price_element.get_text(
                        " ",
                        strip=True
                    )
                )

                break

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

    print(
        f"[PARSE] {category}: "
        f"{len(products)} produits"
    )

    return products


# ============================================================
# REQUETE CATEGORIE
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
            f"{response.status_code}"
        )

        return parse_products(
            response.text,
            category
        )

    except Exception as e:

        print(
            f"[ERREUR] {category}: {e}"
        )

        return None


# ============================================================
# SURVEILLANCE DES CATEGORIES
# ============================================================

def monitor_category(
    category,
    url,
    old_products
):

    new_products = fetch_category(
        category,
        url
    )

    if new_products is None:
        return old_products

    if old_products is None:

        print(
            f"[INIT] {category}: "
            f"{len(new_products)} produits"
        )

        return new_products

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

            continue

        old = old_products[product_id]

        if (
            not old.get("available", False)
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

        elif (
            old.get("available", False)
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

        elif (
            old.get("price") != product["price"]
            and product["price"] != "Prix indisponible"
        ):

            send_discord(
                "💰 Changement de prix",
                (
                    f"**{product['name']}**\n\n"
                    f"📂 {category}\n"
                    f"Ancien prix : **{old.get('price')}**\n"
                    f"Nouveau prix : **{product['price']}**\n\n"
                    f"🔗 {product['url']}"
                ),
                0xF1C40F
            )

    return new_products


# ============================================================
# PARSING D'UNE FICHE PRODUIT
# ============================================================

def parse_product_page(
    html,
    watched_product
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # --------------------------------------------------------
    # NOM
    # --------------------------------------------------------

    h1 = soup.find("h1")

    if h1:

        name = clean_text(
            h1.get_text(
                " ",
                strip=True
            )
        )

    else:

        name = watched_product["name"]


    # --------------------------------------------------------
    # PRIX
    # --------------------------------------------------------

    price = "Prix indisponible"

    price_element = soup.select_one(
        "[itemprop='price'], "
        ".current-price .price, "
        ".product-price, "
        ".current-price"
    )

    if price_element:

        price = clean_text(
            price_element.get_text(
                " ",
                strip=True
            )
        )


    # --------------------------------------------------------
    # TEXTE DE LA FICHE
    # --------------------------------------------------------

    page_text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    ).lower()


    # --------------------------------------------------------
    # DETECTION STOCK
    # --------------------------------------------------------
    #
    # On considère explicitement ces messages comme une
    # rupture.
    #
    # Sinon le produit est considéré disponible.
    #
    # Cela permet de détecter :
    #
    # RUPTURE
    #    ↓
    # DISPONIBLE
    #
    # --------------------------------------------------------

    stock_keywords = (
        "rupture de stock",
        "épuisé",
        "indisponible",
        "out of stock",
        "sold out",
    )

    out_of_stock = any(
        keyword in page_text
        for keyword in stock_keywords
    )


    # --------------------------------------------------------
    # BOUTON PANIER
    # --------------------------------------------------------

    add_to_cart = (
        "ajouter au panier" in page_text
        or "ajout au panier" in page_text
    )


    return {
        "name": name,
        "url": watched_product["url"],
        "ean": watched_product["ean"],
        "category": watched_product["category"],
        "price": price,
        "available": not out_of_stock,
        "add_to_cart": add_to_cart,
    }


# ============================================================
# REQUETE FICHE PRODUIT
# ============================================================

def fetch_watched_product(
    product_id,
    watched_product
):

    try:

        response = requests.get(
            watched_product["url"],
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        product = parse_product_page(
            response.text,
            watched_product
        )

        status = (
            "🟢 DISPONIBLE"
            if product["available"]
            else "🔴 RUPTURE"
        )

        print(
            f"[WATCH] {product['name']}\n"
            f"        {status}\n"
            f"        Prix : {product['price']}\n"
            f"        Panier : "
            f"{product['add_to_cart']}"
        )

        return product

    except Exception as e:

        print(
            f"[WATCH ERROR] "
            f"{watched_product['name']}: {e}"
        )

        return None


# ============================================================
# SURVEILLANCE PRODUIT PRIORITAIRE
# ============================================================

def monitor_watched_product(
    product_id,
    watched_product,
    old_product
):

    new_product = fetch_watched_product(
        product_id,
        watched_product
    )

    # Si la requête échoue, surtout ne pas modifier
    # l'ancien état.
    if new_product is None:

        return old_product


    # --------------------------------------------------------
    # PREMIERE EXECUTION
    # --------------------------------------------------------
    #
    # On initialise l'état sans notification.
    #
    # Si le produit est déjà en stock au premier lancement,
    # on ne veut pas recevoir un faux "retour en stock".
    #
    # --------------------------------------------------------

    if old_product is None:

        status = (
            "DISPONIBLE"
            if new_product["available"]
            else "RUPTURE"
        )

        print(
            f"[INIT WATCH] "
            f"{watched_product['name']} -> {status}"
        )

        return new_product


    old_available = old_product.get(
        "available",
        False
    )

    new_available = new_product.get(
        "available",
        False
    )


    # ========================================================
    # RUPTURE -> DISPONIBLE
    # ========================================================

    if (
        not old_available
        and new_available
    ):

        send_discord(
            "🚨🚨 RETOUR EN STOCK 🚨🚨",
            (
                f"**{new_product['name']}**\n\n"
                f"📂 {watched_product['category']}\n"
                f"💰 **{new_product['price']}**\n\n"
                f"🟢 **DISPONIBLE SUR TZP**\n\n"
                f"📦 EAN : `{watched_product['ean']}`\n\n"
                f"👉 {watched_product['url']}"
            ),
            0x00FF00
        )

        print(
            f"[🚨 STOCK] RETOUR EN STOCK : "
            f"{new_product['name']}"
        )


    # ========================================================
    # DISPONIBLE -> RUPTURE
    # ========================================================

    elif (
        old_available
        and not new_available
    ):

        send_discord(
            "🔴 Produit repassé en rupture",
            (
                f"**{new_product['name']}**\n\n"
                f"📂 {watched_product['category']}\n"
                f"💰 {new_product['price']}\n\n"
                f"🔴 **RUPTURE DE STOCK**\n\n"
                f"📦 EAN : `{watched_product['ean']}`\n\n"
                f"🔗 {watched_product['url']}"
            ),
            0xE74C3C
        )

        print(
            f"[RUPTURE] {new_product['name']}"
        )


    # ========================================================
    # CHANGEMENT DE PRIX
    # ========================================================

    elif (
        old_product.get("price")
        != new_product.get("price")
        and new_product.get("price")
        != "Prix indisponible"
    ):

        send_discord(
            "💰 Changement de prix",
            (
                f"**{new_product['name']}**\n\n"
                f"📂 {watched_product['category']}\n"
                f"Ancien prix : **{old_product.get('price')}**\n"
                f"Nouveau prix : **{new_product.get('price')}**\n\n"
                f"🔗 {watched_product['url']}"
            ),
            0xF1C40F
        )

        print(
            f"[PRIX] {new_product['name']}: "
            f"{old_product.get('price')} -> "
            f"{new_product.get('price')}"
        )


    return new_product


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("TZP MONITOR")
    print("=" * 60)

    state = load_state()

    if "categories" not in state:
        state["categories"] = {}

    if "watched_products" not in state:
        state["watched_products"] = {}


    # ========================================================
    # CATEGORIES
    # ========================================================

    print("\n--- CATEGORIES ---")

    for category, url in CATEGORIES.items():

        old_products = state["categories"].get(
            category
        )

        new_products = monitor_category(
            category,
            url,
            old_products
        )

        if new_products is not None:

            state["categories"][category] = (
                new_products
            )


    # ========================================================
    # PRODUITS PRIORITAIRES
    # ========================================================

    print("\n--- PRODUITS PRIORITAIRES ---")

    for product_id, product in WATCHED_PRODUCTS.items():

        old_product = state[
            "watched_products"
        ].get(product_id)

        new_product = monitor_watched_product(
            product_id,
            product,
            old_product
        )

        if new_product is not None:

            state[
                "watched_products"
            ][product_id] = new_product


    # ========================================================
    # SAUVEGARDE
    # ========================================================

    save_state(state)

    print("\nVérification terminée.")


# ============================================================
# LANCEMENT
# ============================================================

if __name__ == "__main__":
    main()
