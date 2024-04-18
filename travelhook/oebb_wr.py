"grab öbb live station data and try to get plausible train classes from it"
import datetime
import re
import traceback

from aiohttp import ClientSession

from . import database as DB

match_data = {
    # 1016 could also be 1116
    # 1016 could also be 2016 „Hercules“, a diesel loco with the same length
    "1016 xxx": [
        {"lengthOverBuffers": 19.28, "capacityFirstClass": 0, "capacitySecondClass": 0}
    ],
    "1144 xxx": [
        {"lengthOverBuffers": 16.1, "capacityFirstClass": 0, "capacitySecondClass": 0}
    ],
    "1216 xxx": [
        {"lengthOverBuffers": 19.58, "capacityFirstClass": 0, "capacitySecondClass": 0}
    ],
    "4020 xxx": [
        {"lengthOverBuffers": 23.3, "capacitySecondClass": 56},
        {"lengthOverBuffers": 22.8, "capacitySecondClass": 64},
        {"lengthOverBuffers": 23.3, "capacitySecondClass": 64},
    ],
    # Talent 1 with three coaches
    "4023 xxx Talent": [{"lengthOverBuffers": 52.12, "capacitySecondClass": 151}],
    # Talent 1 with four coaches
    # 4024 could also be 4124, they're only distinguished by multi system capability apparently
    "4024 xxx Talent": [{"lengthOverBuffers": 66.87, "capacitySecondClass": 199}],
    # Desiro ML with three coaches and four doors (regional version)
    "4744 xxx Desiro ML": [
        {"lengthOverBuffers": 24.53, "capacitySecondClass": 71},
        {"lengthOverBuffers": 26.1, "capacitySecondClass": 100},
        {"lengthOverBuffers": 24.53, "capacitySecondClass": 83},
    ],
    # Desiro ML with three coaches and six doors (S-Bahn version)
    "4746 xxx Desiro ML": [
        {"lengthOverBuffers": 24.53, "capacitySecondClass": 60},
        {"lengthOverBuffers": 26.1, "capacitySecondClass": 92},
        {"lengthOverBuffers": 24.53, "capacitySecondClass": 72},
    ],
    # Desiro ML with four coaches and eight doors
    "4748 xxx Desiro ML": [
        {"lengthOverBuffers": 24.53, "capacitySecondClass": 68},
        {"lengthOverBuffers": 26.1, "capacitySecondClass": 92},
        {"lengthOverBuffers": 26.1, "capacitySecondClass": 92},
        {"lengthOverBuffers": 24.53, "capacitySecondClass": 38},
    ],
    # Desiro Classic
    "5022 xxx Desiro Classic": [
        {"lengthOverBuffers": 41.7, "capacitySecondClass": 117}
    ],
    "5047 xxx": [{"lengthOverBuffers": 25.4, "capacitySecondClass": 68}],
    # ÖBB railjet 1, trainsets 01-51
    "7x ÖBB Railjet 1": [
        # family coach
        {"lengthOverBuffers": 26.5, "features": 33},
        # regular coach
        {"lengthOverBuffers": 26.5, "capacitySecondClass": 80},
        # quiet coach
        # "features": 128 applies only when the quiet zone is actually active
        # outside of austria, it isn't sometimes, so we don't check for it
        {"lengthOverBuffers": 26.5, "capacitySecondClass": 80},
        # regular coach
        {"lengthOverBuffers": 26.5, "capacitySecondClass": 80},
        # restaurant+prm coach
        {
            "lengthOverBuffers": 26.5,
            "capacitySecondClass": 0,
            "capacityFirstClass": 10,
            "features": 74,
        },
        # first class coach
        {"lengthOverBuffers": 26.5, "capacitySecondClass": 0, "capacityFirstClass": 55},
        # driving + business coach
        {
            "lengthOverBuffers": 26.9,
            "capacitySecondClass": 0,
            "capacityFirstClass": 11,
            "capacityBusinessClass": 16,
        },
    ],
    # ÖBB railjet 1, trainsets 52-60. very similar to ČD trainsets, but with an infopoint in the restaurant.
    "7x ÖBB Railjet 1": [
        # family coach
        {"lengthOverBuffers": 26.5, "features": 33},
        # regular coach
        {"lengthOverBuffers": 26.5, "capacitySecondClass": 80},
        # quiet coach
        # "features": 128 applies only when the quiet zone is actually active
        # outside of austria, it isn't sometimes, so we don't check for it
        {"lengthOverBuffers": 26.5, "capacitySecondClass": 80},
        # regular coaches
        {"lengthOverBuffers": 26.5, "capacitySecondClass": 80},
        {"lengthOverBuffers": 26.5, "capacitySecondClass": 80},
        # restaurant+prm coach
        {
            "lengthOverBuffers": 26.5,
            "capacitySecondClass": 0,
            "capacityFirstClass": 10,
            "features": 74,
        },
        # driving + business coach
        {
            "lengthOverBuffers": 26.9,
            "capacitySecondClass": 0,
            "capacityFirstClass": 32,
            "capacityBusinessClass": 6,
        },
    ],
    # ČD operated railjets have more second class capacity
    "7x ČD Railjet 1": [
        # family coach
        {"lengthOverBuffers": 26.5, "features": 33},
        # regular coaches
        {"lengthOverBuffers": 26.5, "capacitySecondClass": 80},
        {"lengthOverBuffers": 26.5, "capacitySecondClass": 80},
        {"lengthOverBuffers": 26.5, "capacitySecondClass": 80},
        {"lengthOverBuffers": 26.5, "capacitySecondClass": 80},
        # restaurant+prm coach
        {
            "lengthOverBuffers": 26.5,
            "capacitySecondClass": 0,
            "capacityFirstClass": 10,
            "features": 66,
        },
        # driving + business coach
        {
            "lengthOverBuffers": 26.9,
            "capacitySecondClass": 0,
            "capacityFirstClass": 32,
            "capacityBusinessClass": 6,
        },
    ],
    "411 xxx ICE-T": [
        # first class driving coach
        {"lengthOverBuffers": 27.9, "capacityFirstClass": 43},
        # first+second class coach
        {
            "lengthOverBuffers": 25.9,
            "capacityFirstClass": 12,
            "capacitySecondClass": 47,
        },
        # restaurant coach
        {"lengthOverBuffers": 25.9, "capacitySecondClass": 30, "features": 64},
        # second class coaches
        {"lengthOverBuffers": 25.9, "capacitySecondClass": 64},
        {"lengthOverBuffers": 25.9, "capacitySecondClass": 62},
        {"lengthOverBuffers": 25.9, "capacitySecondClass": 62},
        # second class driving coach
        {"lengthOverBuffers": 27.9, "capacitySecondClass": 63},
    ],
    "510 xxx SŽ FLIRT": [
        {
            "lengthOverBuffers": 23.38,
            "capacityFirstClass": 12,
            "capacitySecondClass": 44,
        },
        {"lengthOverBuffers": 16.97, "capacitySecondClass": 55},
        {"lengthOverBuffers": 16.97, "capacitySecondClass": 64},
        {"lengthOverBuffers": 23.38, "capacitySecondClass": 60},
    ],
    # CityShuttle coaches
    "CityShuttle Bmpz-s": [
        {
            "lengthOverBuffers": 26.4,
            "capacitySecondClass": 44,
        }
    ],
    "CityShuttle Bmpz-l": [
        {
            "lengthOverBuffers": 26.4,
            "capacitySecondClass": 80,
            "capacityBicycle": 1,
            "capacityWheelChair": 0,
        }
    ],
    "CityShuttle-Dosto Bmpz-dl": [
        {
            "lengthOverBuffers": 26.8,
            "capacitySecondClass": 110,
        }
    ],
    "Wieseldosto Bmpz-dl": [
        {
            "lengthOverBuffers": 26.8,
            "capacitySecondClass": 114,
        }
    ],
    "Wieseldosto Bbfmpz": [
        {
            "lengthOverBuffers": 27.13,
            "capacitySecondClass": 86,
            "capacityBicycle": 1,
            "capacityWheelChair": 0,
        }
    ],
    # IC coaches
    "ÖBB IC Bmpz": [
        {"lengthOverBuffers": 26.4, "capacitySecondClass": 78, "capacityBicycle": 1}
    ],
    "ÖBB IC Bmz": [{"lengthOverBuffers": 26.4, "capacitySecondClass": 66}],
    # likely, according to vagonweb - verify in person
    "ÖBB IC/NJ Bbmvz": [
        {"lengthOverBuffers": 26.4, "capacitySecondClass": 38, "features": 3}
    ],
    "Wagen": [{}],
}


def match_wagon(match, wagon):
    return all(wagon.get(k) == v for k, v in match.items())


def match_wagons_slice(match_wagons, wagon_slice):
    if not len(match_wagons) == len(wagon_slice):
        return False
    return all(
        match_wagon(match, wagon_slice[i]) for i, match in enumerate(match_wagons)
    ) or all(
        match_wagon(match, wagon_slice[i])
        for i, match in enumerate(reversed(match_wagons))
    )


discard_platform_suffix = re.compile(r"\(Bahnsteige? [\d-]+\)")


def get_station_no(name: str):
    # name = discard_platform_suffix.sub("", name).strip()
    name = name.removesuffix(" Bahnhof")
    name = name.removesuffix(" Bahnhst")
    if row := DB.DB.execute(
        "SELECT eva_nr FROM oebb_stations WHERE name = ?",
        (name,),
    ).fetchone():
        return row["eva_nr"]
    return None


async def get_composition(train_no: int, station_no: int, departure: datetime.datetime):
    async with ClientSession() as session:
        url = f"https://live.oebb.at/backend/info?trainNr={train_no}&station={station_no}&date={departure:%Y-%m-%d}&time={departure:%H%%3A%M}"
        async with session.get(url) as r:
            try:
                data = await r.json()
                if not r.status == 200 or not "train" in data:
                    print(
                        f"ÖBB Live {train_no} from {station_no} at {departure:%d-%m-%Y %H:%M} returned no data: {r.status} {data}\n{url}"
                    )
                    return None
                wagons = data["train"]["wagons"]
                composition = []
                while wagons:
                    for class_name, match_slice in match_data.items():
                        wagons_slice = wagons[: len(match_slice)]
                        if match_wagons_slice(match_slice, wagons_slice):
                            composition.append(
                                {"class_name": class_name, "wagons": wagons_slice}
                            )
                            wagons = wagons[len(match_slice) :]
                            break

                return composition

            except:  # pylint: disable=bare-except
                print(
                    f"ÖBB Live {train_no} from {station_no} at {departure:%d-%m-%Y %H:%M} failed:\n{url}"
                )
                traceback.print_exc()
                return None
