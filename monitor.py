def send_discord(
    title,
    description,
    color=0x00FF00
):
    """
    Envoie une notification Discord avec @everyone
    pour toutes les notifications.
    """

    if not WEBHOOK_URL:

        print(
            "[DISCORD] DISCORD_WEBHOOK "
            "n'est pas configuré."
        )

        return


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

        # Autorise explicitement le ping @everyone
        "allowed_mentions": {
            "parse": ["everyone"]
        }
    }


    try:

        response = requests.post(

            WEBHOOK_URL,

            json=payload,

            timeout=15
        )


        # Gestion du rate limit Discord
        if response.status_code == 429:

            try:

                retry_after = (
                    response
                    .json()
                    .get(
                        "retry_after",
                        1
                    )
                )

            except Exception:

                retry_after = 1


            print(
                "[DISCORD] Rate limit. "
                f"Attente de {retry_after} seconde(s)..."
            )


            time.sleep(
                float(retry_after)
            )


            response = requests.post(

                WEBHOOK_URL,

                json=payload,

                timeout=15
            )


        if response.status_code not in (
            200,
            204
        ):

            print(
                "[DISCORD] Erreur HTTP "
                f"{response.status_code}: "
                f"{response.text}"
            )

        else:

            print(
                "[DISCORD] "
                "@everyone + notification envoyés."
            )


    except Exception as e:

        print(
            f"[DISCORD] Erreur : {e}"
        )

