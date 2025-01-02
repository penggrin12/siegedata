from pathlib import Path
import re
import httpx
from bs4 import BeautifulSoup, Tag
import orjson


OUT_PATH: Path = (Path(".").absolute()) / Path("data.json")
DATA_PATTERN: re.Pattern[str] = re.compile(r"__PRELOADED_STATE__ = ({.+})", flags=re.DOTALL)


async def get_page(client: httpx.AsyncClient, url: str) -> BeautifulSoup:
    response: httpx.Response = await client.get(url)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


async def main():
    result: list[dict] = []
    raw_ops: list[dict[str, str]] = []

    async with httpx.AsyncClient() as client:
        print("Fetching operator list...")
        opslist_soup: BeautifulSoup = await get_page(
            client, "https://www.ubisoft.com/en-gb/game/rainbow-six/siege/game-info/operators"
        )

        card: Tag
        for card in opslist_soup.find_all(attrs={"class": "oplist__card"}):
            name: str = card.find("span").text.strip()
            banner: str = card.find(attrs={"class": "oplist__card__img"})["src"]
            icon: str = card.find(attrs={"class": "oplist__card__icon"})["src"]
            url: str = "https://www.ubisoft.com" + card["href"]
            raw_ops.append({"name": name, "banner": banner, "icon": icon, "url": url})

        print(f"- {len(raw_ops)} operators found.")

        for op in raw_ops:
            raw_name: str = op["url"].split("/")[-1]
            print(f"Fetching {raw_name}...")
            op_soup: BeautifulSoup = await get_page(client, op["url"])

            match: re.Match[str] | None = DATA_PATTERN.search(str(op_soup))
            if match is None:
                raise ValueError(f"No match found for {raw_name}")
            raw_data: dict = orjson.loads(match.group(1))["ContentfulGraphQl"][
                f"OperatorDetailsContainer-{raw_name}"
            ]["content"]

            primary: list[dict[str, str]] = []
            secondary: list[dict[str, str]] = []
            gadgets: list[dict[str, str]] = []
            unique: dict[str, str | dict[str, str | None]] = {}

            weapon: dict[str, str | dict[str, str]]
            for weapon in raw_data["loadout"]:
                weapon_data: dict[str, str | None] = {
                    "name": weapon["title"],
                    "subtype": weapon.get("weaponSubtype", None),
                    "image": weapon["weaponImage"]["url"],
                }

                match weapon["weaponType"]:
                    case "primary":
                        primary.append(weapon_data)
                    case "secondary":
                        secondary.append(weapon_data)
                    case "gadget":
                        gadgets.append(weapon_data)
                    case "unique-ability":
                        unique = weapon_data
                    case _:
                        raise ValueError(
                            f"Unknown weapon type ({weapon['weaponType']}) of {weapon['title']} for {raw_name}"
                        )

            result.append(
                {
                    "info": {
                        "name": raw_name,
                        "pretty_name": op["name"],
                        "side": "attacker" if raw_data["header"]["isAttacker"] else "defender",
                        "banner": op["banner"],
                        "icon": op["icon"],
                        "url": op["url"],
                        "unique_description": raw_data["header"]["ability"]["content"],
                        "real_name": (raw_data["header"]["realName"]),
                        "date_of_birth": (raw_data["header"]["dateOfBirth"]),
                        "place_of_birth": (raw_data["header"]["placeOfBirth"]),
                        "biography": (
                            raw_data["biography"]["biography"] if raw_data["biography"] else None
                        ),
                        "squad": raw_data["header"].get("squad", None),
                        "stats": {
                            "armor": raw_data["header"]["armor"],
                            "speed": raw_data["header"]["speed"],
                            "difficulty": raw_data["header"]["difficulty"],
                        },
                        "roles": raw_data["header"]["roles"],
                    },
                    "loadout": {
                        "primary": primary,
                        "secondary": secondary,
                        "gadgets": gadgets,
                        "unique": unique,
                    },
                }
            )

    print(f"- {len(result)} operators processed.")
    print(f"Writing to {OUT_PATH}...")

    with OUT_PATH.open("wb") as f:
        f.write(orjson.dumps(result))

    print("- Done!")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
