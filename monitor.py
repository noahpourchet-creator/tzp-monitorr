import json
import os
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK", "")

BASE_URL = "https://www.tzp.fr"

CATEGORIES = {
    "Précommandes Pokémon": (
        f"{BASE_URL}/18-precommande"
    ),
    "Pokémon en Français": (
        f"{BASE_URL}/19-coffrets-etb-display-francais"
    ),
    "One Piece": (
        f"{BASE_URL}/17-one-piece"
    ),
}


# ============================================================
# PRODUITS PRIORITAIRES
# ============================================================
#
# Ces produits sont surveillés directement sur leur fiche.
# Ils ne déclencheront pas de notification via la surveillance
# des catégories afin d'éviter les doublons.
#
# ============================================================

WATCHED_PRODUCTS = {
    "etb_me06": {
        "name": (
            "Pokémon ME06 – Règne Delta – "
            "Coffret Dresseur d’Élite – ETB – Français"
        ),
        "url": (
            f"{BASE_URL}/precommande/"
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
            f"{BASE_URL}/precommande/"
            "3528-pokemon-me06-regne-delta-display-36-boosters-"
            "francais-0196214144613.html"
        ),
        "ean": "0196214144613",
        "category": "Précommandes Pokémon",
    },
}


# ============================================================
# FICHIER D'ÉTAT
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
# SESSION HTTP
# ============================================================

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ============================================================
# DISCORD
# ============================================================

def send_discord(
    title,
    description,
    color=0x00FF00
):
    """
    Envoie une notification Discord avec @everyone.

    Gère :
    - absence de webhook
    - timeout
    - erreurs réseau
    - rate limit Discord 429
    - plusieurs tentatives
    """

    if not WEBHOOK_URL:
        print(
            "[DISCORD] DISCORD_WEBHOOK "
            "n'est pas configuré."
        )
        return False

    payload = {
        # Mention @everyone
        "content": "@everyone",

        "username": "TZP Monitor",

        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,

                "footer": {
                    "text": (
                        "TZP Monitor • "
                        "Surveillance TZP"
                    )
                },

                "timestamp": (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
            }
        ],

        # Autorise explicitement @everyone
        "allowed_mentions": {
            "parse": ["everyone"]
        }
    }

    max_attempts = 3

    for attempt in range(1, max_attempts + 1):

        try:

            response = requests.post(
                WEBHOOK_URL,
                json=payload,
                timeout=15
            )

            # ------------------------------------------------
            # RATE LIMIT
            # ------------------------------------------------

            if response.status_code == 429:

                try:
                    retry_after = float(
                        response.json().get(
                            "retry_after",
                            1
                        )
                    )
                except Exception:
                    retry_after = 1.0

                print(
                    "[DISCORD] Rate limit "
                    f"(tentative {attempt}/{max_attempts}). "
                    f"Attente de {retry_after:.2f} seconde(s)..."
                )

                if attempt < max_attempts:
                    time.sleep(retry_after)
                    continue

                print(
                    "[DISCORD] Rate limit persistant."
                )

                return False

            # ------------------------------------------------
            # SUCCÈS
            # ------------------------------------------------

            if response.status_code in (200, 204):

                print(
                    "[DISCORD] "
                    "@everyone + notification envoyés."
                )

                return True

            # ------------------------------------------------
            # ERREUR HTTP
            # ------------------------------------------------

            print(
                "[DISCORD] Erreur HTTP "
                f"{response.status_code}: "
                f"{response.text}"
            )

            return False

        except requests.RequestException as e:

            print(
                "[DISCORD] Erreur réseau "
                f"(tentative {attempt}/{max_attempts}) : "
                f"{e}"
            )

            if attempt < max_attempts:
                time.sleep(2)
                continue

            return False

        except Exception as e:

            print(
                f"[DISCORD] Erreur inattendue : {e}"
            )

            return False

    return False


# ============================================================
# ETAT
# ============================================================

def load_state():
    """
    Charge l'état précédent.
    """

    if not os.path.exists(STATE_FILE):
        return {}

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            state = json.load(file)

            if not isinstance(state, dict):
                print(
                    "[STATE] État invalide. "
                    "Réinitialisation."
                )
                return {}

            return state

    except Exception as e:

        print(
            f"[STATE] Impossible de charger "
            f"{STATE_FILE}: {e}"
        )

        return {}


def save_state(state):
    """
    Sauvegarde atomique de l'état.
    """

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
    """
    Nettoie les espaces inutiles.
    """

    if not text:
        return ""

    return " ".join(
        text.split()
    )


def normalize_text(text):
    """
    Normalise légèrement le texte pour faciliter
    les recherches de disponibilité.
    """

    return clean_text(text).lower()


def get_product_id(link):
    """
    Supprime les paramètres d'URL.
    """

    return link.split("?")[0].rstrip("/")


def normalize_url(href):
    """
    Transforme une URL relative en URL absolue.
    """

    if not href:
        return ""

    if href.startswith("//"):
        return "https:" + href

    if href.startswith("/"):
        return BASE_URL + href

    if href.startswith("http://"):
        return href.replace(
            "http://",
            "https://",
            1
        )

    return href


# ============================================================
# DETECTION DU STOCK
# ============================================================

def detect_stock(soup):
    """
    Détermine la disponibilité d'un produit.

    Principe :
    - Si un élément indique explicitement une rupture,
      le produit est considéré indisponible.
    - Si un bouton "Ajouter au panier" actif existe,
      le produit est considéré disponible.
    - Si aucun indicateur fiable n'est trouvé,
      on considère l'état comme inconnu.

    Retour :
        (available, add_to_cart, stock_known)
    """

    page_text = normalize_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    # --------------------------------------------------------
    # INDICATEURS DE RUPTURE
    # --------------------------------------------------------

    out_of_stock_keywords = (
        "rupture de stock",
        "rupture",
        "épuisé",
        "indisponible",
        "out of stock",
        "sold out",
    )

    explicit_out_of_stock = any(
        keyword in page_text
        for keyword in out_of_stock_keywords
    )

    # --------------------------------------------------------
    # BOUTONS PANIER
    # --------------------------------------------------------

    add_to_cart_found = False
    active_add_to_cart_found = False

    cart_keywords = (
        "ajouter au panier",
        "ajout au panier",
        "add to cart",
    )

    for element in soup.find_all(
        ["button", "a", "input"]
    ):

        text = clean_text(
            element.get_text(
                " ",
                strip=True
            )
        ).lower()

        value = clean_text(
            element.get(
                "value",
                ""
            )
        ).lower()

        combined = f"{text} {value}"

        if not any(
            keyword in combined
            for keyword in cart_keywords
        ):
            continue

        add_to_cart_found = True

        disabled = element.has_attr(
            "disabled"
        )

        classes = " ".join(
            element.get(
                "class",
                []
            )
        ).lower()

        aria_disabled = (
            element.get(
                "aria-disabled",
                ""
            ).lower()
            == "true"
        )

        disabled_by_class = (
            "disabled" in classes
            or "unavailable" in classes
        )

        if not (
            disabled
            or aria_disabled
            or disabled_by_class
        ):
            active_add_to_cart_found = True

    # --------------------------------------------------------
    # MICRODATA / STRUCTURE PRODUIT
    # --------------------------------------------------------

    availability_values = []

    for element in soup.select(
        "[itemprop='availability']"
    ):

        value = (
            element.get("href", "")
            or element.get("content", "")
            or element.get_text(
                " ",
                strip=True
            )
        )

        if value:
            availability_values.append(
                normalize_text(value)
            )

    structured_out_of_stock = any(
        (
            "outofstock" in value
            or "out_of_stock" in value
            or "soldout" in value
        )
        for value in availability_values
    )

    structured_in_stock = any(
        (
            "instock" in value
            or "in_stock" in value
            or "limitedavailability" in value
        )
        for value in availability_values
    )

    # --------------------------------------------------------
    # DECISION
    # --------------------------------------------------------

    if explicit_out_of_stock or structured_out_of_stock:

        return (
            False,
            active_add_to_cart_found,
            True
        )

    if active_add_to_cart_found:

        return (
            True,
            True,
            True
        )

    if structured_in_stock:

        return (
            True,
            add_to_cart_found,
            True
        )

    # État inconnu.
    #
    # On retourne None afin de ne surtout pas transformer
    # une erreur de parsing en faux "retour en stock".
    return (
        None,
        add_to_cart_found,
        False
    )


# ============================================================
# EXTRACTION DU PRIX
# ============================================================

def extract_price(soup):
    """
    Extrait le prix depuis les sélecteurs courants.
    """

    selectors = (
        "[itemprop='price']",
        ".current-price .price",
        ".current-price",
        ".product-price",
        ".price",
    )

    for selector in selectors:

        element = soup.select_one(
            selector
        )

        if not element:
            continue

        price = clean_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if price:
            return price

    # Microdata content
    element = soup.select_one(
        "[itemprop='price'][content]"
    )

    if element:

        value = element.get(
            "content"
        )

        if value:
            return clean_text(
                value
            )

    return "Prix indisponible"


# ============================================================
# PARSING DES CATEGORIES
# ============================================================

def parse_products(
    html,
    category
):
    """
    Parse une page de catégorie.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    products = {}

    category_paths = {
        "Précommandes Pokémon": "/precommande/",
        "Pokémon en Français": (
            "/coffrets-etb-display-francais/"
        ),
        "One Piece": "/one-piece/",
    }

    expected_path = category_paths.get(
        category
    )

    if not expected_path:
        return products

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link.get(
            "href",
            ""
        )

        if expected_path not in href:
            continue

        if ".html" not in href:
            continue

        href = normalize_url(
            href
        )

        # ----------------------------------------------------
        # PRODUITS PRIORITAIRES
        # ----------------------------------------------------
        #
        # On ne les traite pas ici pour éviter les doubles
        # notifications. Leur fiche est surveillée séparément.
        #
        # ----------------------------------------------------

        watched_urls = {
            product["url"].split("?")[0].rstrip("/")
            for product in WATCHED_PRODUCTS.values()
        }

        if href.split("?")[0].rstrip("/") in watched_urls:
            continue

        # ----------------------------------------------------
        # NOM
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # BLOC PRODUIT
        # ----------------------------------------------------

        block = link
        price = "Prix indisponible"
        block_text = ""

        for _ in range(8):

            if not block.parent:
                break

            block = block.parent

            block_text = normalize_text(
                block.get_text(
                    " ",
                    strip=True
                )
            )

            price_element = block.select_one(
                "[itemprop='price'], "
                ".price, "
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

                if price:
                    break

        # ----------------------------------------------------
        # STOCK CATEGORIE
        # ----------------------------------------------------

        out_of_stock_keywords = (
            "rupture de stock",
            "rupture",
            "épuisé",
            "indisponible",
            "out of stock",
            "sold out",
        )

        out_of_stock = any(
            keyword in block_text
            for keyword in out_of_stock_keywords
        )

        product_id = get_product_id(
            href
        )

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

def fetch_category(
    category,
    url
):
    """
    Télécharge une catégorie.
    """

    try:

        response = SESSION.get(
            url,
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

    except requests.RequestException as e:

        print(
            f"[ERREUR HTTP] {category}: {e}"
        )

        return None

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
    """
    Surveille les nouveaux produits, stocks et prix
    d'une catégorie.
    """

    new_products = fetch_category(
        category,
        url
    )

    # Ne jamais écraser l'état si le site n'a pas répondu.
    if new_products is None:
        return old_products

    # --------------------------------------------------------
    # PREMIER LANCEMENT
    # --------------------------------------------------------

    if old_products is None:

        print(
            f"[INIT] {category}: "
            f"{len(new_products)} produits"
        )

        return new_products

    # --------------------------------------------------------
    # COMPARAISON
    # --------------------------------------------------------

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

        old = old_products[
            product_id
        ]

        old_available = old.get(
            "available",
            False
        )

        new_available = product.get(
            "available",
            False
        )

        # ----------------------------------------------------
        # RUPTURE -> DISPONIBLE
        # ----------------------------------------------------

        if (
            not old_available
            and new_available
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

        # ----------------------------------------------------
        # DISPONIBLE -> RUPTURE
        # ----------------------------------------------------

        elif (
            old_available
            and not new_available
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

        # ----------------------------------------------------
        # CHANGEMENT DE PRIX
        # ----------------------------------------------------

        elif (
            old.get("price")
            != product.get("price")
            and product.get("price")
            != "Prix indisponible"
        ):

            send_discord(
                "💰 Changement de prix",
                (
                    f"**{product['name']}**\n\n"
                    f"📂 {category}\n"
                    f"Ancien prix : "
                    f"**{old.get('price')}**\n"
                    f"Nouveau prix : "
                    f"**{product.get('price')}**\n\n"
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
    """
    Parse une fiche produit prioritaire.
    """

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

        name = watched_product[
            "name"
        ]

    # --------------------------------------------------------
    # PRIX
    # --------------------------------------------------------

    price = extract_price(
        soup
    )

    # --------------------------------------------------------
    # STOCK
    # --------------------------------------------------------

    (
        available,
        add_to_cart,
        stock_known
    ) = detect_stock(
        soup
    )

    return {
        "name": name,
        "url": watched_product["url"],
        "ean": watched_product["ean"],
        "category": watched_product["category"],
        "price": price,
        "available": available,
        "add_to_cart": add_to_cart,
        "stock_known": stock_known,
    }


# ============================================================
# REQUETE FICHE PRODUIT
# ============================================================

def fetch_watched_product(
    product_id,
    watched_product
):
    """
    Télécharge et analyse une fiche prioritaire.
    """

    try:

        response = SESSION.get(
            watched_product["url"],
            timeout=20
        )

        response.raise_for_status()

        product = parse_product_page(
            response.text,
            watched_product
        )

        available = product.get(
            "available"
        )

        if available is True:
            status = "🟢 DISPONIBLE"

        elif available is False:
            status = "🔴 RUPTURE"

        else:
            status = "🟡 ÉTAT INCONNU"

        print(
            f"[WATCH] {product['name']}\n"
            f"        {status}\n"
            f"        Prix : {product['price']}\n"
            f"        Panier : "
            f"{product['add_to_cart']}"
        )

        return product

    except requests.RequestException as e:

        print(
            f"[WATCH ERROR] "
            f"{watched_product['name']}: "
            f"{e}"
        )

        return None

    except Exception as e:

        print(
            f"[WATCH ERROR] "
            f"{watched_product['name']}: "
            f"{e}"
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
    """
    Surveille un produit prioritaire.

    Un état inconnu n'écrase jamais un état connu.
    """

    new_product = fetch_watched_product(
        product_id,
        watched_product
    )

    # --------------------------------------------------------
    # REQUETE ECHOUEE
    # --------------------------------------------------------

    if new_product is None:
        return old_product

    # --------------------------------------------------------
    # STOCK INCONNU
    # --------------------------------------------------------
    #
    # Très important :
    # si le parsing ne permet pas de déterminer le stock,
    # on ne doit PAS générer de faux retour en stock.
    #
    # --------------------------------------------------------

    if not new_product.get(
        "stock_known",
        False
    ):

        print(
            f"[WATCH] État du stock inconnu : "
            f"{watched_product['name']}"
        )

        # On peut quand même mettre à jour le prix,
        # mais on conserve l'ancien état de stock.
        if old_product is not None:

            new_product["available"] = (
                old_product.get(
                    "available"
                )
            )

            new_product["stock_known"] = (
                old_product.get(
                    "stock_known",
                    False
                )
            )

        else:

            # Première exécution sans information fiable :
            # on ne prétend pas connaître le stock.
            new_product["available"] = None

        return new_product

    # --------------------------------------------------------
    # PREMIERE EXECUTION
    # --------------------------------------------------------

    if old_product is None:

        if new_product["available"] is True:
            status = "DISPONIBLE"

        elif new_product["available"] is False:
            status = "RUPTURE"

        else:
            status = "INCONNU"

        print(
            f"[INIT WATCH] "
            f"{watched_product['name']} -> {status}"
        )

        return new_product

    old_available = old_product.get(
        "available"
    )

    new_available = new_product.get(
        "available"
    )

    # ========================================================
    # RUPTURE -> DISPONIBLE
    # ========================================================

    if (
        old_available is False
        and new_available is True
    ):

        send_discord(
            "🚨🚨 RETOUR EN STOCK 🚨🚨",
            (
                f"**{new_product['name']}**\n\n"
                f"📂 {watched_product['category']}\n"
                f"💰 **{new_product['price']}**\n\n"
                f"🟢 **DISPONIBLE SUR TZP**\n\n"
                f"📦 EAN : "
                f"`{watched_product['ean']}`\n\n"
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
        old_available is True
        and new_available is False
    ):

        send_discord(
            "🔴 Produit repassé en rupture",
            (
                f"**{new_product['name']}**\n\n"
                f"📂 {watched_product['category']}\n"
                f"💰 {new_product['price']}\n\n"
                f"🔴 **RUPTURE DE STOCK**\n\n"
                f"📦 EAN : "
                f"`{watched_product['ean']}`\n\n"
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
                f"Ancien prix : "
                f"**{old_product.get('price')}**\n"
                f"Nouveau prix : "
                f"**{new_product.get('price')}**\n\n"
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

        old_products = state[
            "categories"
        ].get(category)

        new_products = monitor_category(
            category,
            url,
            old_products
        )

        if new_products is not None:

            state[
                "categories"
            ][category] = new_products

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

    save_state(
        state
    )

    print(
        "\nVérification terminée."
    )


# ============================================================
# LANCEMENT
# ============================================================

if __name__ == "__main__":
    main()
