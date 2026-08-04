import logging
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)

# ================= CONFIGURATION =================

load_dotenv()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

CINEPLEX_URL = "https://apis.cineplex.com/prod/cpx/theatrical/api/v1/dates/bookable"
FILM_ID = "37617"  # The Odyssey

LOCATIONS = {
    "9406": "Cineplex Scotia Montreal",
    "7408": "Cineplex Vaughan",
    "7420": "Cineplex Mississauga",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:153.0) Gecko/20100101 Firefox/153.0",
    "Accept": "*/*",
    "Referer": "https://www.cineplex.com/",
    "Origin": "https://www.cineplex.com",
    "Ocp-Apim-Subscription-Key": os.getenv("OCP_APIM_SUBSCRIPTION_KEY"),
}
# =================================================


def send_discord_error_alert(location_name, status_code, error_message):
    """Sends a critical failure notification to Discord."""
    embed_payload = {
        "content": "🚨 **SCRIPT MONITOR FAILURE**",
        "embeds": [
            {
                "title": f"❌ Error checking {location_name}",
                "description": "The ticket monitoring script encountered a critical error.",
                "color": 15158332,  # Dark Red
                "fields": [
                    {
                        "name": "Status Code",
                        "value": f"`{status_code}`" if status_code else "`N/A`",
                        "inline": True,
                    },
                    {
                        "name": "Possible Cause",
                        "value": (
                            "Expired `Ocp-Apim-Subscription-Key` or User-Agent block"
                            if status_code in [401, 403]
                            else "Network error or API structural change"
                        ),
                        "inline": True,
                    },
                    {
                        "name": "Details",
                        "value": f"```\n{str(error_message)[:1000]}\n```",
                        "inline": False,
                    },
                ],
                "footer": {
                    "text": f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                },
            }
        ],
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=embed_payload, timeout=5)
    except Exception as e:
        logging.error(f"Failed to deliver failure embed to Discord: {e}")


def send_discord_alert(location_id, location_name, dates, is_initial=False):
    """Sends a formatted Discord Embed alert for a specific location."""
    sorted_dates = sorted([d.split("T")[0] for d in dates])
    latest_date = sorted_dates[-1]
    status_prefix = "ℹ️ @everyone Initial Scan" if is_initial else "🚨 NEW TICKETS OPEN"

    embed_payload = {
        "content": f"{'🚨 @everyone ' if not is_initial else ''}**TICKETS ALERT: THE ODYSSEY**",
        "embeds": [
            {
                "title": f"🎟️ {location_name}",
                "description": f"{status_prefix} for location `{LOCATIONS[location_id]}`!",
                "color": 15548997 if not is_initial else 3447003,
                "fields": [
                    {
                        "name": "📅 Latest Available Date",
                        "value": f"• `{latest_date}`",
                        "inline": False,
                    },
                    {
                        "name": "🔗 Quick Link",
                        "value": "[Click here to buy on Cineplex.com](https://www.cineplex.com/)",
                        "inline": False,
                    },
                ],
                "footer": {
                    "text": f"Total bookable dates: {len(sorted_dates)} | Last Checked: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                },
            }
        ],
    }

    response = requests.post(DISCORD_WEBHOOK_URL, json=embed_payload)
    if response.status_code in [200, 204]:
        logging.info(f"✅ Discord alert sent for {location_name}!")
    else:
        logging.error(
            f"❌ Failed to send Discord alert for {location_name}: {response.status_code} - {response.text}"
        )


def monitor_tickets():
    known_dates = {loc_id: set() for loc_id in LOCATIONS}
    first_run = True

    logging.info(
        f"👀 Starting monitor for Film ID {FILM_ID} across {len(LOCATIONS)} locations...\n"
    )

    while True:
        for loc_id, loc_name in LOCATIONS.items():
            try:
                params = {"filmId": FILM_ID, "locationId": loc_id}
                res = requests.get(
                    CINEPLEX_URL, headers=HEADERS, params=params, timeout=10
                )

                # Catch expired API Key (401), Blocked User-Agent (403), or API Errors
                if res.status_code != 200:
                    error_msg = f"HTTP {res.status_code}: {res.text}"
                    logging.error(f"⚠️ [{loc_name}] {error_msg}")

                    # Notify Discord on bad headers/auth issues
                    send_discord_error_alert(loc_name, res.status_code, error_msg)
                    continue

                current_dates = set(res.json())
                new_dates = current_dates - known_dates[loc_id]

                if new_dates:
                    if not first_run:
                        logging.info(f"🎉 [{loc_name}] New dates found: {new_dates}")
                        send_discord_alert(
                            loc_id, loc_name, list(new_dates), is_initial=False
                        )
                    else:
                        logging.info(
                            f"ℹ️ [{loc_name}] Initial scan complete. Bookable dates: {list(current_dates)}"
                        )
                        send_discord_alert(
                            loc_id,
                            loc_name,
                            list(current_dates),
                            is_initial=True,
                        )

                    known_dates[loc_id].update(current_dates)
                else:
                    logging.info(
                        f"[{datetime.now().strftime('%H:%M:%S')}] [{loc_name}] No new dates."
                    )

                time.sleep(1)

            except requests.exceptions.RequestException as req_err:
                logging.error(f"⚠️ [{loc_name}] Request failure: {str(req_err)}")
                send_discord_error_alert(loc_name, None, str(req_err))
            except Exception as e:
                logging.error(f"⚠️ [{loc_name}] Unexpected error during check: {e}")
                send_discord_error_alert(loc_name, None, str(e))

        first_run = False
        logging.info("⏳ Full pass complete. Sleeping for 1 minutes...\n")
        time.sleep(60)


if __name__ == "__main__":
    if not DISCORD_WEBHOOK_URL:
        logging.error("No DISCORD_WEBHOOK_URL in env.")
        exit(1)

    monitor_tickets()
